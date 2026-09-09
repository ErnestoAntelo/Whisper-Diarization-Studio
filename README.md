# 🎙️ Whisper Diarization Studio

![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)
![Platform](https://img.shields.io/badge/Platform-Windows%20(GPU%2FCPU)-blue)
![License](https://img.shields.io/badge/License-MIT-green)
![Language](https://img.shields.io/badge/Interface-Español%20🇪🇸-yellow)

**Created by [@ErnestoAntelo](https://github.com/ErnestoAntelo)** 👨‍💻

**A desktop application for transcribing and diarizing (speaker identification) audio files locally.**
Powered by **OpenAI Whisper** (transcription) and **Pyannote Audio** (diarization), wrapped in a modern GUI designed for heavy workloads.

> **⚠️ COMMUNITY NOTICE**: This software is a passion project and is **NOT perfect**. It was created to solve a specific problem (diarization on limited hardware) and may contain bugs. We encourage developers to fork, improve, and submit Pull Requests!

---

## 🌟 Introduction

### Uso rápido y perfil para RTX 4050 de 6 GB

- Abre `start.bat` y pulsa **Añadir audios…** para seleccionar archivos de cualquier carpeta. Quedan marcados automáticamente y no necesitas copiarlos a `input`.
- **Perfil portátil** selecciona Whisper `medium` y Community-1 con **GPU rápida**, en fases separadas. Community-1 usa un proceso independiente, lotes de ocho, cuDNN activado (sin búsqueda de algoritmos) y pausas de 30 ms entre lotes. **GPU compatible** conserva el perfil anterior sin cuDNN y con pausas mayores; es bastante más lento. **Diarización en CPU** permite elegir la alternativa sin CUDA.
- **Hablantes** permite indicar una cantidad conocida (por ejemplo, `2` para una entrevista); vacío mantiene la detección automática. El número se aplica a todos los audios seleccionados.
- El worker limita el cálculo CPU a dos hilos y al 6% mediante un Job Object de Windows. En GPU se limita el asignador de Torch al 45% de VRAM y se comprueban lecturas de NVIDIA cada dos segundos. A partir de 75 °C o 70 W se espacian más los lotes. A 78 °C u 80 W se **pausa entre lotes conservando el progreso en memoria**, y se reanuda automáticamente al bajar a 74 °C y 65 W. Una lectura ausente también pausa hasta recuperar telemetría. La interfaz muestra la pausa y permite cancelar. Son medidas conservadoras del programa, no límites eléctricos ni una garantía contra reinicios.
- **Reutilizar texto guardado** recupera el JSON sin cargar Whisper cuando es válido. Con token configurado vuelve a ejecutar la diarización y puede reemplazar los nombres de hablantes editados. Para revisar un trabajo terminado, usa **Abrir transcripción…**.
- **Abrir transcripción…** abre directamente el resultado si hay un único audio seleccionado que ya tenga JSON. También permite elegir el audio original o un JSON; si eliges JSON, después seleccionas su audio. **Ver resultados** abre la carpeta de salida.
- La pantalla empieza con una lista vacía. **Añadir carpeta…** agrega sus audios a la selección; **Vaciar lista** solo quita la selección de la pantalla, no borra archivos.
- El editor agrupa las frases consecutivas del mismo hablante y separa las pausas de más de tres segundos. **Separar todo** muestra todas las frases; **Editar frases** separa solo un bloque para corregir su texto. **Agrupar por hablante** vuelve a la lectura por párrafos. El JSON conserva las frases y sus tiempos originales; al guardar, el TXT refleja la vista elegida.
- **Ctrl+O** abre el selector de audios y **Ctrl+S** guarda desde el editor. Al iniciar un trabajo se recuerdan la última carpeta de audio y el destino de resultados.

Equipo comprobado: Intel i9-13980HX, aproximadamente 64 GB de RAM, RTX 4050 Laptop de 6 GB, driver NVIDIA 610.88, Python 3.11.9 y FFmpeg 7.0.1. **GPU rápida completó la diarización del audio de 22:40 en 83,81 s**, incluyendo el arranque del worker (72,30 s de inferencia). Es 6,94 veces más rápido que los 581,64 s del perfil compatible. Los 320 turnos de diarización coinciden exactamente entre ambos resultados. Máximos muestreados de la prueba rápida: **68 °C / 69,73 W**, 436,4 MB de asignación CUDA de Torch y 1.729,7 MB de RAM del worker y sus hijos. Se conservan las 326 frases y sus tiempos; dos hablantes y una frase sin asignar. Se reutilizó el texto ya generado por Whisper. La primera ruta antigua sufrió un reinicio; la nueva prueba no demuestra que su causa esté reparada. Véase [diagnóstico y validación](docs/DIAGNOSTICO_Y_MODELOS.md).

La identificación de hablantes usa ahora **`pyannote/speaker-diarization-community-1` con `pyannote.audio==4.0.7`** y su salida de diarización exclusiva para asignar el texto. Se instala en `.venv-diarization` (CPU) y `.venv-diarization-gpu` (CUDA 12.8), con Torch/torchaudio 2.8.0 y TorchCodec 0.7.0. El audio se decodifica mediante FFmpeg y se entrega al modelo en memoria; no necesita las DLL de decodificación de TorchCodec. Whisper conserva su entorno `.venv` con Torch 2.5.1 CUDA. No se han cambiado drivers, BIOS, ventiladores ni ajustes eléctricos.

`start.bat` prepara los entornos cuando faltan; `instalar_diarizacion.bat cpu` y `instalar_diarizacion.bat gpu` permiten repararlos. Los tokens se entregan al proceso por una tubería, no por argumentos de consola. La telemetría de Pyannote/Hugging Face está desactivada en ese proceso.

**Cancelar** detiene el proceso de diarización y conserva el texto previo. Si aún está transcribiendo, Whisper termina primero el archivo actual. La app vigila la RAM del proceso y sus hijos, lo detiene si supera 4 GB y aplica un tiempo máximo de dos horas. El límite de memoria se comprueba periódicamente, no equivale a una reserva estricta. Solo se admite un worker Community-1 simultáneo.

Whisper estima unos 5 GB para `medium`, 6 GB para `turbo` y 10 GB para `large`; por eso el perfil usa `medium` para dejar algo de margen. Son estimaciones, no una garantía de memoria máxima. Referencias: [Whisper](https://github.com/openai/whisper), [versiones oficiales de PyTorch](https://docs.pytorch.org/get-started/previous-versions/).

Pruebas de regresión sin descargar modelos: `.venv\Scripts\python.exe -X utf8 -m unittest discover -s tests -v`.

### The Problem
Transcribing long meetings (1-2 hours) with highly accurate Speaker Identification (Diarization) is computationally expensive.
- Cloud services are expensive and have privacy concerns.
- Local scripts often crash due to **VRAM OOM (Out of Memory)** or **Thermal Throttling** (Laptop Overheating).

### The Solution: Whisper Diarization Studio
This application was engineered to handle these specific challenges on consumer hardware (e.g., RTX 3050/4050 Laptops).
*   **Resource controls:** Separate inference processes, small batches, CPU limits and monitored GPU readings. Optional CPU diarization reduces GPU load; these measures do not guarantee protection against hardware shutdowns.
*   **♻️ Crash Recovery System:** If your PC shuts down mid-process, you don't lose the transcription. Use the "Resume" feature to skip the heavy lifting and continue from the saved transcription.
*   **✏️ Batch Editor:** A built-in GUI to review audio segments, correct text, and mass-rename speakers (e.g., "SPEAKER_00" -> "Juan") with one click.

**🇪🇸 Native Spanish Interface**: The entire application (logs, buttons, error messages) is in Spanish.

---

## 🚀 Step-by-Step User Guide ("For Dummies")

### 📂 Step 1: Prepare your Files
Keep your audio files in their current folder. Accepted formats: `.mp3`, `.wav`, `.m4a`, `.ogg`, `.flac`, `.opus`.

### 🖥️ Step 2: Open the App
1.  **Double-click `start.bat`**.
2.  The script will automatically set up the environment (installing Python dependencies if needed) and launch the app.
3.  The interface will open.
4.  Click **Añadir audios…** to select files, or **Añadir carpeta…** to add a folder. Added files are selected automatically.

### ⚙️ Step 3: Configure & Run
1.  **Paste Token**: Paste your HuggingFace Token in the "HuggingFace Token" box.
2.  **Choose Strategy**:
    *   **Default**: Whisper and Community-1 use GPU in separate phases. Community-1 uses small batches and a monitored compatibility profile.
    *   **Diarización en CPU** selects the slower CPU alternative.
    *   **Resume**: Check **Reutilizar texto guardado** to recover a saved transcription and run speaker identification again.
    *   **Review**: Use **Abrir transcripción…** to edit an existing result without processing it again.
3.  Click **Transcribir e identificar hablantes**. Progress appears in the log; **Cancelar** stops diarization.

### ✏️ Step 4: The Editor (Magic Time)
When processing finishes, the specific Editor window works.
1.  **Select & Play**: Click `▶` to hear who is speaking.
2.  **Identify**: "Ah, SPEAKER_01 is Juan!".
3.  **Rename**:
    *   Type "Juan" in the name box of *any* SPEAKER_01 row.
    *   **Click the Lightning Bolt (⚡)** button next to it.
    *   **Magic**: The app will search for ALL instances of "SPEAKER_01" and rename them to "Juan" instantly.
4.  **Save**: Click "GUARDAR CAMBIOS".
    *   This updates the `.json` (project) and the `.txt` (readable transcript) in the `output` folder.

---

## �️ Installation Guide (Technical)

### Prerequisites
1.  **Python 3.10+**: [Download Python](https://www.python.org/downloads/).
2.  **FFmpeg**: Necessary tool for audio.
    *   Download [FFmpeg Essentials](https://www.gyan.dev/ffmpeg/builds/).
    *   Extract and add output `bin` folder to Windows PATH.

### 1. Clone & Run
```bash
git clone https://github.com/ErnestoAntelo/Whisper-Diarization-Studio.git
cd Whisper-Diarization-Studio

# Run the auto-installer
start.bat
```

*   The script executes all necessary commands: creating virtualenv, installing generic dependencies, and installing CUDA-enabled PyTorch packages (the NVIDIA driver must already be installed).

### 2. Manual Installation (Only if start.bat fails)
If you prefer to manage your own environment:
```bash
python -m venv .venv
.venv\Scripts\activate
# Install CUDA Torch (Critical for GPU)
pip install torch==2.5.1 torchaudio==2.5.1 --index-url https://download.pytorch.org/whl/cu121
pip install -r requirements.txt
instalar_diarizacion.bat
instalar_diarizacion.bat gpu
python src/gui_app.py
```

### 3. Pyannote Token
Go to [HuggingFace Settings](https://huggingface.co/settings/tokens) and create a token. You must accept use terms for `pyannote/speaker-diarization-community-1`.

### 🛡️ Privacy & Security Note
*   The token is saved in plain text in local `config.json`, which is excluded from Git. Do not share this file.
*   Processing happens locally. Initial model downloads contact Hugging Face and use the token for access; the audio is not uploaded by this pipeline.

---

## 💊 Troubleshooting & Known Issues

1.  **Unexpected shutdown or restart**:
    *   Windows Event 41 alone does not identify the cause. Power, thermal protection and driver or hardware faults require separate diagnosis.
    *   Select **Diarización en CPU** for the alternative without CUDA. GPU monitoring reduces exposure but does not prove a hardware fault has been repaired. See [local findings](docs/DIAGNOSTICO_Y_MODELOS.md).

2.  **"SPEAKER_00" for everyone**:
    *   If diarization fails to load, check token permissions and the Community-1 model terms. If it completes but merges speakers, review the audio and try the known speaker count.

3.  **"y y y y" hallucination**:
    *   `condition_on_previous_text=False` reduces repetition, but does not eliminate all transcription hallucinations.

---

## 🤝 Contributing

**This project is Open Source.** We need your help to make it perfect!
*   Found a bug? Open an Issue.
*   Can code? Submit a Pull Request.
*   Ideas: Add `.srt` export, improve UI aesthetics, add English support.

## 👨‍💻 Founder / CREADOR

**Ernesto Antelo** (@ErnestoAntelo)
*Desarrollado con el objetivo de hacer accesible la IA de audio avanzada en hardware doméstico.*

---
*Built with ❤️ for stable, local AI processing.*
