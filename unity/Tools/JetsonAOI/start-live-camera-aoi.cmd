@echo off
title Jetson Live Camera Inspection
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Start-LiveCameraAOI.ps1"
pause
