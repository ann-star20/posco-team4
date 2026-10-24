@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0test-direct-aoi.ps1"
if errorlevel 1 pause
