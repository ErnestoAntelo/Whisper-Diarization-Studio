@echo off
setlocal
set PYTHONUTF8=1
cd /d "%~dp0"
set VENV_DIR=.venv

:: 1. Check if environment exists
if exist "%VENV_DIR%" goto :START_APP

:: 2. Setup (Only runs if .venv is missing)
echo [INFO] Primera ejecucion detectada. Configurando entorno optimizado...

echo [1/4] Creando entorno virtual...
python -m venv %VENV_DIR%
if errorlevel 1 goto :INSTALL_ERROR

echo [2/4] Actualizando gestor de paquetes (PIP)...
%VENV_DIR%\Scripts\python.exe -m pip install --upgrade pip
if errorlevel 1 goto :INSTALL_ERROR

echo [3/4] Instalando Motor AI con Soporte GPU (NVIDIA CUDA)...
echo        * Esto puede tardar unos minutos...
%VENV_DIR%\Scripts\python.exe -m pip install torch==2.5.1 torchaudio==2.5.1 --index-url https://download.pytorch.org/whl/cu121
if errorlevel 1 goto :INSTALL_ERROR

echo [4/4] Instalando resto de dependencias...
%VENV_DIR%\Scripts\pip install -r requirements.txt
if errorlevel 1 goto :INSTALL_ERROR

echo [EXITO] Instalacion completada.

:: 3. Launch App
:START_APP
if not exist ".venv-diarization\.ready-community-4.0.7" (
    call instalar_diarizacion.bat
    if errorlevel 1 goto :INSTALL_ERROR
)
if not exist ".venv-diarization-gpu\.ready-community-4.0.7" (
    call instalar_diarizacion.bat gpu
    if errorlevel 1 goto :INSTALL_ERROR
)
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
exit /b

:INSTALL_ERROR
echo [ERROR] No se pudo completar la instalacion. Revisa el error anterior.
pause
exit /b 1
