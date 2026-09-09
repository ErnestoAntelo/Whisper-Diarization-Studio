import csv
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from transcript_export import render_export, timestamp, atomic_write
from media_files import MEDIA_EXTENSIONS, media_filetypes

class ExportTests(unittest.TestCase):
    def setUp(self):
        self.segments = [{"start": 59.9996, "end": 63.5, "text": 'Hola, "Ana" <sí>', "speaker": "A"},
                         {"start": 63.5, "end": 66, "text": "Segunda frase.", "speaker": "A"}]
        self.blocks = [{"start": 59.9996, "end": 66, "speaker": "A", "text": "Un párrafo."}]

    def test_subtitles_keep_phrase_timing_in_grouped_view(self):
        text = render_export(self.segments, "srt", blocks=self.blocks)
        self.assertIn("1\n00:01:00,000 --> 00:01:03,500", text)
        self.assertIn("2\n00:01:03,500 --> 00:01:06,000", text)
        self.assertIn("&lt;sí&gt;", text)
        vtt = render_export(self.segments, "vtt", speakers=False)
        self.assertTrue(vtt.startswith("WEBVTT\n\n"))
        self.assertNotIn("A: ", vtt)
        self.assertEqual(timestamp(90061.123), "25:01:01,123")

    def test_plain_text_options_and_json_roundtrip(self):
        self.assertEqual(render_export(self.segments, "txt", self.blocks, False, False), "Un párrafo.\n")
        self.assertEqual(json.loads(render_export(self.segments, "json", self.blocks)), self.segments)
        rows = list(csv.reader(io.StringIO(render_export(self.segments, "csv"))))
        self.assertEqual(rows[1][3], self.segments[0]["text"])

    def test_failed_export_preserves_previous_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "old.txt"
            path.write_text("original", encoding="utf-8")
            with patch("transcript_export.os.replace", side_effect=PermissionError("locked")):
                with self.assertRaises(PermissionError):
                    atomic_write(path, "new")
            self.assertEqual(path.read_text(encoding="utf-8"), "original")
            self.assertEqual(list(Path(folder).glob("*.tmp")), [])

    def test_video_and_unlisted_ffmpeg_formats_remain_selectable(self):
        self.assertTrue({".mp4", ".mkv", ".webm", ".mov", ".mp3", ".aac", ".flac"} <= MEDIA_EXTENSIONS)
        self.assertEqual(media_filetypes()[-1][1], "*.*")
