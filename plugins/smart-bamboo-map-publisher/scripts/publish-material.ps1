[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$SourcePath,
    [Parameter(Mandatory)][ValidateSet("orthophoto", "dsm", "dtm", "tiles-b3dm", "tiles-pnts", "pointcloud-las", "dji-trajectory")][string]$Kind,
    [Parameter(Mandatory)][string]$ProjectName,
    [string]$VersionId = (Get-Date -Format "yyyyMMdd-HHmmss"),
    [Parameter(Mandatory)][string]$ServerHost,
    [string]$SshUser = "root",
    [ValidateRange(1, 65535)][int]$SshPort = 22,
    [Parameter(Mandatory)][string]$SshKeyPath,
    [string]$RemoteInbox = "/srv/smart-bamboo/data/remote-sensing/inbox",
    [string]$PlatformInbox = "/app/data/remote-sensing/inbox",
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Require-Command([string]$Name) {
    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if (-not $command) { throw "缺少命令 $Name，请在 Windows 可选功能中安装 OpenSSH 客户端。" }
    return $command.Source
}

function Invoke-Native([string]$FilePath, [string[]]$Arguments, [string]$FailureMessage) {
    # Windows PowerShell 5.1 converts native stderr into error records when the
    # caller redirects this script's error stream. SSH login banners therefore
    # used to become terminating NativeCommandError records even when ssh
    # exited successfully. Let the native process finish and trust its exit code.
    $previousErrorActionPreference = $ErrorActionPreference
    $nativeExitCode = $null
    try {
        $ErrorActionPreference = "Continue"
        & $FilePath @Arguments 2>&1 | ForEach-Object {
            $outputText = if ($_ -is [System.Management.Automation.ErrorRecord]) { [string]$_.Exception.Message } else { [string]$_ }
            if (-not [string]::IsNullOrWhiteSpace($outputText)) { Write-Output $outputText }
        }
        $nativeExitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    if ($null -eq $nativeExitCode -or $nativeExitCode -ne 0) { throw "$FailureMessage（退出码 $nativeExitCode）" }
}

function New-RemoteActivationScript(
    [string]$Stage,
    [string]$RemoteArchive,
    [string]$RemoteDestination,
    [string]$Backup,
    [string]$DatasetName,
    [string]$Kind
) {
    $requiredPath = "$Stage/$DatasetName"
    $required = if ($Kind -like "tiles-*") {
        "test -f '$requiredPath/tileset.json';"
    } elseif ($Kind -eq "dji-trajectory") {
        "find '$requiredPath' -type f \( -iname 'POS_*.csv' -o -iname '*_sbet.out' -o -iname '*_sbet.txt' -o -iname '*_smrmsg.out' -o -iname '*_smrmsg.txt' \) -print -quit | grep -q .;"
    } else {
        "find '$requiredPath' -type f \( -iname '*.las' -o -iname '*.laz' \) -print -quit | grep -q .;"
    }
    return "set -euo pipefail; stage='$Stage'; archive='$RemoteArchive'; destination='$RemoteDestination'; backup='$Backup'; mkdir -p `"`$stage`"; tar -xf `"`$archive`" -C `"`$stage`"; $required if [ -e `"`$destination`" ]; then mv `"`$destination`" `"`$backup`"; fi; mv `"`$stage/$DatasetName`" `"`$destination`"; rmdir `"`$stage`"; chmod -R a+rX `"`$destination`"; rm -f `"`$archive`""
}

function Assert-SafeName([string]$Value, [string]$Label) {
    if ($Value -notmatch '^[\p{L}\p{Nd}][\p{L}\p{Nd}._-]{0,63}$') {
        throw "$Label 只能包含中文、字母、数字、点、下划线或短横线，且最长 64 个字符。"
    }
}

function Assert-RemoteRoot([string]$Value, [string]$Label) {
    if ($Value -notmatch '^/[A-Za-z0-9._/-]+$' -or $Value.Contains('..')) { throw "$Label 不是安全的 Linux 绝对路径。" }
}

function Format-StorageSize([long]$Bytes) {
    if ($Bytes -ge 1GB) { return "{0:N2} GB" -f ($Bytes / 1GB) }
    if ($Bytes -ge 1MB) { return "{0:N1} MB" -f ($Bytes / 1MB) }
    return "{0:N0} KB" -f ($Bytes / 1KB)
}

function Get-DirectoryContentSize([System.IO.DirectoryInfo]$Directory) {
    $sum = (Get-ChildItem -LiteralPath $Directory.FullName -Recurse -File -ErrorAction Stop | Measure-Object -Property Length -Sum).Sum
    if ($null -eq $sum) { return [long]0 }
    return [long]$sum
}

function Get-ArchiveCacheRoot([System.IO.DirectoryInfo]$SourceDirectory) {
    if (-not $SourceDirectory.Parent) { throw "成果目录不能直接选择磁盘根目录。" }
    $cacheRoot = Join-Path $SourceDirectory.Parent.FullName ".smart-bamboo-publish-cache"
    New-Item -ItemType Directory -Path $cacheRoot -Force | Out-Null
    return [IO.Path]::GetFullPath($cacheRoot)
}

function Assert-ArchiveCacheSpace([string]$CacheRoot, [long]$ContentBytes) {
    $driveRoot = [IO.Path]::GetPathRoot([IO.Path]::GetFullPath($CacheRoot))
    if ([string]::IsNullOrWhiteSpace($driveRoot)) { throw "无法识别缓存目录所在磁盘：$CacheRoot" }
    try { $drive = [IO.DriveInfo]::new($driveRoot) } catch { throw "无法读取缓存磁盘空间：$driveRoot" }
    $reserveBytes = [long][Math]::Max([double](1GB), [Math]::Ceiling($ContentBytes * 0.05))
    if ($ContentBytes -gt ([long]::MaxValue - $reserveBytes)) { throw "成果过大，无法计算缓存空间需求。" }
    $requiredBytes = $ContentBytes + $reserveBytes
    if ($drive.AvailableFreeSpace -lt $requiredBytes) {
        throw "缓存磁盘 $driveRoot 空间不足：成果约 $(Format-StorageSize $ContentBytes)，至少需要 $(Format-StorageSize $requiredBytes)，当前可用 $(Format-StorageSize $drive.AvailableFreeSpace)。请释放空间或把素材移到空间充足的磁盘。"
    }
    Write-Host "本地缓存磁盘：$driveRoot（可用 $(Format-StorageSize $drive.AvailableFreeSpace)，预计需要 $(Format-StorageSize $requiredBytes)）"
}

function Remove-AbandonedArchiveCache([string]$CacheRoot) {
    foreach ($lockFile in @(Get-ChildItem -LiteralPath $CacheRoot -File -Filter "*.tar.lock" -ErrorAction SilentlyContinue)) {
        $ownerPid = 0
        $pidText = try { (Get-Content -LiteralPath $lockFile.FullName -Raw -ErrorAction Stop).Trim() } catch { "" }
        $hasOwner = [int]::TryParse($pidText, [ref]$ownerPid) -and $ownerPid -gt 0 -and [bool](Get-Process -Id $ownerPid -ErrorAction SilentlyContinue)
        if ($hasOwner) { continue }
        $archivePath = $lockFile.FullName.Substring(0, $lockFile.FullName.Length - ".lock".Length)
        if (Test-Path -LiteralPath $archivePath -PathType Leaf) { Remove-Item -LiteralPath $archivePath -Force }
        Remove-Item -LiteralPath $lockFile.FullName -Force
        Write-Host "已清理上次异常中断留下的缓存：$archivePath"
    }
}

Assert-SafeName $ProjectName "项目名"
Assert-SafeName $VersionId "发布批次"
Assert-RemoteRoot $RemoteInbox "服务器素材根目录"
Assert-RemoteRoot $PlatformInbox "平台路径根目录"
$source = Get-Item -LiteralPath $SourcePath -ErrorAction Stop
$keyPath = [Environment]::ExpandEnvironmentVariables($SshKeyPath)
if (-not (Test-Path -LiteralPath $keyPath -PathType Leaf)) { throw "SSH 私钥不存在：$keyPath" }

$ssh = Require-Command "ssh"
$target = "$SshUser@$ServerHost"
$sshCommon = @("-i", $keyPath, "-p", "$SshPort", "-o", "BatchMode=yes", "-o", "ServerAliveInterval=30", "-o", "ServerAliveCountMax=6", "-o", "StrictHostKeyChecking=accept-new")
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$stateCacheRoot = Join-Path $env:LOCALAPPDATA "SmartBamboo\MapPublisher\Cache"
New-Item -ItemType Directory -Path $stateCacheRoot -Force | Out-Null

if ($Kind -in @("orthophoto", "dsm", "dtm")) {
    if ($source.PSIsContainer -or $source.Extension -notin @(".tif", ".tiff")) { throw "二维成果必须是 TIF/TIFF 文件。" }
    $sftp = Require-Command "sftp"
    $remoteFileName = if ($Kind -eq "orthophoto") { "orthophoto.tif" } elseif ($Kind -eq "dsm") { "dsm.tif" } else { "dtm.tif" }
    $remoteDirectory = "$RemoteInbox/$ProjectName/$VersionId/geotiff"
    $remoteDestination = "$remoteDirectory/$remoteFileName"
    $remotePartial = "$remoteDestination.uploading"
    $platformPath = "$PlatformInbox/$ProjectName/$VersionId/geotiff/$remoteFileName"

    Write-Host "准备发布 $Kind：$($source.FullName)"
    Write-Host "目标路径：$platformPath"
    if (-not $DryRun) {
        $prepare = "set -eu; mkdir -p -- '$remoteDirectory' '$RemoteInbox/.releases/$ProjectName/$VersionId/geotiff'; if [ ! -e '$remotePartial' ]; then : > '$remotePartial'; fi"
        Invoke-Native $ssh ($sshCommon + @($target, $prepare)) "准备服务器目录失败"
        $batch = Join-Path $stateCacheRoot "sftp-$([Guid]::NewGuid().ToString('N')).txt"
        $escapedLocal = $source.FullName.Replace('"', '\"')
        $escapedRemote = $remotePartial.Replace('"', '\"')
        [IO.File]::WriteAllText($batch, "reput `"$escapedLocal`" `"$escapedRemote`"`n", [Text.UTF8Encoding]::new($false))
        try {
            Invoke-Native $sftp @("-b", $batch, "-i", $keyPath, "-P", "$SshPort", "-o", "ServerAliveInterval=30", "-o", "ServerAliveCountMax=6", "-o", "StrictHostKeyChecking=accept-new", $target) "SFTP 上传失败；重新发布同一项可续传"
        } finally {
            if (Test-Path -LiteralPath $batch) { Remove-Item -LiteralPath $batch -Force }
        }
        $hash = (Get-FileHash -LiteralPath $source.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        $backup = "$RemoteInbox/.releases/$ProjectName/$VersionId/geotiff/$remoteFileName-$timestamp"
        $finalize = "set -eu; test -f '$remotePartial'; remote_hash=`$(sha256sum '$remotePartial' | awk '{print `$1}'); test `"`$remote_hash`" = '$hash'; if [ -e '$remoteDestination' ]; then mv '$remoteDestination' '$backup'; fi; mv '$remotePartial' '$remoteDestination'; chmod a+r '$remoteDestination'"
        Invoke-Native $ssh ($sshCommon + @($target, $finalize)) "服务器校验或原子切换失败"
    }
} else {
    if (-not $source.PSIsContainer) { throw "三维或点云成果必须选择文件夹。" }
    $tar = Require-Command "tar"
    $scp = Require-Command "scp"
    $datasetName = $source.Name
    Assert-SafeName $datasetName "成果目录名"
    if ($Kind -like "tiles-*") {
        $tileset = Join-Path $source.FullName "tileset.json"
        if (-not (Test-Path -LiteralPath $tileset -PathType Leaf)) { throw "DJI 3D Tiles 目录缺少根 tileset.json。" }
        $expectedExtension = if ($Kind -eq "tiles-b3dm") { ".b3dm" } else { ".pnts" }
        if (-not (Get-ChildItem -LiteralPath $source.FullName -Recurse -File -Filter "*$expectedExtension" -ErrorAction SilentlyContinue | Select-Object -First 1)) {
            throw "目录中没有找到 $expectedExtension 瓦片。"
        }
    } elseif ($Kind -eq "dji-trajectory") {
        if (-not (Get-ChildItem -LiteralPath $source.FullName -Recurse -File -ErrorAction SilentlyContinue | Where-Object {
            $lowerName = $_.Name.ToLowerInvariant()
            $_.Extension -in @(".csv", ".out", ".txt") -and ($lowerName.StartsWith("pos_") -or $lowerName.Contains("_sbet") -or $lowerName.Contains("_smrmsg"))
        } | Select-Object -First 1)) { throw "轨迹目录中没有找到 DJI POS/SBET/SMRMSG 文件。" }
    } elseif (-not (Get-ChildItem -LiteralPath $source.FullName -Recurse -File -Include *.las,*.laz -ErrorAction SilentlyContinue | Select-Object -First 1)) {
        throw "点云目录中没有 LAS/LAZ 文件。"
    }
    $remoteDestination = "$RemoteInbox/$ProjectName/$VersionId/$datasetName"
    $platformPath = "$PlatformInbox/$ProjectName/$VersionId/$datasetName"
    $archiveName = "$ProjectName-$VersionId-$datasetName-$timestamp.tar"
    $archiveCacheRoot = Get-ArchiveCacheRoot $source
    Remove-AbandonedArchiveCache $archiveCacheRoot
    $archivePath = Join-Path $archiveCacheRoot $archiveName
    $archiveLockPath = "$archivePath.lock"
    $remoteArchive = "$RemoteInbox/.incoming/$archiveName"
    Write-Host "准备发布 $Kind：$($source.FullName)"
    Write-Host "目标路径：$platformPath"
    Write-Host "本地缓存：$archivePath"
    if (-not $DryRun) {
        $contentBytes = Get-DirectoryContentSize $source
        Assert-ArchiveCacheSpace $archiveCacheRoot $contentBytes
        try {
            "$PID" | Set-Content -LiteralPath $archiveLockPath -Encoding ASCII
            Invoke-Native $tar @("-cf", $archivePath, "-C", $source.Parent.FullName, $datasetName) "打包成果失败"
            $prepare = "set -eu; mkdir -p '$RemoteInbox/.incoming' '$RemoteInbox/.releases/$ProjectName/$VersionId' '$RemoteInbox/$ProjectName/$VersionId'"
            Invoke-Native $ssh ($sshCommon + @($target, $prepare)) "准备服务器目录失败"
            Invoke-Native $scp @("-i", $keyPath, "-P", "$SshPort", "-o", "ServerAliveInterval=30", "-o", "ServerAliveCountMax=6", "-o", "StrictHostKeyChecking=accept-new", $archivePath, "${target}:$remoteArchive") "上传成果包失败"
            $stage = "$RemoteInbox/.incoming/$ProjectName-$VersionId-$datasetName-$timestamp"
            $backup = "$RemoteInbox/.releases/$ProjectName/$VersionId/$datasetName-$timestamp"
            $remoteScript = New-RemoteActivationScript $stage $remoteArchive $remoteDestination $backup $datasetName $Kind
            $encoded = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($remoteScript))
            $execute = "script_path=`$(mktemp /tmp/smart-bamboo-map-XXXXXX.sh); printf '%s' '$encoded' | base64 -d > `"`$script_path`"; bash `"`$script_path`"; status=`$?; rm -f `"`$script_path`"; exit `$status"
            Invoke-Native $ssh ($sshCommon + @($target, $execute)) "服务器解包或原子切换失败"
        } finally {
            if (Test-Path -LiteralPath $archivePath) { Remove-Item -LiteralPath $archivePath -Force }
            if (Test-Path -LiteralPath $archiveLockPath) { Remove-Item -LiteralPath $archiveLockPath -Force }
        }
    }
}

$result = [ordered]@{ success = $true; kind = $Kind; source = $source.FullName; projectName = $ProjectName; versionId = $VersionId; platformPath = $platformPath; dryRun = [bool]$DryRun }
Write-Output "SMART_BAMBOO_RESULT=$($result | ConvertTo-Json -Compress)"
