@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Agent-Service.ps1"
if errorlevel 1 pause
