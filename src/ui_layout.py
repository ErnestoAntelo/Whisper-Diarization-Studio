"""Task-first desktop layout: add audio or open the transcript editor."""
from pathlib import Path
import queue
import sys
import tkinter as tk
import customtkinter as ctk


def build_main_ui(app, redirect_text):
    app.title("Whisper Studio")
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.geometry("980x720")
    app.minsize(820, 620)
    base = Path(__file__).resolve().parent.parent
    app.input_dir, app.output_dir = base / "input", base / "output"
    app.ui_events = queue.Queue()
    app.grid_columnconfigure(0, weight=1)
    app.grid_rowconfigure(2, weight=1)
    app.configure(fg_color="#111820")

    header = ctk.CTkFrame(app, fg_color="transparent")
    header.grid(row=0, column=0, sticky="ew", padx=28, pady=(24, 16))
    ctk.CTkLabel(header, text="Whisper Studio", font=ctk.CTkFont(size=26, weight="bold")).pack(anchor="w")
    ctk.CTkLabel(header, text="Transcribe un audio o continúa con un texto guardado.", text_color="#9DAFBE").pack(anchor="w")

    choices = ctk.CTkFrame(app, fg_color="transparent")
    choices.grid(row=1, column=0, sticky="ew", padx=28, pady=(0, 20))
    choices.grid_columnconfigure((0, 1), weight=1, uniform="choices")
    for column, title, description in [(0, "Nueva transcripción", "Selecciona un audio de cualquier carpeta."),
                                       (1, "Revisar una transcripción", "Lee, corrige y escucha un trabajo guardado.")]:
        card = ctk.CTkFrame(choices, fg_color="#1C2732", corner_radius=12)
        card.grid(row=0, column=column, sticky="nsew", padx=(0, 8) if column == 0 else (8, 0))
        ctk.CTkLabel(card, text=title, font=ctk.CTkFont(size=18, weight="bold")).pack(anchor="w", padx=20, pady=(18, 4))
        ctk.CTkLabel(card, text=description, text_color="#A9B9C6").pack(anchor="w", padx=20)
        button = ctk.CTkButton(card, text="Añadir audio…" if column == 0 else "Abrir editor…",
                              height=42, font=ctk.CTkFont(size=15, weight="bold"),
                              command=app.add_audio_files if column == 0 else app.open_editor_dialog)
        button.pack(fill="x", padx=20, pady=(16, 20))
        if column == 1:
            app.btn_open_editor = button

    files = ctk.CTkFrame(app, fg_color="#1C2732", corner_radius=12)
    files.grid(row=2, column=0, sticky="nsew", padx=28, pady=(0, 14))
    files.grid_columnconfigure(0, weight=1)
    files.grid_rowconfigure(1, weight=1)
    toolbar = ctk.CTkFrame(files, fg_color="transparent")
    toolbar.grid(row=0, column=0, sticky="ew", padx=16, pady=10)
    app.lbl_file_count = ctk.CTkLabel(toolbar, text="Audios", font=ctk.CTkFont(size=16, weight="bold"))
    app.lbl_file_count.pack(side="left")
    menu = tk.Menu(app, tearoff=False)
    menu.add_command(label="Añadir una carpeta…", command=app.browse_input)
    menu.add_command(label="Quitar todos de la lista", command=app.clear_audio_files)
    menu.add_separator()
    menu.add_command(label="Abrir carpeta de resultados", command=app.open_output_folder)
    more = ctk.CTkButton(toolbar, text="•••", width=40, fg_color="transparent")
    more.configure(command=lambda: menu.tk_popup(more.winfo_rootx(), more.winfo_rooty() + more.winfo_height()))
    more.pack(side="right")
    app.scrollable_file_list = ctk.CTkScrollableFrame(files, height=130, fg_color="transparent")
    app.scrollable_file_list.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
    app.file_checkboxes = []
    app.clear_audio_files()
    app.entry_input = ctk.CTkEntry(app)
    app.entry_input.insert(0, str(app.input_dir))

    app.settings_window = ctk.CTkToplevel(app)
    app.settings_window.withdraw()
    app.settings_window.title("Ajustes de transcripción")
    app.settings_window.geometry("900x350")
    app.settings_window.resizable(False, False)
    app.settings_window.transient(app)
    app.settings_window.protocol("WM_DELETE_WINDOW", app.settings_window.withdraw)
    settings = ctk.CTkFrame(app.settings_window, fg_color="#1C2732", corner_radius=12)
    settings.pack(fill="x", padx=16, pady=16)
    first = ctk.CTkFrame(settings, fg_color="transparent")
    first.pack(fill="x", padx=14, pady=(12, 4))
    ctk.CTkLabel(first, text="Modelo").pack(side="left", padx=(0, 8))
    app.option_model = ctk.CTkOptionMenu(first, values=["medium", "turbo", "small", "base", "tiny", "large-v3"], width=115)
    app.option_model.pack(side="left")
    ctk.CTkLabel(first, text="Idioma").pack(side="left", padx=(18, 8))
    app.option_language = ctk.CTkOptionMenu(first, values=["Spanish", "English", "Portuguese", "French", "Italian", "German", "Japanese"], width=115)
    app.option_language.pack(side="left")
    ctk.CTkLabel(first, text="Hablantes").pack(side="left", padx=(18, 8))
    app.entry_speakers = ctk.CTkEntry(first, width=95, placeholder_text="Automático")
    app.entry_speakers.pack(side="left")
    ctk.CTkButton(first, text="Perfil portátil", width=125, command=app.apply_gpu_profile).pack(side="right", padx=(10, 0))

    second = ctk.CTkFrame(settings, fg_color="transparent")
    second.pack(fill="x", padx=14, pady=8)
    app.check_reuse = ctk.CTkCheckBox(second, text="Reutilizar texto guardado", width=205)
    app.check_reuse.pack(side="left")
    app.check_safe_mode = ctk.CTkCheckBox(second, text="Diarización en CPU", width=185)
    app.check_safe_mode.pack(side="left", padx=12)
    app.check_safe_mode.deselect()
    app.check_cpu = ctk.CTkCheckBox(second, text="Whisper en CPU", width=155)
    app.check_cpu.pack(side="left")
    app.check_debug = ctk.CTkCheckBox(second, text="Monitor GPU", width=120)
    app.option_gpu_profile = ctk.CTkOptionMenu(second, values=["GPU rápida", "GPU compatible"], width=145)
    app.option_gpu_profile.pack(side="right", padx=(12, 0))

    credentials = ctk.CTkFrame(settings, fg_color="transparent")
    credentials.pack(fill="x", padx=14, pady=(0, 12))
    ctk.CTkLabel(credentials, text="Token Hugging Face", text_color="#9DAFBE").pack(side="left", padx=(0, 12))
    app.entry_token = ctk.CTkEntry(credentials, show="*", width=220, placeholder_text="Necesario para identificar hablantes")
    app.entry_token.pack(side="left")
    ctk.CTkLabel(credentials, text="Procesamiento local · audio en tu equipo", text_color="#9DAFBE").pack(side="right")

    destination = ctk.CTkFrame(app.settings_window, fg_color="transparent")
    destination.pack(fill="x", padx=16, pady=(0, 16))
    destination.grid_columnconfigure(1, weight=1)
    ctk.CTkLabel(destination, text="Guardar en", text_color="#9DAFBE").grid(row=0, column=0, padx=(0, 10))
    app.entry_output = ctk.CTkEntry(destination)
    app.entry_output.insert(0, str(app.output_dir))
    app.entry_output.grid(row=0, column=1, sticky="ew")
    ctk.CTkButton(destination, text="Cambiar…", width=85, fg_color="#344453", command=app.browse_output).grid(row=0, column=2, padx=8)
    ctk.CTkButton(destination, text="Ver resultados", width=115, fg_color="#344453", command=app.open_output_folder).grid(row=0, column=3)
    app.load_config()
    app.bind("<Control-o>", lambda event: app.add_audio_files())
    app.bind("<Control-e>", lambda event: app.open_editor_dialog())

    actions = ctk.CTkFrame(app, fg_color="transparent")
    actions.grid(row=3, column=0, sticky="ew", padx=28, pady=(0, 8))
    actions.grid_columnconfigure(0, weight=1)
    app.btn_start = ctk.CTkButton(actions, text="Transcribir audio", state="disabled", height=44,
                                font=ctk.CTkFont(size=15, weight="bold"), command=app.start_thread)
    app.btn_start.grid(row=0, column=0, sticky="ew")
    app.btn_cancel = ctk.CTkButton(actions, text="Cancelar", width=100, height=44, state="disabled",
                                 fg_color="#803C3C", command=app.cancel_process)
    app.label_status = ctk.CTkLabel(app, text="Para empezar, añade un audio o abre el editor de un trabajo guardado.",
                                  text_color="#9DAFBE", anchor="w", wraplength=760)
    app.label_status.grid(row=4, column=0, sticky="ew", padx=28, pady=(0, 6))
    footer = ctk.CTkFrame(app, fg_color="transparent")
    footer.grid(row=5, column=0, sticky="ew", padx=28, pady=(0, 12))
    ctk.CTkLabel(footer, text="Audio y texto en tu equipo", text_color="#9DAFBE").pack(side="left")
    def show_settings():
        app.settings_window.deiconify()
        app.settings_window.lift()
        app.settings_window.focus_set()
    ctk.CTkButton(footer, text="Ajustes", width=80, fg_color="transparent", command=show_settings).pack(side="right")
    app.textbox_log = ctk.CTkTextbox(app, state="disabled", height=110, font=("Consolas", 11))
    def toggle_log():
        if app.textbox_log.winfo_manager():
            app.textbox_log.grid_remove()
            details.configure(text="Ver detalles")
        else:
            app.textbox_log.grid(row=6, column=0, sticky="ew", padx=28, pady=(0, 16))
            details.configure(text="Ocultar detalles")
    details = ctk.CTkButton(footer, text="Ver detalles", width=110, fg_color="transparent", command=toggle_log)
    details.pack(side="right")
    sys.stdout = redirect_text(app.textbox_log, sys.__stdout__, event_queue=app.ui_events)
    sys.stderr = redirect_text(app.textbox_log, sys.__stderr__, event_queue=app.ui_events)
    app.after(60, app.drain_ui_events)
