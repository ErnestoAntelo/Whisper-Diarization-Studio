import argparse
import os
import warnings
import json
import gc
from pathlib import Path
import torch
import whisper
from tqdm import tqdm
from dotenv import load_dotenv
import time
import sys

# Legacy Windows consoles may not support the emojis used in progress logs.
for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(errors="backslashreplace")

# Modern diarization runs in its own environment; no global library patches.
# Suppress pyannote/speechbrain warnings
warnings.filterwarnings("ignore")
# Specific noise from speechbrain about torchaudio backend
warnings.filterwarnings("ignore", message="This version of torchaudio is old")
warnings.filterwarnings("ignore", message=".*set_audio_backend has been deprecated.*")
warnings.filterwarnings("ignore", module="speechbrain")

def setup_device(force_cpu=False):
    if force_cpu:
        return "cpu"
    if torch.cuda.is_available():
        gpu_name = torch.cuda.get_device_name(0)
        print(f"✅ GPU detectada: {gpu_name}")
        torch.backends.cudnn.benchmark = False
        return "cuda"
    else:
        print("⚠️ GPU no detectada. Usando CPU.")
        return "cpu"

# --- RESOURCE MONITOR ---
import threading
import psutil

def log_resources(interval=2, stop_event=None):
    """Logs RAM and VRAM usage periodically."""
    while not stop_event.is_set():
        # RAM
        ram = psutil.virtual_memory()
        ram_usage = f"RAM: {ram.percent}% ({ram.used / (1024**3):.1f}GB / {ram.total / (1024**3):.1f}GB)"
        
        # VRAM (if CUDA)
        vram_usage = ""
        gpu_stats = ""
        if torch.cuda.is_available():
            mem = torch.cuda.memory_allocated() / (1024**3)
            res = torch.cuda.memory_reserved() / (1024**3)
            vram_usage = f" | VRAM: Alloc {mem:.1f}GB / Res {res:.1f}GB"
            
            # Try getting Temp/Power via nvidia-smi
            try:
                import subprocess
                # Query: temperature.gpu, power.draw
                result = subprocess.run(
                    ['nvidia-smi', '--query-gpu=temperature.gpu,power.draw', '--format=csv,noheader,nounits'],
                    capture_output=True, text=True
                )
                if result.returncode == 0:
                    temp, power = result.stdout.strip().split(',')
                    gpu_stats = f" | GPU Temp: {temp}°C | Pwr: {power}W"
            except:
                pass
            
        print(f"[MONITOR] {ram_usage}{vram_usage}{gpu_stats}")
        time.sleep(interval)


def diarize_audio(audio_path, hf_token, device="cpu", pipeline=None, debug=False, num_speakers=None, cancel_event=None, report_path=None, gpu_profile="efficient", status_callback=None):
    """
    Performs speaker diarization using pyannote.audio
    """
    if not hf_token:
        print("⚠️ No HF Token provided. Skipping diarization.")
        return None

    if device not in ("cpu", "cuda") or (pipeline is not None and device != "cpu"):
        raise ValueError("La GPU solo se admite mediante el worker Community-1 aislado.")
    if pipeline is None:
        from community_runner import run_community
        report = run_community(audio_path, hf_token, num_speakers=num_speakers, cancel_event=cancel_event, device=device, gpu_profile=gpu_profile, status_callback=status_callback)
        if report_path:
            Path(report_path).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        return report["turns"]

    temp_wav = None
    previous_threads = torch.get_num_threads()
    if debug:
        print(f"🐛 DEBUG START: Diarization on {device}")
        stop_monitor = threading.Event()
        t = threading.Thread(target=log_resources, args=(2, stop_monitor))
        t.daemon = True
        t.start()

    print("👥 Iniciando diarización (identificación de hablantes)...")
    try:
        if device == "cpu":
            torch.set_num_threads(min(4, previous_threads))
        # CONVERSION: Ensure audio is WAV (Pyannote/Torchaudio on Windows is picky with m4a/mp3)
        temp_wav = None
        input_path = Path(audio_path)
        if input_path.suffix.lower() != ".wav":
            print(f"🔄 Convirtiendo {input_path.name} a WAV para diarización...")
            # Use tempfile to avoid polluting input dir
            import tempfile
            fd, temp_wav_path = tempfile.mkstemp(suffix=".wav")
            os.close(fd)
            temp_wav = Path(temp_wav_path)
            
            # ffmpeg -y -i input -ac 1 -ar 16000 output.wav (Standardize to 16kHz Mono for best results)
            import subprocess
            startupinfo = None
            if os.name == 'nt':
                 startupinfo = subprocess.STARTUPINFO()
                 startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                 
            subprocess.run(["ffmpeg", "-y", "-i", str(input_path), "-ac", "1", "-ar", "16000", str(temp_wav)], 
                           check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, startupinfo=startupinfo)
            audio_path = str(temp_wav)

        pipeline.to(torch.device("cpu"))

        # Run inference
        print(f"▶ Ejecutando pipeline en {device}...")
        options = {"num_speakers": num_speakers} if num_speakers else {}
        from threadpoolctl import threadpool_limits
        with threadpool_limits(limits=4 if device == "cpu" else None):
            diarization = pipeline(audio_path, **options)
        print("✅ Pipeline finalizado.")
        
        if debug:
            stop_monitor.set()
        
        # Cleanup Pipeline Immediately
        del pipeline
        torch.cuda.empty_cache()
        gc.collect()
        
        # Cleanup Temp Audio
        if temp_wav and temp_wav.exists():
            try:
                os.remove(temp_wav)
            except Exception as e:
                print(f"⚠️ No se pudo borrar temp wav: {e}")
        
        return diarization

    except Exception as e:
        print(f"❌ Error en diarización: {e}")
        print("💡 Asegúrate de haber aceptado las condiciones en hf.co/pyannote/speaker-diarization-3.1")
        return None

    finally:
        if device == "cpu":
            torch.set_num_threads(previous_threads)
        if debug:
            stop_monitor.set()
        if temp_wav and temp_wav.exists():
            try:
                temp_wav.unlink()
            except OSError:
                pass

def assign_speakers(whisper_segments, diarization):
    """
    Combines Whisper segments with Pyannote diarization.
    Assigns the speaker active for the majority of the segment's duration.
    """
    if not diarization:
        return whisper_segments

    full_segments = []
    
    # Pre-calculate speaker turns for faster lookup
    if isinstance(diarization, list):
        from types import SimpleNamespace
        turns = [(SimpleNamespace(start=t["start"], end=t["end"]), None, t["speaker"]) for t in diarization]
    else:
        turns = list(diarization.itertracks(yield_label=True))
    
    for seg in whisper_segments:
        start = seg['start']
        end = seg['end']
        text = seg['text']
        
        # Find intersecting speaker turns
        speakers = {}
        for turn, _, speaker in turns:
            # Calculate intersection
            t_start = max(start, turn.start)
            t_end = min(end, turn.end)
            duration = max(0, t_end - t_start)
            
            if duration > 0:
                speakers[speaker] = speakers.get(speaker, 0) + duration

        # Assign dominant speaker
        if speakers:
            best_speaker = max(speakers, key=speakers.get)
        else:
            best_speaker = "Unknown"
            
        full_segments.append({
            "start": start,
            "end": end,
            "speaker": best_speaker,
            "text": text
        })
        
    return full_segments

def format_output(segments):
    output = ""
    for seg in segments:
        time_str = f"{int(seg['start']//60):02d}:{int(seg['start']%60):02d}"
        if "speaker" in seg:
            output += f"[{seg['speaker']}] {time_str}: {seg['text'].strip()}\n"
        else:
            output += f"{time_str}: {seg['text'].strip()}\n"
    return output

def save_transcript(segments, output_path):
    """
    Saves segments to file with proper formatting AND saves a .json copy for the Editor.
    """
    from transcript_export import atomic_write, render_export
    output_path = Path(output_path)
    # Preserve the editable checkpoint first; exports can always be regenerated.
    atomic_write(output_path.with_suffix(".json"), render_export(segments, "json"))
    atomic_write(output_path, render_export(segments, "txt"))
    print(f"✅ Guardado en: {output_path.name} (y .json)")


def transcribe_file(model, audio_path, output_path, language="es", fp16=True, verbose=True, hf_token=None, reuse=False):
    try:
        print(f"🎙️ Procesando: {audio_path.name}...")
        
        segments = None
        
        # 0. Check Reuse
        if reuse:
            json_path = output_path.with_suffix(".json")
            if json_path.exists():
                print(f"♻️ Reutilizando transcripción existente: {json_path.name}")
                try:
                    with open(json_path, "r", encoding="utf-8") as f:
                        segments = json.load(f)
                    print("✅ Transcripción cargada correctamente.")
                except Exception as e:
                    print(f"⚠️ Error cargando JSON existente: {e}. Se volverá a transcribir.")
            else:
                print("⚠️ No se encontró archivo JSON para reutilizar. Se iniciará transcripción.")
        
        # 1. Transcribe (if not reused)
        if segments is None:
            # Anti-Hallucination: condition_on_previous_text=False prevents "y y y y" loops
            result = model.transcribe(
                str(audio_path), 
                language=language, 
                fp16=fp16, 
                verbose=verbose,
                condition_on_previous_text=False
            )
            segments = result["segments"]
            
            # 2. Intermediate Save (Safety Checkpoint)
            # Verify structure before saving (Whisper segment dict vs list)
            print("💾 Guardando punto de control (Transcription Only)...")
            save_transcript(segments, output_path)

        # 3. Diarize if token provided
        if hf_token:
            # STABILITY: Swap Whisper to CPU to free VRAM for Pyannote
            # This allows "Fast GPU Diarization" without crashing 6GB VRAM cards.
            original_device = model.device
            if original_device.type == "cuda":
                print("🔄 Liberando VRAM (Moviendo Whisper a CPU temporariamente)...")
                model.to("cpu")
                torch.cuda.empty_cache()
                
            # Perform diarization (Now safe to use GPU for Pyannote)
            diarization_result = diarize_audio(str(audio_path), hf_token, device="cpu")

            # Restore Whisper
            if original_device.type == "cuda":
                print("🔄 Restaurando VRAM (Moviendo Whisper a GPU)...")
                model.to(original_device) # Restore to original device
                torch.cuda.empty_cache()
            
            final_segments = assign_speakers(segments, diarization_result)
        else:
            final_segments = segments

        # 4. Final Save (Overwrite with speakers if applicable)
        if hf_token:
            save_transcript(final_segments, output_path)
        
        # Cleanup
        if 'result' in locals():
            del result
        if hf_token and 'diarization_result' in locals():
            del diarization_result
            
        torch.cuda.empty_cache()
        gc.collect()
        
        return final_segments
    except Exception as e:
        print(f"❌ Error procesando {audio_path.name}: {e}")
        torch.cuda.empty_cache()
        gc.collect()
        return None

def main():
    parser = argparse.ArgumentParser(description="Transcriptor AI Optimizado")
    parser.add_argument("--model", type=str, default="large-v3", help="Modelo Whisper")
    parser.add_argument("--force-cpu", action="store_true", help="Forzar CPU")
    parser.add_argument("--hf-token", type=str, help="Token HuggingFace para diarización")
    args = parser.parse_args()

    # Rutas
    base_dir = Path(__file__).parent.parent
    input_dir = base_dir / "input"
    output_dir = base_dir / "output"
    
    input_dir.mkdir(exist_ok=True)
    output_dir.mkdir(exist_ok=True)

    device = setup_device(args.force_cpu)
    fp16 = (device == "cuda")

    print(f"⏳ Cargando modelo '{args.model}' en {device}...")
    try:
        model = whisper.load_model(args.model, device=device)
    except Exception as e:
        print(f"❌ Error cargando modelo: {e}")
        return

    from media_files import MEDIA_EXTENSIONS
    audio_extensions = MEDIA_EXTENSIONS
    audio_files = [f for f in input_dir.iterdir() if f.suffix.lower() in audio_extensions]

    if not audio_files:
        print("📭 No hay audios en 'input'.")
        return

    print(f"📂 Encontrados {len(audio_files)} archivos.")

    processed = 0
    for audio_file in tqdm(audio_files, desc="Procesando"):
        # Create subfolder
        file_subdir = output_dir / audio_file.stem
        file_subdir.mkdir(exist_ok=True)
        
        output_file = file_subdir / (audio_file.stem + ".txt")
        if output_file.exists():
            continue
            
        if transcribe_file(model, audio_file, output_file, fp16=fp16, hf_token=args.hf_token):
            processed += 1

    print(f"✅ Completado. Procesados: {processed}")

if __name__ == "__main__":
    main()
