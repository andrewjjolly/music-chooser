@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Creating the project virtual environment...
    py -3.14 -m venv .venv
    if errorlevel 1 exit /b 1
)

if not exist ".venv\.music-chooser-installed" (
    echo Installing project dependencies...
    ".venv\Scripts\python.exe" -m pip install -e .
    if errorlevel 1 exit /b 1
    type nul > ".venv\.music-chooser-installed"
)

echo Starting Music Chooser at http://127.0.0.1:8000
".venv\Scripts\python.exe" -m music_chooser.main
