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
try {
    foreach ($item in @($manifest.items)) {
        "[$(Get-Date -Format HH:mm:ss)] 开始：$($item.kind) / $($item.sourcePath)" | Add-Content -LiteralPath $LogPath -Encoding UTF8
        $arguments = @{
            SourcePath = [string]$item.sourcePath
            Kind = [string]$item.kind
            ProjectName = [string]$item.projectName
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
    "[$(Get-Date -Format HH:mm:ss)] 失败：$($_.Exception.Message)" | Add-Content -LiteralPath $LogPath -Encoding UTF8
    @{ success = $false; error = $_.Exception.Message; items = $results } | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $ResultPath -Encoding UTF8
    exit 1
}
