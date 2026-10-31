@echo off
cd /d "%~dp0"
python run_desktop.py
if errorlevel 1 pause
