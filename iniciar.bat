@echo off
cd /d "%~dp0"
set "PYTHON_BIN=C:\Users\faturamento3\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"

if exist "%PYTHON_BIN%" (
    start "" "http://localhost:8765"
    "%PYTHON_BIN%" server.py
    exit /b
)

start "" "http://localhost:8765"
python server.py
