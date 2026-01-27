@echo off
setlocal
set VENV_DIR=.venv

echo [WARN] Iniciando Limpieza PROFUNDA...
:: Try to delete, if fails (doesnt exist), continue
rmdir /s /q "%VENV_DIR%" 2>nul

echo [INFO] Creando entorno virtual nuevo...
python -m venv %VENV_DIR%

echo [INFO] Actualizando PIP al maximo...
%VENV_DIR%\Scripts\python.exe -m pip install --upgrade pip

echo [INFO] Instalando PyTorch con CUDA (GPU Support)...
%VENV_DIR%\Scripts\pip install torch==2.0.1+cu118 torchaudio==2.0.2+cu118 --index-url https://download.pytorch.org/whl/cu118

echo [INFO] Instalando versiones ESTABLES...
%VENV_DIR%\Scripts\pip install -r requirements.txt

echo.
echo [EXITO] Entorno reparado. Lanzando App...
%VENV_DIR%\Scripts\python src/gui_app.py
pause
