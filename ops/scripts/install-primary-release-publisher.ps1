[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$sourceScript = Join-Path $PSScriptRoot "publish-primary-release.ps1"
$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
if (-not (Test-Path -LiteralPath $sourceScript -PathType Leaf)) {
    throw "Release publisher source script is missing: $sourceScript"
}

$installDirectory = Join-Path $env:LOCALAPPDATA "SmartBamboo\Tools"
$installedScript = Join-Path $installDirectory "publish-primary-release.ps1"
$configPath = Join-Path $installDirectory "release-publisher.json"
$desktopDirectory = [Environment]::GetFolderPath("Desktop")
$launcherPath = Join-Path $desktopDirectory "本地直发智慧竹山平台.cmd"
$shortcutPath = Join-Path $desktopDirectory "本地直发智慧竹山平台.lnk"

New-Item -ItemType Directory -Path $installDirectory -Force | Out-Null
Copy-Item -LiteralPath $sourceScript -Destination $installedScript -Force
$configJson = @{ repository = $repositoryRoot } | ConvertTo-Json
[IO.File]::WriteAllText($configPath, $configJson, (New-Object Text.UTF8Encoding($true)))

$launcher = @'
@echo off
chcp 65001 >nul
title Smart Bamboo Direct Release Publisher
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%LOCALAPPDATA%\SmartBamboo\Tools\publish-primary-release.ps1" -ReuseProductionImage %*
set "PUBLISH_EXIT_CODE=%ERRORLEVEL%"
echo.
if not "%PUBLISH_EXIT_CODE%"=="0" echo Release did not complete. Review the error above.
if "%PUBLISH_EXIT_CODE%"=="0" echo Release workflow finished.
pause
exit /b %PUBLISH_EXIT_CODE%
'@
[IO.File]::WriteAllText($launcherPath, $launcher, [Text.Encoding]::ASCII)

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $env:ComSpec
$shortcut.Arguments = "/d /c `"`"$launcherPath`"`""
$shortcut.WorkingDirectory = $desktopDirectory
$shortcut.IconLocation = "$env:ComSpec,0"
$shortcut.Description = "复用生产依赖层，快速发布智慧竹山平台代码版本"
$shortcut.Save()

Write-Host "Smart Bamboo direct release publisher installed." -ForegroundColor Green
Write-Host "CMD: $launcherPath"
Write-Host "Shortcut: $shortcutPath"
Write-Host "Repository: $repositoryRoot"
