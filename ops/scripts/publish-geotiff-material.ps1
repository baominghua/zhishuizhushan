[CmdletBinding()]
param(
    [string]$SourceRoot = "D:\拷贝任务",
    [string]$SourcePath = "",
    [string]$ProjectName = "",
    [ValidateSet("auto", "orthophoto", "dsm")]
    [string]$AssetType = "auto",
    [string]$ServerHost = "36.140.138.117",
    [string]$SshUser = "root",
    [ValidateRange(1, 65535)]
    [int]$SshPort = 22,
    [string]$RemoteInbox = "/srv/smart-bamboo/data/remote-sensing/inbox",
    [string]$PlatformBaseUrl = "https://36.140.138.117:18081",
    [switch]$SkipOpenBrowser,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Require-Command {
    param([Parameter(Mandatory)][string]$Name)
    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if (-not $command) { throw "缺少命令 $Name。请先安装 Windows OpenSSH 客户端。" }
    return $command.Source
}

function Test-SafeName {
    param([Parameter(Mandatory)][string]$Value, [Parameter(Mandatory)][string]$Label)
    if ($Value -notmatch '^[\p{L}\p{Nd}][\p{L}\p{Nd}._-]{0,63}$') {
        throw "$Label 只能包含中文、字母、数字、点、下划线或短横线，且不能以点开头。"
    }
}

function Invoke-Native {
    param(
        [Parameter(Mandatory)][string]$FilePath,
        [Parameter(Mandatory)][AllowEmptyString()][string[]]$Arguments,
        [Parameter(Mandatory)][string]$FailureMessage
    )
    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$FailureMessage（退出码 $LASTEXITCODE）" }
}

function Find-VisibleLightGeoTiffs {
    param([Parameter(Mandatory)][string]$Root)
    $rootDirectory = Get-Item -LiteralPath $Root -ErrorAction Stop
    if (-not $rootDirectory.PSIsContainer) { throw "素材根目录不是文件夹：$Root" }
    return @(Get-ChildItem -LiteralPath $rootDirectory.FullName -Recurse -File -ErrorAction SilentlyContinue |
        Where-Object {
            $_.Directory.Name -eq "map" -and
            $_.Name -in @("result.tif", "dsm.tif") -and
            ($_.FullName -match '可见光' -or $_.FullName -match '二维') -and
            $_.Length -gt 1MB
        } |
        Sort-Object FullName)
}

$ssh = Require-Command -Name "ssh"
$sftp = Require-Command -Name "sftp"

if (-not $SourcePath) {
    Write-Host "正在查找可见光二维 GeoTIFF……" -ForegroundColor Cyan
    $datasets = @(Find-VisibleLightGeoTiffs -Root $SourceRoot)
    if ($datasets.Count -eq 0) { throw "在 $SourceRoot 中没有找到可见光/二维 map\result.tif 或 map\dsm.tif。" }
    for ($index = 0; $index -lt $datasets.Count; $index += 1) {
        $kind = if ($datasets[$index].Name -ieq "dsm.tif") { "DSM" } else { "正射影像" }
        Write-Host ("[{0}] {1} / {2} / {3:N2} GB`n    {4}" -f ($index + 1), $datasets[$index].Directory.Parent.Name, $kind, ($datasets[$index].Length / 1GB), $datasets[$index].FullName)
    }
    $selectionText = Read-Host "输入要发布的序号"
    $selection = 0
    if (-not [int]::TryParse($selectionText, [ref]$selection) -or $selection -lt 1 -or $selection -gt $datasets.Count) {
        throw "选择的序号无效。"
    }
    $sourceFile = $datasets[$selection - 1]
} else {
    $sourceFile = Get-Item -LiteralPath $SourcePath -ErrorAction Stop
    if ($sourceFile.PSIsContainer -or $sourceFile.Extension -notin @(".tif", ".tiff")) {
        throw "SourcePath 必须是 GeoTIFF 文件。"
    }
}

if (-not $ProjectName) {
    $defaultProjectName = if ($sourceFile.Directory.Name -eq "map" -and $sourceFile.Directory.Parent) { $sourceFile.Directory.Parent.Name } else { $sourceFile.Directory.Name }
    $enteredProjectName = Read-Host "项目目录名（直接回车使用 $defaultProjectName）"
    $ProjectName = if ($enteredProjectName.Trim()) { $enteredProjectName.Trim() } else { $defaultProjectName }
}
Test-SafeName -Value $ProjectName -Label "项目目录名"

if ($AssetType -eq "auto") {
    $AssetType = if ($sourceFile.Name -match '^dsm') { "dsm" } else { "orthophoto" }
}
$remoteFileName = if ($AssetType -eq "dsm") { "dsm.tif" } else { "orthophoto.tif" }
$target = "$SshUser@$ServerHost"
$sshDirectory = Join-Path ([Environment]::GetFolderPath("UserProfile")) ".ssh"
$materialKeyPath = Join-Path $sshDirectory "smart_bamboo_publish_ed25519"
$releaseKeyPath = Join-Path $sshDirectory "smart_bamboo_release_ed25519"
$keyPath = if (Test-Path -LiteralPath $materialKeyPath -PathType Leaf) { $materialKeyPath } elseif (Test-Path -LiteralPath $releaseKeyPath -PathType Leaf) { $releaseKeyPath } else { throw "未找到智慧竹山发布 SSH 密钥。" }
$sshCommon = @("-i", $keyPath, "-p", "$SshPort", "-o", "BatchMode=yes", "-o", "ServerAliveInterval=30", "-o", "ServerAliveCountMax=6", "-o", "StrictHostKeyChecking=accept-new")
$remoteDirectory = "$RemoteInbox/$ProjectName/geotiff"
$remoteDestination = "$remoteDirectory/$remoteFileName"
$remotePartial = "$remoteDestination.uploading"
$platformPath = "/app/data/remote-sensing/inbox/$ProjectName/geotiff/$remoteFileName"

Write-Host ""
Write-Host "二维成果发布计划" -ForegroundColor Cyan
Write-Host "  类型：$(if ($AssetType -eq 'dsm') { 'DSM' } else { '正射影像' })"
Write-Host "  本地：$($sourceFile.FullName)"
Write-Host "  大小：$([Math]::Round($sourceFile.Length / 1GB, 2)) GB"
Write-Host "  服务器：$remoteDestination"
Write-Host "  平台路径：$platformPath"
Write-Host "  传输：SFTP 断点续传；中断后重新运行同一项即可继续"

if ($DryRun) {
    Write-Host "DryRun 完成，未连接服务器。" -ForegroundColor Yellow
    return
}

Invoke-Native -FilePath $ssh -Arguments @($sshCommon + @($target, "mkdir -p '$remoteDirectory' '$RemoteInbox/.releases/$ProjectName/geotiff'")) -FailureMessage "准备服务器目录失败"

$cacheDirectory = Join-Path $SourceRoot ".smart-bamboo-publish-cache"
New-Item -ItemType Directory -Path $cacheDirectory -Force | Out-Null
$batchPath = Join-Path $cacheDirectory "geotiff-upload-$([Guid]::NewGuid().ToString('N')).txt"
$escapedLocalPath = $sourceFile.FullName.Replace('"', '\"')
$escapedRemotePath = $remotePartial.Replace('"', '\"')
[IO.File]::WriteAllText($batchPath, "reput `"$escapedLocalPath`" `"$escapedRemotePath`"`n", [Text.UTF8Encoding]::new($false))

try {
    Write-Host "`n[1/3] SFTP 断点续传中（会持续显示字节和百分比）……" -ForegroundColor Cyan
    Invoke-Native -FilePath $sftp -Arguments @("-b", $batchPath, "-i", $keyPath, "-P", "$SshPort", "-o", "ServerAliveInterval=30", "-o", "ServerAliveCountMax=6", "-o", "StrictHostKeyChecking=accept-new", $target) -FailureMessage "GeoTIFF 上传失败；远端临时文件已保留，重新运行可续传"
} finally {
    if (Test-Path -LiteralPath $batchPath -PathType Leaf) { Remove-Item -LiteralPath $batchPath -Force }
}

Write-Host "[2/3] 计算本地 SHA256……" -ForegroundColor Cyan
$localHash = (Get-FileHash -LiteralPath $sourceFile.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$remoteBackup = "$RemoteInbox/.releases/$ProjectName/geotiff/$remoteFileName-$timestamp"
$finalizeCommand = "set -eu; test -f '$remotePartial'; remote_hash=`$(sha256sum '$remotePartial' | awk '{print `$1}'); test `"`$remote_hash`" = '$localHash'; if [ -e '$remoteDestination' ]; then mv '$remoteDestination' '$remoteBackup'; fi; mv '$remotePartial' '$remoteDestination'; chmod a+r '$remoteDestination'; printf 'REMOTE_SIZE='; stat -c %s '$remoteDestination'; printf '\nREMOTE_SHA256='; sha256sum '$remoteDestination' | awk '{print `$1}'"
Write-Host "[3/3] 服务器校验并原子发布……" -ForegroundColor Cyan
Invoke-Native -FilePath $ssh -Arguments @($sshCommon + @($target, $finalizeCommand)) -FailureMessage "服务器校验失败；不会覆盖现有正式文件"

try {
    Set-Clipboard -Value $platformPath
    Write-Host "平台路径已复制到剪贴板。" -ForegroundColor Green
} catch {
    Write-Host "无法写入剪贴板，请手工复制平台路径。" -ForegroundColor Yellow
}

Write-Host "`n发布完成：$platformPath" -ForegroundColor Green
Write-Host "进入影像成果 → 上传并自动匹配 → GeoTIFF → 服务器/NAS 目录，粘贴路径后登记。"
if (-not $SkipOpenBrowser) { Start-Process "$PlatformBaseUrl/v2/drone/imagery-assets" }

