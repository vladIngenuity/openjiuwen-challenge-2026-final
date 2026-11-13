@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0docker_check.ps1" %*
if errorlevel 1 pause
