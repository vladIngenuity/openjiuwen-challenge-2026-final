@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0probe.ps1" %*
if errorlevel 1 pause
