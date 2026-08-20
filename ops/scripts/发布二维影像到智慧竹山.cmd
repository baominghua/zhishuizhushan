@echo off
chcp 65001 >nul
title Smart Bamboo GeoTIFF Publisher
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0publish-geotiff-material.ps1" %*
set "PUBLISH_EXIT_CODE=%ERRORLEVEL%"
echo.
if not "%PUBLISH_EXIT_CODE%"=="0" echo Publish did not complete. Review the error above.
if "%PUBLISH_EXIT_CODE%"=="0" echo Publish workflow finished.
pause
exit /b %PUBLISH_EXIT_CODE%
