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

import huggingface_hub
# MONKEY PATCH: Fix for use_auth_token compatibility
_original_hub_download = huggingface_hub.hf_hub_download
def _patched_hub_download(*args, **kwargs):
    if 'use_auth_token' in kwargs:
        kwargs['token'] = kwargs.pop('use_auth_token')
    return _original_hub_download(*args, **kwargs)
huggingface_hub.hf_hub_download = _patched_hub_download

# MONKEY PATCH 2: FORCE PYANNOTE COMPATIBILITY WITH TORCH 2.1+
# Pyannote using old 'torchaudio.backend' which was removed in 2.1
import torchaudio
if not hasattr(torchaudio, "backend"):
    # Create a dummy backend module so pyannote doesn't crash on import
    import types
    torchaudio.backend = types.ModuleType("backend")
    torchaudio.backend.common = types.ModuleType("common")
    # Mock AudioMetaData
    class AudioMetaData:
        def __init__(self, sample_rate, num_frames, num_channels, bits_per_sample, encoding):
            self.sample_rate = sample_rate
            self.num_frames = num_frames
            self.num_channels = num_channels
            self.bits_per_sample = bits_per_sample
            self.encoding = encoding
    torchaudio.backend.common.AudioMetaData = AudioMetaData

try:
    import pyannote.audio.core.io
    pyannote.audio.core.io.AudioDecoder = None
except ImportError:
    pass

# Suppress pyannote/speechbrain warnings
warnings.filterwarnings("ignore")
# Specific noise from speechbrain about torchaudio backend
warnings.filterwarnings("ignore", message="This version of torchaudio is old")
warnings.filterwarnings("ignore", module="speechbrain")

def setup_device(force_cpu=False):
    if force_cpu:
        return "cpu"
    if torch.cuda.is_available():
        gpu_name = torch.cuda.get_device_name(0)
        print(f"✅ GPU detectada: {gpu_name}")
        torch.backends.cudnn.benchmark = True
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


def diarize_audio(audio_path, hf_token, device="cuda", pipeline=None, debug=False):
    """
    Performs speaker diarization using pyannote.audio
    """
    if not hf_token:
        print("⚠️ No HF Token provided. Skipping diarization.")
        return None

    if debug:
        print(f"🐛 DEBUG START: Diarization on {device}")
        stop_monitor = threading.Event()
        t = threading.Thread(target=log_resources, args=(2, stop_monitor))
        t.daemon = True
        t.start()

    print("👥 Iniciando diarización (identificación de hablantes)...")
    try:
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

        if pipeline is None:
            from pyannote.audio import Pipeline
            # Load pipeline
            pipeline = Pipeline.from_pretrained(
                "pyannote/speaker-diarization-3.1",
                use_auth_token=hf_token
            )
            
            if device == "cuda":
                pipeline.to(torch.device("cuda"))
            else:
                pipeline.to(torch.device("cpu"))
        else:
            # If pipeline provided, assuming it's already on correct device
            pass

        # Run inference
        print(f"▶ Ejecutando pipeline en {device}...")
        diarization = pipeline(audio_path)
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

def assign_speakers(whisper_segments, diarization):
    """
    Combines Whisper segments with Pyannote diarization.
    Assigns the speaker active for the majority of the segment's duration.
    """
    if not diarization:
        return whisper_segments

    full_segments = []
    
    # Pre-calculate speaker turns for faster lookup
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
    # 1. Save Human-Readable TXT
    with open(output_path, "w", encoding="utf-8") as f:
        for seg in segments:
            start = time.strftime('%H:%M:%S', time.gmtime(seg['start']))
            end = time.strftime('%H:%M:%S', time.gmtime(seg['end']))
            text = seg['text'].strip()
            
            if 'speaker' in seg:
                f.write(f"[{start} --> {end}] {seg['speaker']}: {text}\n")
            else:
                f.write(f"[{start} --> {end}]  {text}\n")
    
    # 2. Save Machine-Readable JSON (for Editor)
    json_path = output_path.with_suffix(".json")
    try:
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(segments, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"⚠️ Error guardando JSON: {e}")

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
            diarization_result = diarize_audio(str(audio_path), hf_token, device="cuda")

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

    audio_extensions = {".m4a", ".mp3", ".opus", ".wav", ".flac", ".ogg"}
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
