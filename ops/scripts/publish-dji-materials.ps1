[CmdletBinding()]
param(
    [string]$SourceRoot = "D:\拷贝任务",
    [string]$SourcePath = "",
    [string]$ProjectName = "",
    [string]$ServerHost = "36.140.138.117",
    [string]$SshUser = "root",
    [ValidateRange(1, 65535)]
    [int]$SshPort = 22,
    [string]$RemoteInbox = "/srv/smart-bamboo/data/remote-sensing/inbox",
    [string]$PlatformBaseUrl = "http://36.140.138.117",
    [switch]$InstallKey,
    [switch]$KeepArchive,
    [switch]$SkipOpenBrowser,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Require-Command {
    param([Parameter(Mandatory)][string]$Name)
    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if (-not $command) {
        throw "缺少命令 $Name。请先安装 Windows OpenSSH 客户端。"
    }
    return $command.Source
}

function Test-SafeName {
    param([Parameter(Mandatory)][string]$Value, [Parameter(Mandatory)][string]$Label)
    if ($Value -notmatch '^[\p{L}\p{Nd}][\p{L}\p{Nd}._-]{0,63}$') {
        throw "$Label 只能包含中文、字母、数字、点、下划线或短横线，且不能以点开头。"
    }
}

function Find-DjiTilesetDirectories {
    param([Parameter(Mandatory)][string]$Root)
    $rootDirectory = Get-Item -LiteralPath $Root -ErrorAction Stop
    if (-not $rootDirectory.PSIsContainer) {
        throw "素材根目录不是文件夹：$Root"
    }
    $queue = [System.Collections.Generic.Queue[System.IO.DirectoryInfo]]::new()
    $queue.Enqueue($rootDirectory)
    $result = [System.Collections.Generic.List[System.IO.DirectoryInfo]]::new()
    while ($queue.Count -gt 0) {
        $current = $queue.Dequeue()
        foreach ($directory in Get-ChildItem -LiteralPath $current.FullName -Directory -ErrorAction SilentlyContinue) {
            if ($directory.Name.StartsWith(".")) {
                continue
            }
            if ($directory.Name -in @("terra_pnts", "terra_b3dms") -and (Test-Path -LiteralPath (Join-Path $directory.FullName "tileset.json") -PathType Leaf)) {
                $result.Add($directory)
                continue
            }
            $queue.Enqueue($directory)
        }
    }
    return @($result | Sort-Object FullName)
}

function Get-DefaultProjectName {
    param([Parameter(Mandatory)][System.IO.DirectoryInfo]$Directory)
    if ($Directory.Parent -and $Directory.Parent.Name -eq "lidars" -and $Directory.Parent.Parent) {
        return $Directory.Parent.Parent.Name
    }
    if ($Directory.Parent) {
        return $Directory.Parent.Name
    }
    return "DJI项目"
}

function Invoke-Native {
    param(
        [Parameter(Mandatory)][string]$FilePath,
        [Parameter(Mandatory)][string[]]$Arguments,
        [Parameter(Mandatory)][string]$FailureMessage
    )
    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$FailureMessage（退出码 $LASTEXITCODE）"
    }
}

function Install-PublishSshKey {
    param(
        [Parameter(Mandatory)][string]$SshExecutable,
        [Parameter(Mandatory)][string]$KeyPath,
        [Parameter(Mandatory)][string]$Target
    )
    if (-not (Test-Path -LiteralPath "$KeyPath.pub" -PathType Leaf)) {
        $sshKeygen = Require-Command -Name "ssh-keygen"
        $keyDirectory = Split-Path -Parent $KeyPath
        New-Item -ItemType Directory -Path $keyDirectory -Force | Out-Null
        Invoke-Native -FilePath $sshKeygen -Arguments @("-t", "ed25519", "-f", $KeyPath, "-N", "", "-C", "smart-bamboo-material-publisher") -FailureMessage "创建素材发布专用 SSH 密钥失败"
    }
    $publicKey = [System.IO.File]::ReadAllText("$KeyPath.pub", [System.Text.Encoding]::UTF8).Trim()
    $publicKeyBase64 = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($publicKey + "`n"))
    $remoteCommand = "umask 077; mkdir -p ~/.ssh; touch ~/.ssh/authorized_keys; printf '%s' '$publicKeyBase64' | base64 -d >> ~/.ssh/authorized_keys; chmod 700 ~/.ssh; chmod 600 ~/.ssh/authorized_keys"
    Write-Host "首次安装专用密钥，请输入一次服务器密码。" -ForegroundColor Yellow
    Invoke-Native -FilePath $SshExecutable -Arguments @("-p", "$SshPort", "-o", "StrictHostKeyChecking=accept-new", $Target, $remoteCommand) -FailureMessage "安装服务器 SSH 密钥失败"
}

$ssh = Require-Command -Name "ssh"
$scp = Require-Command -Name "scp"
$tar = Require-Command -Name "tar"

if (-not $SourcePath) {
    Write-Host "正在查找可直接发布的 DJI 3D Tiles……" -ForegroundColor Cyan
    $datasets = @(Find-DjiTilesetDirectories -Root $SourceRoot)
    if ($datasets.Count -eq 0) {
        throw "在 $SourceRoot 中没有找到 terra_pnts 或 terra_b3dms 根目录。"
    }
    for ($index = 0; $index -lt $datasets.Count; $index += 1) {
        $defaultProject = Get-DefaultProjectName -Directory $datasets[$index]
        Write-Host ("[{0}] {1} / {2}`n    {3}" -f ($index + 1), $defaultProject, $datasets[$index].Name, $datasets[$index].FullName)
    }
    $selectionText = Read-Host "输入要发布的序号"
    $selection = 0
    if (-not [int]::TryParse($selectionText, [ref]$selection) -or $selection -lt 1 -or $selection -gt $datasets.Count) {
        throw "选择的序号无效。"
    }
    $sourceDirectory = $datasets[$selection - 1]
} else {
    $sourceDirectory = Get-Item -LiteralPath $SourcePath -ErrorAction Stop
    if (-not $sourceDirectory.PSIsContainer) {
        throw "SourcePath 必须是包含根 tileset.json 的目录。"
    }
}

$rootTileset = Join-Path $sourceDirectory.FullName "tileset.json"
if (-not (Test-Path -LiteralPath $rootTileset -PathType Leaf)) {
    throw "目录缺少根 tileset.json：$($sourceDirectory.FullName)"
}
if ($sourceDirectory.Name -notin @("terra_pnts", "terra_b3dms")) {
    throw "快捷发布目前只接受 terra_pnts 或 terra_b3dms。"
}

try {
    $tilesetDocument = Get-Content -LiteralPath $rootTileset -Raw -Encoding UTF8 | ConvertFrom-Json
} catch {
    throw "根 tileset.json 无法解析：$($_.Exception.Message)"
}
if (-not $tilesetDocument.root -or -not $tilesetDocument.asset.version) {
    throw "根 tileset.json 缺少 asset.version 或 root。"
}

$defaultProjectName = Get-DefaultProjectName -Directory $sourceDirectory
if (-not $ProjectName) {
    $enteredProjectName = Read-Host "项目目录名（直接回车使用 $defaultProjectName）"
    $ProjectName = if ($enteredProjectName.Trim()) { $enteredProjectName.Trim() } else { $defaultProjectName }
}
Test-SafeName -Value $ProjectName -Label "项目目录名"
Test-SafeName -Value $sourceDirectory.Name -Label "成果目录名"

$datasetName = $sourceDirectory.Name
$target = "$SshUser@$ServerHost"
$keyPath = Join-Path ([Environment]::GetFolderPath("UserProfile")) ".ssh\smart_bamboo_publish_ed25519"
$sshCommon = @("-i", $keyPath, "-p", "$SshPort", "-o", "ServerAliveInterval=30", "-o", "ServerAliveCountMax=6", "-o", "StrictHostKeyChecking=accept-new")
$scpCommon = @("-i", $keyPath, "-P", "$SshPort", "-o", "ServerAliveInterval=30", "-o", "ServerAliveCountMax=6", "-o", "StrictHostKeyChecking=accept-new")

if (-not $DryRun) {
    $keyWorks = $false
    if (Test-Path -LiteralPath $keyPath -PathType Leaf) {
        & $ssh @($sshCommon + @("-o", "BatchMode=yes", "-o", "ConnectTimeout=8", $target, "true"))
        $keyWorks = $LASTEXITCODE -eq 0
    }
    if (-not $keyWorks) {
        if (-not $InstallKey) {
            $answer = Read-Host "尚未配置免密素材发布。现在安装专用 SSH 密钥吗？[Y/n]"
            if ($answer.Trim() -and $answer.Trim().ToLowerInvariant() -ne "y") {
                throw "已取消。使用 -InstallKey 可安装专用密钥。"
            }
        }
        Install-PublishSshKey -SshExecutable $ssh -KeyPath $keyPath -Target $target
        Invoke-Native -FilePath $ssh -Arguments @($sshCommon + @("-o", "BatchMode=yes", $target, "true")) -FailureMessage "专用 SSH 密钥验证失败"
    }
}

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$cacheDirectory = Join-Path $SourceRoot ".smart-bamboo-publish-cache"
$archiveName = "$ProjectName-$datasetName-$timestamp.tar"
$archivePath = Join-Path $cacheDirectory $archiveName
$remoteArchive = "$RemoteInbox/.incoming/$archiveName"
$remoteDestination = "$RemoteInbox/$ProjectName/$datasetName"
$remoteBackup = "$RemoteInbox/.releases/$ProjectName/$datasetName-$timestamp"
$platformPath = "/app/data/remote-sensing/inbox/$ProjectName/$datasetName"

Write-Host ""
Write-Host "发布计划" -ForegroundColor Cyan
Write-Host "  本地：$($sourceDirectory.FullName)"
Write-Host "  服务器：$remoteDestination"
Write-Host "  平台路径：$platformPath"
Write-Host "  原有同名目录：自动移动到 .releases 备份，不直接删除"

if ($DryRun) {
    Write-Host "DryRun 完成，未创建压缩包、未连接服务器。" -ForegroundColor Yellow
    return
}

New-Item -ItemType Directory -Path $cacheDirectory -Force | Out-Null
Write-Host "`n[1/4] 打包目录（不压缩，避免浪费时间）……" -ForegroundColor Cyan
Invoke-Native -FilePath $tar -Arguments @("-cf", $archivePath, "-C", $sourceDirectory.Parent.FullName, $datasetName) -FailureMessage "打包 DJI 素材失败"

Write-Host "[2/4] 准备服务器接收目录……" -ForegroundColor Cyan
$prepareCommand = "set -eu; mkdir -p '$RemoteInbox/.incoming' '$RemoteInbox/.releases/$ProjectName' '$RemoteInbox/$ProjectName'"
Invoke-Native -FilePath $ssh -Arguments @($sshCommon + @($target, $prepareCommand)) -FailureMessage "准备服务器目录失败"

Write-Host "[3/4] 上传素材包……" -ForegroundColor Cyan
Invoke-Native -FilePath $scp -Arguments @($scpCommon + @($archivePath, "${target}:$remoteArchive")) -FailureMessage "上传素材包失败；本地 TAR 已保留，可重试"

Write-Host "[4/4] 服务器校验并原子切换快捷路径……" -ForegroundColor Cyan
$remoteScript = @"
set -euo pipefail
stage='$RemoteInbox/.incoming/$ProjectName-$datasetName-$timestamp'
archive='$remoteArchive'
destination='$remoteDestination'
backup='$remoteBackup'
mkdir -p "`$stage"
tar -xf "`$archive" -C "`$stage"
test -f "`$stage/$datasetName/tileset.json"
if [ -e "`$destination" ]; then
  mv "`$destination" "`$backup"
fi
if ! mv "`$stage/$datasetName" "`$destination"; then
  if [ -e "`$backup" ] && [ ! -e "`$destination" ]; then
    mv "`$backup" "`$destination"
  fi
  exit 1
fi
rmdir "`$stage"
chmod -R a+rX "`$destination"
rm -f "`$archive"
printf 'REMOTE_SIZE='
du -sh "`$destination" | awk '{print `$1}'
printf 'REMOTE_FILES='
find "`$destination" -type f | wc -l
"@
$remoteScriptBase64 = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($remoteScript))
$executeCommand = "script_path=`$(mktemp /tmp/smart-bamboo-material-XXXXXX.sh); printf '%s' '$remoteScriptBase64' | base64 -d > `"`$script_path`"; bash `"`$script_path`"; status=`$?; rm -f `"`$script_path`"; exit `$status"
Invoke-Native -FilePath $ssh -Arguments @($sshCommon + @($target, $executeCommand)) -FailureMessage "服务器解包或路径切换失败；远端接收包已保留"

if (-not $KeepArchive) {
    $resolvedArchive = (Get-Item -LiteralPath $archivePath).FullName
    $resolvedCache = (Get-Item -LiteralPath $cacheDirectory).FullName
    if (-not $resolvedArchive.StartsWith($resolvedCache + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        throw "拒绝删除缓存目录之外的临时包：$resolvedArchive"
    }
    Remove-Item -LiteralPath $resolvedArchive -Force
    Write-Host "本地临时 TAR 已在成功校验后删除；原始素材未改动。"
}

try {
    Set-Clipboard -Value $platformPath
    Write-Host "平台路径已复制到剪贴板。" -ForegroundColor Green
} catch {
    Write-Host "无法写入剪贴板，请手工复制平台路径。" -ForegroundColor Yellow
}

Write-Host "`n发布完成：$platformPath" -ForegroundColor Green
Write-Host "进入影像成果 → 上传成果 → DJI 3D Tiles，粘贴该路径并登记。"
if (-not $SkipOpenBrowser) {
    Start-Process "$PlatformBaseUrl/v2/drone/imagery-assets"
}
