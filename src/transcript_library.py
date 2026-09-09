"""List finished transcript projects without exposing exports or diagnostics."""
import json
from pathlib import Path


def list_transcripts(folder):
    root = Path(folder)
    projects = []
    candidates = list(root.glob("*.json")) + list(root.glob("*/*.json"))
    for path in candidates:
        # Each project owns one canonical JSON; siblings are reports/backups.
        if path.parent != root and path.stem != path.parent.name:
            continue
        if path.parent == root and not path.with_suffix(".txt").is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, list) or not data:
                continue
            if not all(isinstance(s, dict) and isinstance(s.get("text"), str)
                       and isinstance(s.get("start"), (int, float))
                       and isinstance(s.get("end"), (int, float)) for s in data):
                continue
            projects.append({"path": path, "name": path.stem, "phrases": len(data),
                             "duration": max(s["end"] for s in data), "modified": path.stat().st_mtime})
        except (OSError, ValueError):
            continue
    # Prefer the current folder layout if a legacy flat export also exists.
    projects.sort(key=lambda p: (p["path"].parent != root, p["modified"]), reverse=True)
    unique = {}
    for project in projects:
        unique.setdefault(project["name"].casefold(), project)
    return sorted(unique.values(), key=lambda p: p["modified"], reverse=True)


def open_library(app):
    import customtkinter as ctk
    from tkinter import filedialog
    if getattr(app, "library_window", None) is not None and app.library_window.winfo_exists():
        app.library_window.lift()
        return
    window = app.library_window = ctk.CTkToplevel(app)
    window.title("Mis transcripciones")
    window.geometry("760x540")
    window.transient(app)
    ctk.CTkLabel(window, text="Mis transcripciones", font=ctk.CTkFont(size=24, weight="bold")).pack(anchor="w", padx=24, pady=(24, 4))
    ctk.CTkLabel(window, text="Un trabajo por audio. Elige el que quieras leer o corregir.", text_color="#A9B9C6").pack(anchor="w", padx=24)
    query = ctk.CTkEntry(window, placeholder_text="Buscar por nombre…")
    query.pack(fill="x", padx=24, pady=16)
    rows = ctk.CTkScrollableFrame(window)
    rows.pack(fill="both", expand=True, padx=24, pady=(0, 12))
    projects = list_transcripts(app.entry_output.get())
    def choose(project):
        window.destroy()
        app.open_saved_transcript(project["path"])
    def render(*_):
        for widget in rows.winfo_children():
            widget.destroy()
        matches = [p for p in projects if query.get().casefold() in p["name"].casefold()]
        if not matches:
            ctk.CTkLabel(rows, text="No hay transcripciones aquí. Puedes buscar en otra carpeta.", wraplength=550).pack(pady=35)
        for project in matches:
            row = ctk.CTkFrame(rows, fg_color="transparent")
            row.pack(fill="x", pady=8)
            button = ctk.CTkButton(row, text="Abrir", width=85, command=lambda p=project: choose(p))
            button.pack(side="right", padx=8)
            ctk.CTkLabel(row, text=project["name"], font=ctk.CTkFont(size=15, weight="bold")).pack(anchor="w", padx=10)
            minutes, seconds = divmod(int(project["duration"]), 60)
            ctk.CTkLabel(row, text=f"Texto hasta {minutes}:{seconds:02d}", text_color="#A9B9C6").pack(anchor="w", padx=10)
    def folder():
        nonlocal projects
        selected = filedialog.askdirectory(parent=window, title="Carpeta de transcripciones", initialdir=app.entry_output.get())
        if selected:
            projects = list_transcripts(selected)
            query.delete(0, "end")
            render()
    def external_project():
        selected = filedialog.askopenfilename(parent=window, title="Abrir proyecto editable", filetypes=[("Proyecto editable", "*.json")])
        if not selected:
            return
        try:
            data = json.loads(Path(selected).read_text(encoding="utf-8"))
            if not isinstance(data, list) or not data or not all(isinstance(s, dict) and isinstance(s.get("text"), str) and isinstance(s.get("start"), (int, float)) and isinstance(s.get("end"), (int, float)) for s in data):
                raise ValueError("El archivo no es un proyecto de transcripción editable.")
            window.destroy()
            app.open_saved_transcript(Path(selected))
        except (OSError, ValueError) as error:
            from tkinter import messagebox
            messagebox.showerror("No se puede abrir", str(error), parent=window)
    ctk.CTkButton(window, text="Abrir proyecto externo…", fg_color="transparent", command=external_project).pack(anchor="w", padx=24, pady=(0, 4))
    query.bind("<KeyRelease>", render)
    ctk.CTkButton(window, text="Buscar en otra carpeta…", fg_color="transparent", command=folder).pack(anchor="w", padx=24, pady=(0, 16))
    render()
    window.after(100, window.lift)
