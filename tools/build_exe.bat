@echo off
rem Repack release\MoonPet.exe (needs: pip install pyinstaller)
cd /d "%~dp0.."
python tools\make_icon.py
python -m PyInstaller --noconfirm --onefile --noconsole --name MoonPet ^
  --icon "%~dp0..\pet.ico" ^
  --add-data "%~dp0..\assets;assets" ^
  --distpath "%~dp0..\release" ^
  --workpath "%~dp0..\build\pyi" ^
  --specpath "%~dp0..\build" ^
  "%~dp0..\pet\main.py"
echo.
echo done: release\MoonPet.exe
pause
