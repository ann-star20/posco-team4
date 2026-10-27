@echo off
set "FAB_PYTHON=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if not exist "%FAB_PYTHON%" (
  echo Python runtime not found. Install Python 3.9 or later and run server.py.
  pause
  exit /b 1
)
"%FAB_PYTHON%" -u "%~dp0server.py"
pause
