@echo off
cd /d "%~dp0"
python -m lidar_agent.gui
if errorlevel 1 pause
