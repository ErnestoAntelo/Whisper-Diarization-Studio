"""Exports are copies; the editable project always keeps phrase timestamps."""
import csv
import io
import json
import os
import tempfile
from pathlib import Path

FORMATS = {"Texto (.txt)": "txt", "Subtítulos (.srt)": "srt", "Subtítulos web (.vtt)": "vtt",
           "Tabla (.csv)": "csv", "Proyecto editable (.json)": "json"}

def timestamp(seconds, separator=","):
    milliseconds = max(0, round(float(seconds) * 1000))
    hours, rest = divmod(milliseconds, 3600000)
    minutes, rest = divmod(rest, 60000)
    seconds, ms = divmod(rest, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}{separator}{ms:03d}"

def render_export(segments, kind, blocks=None, timestamps=True, speakers=True):
    if kind == "json":
        return json.dumps(segments, ensure_ascii=False, indent=2) + "\n"
    if kind == "txt":
        paragraphs = []
        for s in (blocks if blocks is not None else segments):
            prefix = f"[{timestamp(s['start'], '.')[:-4]} → {timestamp(s['end'], '.')[:-4]}] " if timestamps else ""
            speaker = (s.get("speaker") or "").strip()
            if speakers and speaker:
                prefix += speaker + ": "
            paragraphs.append(prefix + s["text"].strip())
        return "\n\n".join(paragraphs) + "\n"
    if kind == "csv":
        output = io.StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow(["start", "end", "speaker", "text"])
        for s in segments:
            writer.writerow([s["start"], s["end"], s.get("speaker", "") if speakers else "", s["text"]])
        return output.getvalue()
    if kind in ("srt", "vtt"):
        import html
        cues = []
        for s in segments:
            text = s["text"].strip()
            if not text or s["end"] <= s["start"]:
                continue
            # Escape cue markup and prevent blank lines from ending a cue early.
            text = "\n".join(line.strip() for line in text.splitlines() if line.strip())
            speaker = (s.get("speaker") or "").strip()
            text = html.escape((speaker + ": " if speakers and speaker else "") + text)
            start = timestamp(s["start"], "," if kind == "srt" else ".")
            end = timestamp(max(s["end"], s["start"] + .001), "," if kind == "srt" else ".")
            cues.append(f"{len(cues)+1}\n{start} --> {end}\n{text}")
        return ("WEBVTT\n\n" if kind == "vtt" else "") + "\n\n".join(cues) + "\n"
    raise ValueError("Formato de exportación no reconocido")

def atomic_write(path, text):
    path = Path(path)
    fd, temporary = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)

def open_export_dialog(editor):
    import customtkinter as ctk
    from tkinter import filedialog
    editor.sync_page_to_memory()
    window = ctk.CTkToplevel(editor)
    window.title("Exportar transcripción")
    window.geometry("550x420")
    window.transient(editor)
    ctk.CTkLabel(window, text="Exportar una copia", font=ctk.CTkFont(size=22, weight="bold")).pack(anchor="w", padx=24, pady=(24, 8))
    format_choice = ctk.CTkOptionMenu(window, values=list(FORMATS))
    format_choice.pack(fill="x", padx=24, pady=10)
    include_time = ctk.CTkCheckBox(window, text="Incluir tiempos en el texto")
    include_time.select()
    include_time.pack(anchor="w", padx=24, pady=8)
    include_speaker = ctk.CTkCheckBox(window, text="Incluir nombres de hablantes")
    include_speaker.select()
    include_speaker.pack(anchor="w", padx=24, pady=8)
    status = ctk.CTkLabel(window, text="", wraplength=490, justify="left")
    status.pack(fill="x", padx=24, pady=8)
    def update_options(*_):
        kind = FORMATS[format_choice.get()]
        include_time.configure(state="normal" if kind == "txt" else "disabled")
        include_speaker.configure(state="disabled" if kind == "json" else "normal")
        status.configure(text={"txt": "El texto utiliza la agrupación que estás viendo en el editor.",
            "srt": "Los subtítulos usan los tiempos de cada frase, aunque la vista esté agrupada.",
            "vtt": "Los subtítulos usan los tiempos de cada frase, aunque la vista esté agrupada.",
            "csv": "Una fila por frase, con tiempos en segundos. Compatible con hojas de cálculo.",
            "json": "Copia completa de las frases, tiempos y hablantes para volver a editarla."}[kind])
    format_choice.configure(command=update_options)
    def export():
        kind = FORMATS[format_choice.get()]
        destination = Path(getattr(editor, "last_export_dir", Path(editor.json_path).parent / "exports"))
        destination.mkdir(parents=True, exist_ok=True)
        path = filedialog.asksaveasfilename(parent=window, title="Guardar exportación", initialdir=destination,
            initialfile=Path(editor.json_path).stem + "." + kind, defaultextension="." + kind,
            filetypes=[(format_choice.get(), "*." + kind)])
        if not path:
            return
        try:
            if Path(path).suffix.lower() != "." + kind:
                raise ValueError("El nombre debe terminar en ." + kind)
            if getattr(editor, "audio_path", "") and Path(path).resolve() == Path(editor.audio_path).resolve():
                raise ValueError("La exportación no puede reemplazar el archivo original.")
            if Path(path).resolve() == Path(editor.json_path).resolve():
                raise ValueError("Elige otro nombre para la copia. Usa Guardar para actualizar el proyecto.")
            editor.sync_page_to_memory()
            text = render_export(editor.segments, kind, blocks=editor.display_blocks(),
                                 timestamps=bool(include_time.get()), speakers=bool(include_speaker.get()))
            atomic_write(path, text)
            editor.last_export_dir = Path(path).parent
            editor.lbl_status.configure(text="Exportación guardada", text_color="green")
            status.configure(text="Exportado: " + str(path), text_color="green")
            reveal.configure(state="normal", command=lambda: os.startfile(str(Path(path).parent)))
        except Exception as error:
            status.configure(text=str(error), text_color="red")
    ctk.CTkButton(window, text="Elegir destino y exportar…", command=export).pack(fill="x", padx=24, pady=8)
    reveal = ctk.CTkButton(window, text="Abrir carpeta de exportación", state="disabled", fg_color="transparent")
    reveal.pack(pady=4)
    update_options()
    window.after(100, window.lift)
