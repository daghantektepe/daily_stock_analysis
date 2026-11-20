@echo off
setlocal
set "ROOT=%~dp0"
set "VENV_PY=%ROOT%.venv\Scripts\python.exe"
set "LOCAL_VENV_PY=%USERPROFILE%\.dsa-venv\Scripts\python.exe"
set "PYTHON_BIN=python"

if exist "%VENV_PY%" (
    "%VENV_PY%" -c "import sys" >nul 2>nul
    if not errorlevel 1 (
        set "PYTHON_BIN=%VENV_PY%"
    )
)
if "%PYTHON_BIN%"=="python" if exist "%LOCAL_VENV_PY%" (
    "%LOCAL_VENV_PY%" -c "import sys" >nul 2>nul
    if not errorlevel 1 (
        set "PYTHON_BIN=%LOCAL_VENV_PY%"
    )
)

"%PYTHON_BIN%" "%ROOT%scripts\dsa_cli.py" %*
exit /b %ERRORLEVEL%
