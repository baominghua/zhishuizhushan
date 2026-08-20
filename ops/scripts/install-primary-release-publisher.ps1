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
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%LOCALAPPDATA%\SmartBamboo\Tools\publish-primary-release.ps1" -IncludeImage %*
set "PUBLISH_EXIT_CODE=%ERRORLEVEL%"
echo.
if not "%PUBLISH_EXIT_CODE%"=="0" echo Release did not complete. Review the error above.
if "%PUBLISH_EXIT_CODE%"=="0" echo Release workflow finished.
pause
exit /b %PUBLISH_EXIT_CODE%
'@
[IO.File]::WriteAllText($launcherPath, $launcher, [Text.Encoding]::ASCII)

$powershellPath = Join-Path $PSHOME "powershell.exe"
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $powershellPath
$shortcut.Arguments = "-NoLogo -NoProfile -ExecutionPolicy Bypass -File `"$installedScript`" -IncludeImage"
$shortcut.WorkingDirectory = $installDirectory
$shortcut.IconLocation = "$powershellPath,0"
$shortcut.Description = "在本机构建镜像并直接上传发布智慧竹山平台"
$shortcut.Save()

Write-Host "Smart Bamboo direct release publisher installed." -ForegroundColor Green
Write-Host "CMD: $launcherPath"
Write-Host "Shortcut: $shortcutPath"
Write-Host "Repository: $repositoryRoot"
