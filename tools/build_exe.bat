@echo off
rem Repack release\MoonPet-vX.Y.Z.exe  (needs: pip install pyinstaller)
rem Version comes from VERSION in pet\main.py -- edit that one line before releasing.
rem NOTE: "python" on PATH may point to another (older) interpreter -> find 3.14 explicitly.
cd /d "%~dp0.."
set "PY=%LOCALAPPDATA%\Programs\Python\Python314\python.exe"
if not exist "%PY%" set "PY=py -3"

%PY% tools\make_version_file.py || goto :err
%PY% tools\bongo_bg.py || goto :err
set /p VER=<build\ver.txt
echo Building MoonPet-v%VER%.exe ...

%PY% -m PyInstaller --noconfirm --onefile --noconsole --name "MoonPet-v%VER%" ^
  --icon "%CD%\pet.ico" ^
  --version-file "%CD%\build\version_info.txt" ^
  --add-data "%CD%\skins;skins" ^
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
