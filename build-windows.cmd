@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    py -3 -m venv .venv
    if errorlevel 1 exit /b 1
)
".venv\Scripts\python.exe" -m pip install -r requirements-build.txt
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" -m PyInstaller --clean --noconfirm "Cockpit Playlist Editor.spec"
if errorlevel 1 exit /b 1
echo Built: "%~dp0dist\Cockpit Playlist Editor.exe"
