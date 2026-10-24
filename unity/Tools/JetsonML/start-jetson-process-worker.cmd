@echo off
title Jetson Process Analysis Worker
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Start-ProcessWorker-Resolved.ps1"
if errorlevel 1 pause
