@echo off
setlocal

set VENV_DIR=.venv

if not exist "%VENV_DIR%" (
    echo [INFO] Creando entorno virtual...
    python -m venv %VENV_DIR%
)

echo [INFO] Verificando dependencias (numpy 1.26 fixed)...
%VENV_DIR%\Scripts\pip install --upgrade pip
%VENV_DIR%\Scripts\pip install -r requirements.txt

:START_APP
echo [INFO] Iniciando App...
%VENV_DIR%\Scripts\python src/gui_app.py
if %errorlevel% neq 0 pause
