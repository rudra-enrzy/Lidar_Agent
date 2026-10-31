@echo off
rem Builds dist\LineClearanceAgent\LineClearanceAgent.exe (a folder: zip it and send it, or run it from anywhere writable).
cd /d "%~dp0"
python -m pip install -r requirements.txt -r requirements-desktop.txt -r requirements-build.txt || goto :err
python -m PyInstaller --noconfirm --clean --windowed --name LineClearanceAgent ^
  --icon lidar_agent\assets\logo.ico --contents-directory . ^
  --add-data "lidar_agent\app.html;lidar_agent" --add-data "lidar_agent\orb.js;lidar_agent" ^
  --add-data "lidar_agent\assets;lidar_agent\assets" --add-data "lidar_agent\vendor;lidar_agent\vendor" ^
  --add-data "potree_viewer;potree_viewer" --add-data "config.json;." ^
  --collect-all laspy --collect-all lazrs --collect-submodules scipy --collect-all webview ^
  --exclude-module matplotlib --exclude-module tkinter.test ^
  run_desktop.py || goto :err
if exist tools xcopy /E /I /Y tools dist\LineClearanceAgent\tools >nul
if exist config.local.json copy /Y config.local.json dist\LineClearanceAgent\ >nul
echo.
echo Done: dist\LineClearanceAgent\LineClearanceAgent.exe
echo PotreeConverter: put PotreeConverter.exe in dist\LineClearanceAgent\tools\PotreeConverter\ (or set "potree_converter" in config.local.json).
goto :eof
:err
echo Build failed - see the messages above.
exit /b 1
