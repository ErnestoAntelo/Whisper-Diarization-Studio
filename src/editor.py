import customtkinter as ctk
import json
import threading
import time
import os
from pathlib import Path

# Try import pygame
try:
    import pygame
    PYGAME_AVAILABLE = True
except ImportError:
    PYGAME_AVAILABLE = False

class EditorWindow(ctk.CTkToplevel):
    def __init__(self, parent, audio_path, json_path):
        super().__init__(parent)
        self.title(f"Editor: {Path(audio_path).name}")
        self.transient(parent)
        self.geometry("1000x800")
        
        self.audio_path = str(audio_path)
        self.json_path = str(json_path)
        self.bind("<Control-s>", lambda event: self.save_changes() if hasattr(self, "row_widgets") else None)
        self.segments = []
        self.grouped_view = True
        self.expanded_segments = set()
        self.row_widgets = []
        
# Audio State
        self.is_playing = False
        self.current_playing_index = -1
        self.stop_playback = threading.Event()
        self.playback_after_id = None
        
        # Pagination State
        self.current_page = 1
        self.items_per_page = 50
        
        if not PYGAME_AVAILABLE:
            ctk.CTkLabel(self, text="❌ Pygame no instalado. No se puede reproducir audio.", text_color="red").pack(pady=10)
        else:
            pygame.mixer.init()
            
            # Protocol to handle X button
            self.protocol("WM_DELETE_WINDOW", self.on_close)
            
            # --- OVERLAY FOR LOADING (Blocking UI) ---
            self.overlay_frame = ctk.CTkFrame(self, fg_color="#2B2B2B")
            self.overlay_frame.place(relx=0, rely=0, relwidth=1, relheight=1)
            
            lbl_title = ctk.CTkLabel(self.overlay_frame, text="Preparando Editor...", font=ctk.CTkFont(size=20, weight="bold"))
            lbl_title.pack(expand=True, pady=(0, 20))
            
            self.lbl_loading = ctk.CTkLabel(self.overlay_frame, text="Cargando audio...", text_color="yellow")
            self.lbl_loading.pack(pady=5)
            
            self.progress_bar = ctk.CTkProgressBar(self.overlay_frame, width=400, mode="indeterminate")
            self.progress_bar.pack(pady=20)
            self.progress_bar.start()

            # Start Load Sequence
            self.after(500, self.start_load_sequence)

    def start_load_sequence(self):
        t = threading.Thread(target=self._load_audio_thread)
        t.start()
        
    def _load_audio_thread(self):
        try:
            # Try loading original
            pygame.mixer.music.load(self.audio_path)
            self.after(0, self._on_load_success)
        except Exception:
            # Silent fallback
            self.after(0, lambda: self.lbl_loading.configure(text="🔄 Optimizando formato...", text_color="cyan"))
            
            try:
                # Fallback: Convert to system temp WAV (avoid cluttering input folder)
                import subprocess
                import os
                import tempfile
                
                # Create a temp file path
                fd, temp_wav = tempfile.mkstemp(suffix=".wav")
                os.close(fd) # Close file handle from mkstemp
                temp_wav_path = str(Path(temp_wav))
                
                # HIDE CONSOLE WINDOW on Windows
                startupinfo = None
                if os.name == 'nt':
                     startupinfo = subprocess.STARTUPINFO()
                     startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                
                subprocess.run(["ffmpeg", "-y", "-i", self.audio_path, "-ac", "2", "-ar", "44100", temp_wav_path], 
                               check=True, 
                               stdout=subprocess.DEVNULL, 
                               stderr=subprocess.DEVNULL, 
                               stdin=subprocess.DEVNULL,
                               startupinfo=startupinfo,
                               creationflags=0x08000000 if os.name == 'nt' else 0) 
                
                self.temp_audio_path = temp_wav_path
                
                if not Path(self.temp_audio_path).exists():
                     raise FileNotFoundError("FFmpeg failed to create output file")
                
                pygame.mixer.music.load(self.temp_audio_path)
                print(f"✅ Conversión exitosa (Temp): {Path(temp_wav_path).name}")
                self.after(0, self._on_load_success)
                
            except Exception as e2:
                print(f"❌ Error fatal en audio: {e2}")
                self.after(0, lambda message=str(e2): self.lbl_loading.configure(text=f"❌ Error Audio: {message}", text_color="red"))
                self.after(0, self.progress_bar.stop)

    def _on_load_success(self):
        # Remove Overlay
        self.progress_bar.stop()
        self.overlay_frame.destroy()
        
        # Load Data FIRST
        self.load_data()
        
        # Build Main UI
        self.init_main_ui()
        self.render_rows()
        self.lift()
        self.focus_set()

    def load_data(self):
        self.load_error = None
        try:
            # Check file exists
            if not Path(self.json_path).exists():
                self.load_error = f"Archivo no encontrado:\n{self.json_path}"
                self.segments = []
                return

            with open(self.json_path, "r", encoding="utf-8") as f:
                raw_data = json.load(f)
            
            # MERGE CONSECUTIVE SEGMENTS (Reader Mode)
            # Preserve original phrase boundaries when opening and saving a project.
            self.segments = raw_data
                
            if not self.segments:
                self.load_error = "El archivo JSON está vacío ([])."
            
            # Update Stats after load
            self.update_statistics()
                
        except Exception as e:
            print(f"Error loading JSON: {e}")
            self.load_error = f"Error leyendo JSON:\n{e}"
            self.segments = []

    def display_blocks(self):
        # The view references original phrases; grouping never rewrites timestamps.
        blocks = []
        for index, segment in enumerate(self.segments):
            speaker = segment.get("speaker") or "UNKNOWN"
            can_join = (
                self.grouped_view and blocks and speaker.upper() != "UNKNOWN"
                and blocks[-1]["speaker"] == speaker
                and segment["start"] - blocks[-1]["end"] <= 3.0
                and index not in self.expanded_segments
                and blocks[-1]["indices"][-1] not in self.expanded_segments
            )
            if can_join:
                block = blocks[-1]
                block["end"] = max(block["end"], segment["end"])
                block["text"] += " " + segment["text"].strip()
                block["indices"].append(index)
            else:
                blocks.append(dict(start=segment["start"], end=segment["end"],
                                   speaker=speaker, text=segment["text"].strip(), indices=[index]))
        return blocks

    def set_grouping(self, grouped):
        self.sync_page_to_memory()
        self.stop_audio()
        self.grouped_view = grouped
        self.expanded_segments.clear()
        self.current_page = 1
        self.render_rows()
        self.scroll_frame._parent_canvas.yview_moveto(0.0)
        self.lbl_status.configure(text="Vista agrupada" if grouped else "Todas las frases separadas",
                                  text_color="cyan")

    def split_block(self, indices):
        self.sync_page_to_memory()
        self.stop_audio()
        self.expanded_segments.update(indices)
        blocks = self.display_blocks()
        position = next(i for i, block in enumerate(blocks) if indices[0] in block["indices"])
        self.current_page = position // self.items_per_page + 1
        self.render_rows()
        self.scroll_frame._parent_canvas.yview_moveto(0.0)
        self.lbl_status.configure(text="Bloque separado: ya puedes editar cada frase", text_color="cyan")

    def update_statistics(self):
        if not hasattr(self, 'lbl_stats'): return
        
        unique_speakers = set()
        pending_count = 0
        unassigned_count = 0
        
        for seg in self.segments:
            s = seg.get('speaker', 'UNKNOWN')
            if not s or s.upper() == "UNKNOWN":
                unassigned_count += 1
                continue
            unique_speakers.add(s)
            if "SPEAKER_" in s:
                pending_count += 1 # Count SEGMENTS pending
                # Or count SPEAKERS pending? "Pendientes" usually implies distinct unknown people.
                # Let's count Pending Segments? No, usage: "Faltan 50 frases por corregir".
        
        # Analyze unique pending speakers
        pending_speakers = [s for s in unique_speakers if "SPEAKER_" in s]
        
        txt = f"Hablantes: {len(unique_speakers)} · Sin nombre: {len(pending_speakers)} · Sin asignar: {unassigned_count}"
        self.lbl_stats.configure(text=txt)

    def init_main_ui(self):
        # Top Bar
        top_frame = ctk.CTkFrame(self)
        top_frame.pack(fill="x", padx=10, pady=10)
        
        ctk.CTkButton(top_frame, text="GUARDAR CAMBIOS", fg_color="green", command=self.save_changes).pack(side="right", padx=10)
        
        self.btn_stop = ctk.CTkButton(top_frame, text="⏹ DETENER AUDIO", fg_color="gray", command=self.stop_audio, state="disabled")
        self.btn_stop.pack(side="left", padx=10)
        
        self.lbl_status = ctk.CTkLabel(top_frame, text="Listo")
        self.lbl_status.pack(side="left", padx=20)
        
        # Stats Label (New)
        self.lbl_stats = ctk.CTkLabel(top_frame, text="...", text_color="#AAAAAA")
        self.lbl_stats.pack(side="left", padx=20)

        view_bar = ctk.CTkFrame(self)
        view_bar.pack(fill="x", padx=10)
        ctk.CTkButton(view_bar, text="Agrupar por hablante", command=lambda: self.set_grouping(True)).pack(side="left", padx=8, pady=8)
        ctk.CTkButton(view_bar, text="Separar todo", command=lambda: self.set_grouping(False)).pack(side="left", padx=8)
        ctk.CTkLabel(view_bar, text="Para corregir el texto de un bloque, pulsa Editar frases.", text_color="#AAAAAA").pack(side="left", padx=8)

        # Scrollable Area
        self.scroll_frame = ctk.CTkScrollableFrame(self, label_text="Transcripción")
        self.scroll_frame.pack(fill="both", expand=True, padx=10, pady=10)

    def render_rows(self):
        import tkinter as tk # Use standard tk widgets for performance
        
        # Clear (Optimized: Destroy frame content)
        for w in self.scroll_frame.winfo_children():
            w.destroy()

        # DIAGNOSTICS FOR EMPTY STATE
        if self.load_error:
            lbl = ctk.CTkLabel(self.scroll_frame, text=f"❌ {self.load_error}", text_color="red", font=("Arial", 14))
            lbl.pack(pady=20)
            lbl2 = ctk.CTkLabel(self.scroll_frame, text="Sugerencia: Vuelve a procesar el archivo en la pantalla principal.", text_color="gray")
            lbl2.pack()
            return

        if not self.segments:
             lbl = ctk.CTkLabel(self.scroll_frame, text="⚠️ No hay segmentos de transcripción.", text_color="orange", font=("Arial", 14))
             lbl.pack(pady=20)
             lbl2 = ctk.CTkLabel(self.scroll_frame, text="Esto puede ocurrir si el audio no tiene voz o el modelo no detectó nada.", text_color="gray")
             lbl2.pack()
             return

        self.row_widgets = [] 
        
        blocks = self.display_blocks()
        total_pages = max(1, (len(blocks) + self.items_per_page - 1) // self.items_per_page)
        self.current_page = min(self.current_page, total_pages)
        # PAGINATION SLICE
        start_index = (self.current_page - 1) * self.items_per_page
        end_index = start_index + self.items_per_page
        visible_segments = blocks[start_index:end_index]
        
        # Calculate totals for display
        total_pages = (len(self.display_blocks()) + self.items_per_page - 1) // self.items_per_page or 1
        
        # Info Label
        ctk.CTkLabel(self.scroll_frame, text=f"📄 Página {self.current_page} de {total_pages} (Filas {start_index+1}-{min(end_index, len(blocks))})",
                     text_color="gray", font=("Arial", 12)).pack(pady=(5, 15))

        # Use tk Frame for lighter weight items? No, row container needs to be ctk or tk?
        # ctk frame is okay if content is tk.
        
        # Define Styles for Native Widgets to match Dark Mode
        BG_COLOR = "#2B2B2B"
        FG_COLOR = "white"
        ENTRY_BG = "#343638"
        
        for i, seg in enumerate(visible_segments):
            
            row = ctk.CTkFrame(self.scroll_frame, fg_color="transparent") # Transparent to save draw
            row.pack(fill="x", pady=8) # Ultra spacious padding
            
            metadata = ctk.CTkFrame(row, fg_color="transparent")
            metadata.pack(fill="x")

            # Times (Native Label)
            start_str = time.strftime('%H:%M:%S', time.gmtime(seg['start']))
            end_str = time.strftime('%H:%M:%S', time.gmtime(seg['end']))
            
            ts_label = tk.Label(metadata, text=f"[{start_str}-{end_str}]", width=18, bg=BG_COLOR, fg="#AAAAAA", font=("Consolas", 13))
            ts_label.pack(side="left", padx=6)

            # Play Button (Native)
            btn_play = tk.Button(metadata, text="▶", width=5, bg="#444", fg="white", relief="flat",
                                 font=("Arial", 12, "bold"),
                                 command=lambda s=seg['start'], e=seg['end'], idx=i: self.play_segment(s, e, idx))
            btn_play.pack(side="left", padx=4)

            # Speaker (Native Entry)
            speaker_val = seg.get('speaker', 'SPEAKER_00')
            entry_speaker = tk.Entry(metadata, width=20, bg=ENTRY_BG, fg=FG_COLOR, insertbackground="white", relief="flat",
                                     font=("Arial", 14))
            entry_speaker.insert(0, speaker_val)
            entry_speaker.pack(side="left", padx=6)

            # Global Rename Button (Native)
            # FIX: Must pass REAL INDEX (start_index + i), not relative 'i'
            real_idx_val = seg["indices"][0]
            btn_rename_global = tk.Button(metadata, text="⚡", width=5, bg="#555", fg="yellow", relief="flat",
                                          font=("Arial", 12, "bold"),
                                          command=lambda idx=real_idx_val: self.rename_global(idx))
            btn_rename_global.pack(side="left", padx=4)

            if len(seg["indices"]) > 1:
                tk.Button(metadata, text=f"Editar frases ({len(seg['indices'])})", bg="#444", fg="white",
                          relief="flat", command=lambda indices=seg["indices"]: self.split_block(indices)).pack(side="left", padx=8)

            # Text (Native Multiline Text)
            entry_content = tk.Text(row, bg=ENTRY_BG, fg=FG_COLOR, insertbackground="white", relief="flat",
                                     font=("Segoe UI", 16), height=min(18, max(3, (len(seg["text"]) + 84) // 85)), wrap="word") # Multiline!
            entry_content.insert("1.0", seg['text'].strip())
            entry_content.pack(fill="x", expand=True, padx=10, pady=5)
            if len(seg["indices"]) > 1:
                entry_content.configure(state="disabled")

            self.row_widgets.append({
                "speaker": entry_speaker,
                "text": entry_content,
                "data": seg, 
                "real_index": real_idx_val,
                "indices": seg["indices"]
            })
            
        # PAGINATION CONTROLS
        self.render_pagination_controls(total_pages)
        self.update_statistics()

    def render_pagination_controls(self, total_pages):
        frame_nav = ctk.CTkFrame(self.scroll_frame, fg_color="transparent")
        frame_nav.pack(pady=30)
        
        # Prev
        state_prev = "normal" if self.current_page > 1 else "disabled"
        btn_prev = ctk.CTkButton(frame_nav, text="⬅ Anterior", state=state_prev, width=120,
                                 command=self.prev_page)
        btn_prev.pack(side="left", padx=20)
        
        # Label
        lbl = ctk.CTkLabel(frame_nav, text=f"{self.current_page} / {total_pages}", font=("Arial", 16, "bold"))
        lbl.pack(side="left", padx=20)

        # Next
        state_next = "normal" if self.current_page < total_pages else "disabled"
        btn_next = ctk.CTkButton(frame_nav, text="Siguiente ➡", state=state_next, width=120,
                                 command=self.next_page)
        btn_next.pack(side="left", padx=20)

    def prev_page(self):
        self.sync_page_to_memory()
        if self.current_page > 1:
            self.current_page -= 1
            self.render_rows()
            # Jump to top
            self.scroll_frame._parent_canvas.yview_moveto(0.0)

    def next_page(self):
        self.sync_page_to_memory()
        # total_pages calc
        total_pages = (len(self.display_blocks()) + self.items_per_page - 1) // self.items_per_page or 1
        
        if self.current_page < total_pages:
            self.current_page += 1
            self.render_rows()
            # Jump to top
            self.scroll_frame._parent_canvas.yview_moveto(0.0)
    
    def sync_page_to_memory(self):
        for row in self.row_widgets:
            indices = row.get("indices", [row["real_index"]])
            speaker = row["speaker"].get().strip()
            for index in indices:
                self.segments[index]["speaker"] = speaker
            # A paragraph has no new word alignment: edits happen on its original phrases.
            if len(indices) == 1:
                value = row["text"].get("1.0", "end-1c").strip()
                if value != self.segments[indices[0]]["text"].strip():
                    self.segments[indices[0]]["text"] = value

    def rename_global(self, real_idx):
        # CRITICAL FIX: Get OLD name from memory BEFORE syncing!
        # Because sync overwrites memory with UI value.
        
        target_seg_memory = self.segments[real_idx]
        old_name = target_seg_memory.get('speaker', 'SPEAKER_00') 
        
        # Now find the NEW name from the UI widget
        target_widget_row = None
        for w in self.row_widgets:
            if w["real_index"] == real_idx:
                target_widget_row = w
                break
        
        if not target_widget_row: return
        
        new_name = target_widget_row["speaker"].get().strip()
        
        # Compare
        if new_name == old_name:
            self.lbl_status.configure(text=f"⚠️ Cambia el nombre en la casilla antes de pulsar el rayo.", text_color="orange")
            print(f"⚠️ Rename skipped: Name '{new_name}' identical to old.")
            return

        # Now we can sync purely to save other changes (like text edits on same row)
        self.sync_page_to_memory()
        
        # Debug Info
        print(f"⚡ Global Rename Triggered: '{old_name}' -> '{new_name}'")
        
        # Update ALL segments that match 'old_name'
        count = 0
        for seg in self.segments:
            current_speaker = seg.get('speaker', 'SPEAKER_00').strip() # Safety strip
            if current_speaker == old_name.strip(): # Valid comparison
                seg['speaker'] = new_name
                count += 1
                
        print(f"✅ Replaced {count} occurrences (excluding current row if already synced).")
        
        # Count correction: We changed 1 via sync + 'count' via loop.
        # Total changed = count + 1.
        total_changes = count + 1
        
        # Refresh UI
        self.render_rows()
        self.lbl_status.configure(text=f"⚡ {old_name} ➔ {new_name} ({total_changes} cambios)", text_color="cyan")

    def play_segment(self, start_sec, end_sec, idx):
        if not PYGAME_AVAILABLE:
            return
        
        self.stop_audio()
        # Enable Stop button
        if hasattr(self, 'btn_stop'):
            self.btn_stop.configure(state="normal", fg_color="red") # Active Red

        # Start new thread for playback monitoring
        self.is_playing = True
        self.lbl_status.configure(text=f"Reproduciendo...", text_color="cyan")
        
        try:
            # Re-load to seek properly (pygame music seek is flaky on some formats, but Play(start=) works)
            # Convert start_sec to start argument
            # pygame.mixer.music.play(loops=0, start=start_sec)
            # Note: 'start' argument in play() is usually for MP3/OGG. For WAV it might depend.
            # Assuming 'main.py' converted to WAV for diarization? But GUI selects original file?
            # If original file is M4A, pygame handles it usually if ffmpeg is on system.
            pygame.mixer.music.play(start=start_sec)
            
            # Monitor stop
            self.playback_after_id = self.after(max(1, int((end_sec - start_sec) * 1000)), self.stop_audio)
        except Exception as e:
            print(f"Play Error: {e}")
            self.stop_audio()
            self.lbl_status.configure(text="Error reproducción", text_color="red")

    def _monitor_playback(self, start, end):
        duration = end - start
        start_time = time.time()
        
        while self.is_playing:
            if time.time() - start_time >= duration:
                break
            if not pygame.mixer.music.get_busy():
                break
            time.sleep(0.1)
        
        pygame.mixer.music.stop()
        self.is_playing = False
        # Update UI via main thread safe call? Tkinter is not thread safe usually.
        # But configure() is often tolerant. Better to not touch UI from thread if possible.

    def stop_audio(self):
        if self.playback_after_id is not None:
            self.after_cancel(self.playback_after_id)
            self.playback_after_id = None
        if PYGAME_AVAILABLE:
            self.is_playing = False
            pygame.mixer.music.stop()
            if hasattr(self, 'btn_stop'):
                self.btn_stop.configure(state="disabled", fg_color="gray")
            if hasattr(self, 'lbl_status'):
                self.lbl_status.configure(text="Detenido", text_color="gray")

    def save_changes(self):
        # 1. Sync current page edits to memory
        self.sync_page_to_memory()
        
        # 2. Save ALL segments from memory (self.segments)
        try:
            import tempfile
            fd, temporary = tempfile.mkstemp(dir=Path(self.json_path).parent, suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(self.segments, f, indent=4, ensure_ascii=False)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(temporary, self.json_path)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
        except Exception as e:
            print(f"Save JSON Error: {e}")
            self.lbl_status.configure(text="Error guardando JSON", text_color="red")
            return

        # 2. Save TXT (Reusing main.py logic logic or recreating here?)
        # Recreating simple logic here to avoid importing complex main dependencies
        # 2. Save TXT
        try:
            txt_path = Path(self.json_path).with_suffix(".txt")
            with open(txt_path, "w", encoding="utf-8") as f:
                for seg in self.display_blocks():
                    start = time.strftime('%H:%M:%S', time.gmtime(seg['start']))
                    end = time.strftime('%H:%M:%S', time.gmtime(seg['end']))
                    text_content = seg['text'].strip()
                    speaker = seg.get('speaker', 'UNKNOWN')
                    
                    f.write(f"[{start} --> {end}] {speaker}: {text_content}\n")
            
            self.lbl_status.configure(text="✅ ¡Guardado Correctamente!", text_color="green")
            # self.segments is already up to date
        except Exception as e:
             self.lbl_status.configure(text=f"Error TXT: {e}", text_color="red")

    def on_close(self):
        self.stop_audio()
        if PYGAME_AVAILABLE:
            try:
                pygame.mixer.music.unload() # Try to release file lock (Pygame 2.0.0+)
            except: pass
            
        # Try to delete temp file
        if hasattr(self, 'temp_audio_path') and self.temp_audio_path:
            try:
                os.remove(self.temp_audio_path)
                print(f"🧹 Temp deleted: {self.temp_audio_path}")
            except Exception as e:
                print(f"⚠️ Could not delete temp: {e}")
                
        self.destroy()
