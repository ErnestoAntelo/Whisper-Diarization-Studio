"""Run modern diarization without changing the transcription environment."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import time
import psutil
from gpu_control import GpuController, write_control


class ProcessingCancelled(RuntimeError):
    pass


def gpu_reading():
    result = subprocess.run(
        ["nvidia-smi", "-i", "0", "--query-gpu=temperature.gpu,power.draw,memory.used", "--format=csv,noheader,nounits"],
        check=True, capture_output=True, text=True, timeout=3,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    temperature, power, memory = [float(value.strip()) for value in result.stdout.strip().split(",")]
    return {"temperature_c": temperature, "power_w": power, "memory_mb": memory}


def run_community(audio_path, token, num_speakers=None, cancel_event=None, max_seconds=None, timeout=7200, device="cpu", gpu_profile="efficient", status_callback=None):
    if device not in ("cpu", "cuda"):
        raise ValueError("Dispositivo de diarización no válido")
    if gpu_profile not in ("compatible", "efficient"):
        raise ValueError("Perfil GPU no válido")
    base = Path(__file__).resolve().parent.parent
    env_name = ".venv-diarization-gpu" if device == "cuda" else ".venv-diarization"
    python = base / env_name / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not python.exists():
        raise RuntimeError(f"Falta {env_name}. Ejecuta instalar_diarizacion.bat {'gpu' if device == 'cuda' else 'cpu'}.")
    env = os.environ.copy()
    env.update(PYTHONUTF8="1", CUDA_VISIBLE_DEVICES="0" if device == "cuda" else "", PYANNOTE_METRICS_ENABLED="0", HF_HUB_DISABLE_TELEMETRY="1")
    gpu_peak = {}
    with tempfile.TemporaryDirectory(prefix="whisper-community-") as folder:
        result_path = Path(folder) / "result.json"
        control_path = Path(folder) / "gpu-control.json"
        controller = GpuController()
        # Start paused; the supervisor supplies a reading before any GPU inference.
        write_control(control_path, controller.update(None))
        with subprocess.Popen([str(python), "-u", str(base / "src/community_worker.py")],
                              stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              text=True, encoding="utf-8", env=env,
                              creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0) as process:
            process.stdin.write(json.dumps({"audio": str(Path(audio_path).resolve()), "token": token,
                                           "num_speakers": num_speakers, "max_seconds": max_seconds, "device": device,
                                           "gpu_profile": gpu_profile,
                                           "control_path": str(control_path),
                                           "result_path": str(result_path)}))
            process.stdin.close()
            recent = []
            def read_output():
                for line in process.stdout:
                    line = line.replace(token, "[token]") if token else line
                    recent.append(line.rstrip())
                    del recent[:-15]
                    print(line.rstrip(), flush=True)
            reader = threading.Thread(target=read_output, daemon=True)
            reader.start()
            started = time.monotonic()
            max_rss = 0
            last_gpu_check = 0
            cooling_started = None
            cooling_seconds = 0.0
            cooling_pauses = 0
            last_pause = None
            try:
                while process.poll() is None:
                    if cancel_event is not None and cancel_event.is_set():
                        raise ProcessingCancelled("Diarización cancelada; el texto guardado se conserva.")
                    if time.monotonic() - started > timeout:
                        raise TimeoutError("La diarización superó el tiempo máximo.")
                    if device == "cuda" and time.monotonic() - last_gpu_check >= 2:
                        try:
                            reading = gpu_reading()
                        except (OSError, ValueError, subprocess.SubprocessError):
                            reading = None
                        state = controller.update(reading)
                        write_control(control_path, state)
                        if reading is not None:
                            gpu_peak = {key: max(gpu_peak.get(key, value), value) for key, value in reading.items()}
                        if state["paused"] != last_pause:
                            if state["paused"]:
                                cooling_started = time.monotonic()
                                cooling_pauses += 1
                                reason = (f"GPU {reading['temperature_c']:.0f} °C / {reading['power_w']:.1f} W"
                                          if reading else "esperando telemetría GPU")
                                message = f"Pausa de diarización: {reason}. El progreso se conserva; se reanudará automáticamente."
                                print(message, flush=True)
                                if status_callback:
                                    status_callback(message)
                            elif last_pause:
                                cooling_seconds += time.monotonic() - cooling_started
                                print("GPU enfriada: reanudando desde el mismo lote.", flush=True)
                                if status_callback:
                                    status_callback("GPU enfriada: reanudando la diarización desde el mismo lote.")
                            last_pause = state["paused"]
                        last_gpu_check = time.monotonic()
                    try:
                        root = psutil.Process(process.pid)
                        rss = sum(p.memory_info().rss for p in [root, *root.children(recursive=True)])
                        max_rss = max(max_rss, rss)
                        if rss > 4 * 1024**3:
                            raise MemoryError("Diarización detenida al superar 4 GB de RAM.")
                    except psutil.NoSuchProcess:
                        pass
                    time.sleep(0.25)
                reader.join(timeout=5)
                if process.returncode or not result_path.exists():
                    raise RuntimeError("Community-1 no terminó correctamente:\n" + "\n".join(recent))
                report = json.loads(result_path.read_text(encoding="utf-8"))
                report["peak_worker_rss_mb"] = round(max_rss / 1024**2, 1)
                report["gpu_sampled_peaks"] = gpu_peak or None
                report["worker_wall_seconds"] = round(time.monotonic() - started, 2)
                report["cooling_pauses"] = cooling_pauses
                report["cooling_seconds"] = round(cooling_seconds + (time.monotonic() - cooling_started if last_pause else 0), 2)
                return report
            finally:
                if process.poll() is None:
                    parent = psutil.Process(process.pid)
                    for child in parent.children(recursive=True):
                        try:
                            child.terminate()
                        except psutil.NoSuchProcess:
                            pass
                    process.kill()
                    process.wait(timeout=10)
                reader.join(timeout=5)
