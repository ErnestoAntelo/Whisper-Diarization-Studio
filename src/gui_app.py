import customtkinter as ctk
import threading
import sys
import os
import json
from pathlib import Path
import time
import torch

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
    def __init__(self, text_widget, original_stream, log_file="debug_log.txt"):
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
        # Write to GUI
        try:
            self.text_widget.configure(state="normal")
            self.text_widget.insert("end", string)
            self.text_widget.see("end")
            self.text_widget.configure(state="disabled")
            self.text_widget.update_idletasks()
        except:
            pass 
            
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

    def flush(self):
        if self.original_stream:
            self.original_stream.flush()

class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Transcriptor AI - GPU Optimized")
        self.geometry("900x700")

        # Config paths
        base_dir = Path(__file__).parent.parent
        self.input_dir = base_dir / "input"
        self.output_dir = base_dir / "output"

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(6, weight=1) # Log area expands (now at row 6)

        # --- Header ---
        self.header_frame = ctk.CTkFrame(self)
        self.header_frame.grid(row=0, column=0, padx=20, pady=20, sticky="ew")
        
        self.label_title = ctk.CTkLabel(self.header_frame, text="Whisper Transcriptor", font=ctk.CTkFont(size=24, weight="bold"))
        self.label_title.pack(pady=10)

        # --- Directories ---
        self.frame_dirs = ctk.CTkFrame(self)
        self.frame_dirs.grid(row=1, column=0, padx=20, pady=(0, 20), sticky="ew")
        self.frame_dirs.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(self.frame_dirs, text="Entrada (Audio):").grid(row=0, column=0, padx=10, pady=10)
        self.entry_input = ctk.CTkEntry(self.frame_dirs)
        self.entry_input.grid(row=0, column=1, padx=10, pady=10, sticky="ew")
        self.entry_input.insert(0, str(self.input_dir))
        ctk.CTkButton(self.frame_dirs, text="...", width=30, command=self.browse_input).grid(row=0, column=2, padx=10)

        ctk.CTkLabel(self.frame_dirs, text="Salida (Texto):").grid(row=1, column=0, padx=10, pady=10)
        self.entry_output = ctk.CTkEntry(self.frame_dirs)
        self.entry_output.grid(row=1, column=1, padx=10, pady=10, sticky="ew")
        self.entry_output.insert(0, str(self.output_dir))
        ctk.CTkButton(self.frame_dirs, text="...", width=30, command=self.browse_output).grid(row=1, column=2, padx=10)

        # --- File Preview List ---
        self.frame_files = ctk.CTkFrame(self)
        self.frame_files.grid(row=2, column=0, padx=20, pady=(0, 20), sticky="ew")
        self.frame_files.grid_columnconfigure(0, weight=1)
        
        ctk.CTkLabel(self.frame_files, text="Archivos detectados:").pack(anchor="w", padx=10, pady=(10,0))
        
        # Add Select All / None buttons
        btn_frame = ctk.CTkFrame(self.frame_files, fg_color="transparent")
        btn_frame.pack(anchor="w", padx=10, pady=(0, 5))
        
        ctk.CTkButton(btn_frame, text="Todas", width=60, height=20, command=self.select_all).pack(side="left", padx=(0, 5))
        ctk.CTkButton(btn_frame, text="Ninguna", width=60, height=20, command=self.select_none).pack(side="left")

        self.scrollable_file_list = ctk.CTkScrollableFrame(self.frame_files, height=100, label_text="Archivos")
        self.scrollable_file_list.pack(fill="x", padx=10, pady=5)
        
        # --- Settings ---
        self.frame_settings = ctk.CTkFrame(self)
        self.frame_settings.grid(row=3, column=0, padx=20, pady=(0, 20), sticky="ew")

        # Model Selector
        ctk.CTkLabel(self.frame_settings, text="Modelo:").pack(side="left", padx=10, pady=10)
        self.option_model = ctk.CTkOptionMenu(self.frame_settings, values=["large-v3", "medium", "small", "base", "tiny", "turbo"])
        self.option_model.pack(side="left", padx=5)

        # Language Selector
        ctk.CTkLabel(self.frame_settings, text="Idioma:").pack(side="left", padx=10, pady=10)
        self.option_language = ctk.CTkOptionMenu(self.frame_settings, values=["Spanish", "English", "Portuguese", "French", "Italian", "German", "Japanese"])
        self.option_language.pack(side="left", padx=5)

        # Advanced Options
        self.check_cpu = ctk.CTkCheckBox(self.frame_settings, text="Forzar CPU (Whisper)")
        self.check_cpu.pack(side="left", padx=15)

        self.check_safe_mode = ctk.CTkCheckBox(self.frame_settings, text="Modo Seguro (CPU Diarización)")
        self.check_safe_mode.pack(side="left", padx=15)
        # self.check_safe_mode.select() # Disabled by request (run full speed)
        
        self.check_reuse = ctk.CTkCheckBox(self.frame_settings, text="♻️ Reutilizar Transcripción (Saltar Whisper)")
        self.check_reuse.pack(side="left", padx=15)
        
        self.check_debug = ctk.CTkCheckBox(self.frame_settings, text="Debug Info")
        self.check_debug.pack(side="left", padx=15)
        self.check_debug.select() # Default ON for now

        # HF Token
        self.label_token = ctk.CTkLabel(self.frame_settings, text="HF Token (Diarización):")
        self.label_token.pack(side="left", padx=10)
        self.entry_token = ctk.CTkEntry(self.frame_settings, width=150, show="*")
        self.entry_token.pack(side="left", padx=5)

        self.load_config()

        # Hide token field if already configured
        if self.entry_token.get().strip():
            self.label_token.pack_forget()
            self.entry_token.pack_forget()
            ctk.CTkLabel(self.frame_settings, text="✅ Diarización Activada", text_color="green").pack(side="left", padx=10)

        # --- Actions ---
        self.label_status = ctk.CTkLabel(self, text="Estado: Esperando orden...", text_color="gray")
        self.label_status.grid(row=5, column=0, padx=20, pady=(0, 5))

        self.btn_start = ctk.CTkButton(self, text="INICIAR TRANSCRIPCIÓN", height=50, font=ctk.CTkFont(size=18, weight="bold"), command=self.start_thread)
        self.btn_start.grid(row=6, column=0, padx=20, pady=(0, 20), sticky="ew")

        self.btn_open_editor = ctk.CTkButton(self, text="📝 ABRIR EDITOR", height=40, font=ctk.CTkFont(size=14), fg_color="#3B8ED0", command=self.open_editor_dialog)
        self.btn_open_editor.grid(row=8, column=0, padx=20, pady=(0, 20), sticky="ew")

        # --- Logs ---
        self.textbox_log = ctk.CTkTextbox(self, state="disabled")
        self.textbox_log.grid(row=9, column=0, padx=20, pady=(0, 20), sticky="nsew")

        # Redirect stdout
        sys.stdout = RedirectText(self.textbox_log, sys.__stdout__)
        sys.stderr = RedirectText(self.textbox_log, sys.__stderr__)

        # Initial Scan
        self.refresh_file_list()

    def load_config(self):
        config_path = Path(__file__).parent.parent / "config.json"
        if config_path.exists():
            try:
                with open(config_path, "r") as f:
                    data = json.load(f)
                    if "model" in data:
                        self.option_model.set(data["model"])
                    if "language" in data:
                        self.option_language.set(data["language"])
                    if "hf_token" in data:
                        self.entry_token.delete(0, "end")
                        self.entry_token.insert(0, data["hf_token"])
            except Exception as e:
                print(f"Error cargando config: {e}")

    def save_config(self):
        config_path = Path(__file__).parent.parent / "config.json"
        data = {
            "model": self.option_model.get(),
            "language": self.option_language.get(),
            "hf_token": self.entry_token.get().strip()
        }
        try:
            with open(config_path, "w") as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            print(f"Error guardando config: {e}")

    def browse_input(self):
        d = ctk.filedialog.askdirectory(initialdir=self.input_dir)
        if d:
            self.input_dir = Path(d)
            self.entry_input.delete(0, "end")
            self.entry_input.insert(0, d)
            self.refresh_file_list()

    def browse_output(self):
        d = ctk.filedialog.askdirectory(initialdir=self.output_dir)
        if d:
            self.output_dir = Path(d)
            self.entry_output.delete(0, "end")
            self.entry_output.insert(0, d)

    def select_all(self):
        if hasattr(self, 'file_checkboxes'):
            for _, chk in self.file_checkboxes:
                chk.select()

    def select_none(self):
        if hasattr(self, 'file_checkboxes'):
            for _, chk in self.file_checkboxes:
                chk.deselect()

    def refresh_file_list(self):
        # Clear existing
        for widget in self.scrollable_file_list.winfo_children():
            widget.destroy()

        self.file_checkboxes = [] # Store references

        # Find files
        path = Path(self.entry_input.get())
        if not path.exists():
            return

        audio_extensions = {".m4a", ".mp3", ".opus", ".wav", ".flac", ".ogg"}
        files = [f for f in path.iterdir() if f.suffix.lower() in audio_extensions and f.is_file()]

        if not files:
            label = ctk.CTkLabel(self.scrollable_file_list, text="(No se encontraron archivos de audio)")
            label.pack(anchor="w")
        
        for f in files:
            chk = ctk.CTkCheckBox(self.scrollable_file_list, text=f.name)
            chk.pack(anchor="w", padx=5, pady=2)
            # chk.select() # Deshabilitado por defecto
            
            # Store tuple (path, checkbox_widget)
            self.file_checkboxes.append((f, chk))

    def start_thread(self):
        self.btn_start.configure(state="disabled", text="Procesando...")
        t = threading.Thread(target=self.run_process)
        t.start()

    def open_editor_dialog(self):
        # User pick audio file
        audio_file = ctk.filedialog.askopenfilename(
            initialdir=self.input_dir, 
            title="Selecciona el Audio Original",
            filetypes=[("Audio", "*.mp3 *.m4a *.wav *.ogg *.flac")]
        )
        if not audio_file:
            return

        audio_path = Path(audio_file)
        
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
            
        # Open Editor
        try:
            from editor import EditorWindow
            EditorWindow(self, audio_path, json_path)
            self.label_status.configure(text=f"Editor abierto para {audio_path.name}", text_color="green")
        except Exception as e:
            print(f"Error abriendo editor: {e}")
            self.label_status.configure(text="Error abriendo editor", text_color="red")

    def run_process(self):

        try:
            model_name = self.option_model.get() or "large-v3"
            language_code = {"Spanish": "es", "English": "en", "Portuguese": "pt", "French": "fr", "Italian": "it", "German": "de", "Japanese": "ja"}.get(self.option_language.get(), "es")
            
            force_cpu = self.check_cpu.get() == 1
            safe_mode = self.check_safe_mode.get() == 1
            debug_mode = self.check_debug.get() == 1
            reuse_transcription = self.check_reuse.get() == 1
            
            device = setup_device(force_cpu)
            fp16 = (device == "cuda")
            hf_token = self.entry_token.get().strip() or None
            
            # --- FILE SELECTION ---
            selected_files = []
            if hasattr(self, 'file_checkboxes'):
                selected_files = [path for path, chk in self.file_checkboxes if chk.get() == 1]
            else:
                inp = Path(self.entry_input.get())
                audio_extensions = {".m4a", ".mp3", ".opus", ".wav", ".flac", ".ogg"}
                selected_files = [f for f in inp.iterdir() if f.suffix.lower() in audio_extensions and f.is_file()]

            if not selected_files:
                self.label_status.configure(text="No hay archivos seleccionados", text_color="orange")
                self.reset_ui()
                return

            out = Path(self.entry_output.get())
            out.mkdir(parents=True, exist_ok=True)
            self.save_config()

            # --- PHASE 1: TRANSCRIPTION (Batch) ---
            print(f"\n🚀 FASE 1: TRANSCRIPCIÓN (Whisper) - {len(selected_files)} archivos")
            self.label_status.configure(text=f"Cargando Whisper ({model_name})...", text_color="yellow")
            
            try:
                model = whisper.load_model(model_name, device=device)
            except Exception as e:
                print(f"❌ Error fatal cargando Whisper: {e}")
                self.reset_ui()
                return

            transcription_results = [] # Stores (file_path, output_path, segments)
            
            for i, f in enumerate(selected_files):
                self.label_status.configure(text=f"Transcribiendo {i+1}/{len(selected_files)}: {f.name}...", text_color="cyan")
                
                # New Organization: Create subfolder for file
                file_subdir = out / f.stem
                file_subdir.mkdir(exist_ok=True)
                
                outfile = file_subdir / (f.stem + ".txt")
                
                # Check exist
                if outfile.exists() and not reuse_transcription:
                    print(f"⏩ {f.name} ya existe. (Si deseas reprocesar, bórralo antes).")
                    continue
                elif outfile.exists() and reuse_transcription:
                    print(f"♻️ {f.name} ya existe. Intentando REUTILIZAR...")
                
                # Transcribe (hf_token=None force skip internal diarization)
                # verbose=True logs directly to captured stdout
                segments = transcribe_file(model, f, outfile, language=language_code, fp16=fp16, verbose=True, hf_token=None, reuse=reuse_transcription)
                
                if segments is not None:
                    transcription_results.append({
                        "file": f,
                        "outfile": outfile,
                        "segments": segments
                    })

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
                self.label_status.configure(text="Cargando Pyannote...", text_color="magenta")
                
                # Load Pipeline ONCE
                from pyannote.audio import Pipeline
                from main import diarize_audio, assign_speakers, save_transcript

                # Load pipeline logic inside gui thread
                try:
                    pipeline = Pipeline.from_pretrained("pyannote/speaker-diarization-3.1", use_auth_token=hf_token)
                    if device == "cuda":
                        pipeline.to(torch.device("cuda"))
                    
                    for i, item in enumerate(transcription_results):
                        f = item["file"]
                        segs = item["segments"]
                        outfile = item["outfile"]
                        
                        self.label_status.configure(text=f"Diarizando {i+1}/{len(transcription_results)}: {f.name}...", text_color="magenta")
                        
                        # Use loaded pipeline
                        # Safety: If safe_mode is ON, pass 'cpu', else pass 'cuda' (if avail)
                        dia_device = "cpu" if safe_mode else device
                        
                        diarization = diarize_audio(str(f), hf_token, device=dia_device, pipeline=pipeline, debug=debug_mode)
                        
                        if diarization:
                            final_segments = assign_speakers(segs, diarization)
                            # Overwrite file with speakers
                            save_transcript(final_segments, outfile)
                        
                        # SAFETY THROTTLE
                        time.sleep(3)
                        gc.collect()
                        
                except Exception as e:
                    print(f"❌ Error en Diarización Batch: {e}")
                    import traceback
                    traceback.print_exc()
                
                # Unload Pipeline
                del pipeline
                torch.cuda.empty_cache()
                gc.collect()
            
            print(f"✨ ¡Proceso Batch Finalizado!")
            self.label_status.configure(text="Proceso completado con éxito", text_color="green")

        except Exception as e:
            print(f"❌ Error inesperado: {e}")
            self.label_status.configure(text="Error inesperado", text_color="red")
        finally:
            self.reset_ui()

    def reset_ui(self):
        self.btn_start.configure(state="normal", text="INICIAR TRANSCRIPCIÓN")
        # Don't convert status back to "Ready" immediately so user can see result
        # self.label_status.configure(text="Listo para empezar", text_color="gray")

if __name__ == "__main__":
    try:
        app = App()
        app.mainloop()
    except Exception as e:
        print(f"CRASH: {e}")
        input("Presiona Enter para salir...")
