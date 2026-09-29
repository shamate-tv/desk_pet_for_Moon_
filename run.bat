@echo off
rem Launch the desk pet without a console window
cd /d "%~dp0"
start "" pythonw "pet\main.py" %*
