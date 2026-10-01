@echo off
rem Launch with a console window (for troubleshooting).
rem NOTE: "python" on PATH may point to another (older) interpreter -> find 3.14 explicitly.
cd /d "%~dp0"
set "PY=%LOCALAPPDATA%\Programs\Python\Python314\python.exe"
if not exist "%PY%" set "PY=py -3"
"%PY%" "pet\main.py" %*
pause
