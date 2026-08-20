[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$sourceScript = Join-Path $PSScriptRoot "publish-geotiff-material.ps1"
if (-not (Test-Path -LiteralPath $sourceScript -PathType Leaf)) {
    throw "Publisher source script is missing: $sourceScript"
}

$installDirectory = Join-Path $env:LOCALAPPDATA "SmartBamboo\Tools"
$installedScript = Join-Path $installDirectory "publish-geotiff-material.ps1"
$desktopDirectory = [Environment]::GetFolderPath("Desktop")
$launcherPath = Join-Path $desktopDirectory "发布二维影像到智慧竹山.cmd"
$shortcutPath = Join-Path $desktopDirectory "发布二维影像到智慧竹山.lnk"

New-Item -ItemType Directory -Path $installDirectory -Force | Out-Null
Copy-Item -LiteralPath $sourceScript -Destination $installedScript -Force

$launcher = @'
@echo off
chcp 65001 >nul
title Smart Bamboo GeoTIFF Publisher
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%LOCALAPPDATA%\SmartBamboo\Tools\publish-geotiff-material.ps1" %*
set "PUBLISH_EXIT_CODE=%ERRORLEVEL%"
echo.
if not "%PUBLISH_EXIT_CODE%"=="0" echo Publish did not complete. Review the error above.
if "%PUBLISH_EXIT_CODE%"=="0" echo Publish workflow finished.
pause
exit /b %PUBLISH_EXIT_CODE%
'@
[IO.File]::WriteAllText($launcherPath, $launcher, [Text.Encoding]::ASCII)

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $env:ComSpec
$shortcut.Arguments = "/d /c `"`"$launcherPath`"`""
$shortcut.WorkingDirectory = $desktopDirectory
$shortcut.IconLocation = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe,0"
$shortcut.Description = "断点续传二维 GeoTIFF 到智慧竹山平台"
$shortcut.Save()

Write-Host "GeoTIFF publisher installed." -ForegroundColor Green
Write-Host "CMD: $launcherPath"
Write-Host "Shortcut: $shortcutPath"
Write-Host "Tool: $installedScript"

