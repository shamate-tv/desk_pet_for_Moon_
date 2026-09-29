@echo off
rem Launch with a console window (for troubleshooting)
cd /d "%~dp0"
python "pet\main.py" %*
pause
