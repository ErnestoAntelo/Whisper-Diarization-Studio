@echo off
setlocal
set PYTHONUTF8=1
cd /d "%~dp0"
set DIA_ENV=.venv-diarization
set DIA_INDEX=cpu
if /i "%~1"=="gpu" (
    set DIA_ENV=.venv-diarization-gpu
    set DIA_INDEX=cu128
)
if exist "%DIA_ENV%\Scripts\python.exe" goto :INSTALL
if exist ".venv\Scripts\python.exe" (
    .venv\Scripts\python.exe -m venv "%DIA_ENV%"
) else (
    python -m venv "%DIA_ENV%"
)
if errorlevel 1 goto :FAIL
:INSTALL
echo Instalando Community-1 en un entorno separado: %DIA_INDEX%...
%DIA_ENV%\Scripts\python.exe -m pip install torch==2.8.0 torchaudio==2.8.0 --index-url https://download.pytorch.org/whl/%DIA_INDEX%
if errorlevel 1 goto :FAIL
%DIA_ENV%\Scripts\python.exe -m pip install -r requirements-diarization.txt
if errorlevel 1 goto :FAIL
%DIA_ENV%\Scripts\python.exe -m pip check
if errorlevel 1 goto :FAIL
%DIA_ENV%\Scripts\python.exe -c "import torch; import importlib.metadata as m; assert m.version('pyannote.audio') == '4.0.7'; assert (torch.version.cuda is not None) == ('%DIA_INDEX%' != 'cpu')"
if errorlevel 1 goto :FAIL
echo Community-1 %DIA_INDEX% 4.0.7 > "%DIA_ENV%\.ready-community-4.0.7"
exit /b 0
:FAIL
echo No se completo la instalacion. El entorno anterior se conserva.
exit /b 1
