@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>&1
if errorlevel 1 (
  echo Necesitas Python 3.11 o superior instalado en Windows.
  pause
  exit /b 1
)
py -m venv .venv
if errorlevel 1 goto fail
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements.txt "pyinstaller>=6,<7"
if errorlevel 1 goto fail
python -m PyInstaller --noconfirm --clean --windowed --name PokeVault --collect-all PySide6 --add-data "assets;assets" code\main.py
if errorlevel 1 goto fail
echo.
echo Ejecutable listo en dist\PokeVault\PokeVault.exe
explorer dist\PokeVault
pause
exit /b 0
:fail
echo Error al crear el ejecutable. Revisa los mensajes anteriores.
pause
exit /b 1
