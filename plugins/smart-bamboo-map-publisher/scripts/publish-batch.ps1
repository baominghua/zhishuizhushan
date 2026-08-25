[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$ManifestPath,
    [Parameter(Mandatory)][string]$ResultPath,
    [Parameter(Mandatory)][string]$LogPath
)

$ErrorActionPreference = "Stop"
$manifest = Get-Content -LiteralPath $ManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
$publisher = Join-Path $PSScriptRoot "publish-material.ps1"
$results = @()
$versionProperty = $manifest.PSObject.Properties["versionId"]
$versionId = if ($versionProperty -and -not [string]::IsNullOrWhiteSpace([string]$versionProperty.Value)) { [string]$versionProperty.Value } else { Get-Date -Format "yyyyMMdd-HHmmss" }

function Get-PublishErrorMessage([System.Management.Automation.ErrorRecord]$Record) {
    $message = [string]$Record.Exception.Message
    if (-not [string]::IsNullOrWhiteSpace($message)) { return $message.Trim() }
    $recordText = [string]$Record
    if (-not [string]::IsNullOrWhiteSpace($recordText) -and $recordText -ne $Record.Exception.GetType().FullName) { return $recordText.Trim() }
    if (-not [string]::IsNullOrWhiteSpace($Record.FullyQualifiedErrorId)) { return $Record.FullyQualifiedErrorId.Trim() }
    return "未知发布错误，请保留运行日志并联系管理员。"
}

try {
    foreach ($item in @($manifest.items)) {
        "[$(Get-Date -Format HH:mm:ss)] 开始：$($item.kind) / $($item.sourcePath)" | Add-Content -LiteralPath $LogPath -Encoding UTF8
        $arguments = @{
            SourcePath = [string]$item.sourcePath
            Kind = [string]$item.kind
            ProjectName = [string]$item.projectName
            VersionId = $versionId
            ServerHost = [string]$manifest.config.serverHost
            SshUser = [string]$manifest.config.sshUser
            SshPort = [int]$manifest.config.sshPort
            SshKeyPath = [string]$manifest.config.sshKeyPath
            RemoteInbox = [string]$manifest.config.remoteInbox
            PlatformInbox = [string]$manifest.config.platformInbox
        }
        $output = @(& $publisher @arguments 2>&1 | ForEach-Object {
            $_.ToString() | Add-Content -LiteralPath $LogPath -Encoding UTF8
            $_
        })
        if ($LASTEXITCODE -ne 0) { throw "发布命令退出码为 $LASTEXITCODE" }
        $resultLine = @($output | ForEach-Object { $_.ToString() } | Where-Object { $_.StartsWith("SMART_BAMBOO_RESULT=") } | Select-Object -Last 1)
        if (-not $resultLine) { throw "发布脚本没有返回结果路径。" }
        $results += ($resultLine.Substring("SMART_BAMBOO_RESULT=".Length) | ConvertFrom-Json)
        "[$(Get-Date -Format HH:mm:ss)] 完成：$($results[-1].platformPath)" | Add-Content -LiteralPath $LogPath -Encoding UTF8
    }
    @{ success = $true; items = $results } | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $ResultPath -Encoding UTF8
} catch {
    $errorMessage = Get-PublishErrorMessage $_
    "[$(Get-Date -Format HH:mm:ss)] 失败：$errorMessage" | Add-Content -LiteralPath $LogPath -Encoding UTF8
    @{ success = $false; error = $errorMessage; items = $results } | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $ResultPath -Encoding UTF8
    exit 1
}
