@echo off
REM Launcher for the 01V96i bridge on Windows: uses the project venv.
setlocal
set "HERE=%~dp0"
if not exist "%HERE%.venv\Scripts\python.exe" (
    echo No virtualenv at %HERE%.venv - see README # Setup 1>&2
    exit /b 1
)
"%HERE%.venv\Scripts\python.exe" "%HERE%main.py" %*
