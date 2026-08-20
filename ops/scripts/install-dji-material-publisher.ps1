[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$sourceScript = Join-Path $PSScriptRoot "publish-dji-materials.ps1"
if (-not (Test-Path -LiteralPath $sourceScript -PathType Leaf)) {
    throw "Publisher source script is missing: $sourceScript"
}

$installDirectory = Join-Path $env:LOCALAPPDATA "SmartBamboo\Tools"
$installedScript = Join-Path $installDirectory "publish-dji-materials.ps1"
$desktopDirectory = [Environment]::GetFolderPath("Desktop")
$launcherPath = Join-Path $desktopDirectory "发布大疆素材到智慧竹山.cmd"
$shortcutPath = Join-Path $desktopDirectory "发布大疆素材到智慧竹山.lnk"

New-Item -ItemType Directory -Path $installDirectory -Force | Out-Null
Copy-Item -LiteralPath $sourceScript -Destination $installedScript -Force

# Keep the batch file ASCII-only so cmd.exe never has to decode a Chinese
# repository path. The installed tool path is stable and contains ASCII only.
$launcher = @'
@echo off
chcp 65001 >nul
title Smart Bamboo DJI Material Publisher
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%LOCALAPPDATA%\SmartBamboo\Tools\publish-dji-materials.ps1" %*
set "PUBLISH_EXIT_CODE=%ERRORLEVEL%"
echo.
if not "%PUBLISH_EXIT_CODE%"=="0" echo Publish did not complete. Review the error above.
if "%PUBLISH_EXIT_CODE%"=="0" echo Publish workflow finished.
pause
exit /b %PUBLISH_EXIT_CODE%
'@
[IO.File]::WriteAllText($launcherPath, $launcher, [Text.Encoding]::ASCII)

$powershellPath = Join-Path $PSHOME "powershell.exe"
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $powershellPath
$shortcut.Arguments = "-NoLogo -NoProfile -ExecutionPolicy Bypass -File `"$installedScript`""
$shortcut.WorkingDirectory = $installDirectory
$shortcut.IconLocation = "$powershellPath,0"
$shortcut.Description = "发布 DJI 3D Tiles 素材到智慧竹山平台"
$shortcut.Save()

Write-Host "DJI material publisher installed." -ForegroundColor Green
Write-Host "CMD: $launcherPath"
Write-Host "Shortcut: $shortcutPath"
Write-Host "Tool: $installedScript"
