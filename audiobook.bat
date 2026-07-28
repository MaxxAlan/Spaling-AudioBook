@echo off
set "ROOT=%~dp0"
set "PYTHON_EXE=%ROOT%.venv\Scripts\python.exe"
set "PYTHONW_EXE=%ROOT%.venv\Scripts\pythonw.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"
if not exist "%PYTHONW_EXE%" set "PYTHONW_EXE=pythonw"
if /I "%~1"=="web" (
    rem Web UI is a background app; keep the terminal free for the user.
    start "" /b "%PYTHONW_EXE%" "%ROOT%audiobook.py" %*
    exit /b 0
)
"%PYTHON_EXE%" "%ROOT%audiobook.py" %*
