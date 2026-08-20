[CmdletBinding()]
param(
    [string]$Repository = "",
    [string]$TargetCommit = "",
    [string]$ReleaseTag = "",
    [string]$ServerHost = "36.140.138.117",
    [string]$SshUser = "root",
    [ValidateRange(1, 65535)]
    [int]$SshPort = 22,
    [string]$RemoteRepository = "/opt/smart-bamboo",
    [string]$RemoteBundleDirectory = "/srv/smart-bamboo/releases/incoming",
    [switch]$InstallKey,
    [switch]$Force,
    [switch]$KeepBundle,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Require-Command {
    param([Parameter(Mandatory)][string]$Name)
    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if (-not $command) {
        throw "缺少命令 $Name。"
    }
    return $command.Source
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

function Get-NativeText {
    param(
        [Parameter(Mandatory)][string]$FilePath,
        [Parameter(Mandatory)][string[]]$Arguments,
        [Parameter(Mandatory)][string]$FailureMessage
    )
    $output = @(& $FilePath @Arguments 2>&1)
    if ($LASTEXITCODE -ne 0) {
        throw "$FailureMessage：$($output -join ' ')"
    }
    return ($output -join "`n").Trim()
}

function Install-ReleaseSshKey {
    param(
        [Parameter(Mandatory)][string]$SshExecutable,
        [Parameter(Mandatory)][string]$SshKeygenExecutable,
        [Parameter(Mandatory)][string]$KeyPath,
        [Parameter(Mandatory)][string]$Target
    )
    $keyDirectory = Split-Path -Parent $KeyPath
    New-Item -ItemType Directory -Path $keyDirectory -Force | Out-Null
    if (-not (Test-Path -LiteralPath $KeyPath -PathType Leaf)) {
        Invoke-Native -FilePath $SshKeygenExecutable -Arguments @("-t", "ed25519", "-N", "", "-C", "smart-bamboo-release", "-f", $KeyPath) -FailureMessage "生成发布专用 SSH 密钥失败"
    }
    $publicKey = [IO.File]::ReadAllText("$KeyPath.pub", [Text.Encoding]::UTF8).Trim()
    $publicKeyBase64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($publicKey + "`n"))
    $remoteCommand = "umask 077; mkdir -p ~/.ssh; touch ~/.ssh/authorized_keys; key=`$(printf '%s' '$publicKeyBase64' | base64 -d); grep -Fqx `"`$key`" ~/.ssh/authorized_keys || printf '%s`n' `"`$key`" >> ~/.ssh/authorized_keys; chmod 700 ~/.ssh; chmod 600 ~/.ssh/authorized_keys"
    Write-Host "首次配置本地直发，请输入一次服务器密码。" -ForegroundColor Yellow
    Invoke-Native -FilePath $SshExecutable -Arguments @("-p", "$SshPort", "-o", "StrictHostKeyChecking=accept-new", $Target, $remoteCommand) -FailureMessage "安装服务器 SSH 密钥失败"
}

$git = Require-Command -Name "git"
$ssh = Require-Command -Name "ssh"
$scp = Require-Command -Name "scp"
$sshKeygen = Require-Command -Name "ssh-keygen"

if (-not $Repository) {
    $configPath = Join-Path $env:LOCALAPPDATA "SmartBamboo\Tools\release-publisher.json"
    if (Test-Path -LiteralPath $configPath -PathType Leaf) {
        $config = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
        $Repository = [string]$config.repository
    } else {
        $Repository = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
    }
}
$repositoryRoot = (Resolve-Path -LiteralPath $Repository).Path
if (-not (Test-Path -LiteralPath (Join-Path $repositoryRoot ".git"))) {
    throw "不是 Git 工作树：$repositoryRoot"
}
if ($RemoteRepository -notmatch '^/[A-Za-z0-9._/-]+$' -or $RemoteRepository.Contains("..")) {
    throw "RemoteRepository 路径不安全。"
}
if ($RemoteBundleDirectory -notmatch '^/[A-Za-z0-9._/-]+$' -or $RemoteBundleDirectory.Contains("..")) {
    throw "RemoteBundleDirectory 路径不安全。"
}

$headCommit = Get-NativeText -FilePath $git -Arguments @("-C", $repositoryRoot, "rev-parse", "HEAD") -FailureMessage "读取本地提交失败"
if (-not $TargetCommit) {
    $TargetCommit = $headCommit
}
if ($TargetCommit -notmatch '^[0-9a-f]{40}$') {
    throw "TargetCommit 必须是完整的 40 位小写 Git 提交号。"
}
if ($TargetCommit -ne $headCommit) {
    throw "本地直发只发布当前 HEAD。当前为 $headCommit，指定为 $TargetCommit。"
}
$worktreeStatus = Get-NativeText -FilePath $git -Arguments @("-C", $repositoryRoot, "status", "--porcelain") -FailureMessage "检查本地工作树失败"
if ($worktreeStatus) {
    throw "本地工作树存在未提交修改，请先提交后再发布。"
}

if (-not $ReleaseTag) {
    $ReleaseTag = "$(Get-Date -Format 'yyyyMMdd')-$($TargetCommit.Substring(0, 12))"
}
if ($ReleaseTag -notmatch '^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$' -or -not $ReleaseTag.Contains($TargetCommit.Substring(0, 12))) {
    throw "ReleaseTag 格式无效，且必须包含提交号前 12 位。"
}

$cacheDirectory = Join-Path $env:LOCALAPPDATA "SmartBamboo\ReleaseCache"
New-Item -ItemType Directory -Path $cacheDirectory -Force | Out-Null
$bundlePath = Join-Path $cacheDirectory "$ReleaseTag.bundle"
$remoteBundle = "$RemoteBundleDirectory/$ReleaseTag.bundle"
$keyPath = Join-Path ([Environment]::GetFolderPath("UserProfile")) ".ssh\smart_bamboo_release_ed25519"
$target = "$SshUser@$ServerHost"
$sshCommon = @("-i", $keyPath, "-p", "$SshPort", "-o", "ServerAliveInterval=30", "-o", "ServerAliveCountMax=6", "-o", "StrictHostKeyChecking=accept-new")
$scpCommon = @("-i", $keyPath, "-P", "$SshPort", "-o", "ServerAliveInterval=30", "-o", "ServerAliveCountMax=6", "-o", "StrictHostKeyChecking=accept-new")

Write-Host "`n智慧竹山本地直发计划" -ForegroundColor Cyan
Write-Host "  本地仓库：$repositoryRoot"
Write-Host "  提交：$TargetCommit"
Write-Host "  发布标签：$ReleaseTag"
Write-Host "  服务器：$target"
Write-Host "  传输方式：Git Bundle → SSH（服务器无需访问 GitHub）"
Write-Host "  说明：服务器仍会使用本地缓存的 Docker 基础镜像完成构建。"

if (-not $Force -and -not $DryRun) {
    $answer = Read-Host "确认发布当前提交到生产服务器吗？输入 YES 继续"
    if ($answer.Trim() -cne "YES") {
        throw "已取消发布。"
    }
}

if (Test-Path -LiteralPath $bundlePath -PathType Leaf) {
    Remove-Item -LiteralPath $bundlePath -Force
}
Write-Host "`n[1/4] 生成并校验 Git Bundle……" -ForegroundColor Cyan
Invoke-Native -FilePath $git -Arguments @("-C", $repositoryRoot, "bundle", "create", $bundlePath, "HEAD") -FailureMessage "生成 Git Bundle 失败"
Invoke-Native -FilePath $git -Arguments @("-C", $repositoryRoot, "bundle", "verify", $bundlePath) -FailureMessage "校验 Git Bundle 失败"
$bundleHash = (Get-FileHash -LiteralPath $bundlePath -Algorithm SHA256).Hash.ToLowerInvariant()
$bundleSize = [Math]::Round((Get-Item -LiteralPath $bundlePath).Length / 1MB, 2)
Write-Host "  Bundle：$bundleSize MB / SHA256 $bundleHash"

if ($DryRun) {
    Write-Host "DryRun 完成，未连接服务器。Bundle 保留在：$bundlePath" -ForegroundColor Yellow
    return
}

$keyWorks = $false
if (Test-Path -LiteralPath $keyPath -PathType Leaf) {
    & $ssh @($sshCommon + @("-o", "BatchMode=yes", "-o", "ConnectTimeout=8", $target, "true"))
    $keyWorks = $LASTEXITCODE -eq 0
}
if (-not $keyWorks) {
    if (-not $InstallKey) {
        $answer = Read-Host "尚未配置本地直发 SSH 密钥。现在安装吗？[Y/n]"
        if ($answer.Trim() -and $answer.Trim().ToLowerInvariant() -ne "y") {
            throw "已取消。使用 -InstallKey 可安装专用密钥。"
        }
    }
    Install-ReleaseSshKey -SshExecutable $ssh -SshKeygenExecutable $sshKeygen -KeyPath $keyPath -Target $target
    Invoke-Native -FilePath $ssh -Arguments @($sshCommon + @("-o", "BatchMode=yes", $target, "true")) -FailureMessage "发布专用 SSH 密钥验证失败"
}

Write-Host "[2/4] 准备服务器接收目录……" -ForegroundColor Cyan
Invoke-Native -FilePath $ssh -Arguments @($sshCommon + @($target, "mkdir -p '$RemoteBundleDirectory'")) -FailureMessage "准备服务器发布目录失败"

Write-Host "[3/4] 从本机上传 Git Bundle……" -ForegroundColor Cyan
Invoke-Native -FilePath $scp -Arguments @($scpCommon + @($bundlePath, "${target}:$remoteBundle")) -FailureMessage "上传 Git Bundle 失败"

Write-Host "[4/4] 校验提交并执行生产发布……" -ForegroundColor Cyan
$remoteScript = @"
set -Eeuo pipefail
bundle='$remoteBundle'
expected_hash='$bundleHash'
repository='$RemoteRepository'
target_commit='$TargetCommit'
release_tag='$ReleaseTag'
test -f "`$bundle"
actual_hash=`$(sha256sum "`$bundle" | awk '{print `$1}')
test "`$actual_hash" = "`$expected_hash"
cd "`$repository"
test -z "`$(git status --porcelain)"
git bundle verify "`$bundle" >/dev/null
git fetch --no-tags "`$bundle" "`$target_commit"
test "`$(git rev-parse FETCH_HEAD)" = "`$target_commit"
git merge-base --is-ancestor HEAD "`$target_commit"
git merge --ff-only "`$target_commit"
RELEASE_BUNDLE="`$bundle" TARGET_COMMIT="`$target_commit" RELEASE_TAG="`$release_tag" \
  bash ops/scripts/deploy-primary-release.sh
rm -f "`$bundle"
"@
$remoteScriptBase64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($remoteScript))
$executeCommand = "script_path=`$(mktemp /tmp/smart-bamboo-release-XXXXXX.sh); printf '%s' '$remoteScriptBase64' | base64 -d > `"`$script_path`"; bash `"`$script_path`"; status=`$?; rm -f `"`$script_path`"; exit `$status"
Invoke-Native -FilePath $ssh -Arguments @($sshCommon + @($target, $executeCommand)) -FailureMessage "服务器生产发布失败；远端 Bundle 已保留，可重试"

if (-not $KeepBundle) {
    $resolvedBundle = (Resolve-Path -LiteralPath $bundlePath).Path
    $resolvedCache = (Resolve-Path -LiteralPath $cacheDirectory).Path
    if (-not $resolvedBundle.StartsWith($resolvedCache + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        throw "拒绝删除缓存目录之外的 Bundle：$resolvedBundle"
    }
    Remove-Item -LiteralPath $resolvedBundle -Force
}

Write-Host "`n本地直发完成：$ReleaseTag" -ForegroundColor Green
Write-Host "服务器已发布提交：$TargetCommit"
