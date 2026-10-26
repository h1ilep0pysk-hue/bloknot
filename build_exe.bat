@echo off
cd /d "%~dp0"

echo [1/4] Creating virtual environment .venv (Python 3.11+ required)...
python -m venv .venv
if errorlevel 1 goto error
call .venv\Scripts\activate.bat

echo [2/4] Installing requirements and PyInstaller...
python -m pip install --upgrade pip
if errorlevel 1 goto error
pip install -r requirements.txt pyinstaller
if errorlevel 1 goto error

echo [3/4] Building Bloknot.exe...
pyinstaller --noconfirm --windowed --name Bloknot --icon bloknot\assets\icon\icon.ico --add-data "bloknot\assets;bloknot\assets" main.py
if errorlevel 1 goto error

echo [4/4] DONE: dist\Bloknot\Bloknot.exe
echo Copy the whole dist\Bloknot folder. The database will be created in dist\Bloknot\data.
pause
exit /b 0

:error
echo.
echo ERROR: the last step failed. Read the messages above.
pause
exit /b 1