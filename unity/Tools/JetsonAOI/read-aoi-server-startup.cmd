@echo off
title Read AOI 8500 and 8400 Startup
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Read-AoiServerStartup.ps1"
pause
