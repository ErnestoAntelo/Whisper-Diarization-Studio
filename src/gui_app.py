import customtkinter as ctk
import threading
import sys
import os
import json
from pathlib import Path
import time
import torch
from tkinter import filedialog

# Import shared logic or fallback
try:
    from main import setup_device, transcribe_file
    import whisper
except ImportError:
    sys.path.append(str(Path(__file__).parent))
    from main import setup_device, transcribe_file
    import whisper
    import torch

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

class RedirectText:
    def __init__(self, text_widget, original_stream, log_file="debug_log.txt", event_queue=None):
        self.event_queue = event_queue
        self.text_widget = text_widget
        self.original_stream = original_stream
        
        # Use absolute path for log file to ensure we find it
        base_dir = Path(__file__).parent.parent
        self.log_file = base_dir / log_file
        
        # Clear log on start
        try:
            with open(self.log_file, "w", encoding="utf-8") as f:
                f.write(f"--- SESSION START {time.ctime()} ---\n")
        except Exception as e:
            print(f"Log Error: {e}")

    def write(self, string):
        if self.event_queue is not None:
            self.event_queue.put((self.append_gui, {"string": string}))

        # Write to Terminal
        if self.original_stream:
            self.original_stream.write(string)
            self.original_stream.flush()

        # Write to File (Aggressive Flush for Crash Debugging)
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(string)
                f.flush()
                # os.fsync(f.fileno()) # Extreme safety (slows down bit, but safe)
        except:
            pass

    def append_gui(self, string):
        self.text_widget.configure(state="normal")
        self.text_widget.insert("end", string)
        if int(self.text_widget.index("end-1c").split(".")[0]) > 2000:
            self.text_widget.delete("1.0", "500.0")
        self.text_widget.see("end")
        self.text_widget.configure(state="disabled")

    def flush(self):
        if self.original_stream:
            self.original_stream.flush()

class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        from ui_layout import build_main_ui
        self.cancel_event = threading.Event()
        build_main_ui(self, RedirectText)

    def drain_ui_events(self):
        import queue
        for _ in range(150):
            try:
                callback, kwargs = self.ui_events.get_nowait()
            except queue.Empty:
                break
            callback(**kwargs)
        self.after(60, self.drain_ui_events)

    def post_status(self, **kwargs):
        self.ui_events.put((self.label_status.configure, kwargs))

    def post_reset(self):
        self.ui_events.put((self.reset_ui, {}))

    def clear_audio_files(self):
        for widget in self.scrollable_file_list.winfo_children():
            widget.destroy()
        self.file_checkboxes = []
        ctk.CTkLabel(self.scrollable_file_list, text="Todavía no has añadido audios.",
                     font=ctk.CTkFont(size=17), text_color="#B5C4D0").pack(pady=(24, 6))
        ctk.CTkLabel(self.scrollable_file_list, text="Pulsa Añadir audio arriba. Si ya tienes el texto, pulsa Abrir editor.",
                     text_color="#9DAFBE").pack(pady=(0, 20))
        self.lbl_file_count.configure(text="Audios")
        if hasattr(self, "btn_start"):
            self.update_start_button()

    def load_config(self):
        config_path = Path(__file__).parent.parent / "config.json"
        if config_path.exists():
            try:
                with open(config_path, "r") as f:
                    data = json.load(f)
                    if "model" in data:
                        self.option_model.set(data["model"])
                    if data.get("gpu_profile") in ("GPU rápida", "GPU compatible"):
                        self.option_gpu_profile.set(data["gpu_profile"])
                    if "language" in data:
                        self.option_language.set(data["language"])
                    if "hf_token" in data:
                        self.entry_token.delete(0, "end")
                        self.entry_token.insert(0, data["hf_token"])
                    if data.get("last_audio_dir") and Path(data["last_audio_dir"]).is_dir():
                        self.input_dir = Path(data["last_audio_dir"])
                    if data.get("output_dir"):
                        self.output_dir = Path(data["output_dir"])
                        self.entry_output.delete(0, "end")
                        self.entry_output.insert(0, str(self.output_dir))
            except Exception as e:
                print(f"Error cargando config: {e}")

    def save_config(self):
        config_path = Path(__file__).parent.parent / "config.json"
        data = {
            "model": self.option_model.get(),
            "gpu_profile": self.option_gpu_profile.get(),
            "language": self.option_language.get(),
            "hf_token": self.entry_token.get().strip(),
            "last_audio_dir": str(self.input_dir),
            "output_dir": self.entry_output.get()
        }
        try:
            with open(config_path, "w") as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            print(f"Error guardando config: {e}")

    def browse_input(self):
        d = filedialog.askdirectory(initialdir=self.input_dir)
        if d:
            self.input_dir = Path(d)
            self.entry_input.delete(0, "end")
            self.entry_input.insert(0, d)
            extensions = {".mp3", ".m4a", ".wav", ".ogg", ".flac", ".opus"}
            self.add_paths(sorted(p for p in Path(d).iterdir() if p.is_file() and p.suffix.lower() in extensions))

    def browse_output(self):
        d = filedialog.askdirectory(initialdir=self.output_dir)
        if d:
            self.output_dir = Path(d)
            self.entry_output.delete(0, "end")
            self.entry_output.insert(0, d)
            self.render_audio_files({path for path, chk in self.file_checkboxes if chk.get() == 1})

    def apply_gpu_profile(self):
        self.option_model.set("medium")
        self.check_cpu.deselect()
        self.check_safe_mode.deselect()
        self.check_debug.deselect()
        self.option_gpu_profile.set("GPU rápida")
        self.label_status.configure(text="Perfil portátil: Whisper medium + Community-1 en GPU con lotes pequeños y vigilancia.", text_color="cyan")

    def add_audio_files(self):
        paths = filedialog.askopenfilenames(
            title="Selecciona uno o varios audios", initialdir=self.input_dir,
            filetypes=[("Audio", "*.mp3 *.m4a *.wav *.ogg *.flac *.opus")])
        self.add_paths(paths)

    def transcript_for(self, audio):
        root = Path(self.entry_output.get())
        return next((p for p in [root / audio.stem / (audio.stem + ".json"),
                                root / (audio.stem + ".json")] if p.is_file()), None)

    def update_start_button(self):
        if hasattr(self, "worker_thread") and self.worker_thread.is_alive():
            return
        count = sum(chk.get() == 1 for _, chk in self.file_checkboxes)
        self.btn_start.configure(state="normal" if count else "disabled",
                                 text=f"Transcribir {count} audios" if count > 1 else "Transcribir audio")

    def render_audio_files(self, selected_paths):
        paths = [path for path, _ in self.file_checkboxes]
        for widget in self.scrollable_file_list.winfo_children():
            widget.destroy()
        self.file_checkboxes = []
        busy = hasattr(self, "worker_thread") and self.worker_thread.is_alive()
        for path in paths:
            row = ctk.CTkFrame(self.scrollable_file_list, fg_color="transparent")
            row.pack(fill="x", padx=4, pady=6)
            row.grid_columnconfigure(0, weight=1)
            chk = ctk.CTkCheckBox(row, text=path.name, command=self.update_start_button)
            chk.grid(row=0, column=0, sticky="w", padx=6)
            if path in selected_paths:
                chk.select()
            self.file_checkboxes.append((path, chk))
            available = self.transcript_for(path) is not None
            ctk.CTkLabel(row, text="Texto guardado" if available else "Pendiente de transcribir",
                         text_color="#9DAFBE").grid(row=1, column=0, sticky="w", padx=36)
            if available:
                ctk.CTkButton(row, text="Abrir editor", width=125, state="disabled" if busy else "normal",
                              command=lambda audio=path: self.open_editor_dialog(str(audio))).grid(row=0, column=1, rowspan=2, padx=6)
        self.lbl_file_count.configure(text=f"Audios · {len(paths)}")
        self.update_start_button()

    def add_paths(self, paths):
        if not paths:
            return
        selected = {path for path, chk in self.file_checkboxes if chk.get() == 1}
        existing = {path for path, _ in self.file_checkboxes}
        for name in paths:
            path = Path(name).resolve()
            self.input_dir = path.parent
            selected.add(path)
            if path not in existing:
                self.file_checkboxes.append((path, None))
                existing.add(path)
        self.render_audio_files(selected)

    def open_output_folder(self):
        path = Path(self.entry_output.get())
        path.mkdir(parents=True, exist_ok=True)
        os.startfile(str(path.resolve()))

    def select_all(self):
        if hasattr(self, 'file_checkboxes'):
            for _, chk in self.file_checkboxes:
                chk.select()

    def select_none(self):
        if hasattr(self, 'file_checkboxes'):
            for _, chk in self.file_checkboxes:
                chk.deselect()

    def refresh_file_list(self):
        path = Path(self.entry_input.get())
        self.clear_audio_files()
        if path.is_dir():
            extensions = {".m4a", ".mp3", ".opus", ".wav", ".flac", ".ogg"}
            self.add_paths(sorted(f for f in path.iterdir() if f.is_file() and f.suffix.lower() in extensions))

    def start_thread(self):
        value = self.entry_speakers.get().strip()
        if value and (not value.isdigit() or int(value) < 1):
            self.label_status.configure(text="Indica un número positivo de hablantes o deja el campo vacío.", text_color="orange")
            return
        selected = [p for p, chk in self.file_checkboxes if chk.get() == 1]
        if not selected:
            self.label_status.configure(text="Añade y selecciona al menos un audio.", text_color="orange")
            return
        stems = [p.stem.casefold() for p in selected]
        if len(stems) != len(set(stems)):
            self.label_status.configure(text="Hay audios con el mismo nombre base: renómbralos para evitar sobrescribir resultados.", text_color="orange")
            return
        self.cancel_event.clear()
        self.btn_cancel.configure(state="normal")
        self.btn_cancel.grid(row=0, column=1, padx=(12, 0))
        self.btn_start.configure(state="disabled", text="Procesando...")
        self.btn_open_editor.configure(state="disabled")
        settings = self.collect_settings()
        self.save_config()
        t = threading.Thread(target=self.run_process, args=(settings,))
        self.worker_thread = t
        t.start()

    def cancel_process(self):
        self.cancel_event.set()
        self.label_status.configure(text="Cancelando; si Whisper está activo, terminará el archivo actual.", text_color="orange")

    def on_close(self):
        self.cancel_event.set()
        if hasattr(self, "worker_thread") and self.worker_thread.is_alive():
            self.label_status.configure(text="Cerrando tras cancelar. Si Whisper está activo, termina el archivo actual.", text_color="orange")
            self.after(250, self.on_close)
            return
        sys.stdout, sys.stderr = sys.__stdout__, sys.__stderr__
        self.destroy()

    def open_editor_dialog(self, audio_file=None):
        if hasattr(self, "worker_thread") and self.worker_thread.is_alive():
            self.label_status.configure(text="Espera a que termine el proceso para editar el resultado.", text_color="orange")
            return
        if audio_file is None:
            from transcript_library import open_library
            open_library(self)
            return
        audio_path = Path(audio_file)
        if audio_path.suffix.lower() == ".json":
            self.open_saved_transcript(audio_path)
            return

        # Look for JSON in output dir
        out_root = Path(self.entry_output.get())
        
        # Check Subfolder (New Standard)
        json_path_subdir = out_root / audio_path.stem / (audio_path.stem + ".json")
        # Check Root (Legacy)
        json_path_flat = out_root / (audio_path.stem + ".json")
        
        if json_path_subdir.exists():
            json_path = json_path_subdir
        elif json_path_flat.exists():
            json_path = json_path_flat
        else:
            self.label_status.configure(text=f"❌ No se encontró transcripción (.json) para {audio_path.name}", text_color="red")
            print(f"Buscado en:\n1. {json_path_subdir}\n2. {json_path_flat}")
            return
            
        self.launch_editor(audio_path, json_path)

    def open_saved_transcript(self, json_path):
        if hasattr(self, "worker_thread") and self.worker_thread.is_alive():
            self.label_status.configure(text="Espera a que termine el proceso para editar el resultado.", text_color="orange")
            return
        self.launch_editor(self.find_transcript_audio(json_path), json_path)

    def find_transcript_audio(self, json_path):
        extensions = (".mp3", ".m4a", ".wav", ".ogg", ".flac", ".opus")
        for path, _ in self.file_checkboxes:
            if path.stem == json_path.stem and path.is_file():
                return path
        for folder in (json_path.parent, self.input_dir, Path.home() / "Downloads"):
            for extension in extensions:
                candidate = folder / (json_path.stem + extension)
                if candidate.is_file():
                    return candidate
        return None

    def launch_editor(self, audio_path, json_path):
        try:
            from editor import EditorWindow
            EditorWindow(self, audio_path, json_path)
            self.label_status.configure(text=f"Editor abierto para {json_path.stem}", text_color="green")
        except Exception as e:
            print(f"Error abriendo editor: {e}")
            self.label_status.configure(text="Error abriendo editor", text_color="red")

    def collect_settings(self):
        return {
            "model": self.option_model.get() or "medium",
            "language": self.option_language.get(),
            "force_cpu": self.check_cpu.get() == 1,
            "safe_mode": self.check_safe_mode.get() == 1,
            "debug": self.check_debug.get() == 1,
            "gpu_profile": "compatible" if self.option_gpu_profile.get() == "GPU compatible" else "efficient",
            "reuse": self.check_reuse.get() == 1,
            "speakers": int(self.entry_speakers.get()) if self.entry_speakers.get().strip() else None,
            "token": self.entry_token.get().strip() or None,
            "files": [p for p, chk in self.file_checkboxes if chk.get() == 1],
            "output": Path(self.entry_output.get()),
        }

    def run_process(self, settings=None):
        try:
            from community_runner import ProcessingCancelled
            settings = self.collect_settings() if settings is None else settings
            model_name = settings["model"]
            language_code = {"Spanish": "es", "English": "en", "Portuguese": "pt", "French": "fr", "Italian": "it", "German": "de", "Japanese": "ja"}.get(settings["language"], "es")
            safe_mode, debug_mode = settings["safe_mode"], settings["debug"]
            reuse_transcription, num_speakers = settings["reuse"], settings["speakers"]
            device = setup_device(settings["force_cpu"])
            fp16 = device == "cuda"
            hf_token, selected_files = settings["token"], settings["files"]
            out = settings["output"]
            out.mkdir(parents=True, exist_ok=True)

            # --- PHASE 1: TRANSCRIPTION (Batch) ---
            print(f"\n🚀 FASE 1: TRANSCRIPCIÓN (Whisper) - {len(selected_files)} archivos")
            self.post_status(text="Preparando archivos...", text_color="yellow")
            
            model = None
            failures = 0
            completed = 0
            skipped = 0

            transcription_results = [] # Stores (file_path, output_path, segments)
            
            for i, f in enumerate(selected_files):
                if self.cancel_event.is_set():
                    from community_runner import ProcessingCancelled
                    raise ProcessingCancelled("Proceso cancelado; los archivos guardados se conservan.")
                self.post_status(text=f"Transcribiendo {i+1}/{len(selected_files)}: {f.name}...", text_color="cyan")
                
                # New Organization: Create subfolder for file
                file_subdir = out / f.stem
                file_subdir.mkdir(exist_ok=True)
                
                outfile = file_subdir / (f.stem + ".txt")
                
                # Check exist
                if outfile.exists() and not reuse_transcription:
                    print(f"⏩ {f.name} ya existe. (Si deseas reprocesar, bórralo antes).")
                    skipped += 1
                    continue
                elif outfile.exists() and reuse_transcription:
                    print(f"♻️ {f.name} ya existe. Intentando REUTILIZAR...")
                
                # Transcribe (hf_token=None force skip internal diarization)
                # verbose=True logs directly to captured stdout
                segments = None
                if reuse_transcription and outfile.with_suffix(".json").exists():
                    try:
                        with open(outfile.with_suffix(".json"), encoding="utf-8") as stream:
                            segments = json.load(stream)
                        if not isinstance(segments, list) or any(
                            not isinstance(s, dict) or not {"start", "end", "text"} <= s.keys() for s in segments
                        ):
                            raise ValueError("JSON de transcripción no válido")
                        print(f"♻️ Transcripción recuperada: {f.name}")
                    except (OSError, ValueError) as exc:
                        print(f"❌ No se puede recuperar {f.name}: {exc}")
                        failures += 1
                        continue
                if segments is None:
                    if model is None:
                        model = whisper.load_model(model_name, device=device)
                    segments = transcribe_file(model, f, outfile, language=language_code, fp16=fp16, verbose=True)
                
                if segments is not None:
                    transcription_results.append({
                        "file": f,
                        "outfile": outfile,
                        "segments": segments
                    })
                    if not hf_token:
                        completed += 1
                else:
                    failures += 1

                # SAFETY THROTTLE: Sleep to let GPU cool down
                time.sleep(3)
                import gc
                gc.collect()

            # UNLOAD WHISPER COMPLETELY
            print("🧹 Liberando Whisper de GPU...")
            del model
            torch.cuda.empty_cache()
            import gc
            gc.collect()

            # --- PHASE 2: DIARIZATION (Batch) ---
            if hf_token and transcription_results:
                print(f"\n🚀 FASE 2: DIARIZACIÓN (Pyannote) - {len(transcription_results)} archivos")
                self.post_status(text="Cargando Pyannote...", text_color="magenta")
                
                from main import diarize_audio, assign_speakers, save_transcript
                from community_runner import ProcessingCancelled

                try:
                    dia_device = "cpu" if safe_mode or device == "cpu" else "cuda"
                    
                    for i, item in enumerate(transcription_results):
                        f = item["file"]
                        segs = item["segments"]
                        outfile = item["outfile"]
                        
                        self.post_status(text=f"Diarizando {i+1}/{len(transcription_results)}: {f.name}...", text_color="magenta")
                        
                        diarization = diarize_audio(
                            str(f), hf_token, device=dia_device, num_speakers=num_speakers,
                            cancel_event=self.cancel_event, report_path=outfile.with_suffix(".diarization.json"),
                            gpu_profile=settings["gpu_profile"],
                            status_callback=lambda message: self.post_status(text=message, text_color="orange" if message.startswith("Pausa") else "cyan"))
                        
                        if diarization:
                            final_segments = assign_speakers(segs, diarization)
                            # Overwrite file with speakers
                            save_transcript(final_segments, outfile)
                            completed += 1
                        else:
                            failures += 1
                        
                        # SAFETY THROTTLE
                        time.sleep(3)
                        gc.collect()
                        
                except ProcessingCancelled:
                    raise
                except Exception as e:
                    failures = len(selected_files) - skipped - completed
                    print(f"❌ Error en Diarización Batch: {e}")
                    import traceback
                    traceback.print_exc()
                
                # Unload Pipeline
                torch.cuda.empty_cache()
                gc.collect()
            
            print(f"✨ ¡Proceso Batch Finalizado!")
            self.post_status(
                text=f"Finalizado: {completed} completados, {failures} con errores, {skipped} omitidos.",
                text_color="orange" if failures else "green")

        except ProcessingCancelled as e:
            self.post_status(text=str(e), text_color="orange")
        except Exception as e:
            print(f"❌ Error inesperado: {e}")
            self.post_status(text="Error inesperado", text_color="red")
        finally:
            self.post_reset()

    def reset_ui(self):
        if hasattr(self, "worker_thread") and self.worker_thread.is_alive():
            self.after(100, self.reset_ui)
            return
        self.btn_cancel.configure(state="disabled")
        self.btn_cancel.grid_remove()
        self.btn_open_editor.configure(state="normal")
        self.render_audio_files({path for path, chk in self.file_checkboxes if chk.get() == 1})
        self.update_start_button()
        # Don't convert status back to "Ready" immediately so user can see result
        # self.label_status.configure(text="Listo para empezar", text_color="gray")

if __name__ == "__main__":
    try:
        app = App()
        app.mainloop()
    except Exception as e:
        print(f"CRASH: {e}")
        input("Presiona Enter para salir...")
