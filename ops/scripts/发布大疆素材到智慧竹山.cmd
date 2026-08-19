@echo off
chcp 65001 >nul
title 发布大疆素材到智慧竹山
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0publish-dji-materials.ps1"
echo.
if errorlevel 1 (
  echo 发布未完成，请查看上方错误。
) else (
  echo 发布流程已结束。
)
pause
