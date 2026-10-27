@echo off
title Jetson AOI Connection Check
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Probe-JetsonAOI.ps1"
pause
