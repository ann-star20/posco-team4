@echo off
title Restart Jetson AOI with Current Phone IP
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Start-Aoi8500And8400.ps1" -Restart
pause
