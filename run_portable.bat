@echo off
setlocal

set VENV_DIR=.venv

if exist "%VENV_DIR%" goto :START_APP

echo [INFO] Creando entorno virtual...
python -m venv %VENV_DIR%

echo [INFO] Instalando dependencias (numpy 1.26 fixed)...
%VENV_DIR%\Scripts\pip install --upgrade pip
%VENV_DIR%\Scripts\pip install -r requirements.txt

:START_APP
echo [INFO] Iniciando App...
%VENV_DIR%\Scripts\python src/gui_app.py
if %errorlevel% neq 0 pause
