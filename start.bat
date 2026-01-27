@echo off
setlocal
set VENV_DIR=.venv

:: 1. Check if environment exists
if exist "%VENV_DIR%" goto :START_APP

:: 2. Setup (Only runs if .venv is missing)
echo [INFO] Primera ejecucion detectada. Configurando entorno optimizado...

echo [1/4] Creando entorno virtual...
python -m venv %VENV_DIR%

echo [2/4] Actualizando gestor de paquetes (PIP)...
%VENV_DIR%\Scripts\python.exe -m pip install --upgrade pip

echo [3/4] Instalando Motor AI con Soporte GPU (NVIDIA CUDA)...
echo        * Esto puede tardar unos minutos...
%VENV_DIR%\Scripts\pip install torch==2.0.1+cu118 torchaudio==2.0.2+cu118 --index-url https://download.pytorch.org/whl/cu118

echo [4/4] Instalando resto de dependencias...
%VENV_DIR%\Scripts\pip install -r requirements.txt

echo [EXITO] Instalacion completada.

:: 3. Launch App
:START_APP
echo [INFO] Entorno verificado. Iniciando...
echo.
%VENV_DIR%\Scripts\python src/gui_app.py

:: 4. Error handling
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] La aplicacion se cerro con error.
    echo [TIP] Si tienes problemas, borra la carpeta ".venv" y ejecuta este script de nuevo.
    pause
)
