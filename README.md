# 🎙️ Whisper Diarization Studio

![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)
![Platform](https://img.shields.io/badge/Platform-Windows%20(GPU%2FCPU)-blue)
![License](https://img.shields.io/badge/License-MIT-green)
![Language](https://img.shields.io/badge/Interface-Español%20🇪🇸-yellow)

**Created by [@ErnestoAntelo](https://github.com/ErnestoAntelo)** 👨‍💻

**A professional, crash-proof desktop application for transcribing and diarizing (speaker identification) audio files locally.**  
Powered by **OpenAI Whisper** (transcription) and **Pyannote Audio** (diarization), wrapped in a modern GUI designed for heavy workloads.

> **⚠️ COMMUNITY NOTICE**: This software is a passion project and is **NOT perfect**. It was created to solve a specific problem (diarization on limited hardware) and may contain bugs. We encourage developers to fork, improve, and submit Pull Requests!

---

## 🌟 Introduction

### The Problem
Transcribing long meetings (1-2 hours) with highly accurate Speaker Identification (Diarization) is computationally expensive.
- Cloud services are expensive and have privacy concerns.
- Local scripts often crash due to **VRAM OOM (Out of Memory)** or **Thermal Throttling** (Laptop Overheating).

### The Solution: Whisper Diarization Studio
This application was engineered to handle these specific challenges on consumer hardware (e.g., RTX 3050/4050 Laptops).
*   **🛡️ Thermal Safe Mode:** A unique feature that splits the workload. It runs transcription on GPU but offloads the intensive Diarization to the CPU to prevent thermal shutdowns.
*   **♻️ Crash Recovery System:** If your PC shuts down mid-process, you don't lose the transcription. Use the "Resume" feature to skip the heavy lifting and finish the job instantly.
*   **✏️ Batch Editor:** A built-in GUI to review audio segments, correct text, and mass-rename speakers (e.g., "SPEAKER_00" -> "Juan") with one click.

**🇪🇸 Native Spanish Interface**: The entire application (logs, buttons, error messages) is in Spanish.

---

## 🚀 Step-by-Step User Guide ("For Dummies")

### 📂 Step 1: Prepare your Files
1.  Go to the `Whisper-Diarization-Studio` folder.
2.  Open the **`input`** folder.
3.  **Paste your audio files here**.
    *   **Accepted Formats**: `.mp3`, `.wav`, `.m4a`, `.ogg`, `.flac`, `.opus`.
    *   *Tip: You don't need to rename them. Just drop them in.*

### 🖥️ Step 2: Open the App
1.  **Double-click `start.bat`**.
2.  The script will automatically set up the environment (installing GPU drivers if needed) and launch the app.
3.  The interface will open.
4.  **IMPORTANT:** Look at the list "Archivos Detectados". **You must manually check ☑️ the box next to the files you want to transcribe.**

### ⚙️ Step 3: Configure & Run
1.  **Paste Token**: Paste your HuggingFace Token in the "HuggingFace Token" box.
2.  **Choose Strategy**:
    *   **Normal**: Just hit "TRANSCRIBIR". (Fastest, uses GPU).
    *   **Laptop Heating?**: Check **"🛡️ Modo Seguro (CPU Diarización)"**. Use this if your fans go crazy or PC shuts down.
    *   **Resume / Open Editor**: Check **"♻️ Reutilizar Transcripción"**.
        *   Use this if the app crashed previously.
        *   **OR if you want to re-open the Editor** for a file you already finished. It will skip processing and open the window immediately.
3.  **Click "INICIAR TRANSCRIPCIÓN"**.
    *   *Now wait. Review the "Matrix" logs to watch progress.*

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

*   The script executes all necessary commands: creating virtualenv, installing generic dependencies, and setting up **NVIDIA CUDA** drivers for GPU acceleration.

### 2. Manual Installation (Only if start.bat fails)
If you prefer to manage your own environment:
```bash
python -m venv .venv
.venv\Scripts\activate
# Install CUDA Torch (Critical for GPU)
pip install torch==2.0.1+cu118 torchaudio==2.0.2+cu118 --index-url https://download.pytorch.org/whl/cu118
pip install -r requirements.txt
python src/gui_app.py
```

### 3. Pyannote Token
Go to [HuggingFace Settings](https://huggingface.co/settings/tokens) and create a token. You must accept use terms for `pyannote/speaker-diarization-3.1`.

### 🛡️ Privacy & Security Note
*   **Your Token is Safe**: When you paste your token into the app, it is saved locally to a file named `config.json` on **your computer**.
*   **No Cloud Upload**: This file is excluded from git (`.gitignore`), so your token will **NEVER** be shared or uploaded to GitHub.
*   **Offline First**: All processing happens locally on your hardware.

---

## 💊 Troubleshooting & Known Issues

1.  **System Gridown/Shutdown**:
    *   *Cause*: GPU Overheating (>100W).
    *   *Solution*: Check **"Modo Seguro"** in the app.

2.  **"SPEAKER_00" for everyone**:
    *   *Cause*: Bad audio or Token issues.
    *   *Solution*: Check token permissions.

3.  **"y y y y" hallucination**:
    *   *Status*: **Fixed**. Includes `condition_on_previous_text=False` patch.

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
