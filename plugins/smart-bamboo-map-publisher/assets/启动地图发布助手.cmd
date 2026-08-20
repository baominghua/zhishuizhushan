@echo off
chcp 65001 >nul
set "ASSISTANT_HOME=%~dp0"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -STA -File "%ASSISTANT_HOME%scripts\SmartBambooMapPublisher.ps1"
if errorlevel 1 pause
