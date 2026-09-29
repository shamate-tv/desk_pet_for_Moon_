@echo off
rem Repack release\MoonPet-vX.Y.Z.exe  (needs: pip install pyinstaller)
rem Version comes from VERSION in pet\main.py -- edit that one line before releasing.
cd /d "%~dp0.."

python tools\make_version_file.py || goto :err
python tools\make_icon.py || goto :err
set /p VER=<build\ver.txt
echo Building MoonPet-v%VER%.exe ...

python -m PyInstaller --noconfirm --onefile --noconsole --name "MoonPet-v%VER%" ^
  --icon "%CD%\pet.ico" ^
  --version-file "%CD%\build\version_info.txt" ^
  --add-data "%CD%\assets;assets" ^
  --distpath "%CD%\release" ^
  --workpath "%CD%\build\pyi" ^
  --specpath "%CD%\build" ^
  "%CD%\pet\main.py" || goto :err

echo.
echo done: release\MoonPet-v%VER%.exe
echo (upload this file to the GitHub Release with tag v%VER%)
pause
exit /b 0

:err
echo.
echo BUILD FAILED
pause
exit /b 1
