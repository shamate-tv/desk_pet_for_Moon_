@echo off
rem Launch the desk pet without a console window.
rem NOTE: "python" on PATH may point to another (older) interpreter, so we look
rem for the 3.14 install explicitly and only fall back to PATH as a last resort.
cd /d "%~dp0"
set "PYW=%LOCALAPPDATA%\Programs\Python\Python314\pythonw.exe"
if exist "%PYW%" ( start "" "%PYW%" "pet\main.py" %* & exit /b 0 )
where py >nul 2>nul && ( start "" py -3 "pet\main.py" %* & exit /b 0 )
start "" pythonw "pet\main.py" %*
