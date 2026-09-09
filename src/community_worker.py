"""Isolated Community-1 worker. Credentials arrive over stdin, never argv."""
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import warnings

MODEL = "pyannote/speaker-diarization-community-1"
GPU_PROFILES = {
    "compatible": {"cudnn": False, "segmentation_batch": 4, "embedding_batch": 2,
                   "segmentation_pause": 0.05, "embedding_pause": 0.15},
    "efficient": {"cudnn": True, "segmentation_batch": 8, "embedding_batch": 8,
                  "segmentation_pause": 0.03, "embedding_pause": 0.03},
}
_job_handle = None
_mutex_handle = None


def apply_windows_cpu_limit(percent=6):
    """Hard cap this job's CPU time, measured across all logical processors."""
    global _job_handle, _mutex_handle
    if os.name != "nt":
        return False
    class CpuRate(ctypes.Structure):
        _fields_ = [("ControlFlags", wintypes.DWORD), ("CpuRate", wintypes.DWORD)]
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    kernel.CreateMutexW.restype = wintypes.HANDLE
    mutex = kernel.CreateMutexW(None, True, "Local\\WhisperStudio.Community1")
    if not mutex:
        raise ctypes.WinError(ctypes.get_last_error())
    if ctypes.get_last_error() == 183:
        raise RuntimeError("Ya hay otra diarización Community-1 en marcha. Espera a que termine o cancélala.")
    _mutex_handle = mutex
    kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel.CreateJobObjectW.restype = wintypes.HANDLE
    kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    kernel.SetInformationJobObject.restype = wintypes.BOOL
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel.AssignProcessToJobObject.restype = wintypes.BOOL
    handle = kernel.CreateJobObjectW(None, None)
    info = CpuRate(0x1 | 0x4, int(percent * 100))  # ENABLE | HARD_CAP
    if not handle or not kernel.SetInformationJobObject(handle, 15, ctypes.byref(info), ctypes.sizeof(info)):
        raise ctypes.WinError(ctypes.get_last_error())
    if not kernel.AssignProcessToJobObject(handle, kernel.GetCurrentProcess()):
        raise ctypes.WinError(ctypes.get_last_error())
    _job_handle = handle  # Keep the limit alive for the entire process.
    return True


def main():
    request = json.load(sys.stdin)
    device = request.get("device", "cpu")
    if device not in ("cpu", "cuda"):
        raise ValueError("Dispositivo de diarización no válido")
    profile_name = request.get("gpu_profile", "efficient")
    profile = GPU_PROFILES[profile_name]
    limited = apply_windows_cpu_limit()
    for key in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        os.environ[key] = "2"
    os.environ["CUDA_VISIBLE_DEVICES"] = "0" if device == "cuda" else ""
    os.environ["PYANNOTE_METRICS_ENABLED"] = "0"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    import psutil
    proc = psutil.Process()
    if os.name == "nt":
        proc.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
    import numpy as np
    import torch
    if device == "cpu" and torch.version.cuda is not None:
        raise RuntimeError("El entorno de diarización debe usar Torch CPU, sin CUDA.")
    if device == "cuda":
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA no está disponible en el entorno Community-1 GPU.")
        # Enable the optimized backend independently of algorithm benchmarking.
        torch.backends.cudnn.enabled = profile["cudnn"]
        torch.backends.cudnn.benchmark = False
        torch.cuda.set_per_process_memory_fraction(0.45)
        torch.cuda.reset_peak_memory_stats()
    torch.set_num_threads(2)
    torch.set_num_interop_threads(1)
    # We supply decoded waveforms explicitly, as supported by pyannote. The
    # optional TorchCodec DLL decoder is unnecessary for this Windows path.
    warnings.filterwarnings("ignore", message=r"\s*torchcodec is not installed correctly.*", category=UserWarning)
    from pyannote.audio import Pipeline
    from threadpoolctl import threadpool_limits
    print(f"Community-1 · {device} · 2 hilos · límite CPU Windows 6%: {limited}", flush=True)
    started = time.monotonic()
    command = ["ffmpeg", "-nostdin", "-v", "error", "-threads", "1", "-i", request["audio"]]
    if request.get("max_seconds"):
        command += ["-t", str(request["max_seconds"])]
    command += ["-vn", "-ac", "1", "-ar", "16000", "-f", "f32le", "pipe:1"]
    decoded = subprocess.run(command, check=True, capture_output=True, timeout=180,
                             creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    waveform = torch.from_numpy(np.frombuffer(decoded.stdout, dtype=np.float32).copy()).unsqueeze(0)
    if waveform.shape[1] == 0:
        raise ValueError("El audio está vacío.")
    decoded_at = time.monotonic()
    print(f"Audio cargado: {waveform.shape[1] / 16000:.1f} segundos", flush=True)
    pipeline = Pipeline.from_pretrained(MODEL, token=request["token"])
    if device == "cuda":
        from gpu_control import wait_for_gpu
        wait_for_gpu(request["control_path"])
    pipeline.to(torch.device(device))
    pipeline.segmentation_batch_size = profile["segmentation_batch"] if device == "cuda" else 4
    pipeline.embedding_batch_size = profile["embedding_batch"] if device == "cuda" else 4
    loaded_at = time.monotonic()
    last = [0.0]
    pause_seconds = [0.0]
    def progress(step, artifact, **kwargs):
        if device == "cuda":
            # Finish the current batch before yielding; all pipeline state stays
            # in this process while the supervisor waits for cooling.
            torch.cuda.synchronize()
            wait_for_gpu(request["control_path"])
        pause = profile["embedding_pause"] if step == "embeddings" else profile["segmentation_pause"]
        if device == "cuda" and pause:
            torch.cuda.synchronize()
            before_pause = time.monotonic()
            time.sleep(pause)
            pause_seconds[0] += time.monotonic() - before_pause
        now = time.monotonic()
        if now - last[0] >= 10:
            print(f"Diarización: {step} {kwargs.get('completed', '')}/{kwargs.get('total', '')}", flush=True)
            last[0] = now
    options = {"num_speakers": request["num_speakers"]} if request.get("num_speakers") else {}
    with threadpool_limits(limits=2), torch.inference_mode():
        result = pipeline({"waveform": waveform, "sample_rate": 16000}, hook=progress, **options)
    finished_at = time.monotonic()
    annotation = result.exclusive_speaker_diarization
    turns = [{"start": float(turn.start), "end": float(turn.end), "speaker": speaker}
             for turn, _, speaker in annotation.itertracks(yield_label=True)]
    report = {"model": MODEL, "device": device, "torch": torch.__version__, "threads": 2,
              "gpu_profile": profile_name if device == "cuda" else None,
              "decode_seconds": round(decoded_at - started, 2),
              "model_load_seconds": round(loaded_at - decoded_at, 2),
              "inference_seconds": round(finished_at - loaded_at, 2),
              "progress_pause_seconds": round(pause_seconds[0], 2),
              "segmentation_batch_size": pipeline.segmentation_batch_size,
              "embedding_batch_size": pipeline.embedding_batch_size,
              "cudnn_enabled": torch.backends.cudnn.enabled if device == "cuda" else None,
              "peak_cuda_allocated_mb": round(torch.cuda.max_memory_allocated() / 1024**2, 1) if device == "cuda" else 0,
              "cpu_hard_cap_percent": 6 if limited else None,
              "duration_seconds": waveform.shape[1] / 16000,
              "elapsed_seconds": round(time.monotonic() - started, 2), "turns": turns}
    Path(request["result_path"]).write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
    print(f"Completado: {len(turns)} turnos, {len(set(t['speaker'] for t in turns))} hablantes", flush=True)


if __name__ == "__main__":
    main()
