"""Regression checks that do not download models or process private audio."""
import json
import sys
import tempfile
import unittest
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import main
from gui_app import App
from editor import EditorWindow


class OptimizationsTest(unittest.TestCase):
    def test_grouping_preserves_phrases_and_respects_pauses_and_unknown(self):
        from copy import deepcopy
        segments = [
            {"start": 0, "end": 1, "text": "Uno.", "speaker": "A"},
            {"start": 1, "end": 2, "text": "Dos.", "speaker": "A"},
            {"start": 6, "end": 7, "text": "Tres.", "speaker": "A"},
            {"start": 7, "end": 8, "text": "Otro.", "speaker": "B"},
            {"start": 8, "end": 9, "text": "Sin asignar.", "speaker": "UNKNOWN"},
            {"start": 9, "end": 10, "text": "También.", "speaker": "UNKNOWN"},
        ]
        original = deepcopy(segments)
        app = SimpleNamespace(segments=segments, grouped_view=True, expanded_segments=set())
        blocks = EditorWindow.display_blocks(app)
        self.assertEqual([b["indices"] for b in blocks], [[0, 1], [2], [3], [4], [5]])
        self.assertEqual(blocks[0]["text"], "Uno. Dos.")
        self.assertEqual(segments, original)
        app.expanded_segments.update([0, 1])
        self.assertEqual(len(EditorWindow.display_blocks(app)), 6)
        app.expanded_segments.clear()
        app.grouped_view = False
        self.assertEqual(len(EditorWindow.display_blocks(app)), 6)

    def test_grouped_speaker_edit_keeps_original_text_and_times(self):
        segments = [{"start": 0, "end": 1, "text": "Uno", "speaker": "A"},
                    {"start": 1, "end": 2, "text": "Dos", "speaker": "A"}]
        speaker = Mock()
        speaker.get.return_value = "Ana"
        text = Mock()
        app = SimpleNamespace(segments=segments, row_widgets=[
            {"real_index": 0, "indices": [0, 1], "speaker": speaker, "text": text}])
        EditorWindow.sync_page_to_memory(app)
        self.assertEqual([s["speaker"] for s in segments], ["Ana", "Ana"])
        self.assertEqual([s["text"] for s in segments], ["Uno", "Dos"])
        self.assertEqual([(s["start"], s["end"]) for s in segments], [(0, 1), (1, 2)])
        text.get.assert_not_called()

    def test_legacy_gpu_diarization_is_rejected(self):
        with self.assertRaises(ValueError):
            main.diarize_audio("sample.wav", "test", device="cuda", pipeline=Mock())

    def test_gpu_diarization_uses_isolated_worker(self):
        with patch("community_runner.run_community", return_value={"turns": []}) as run:
            main.diarize_audio("sample.wav", "test", device="cuda")
            self.assertEqual(run.call_args.kwargs["device"], "cuda")
            self.assertEqual(run.call_args.kwargs["gpu_profile"], "efficient")

    def test_compatibility_profile_can_be_selected(self):
        with patch("community_runner.run_community", return_value={"turns": []}) as run:
            main.diarize_audio("sample.wav", "test", device="cuda", gpu_profile="compatible")
            self.assertEqual(run.call_args.kwargs["gpu_profile"], "compatible")

    def test_reported_temperature_pauses_then_resumes_with_hysteresis(self):
        from gpu_control import GpuController
        controller = GpuController()
        self.assertTrue(controller.update({"temperature_c": 78, "power_w": 73.9})["paused"])
        self.assertTrue(controller.update({"temperature_c": 77, "power_w": 60})["paused"])
        self.assertFalse(controller.update({"temperature_c": 74, "power_w": 60})["paused"])
        self.assertTrue(controller.update({"temperature_c": 60, "power_w": 80})["paused"])
        self.assertTrue(controller.update(None)["paused"])
        self.assertFalse(controller.update({"temperature_c": 60, "power_w": 50})["paused"])

    def test_worker_keeps_position_while_cooling(self):
        from gpu_control import wait_for_gpu, write_control
        import time
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "control.json"
            write_control(path, {"paused": True, "updated_at": time.time()})
            completed = threading.Event()
            worker = threading.Thread(target=lambda: (wait_for_gpu(path), completed.set()))
            worker.start()
            try:
                self.assertFalse(completed.wait(0.2))
            finally:
                write_control(path, {"paused": False, "updated_at": time.time()})
                worker.join(timeout=2)
            self.assertTrue(completed.is_set())

    def test_stale_reading_does_not_resume_work(self):
        from gpu_control import wait_for_gpu, write_control
        import time
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "control.json"
            write_control(path, {"paused": False, "updated_at": time.time() - 30})
            completed = threading.Event()
            worker = threading.Thread(target=lambda: (wait_for_gpu(path), completed.set()))
            worker.start()
            try:
                self.assertFalse(completed.wait(0.2))
            finally:
                write_control(path, {"paused": False, "updated_at": time.time()})
                worker.join(timeout=2)
            self.assertTrue(completed.is_set())

    def test_community_turns_assign_speakers(self):
        segments = [{"start": 0, "end": 4, "text": "test"}]
        turns = [{"start": 0, "end": 1, "speaker": "A"}, {"start": 1, "end": 4, "speaker": "B"}]
        self.assertEqual(main.assign_speakers(segments, turns)[0]["speaker"], "B")

    def test_default_diarization_uses_isolated_community_worker(self):
        with patch("community_runner.run_community", return_value={"turns": []}) as run:
            self.assertEqual(main.diarize_audio("sample.wav", "test", num_speakers=2), [])
            self.assertEqual(run.call_args.kwargs["num_speakers"], 2)

    def test_cpu_thread_limit_is_applied_and_restored(self):
        previous = main.torch.get_num_threads()
        observed = []
        pipeline = Mock(side_effect=lambda *a, **k: observed.append(main.torch.get_num_threads()) or "result")
        self.assertEqual(main.diarize_audio("sample.wav", "test", pipeline=pipeline), "result")
        self.assertLessEqual(observed[0], 4)
        self.assertEqual(main.torch.get_num_threads(), previous)

    def test_editor_write_failure_preserves_previous_json(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "project.json"
            original = '[{"start": 0, "end": 1, "text": "original"}]'
            path.write_text(original, encoding="utf-8")
            app = SimpleNamespace(json_path=str(path), segments=[{"text": "changed"}],
                                  sync_page_to_memory=Mock(), lbl_status=Mock())
            with patch("editor.json.dump", side_effect=OSError("disk full")):
                EditorWindow.save_changes(app)
            self.assertEqual(path.read_text(encoding="utf-8"), original)
            self.assertEqual(list(Path(folder).glob("*.tmp")), [])

    def test_safe_mode_moves_existing_pipeline_and_passes_speakers(self):
        pipeline = Mock(return_value="result")
        result = main.diarize_audio("sample.wav", "test", device="cpu",
                                   pipeline=pipeline, num_speakers=2)
        self.assertEqual(result, "result")
        self.assertEqual(pipeline.to.call_args.args[0].type, "cpu")
        pipeline.assert_called_once_with("sample.wav", num_speakers=2)

    def test_failed_conversion_cleans_temporary_audio(self):
        with tempfile.TemporaryDirectory() as folder:
            wav = Path(folder) / "temporary.wav"
            import os
            fd = os.open(str(wav), os.O_CREAT | os.O_RDWR)
            with patch("tempfile.mkstemp", return_value=(fd, str(wav))), \
                 patch("subprocess.run", side_effect=RuntimeError("conversion failed")):
                self.assertIsNone(main.diarize_audio("sample.mp3", "test", device="cpu", pipeline=Mock()))
            self.assertFalse(wav.exists())

    def run_recovery(self, folder, token=""):
        root = Path(folder)
        target = root / "sample"
        target.mkdir()
        (target / "sample.json").write_text(json.dumps([
            {"start": 0, "end": 1, "text": "Test"}
        ]), encoding="utf-8")
        control = lambda value: Mock(get=Mock(return_value=value))
        app = SimpleNamespace(
            option_model=control("turbo"), option_language=control("Spanish"),
            option_gpu_profile=control("GPU rápida"),
            check_cpu=control(1), check_safe_mode=control(1), check_debug=control(0),
            check_reuse=control(1), entry_speakers=control("2"),
            entry_token=control(token), entry_output=control(str(root)),
            file_checkboxes=[(root / "sample.wav", control(1))],
            label_status=Mock(), reset_ui=Mock(), save_config=Mock(), cancel_event=threading.Event())
        app.collect_settings = lambda: App.collect_settings(app)
        app.post_status = app.label_status.configure
        app.post_reset = app.reset_ui
        with patch("gui_app.whisper.load_model") as load, patch("gui_app.time.sleep"):
            App.run_process(app)
            load.assert_not_called()
        return app

    def test_recovery_does_not_load_whisper(self):
        with tempfile.TemporaryDirectory() as folder:
            app = self.run_recovery(folder)
            self.assertIn("1 completados, 0 con errores", app.label_status.configure.call_args.kwargs["text"])

    def test_pipeline_load_error_is_not_success(self):
        with tempfile.TemporaryDirectory() as folder, \
             patch("community_runner.run_community", side_effect=RuntimeError("model unavailable")):
            app = self.run_recovery(folder, token="test")
            self.assertIn("0 completados, 1 con errores", app.label_status.configure.call_args.kwargs["text"])


if __name__ == "__main__":
    unittest.main()
