[CmdletBinding()]
param(
    [switch]$ValidateOnly,
    [string]$ScanPath = "",
    [switch]$HistoryOnly,
    [string]$HistoryStateRoot = "",
    [switch]$ValidateUi
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Get-DefaultConfig {
    [ordered]@{
        serverHost = "36.140.138.117"
        sshUser = "root"
        sshPort = 22
        sshKeyPath = "%USERPROFILE%\.ssh\smart_bamboo_release_ed25519"
        remoteInbox = "/srv/smart-bamboo/data/remote-sensing/inbox"
        platformInbox = "/app/data/remote-sensing/inbox"
        platformBaseUrl = "https://36.140.138.117:18081"
        lastSourceRoot = "D:\数据迁移"
    }
}

function Get-ConfigPath {
    $directory = Join-Path $env:LOCALAPPDATA "SmartBamboo\MapPublisher"
    New-Item -ItemType Directory -Path $directory -Force | Out-Null
    Join-Path $directory "config.json"
}

function Read-PublisherConfig {
    $defaults = Get-DefaultConfig
    $path = Get-ConfigPath
    if (Test-Path -LiteralPath $path -PathType Leaf) {
        $stored = Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json
        foreach ($property in $stored.PSObject.Properties) {
            if ($defaults.Contains($property.Name)) { $defaults[$property.Name] = $property.Value }
        }
    }
    [pscustomobject]$defaults
}

function Get-PublisherStateRoot([string]$Override = "") {
    $directory = if ([string]::IsNullOrWhiteSpace($Override)) { Join-Path $env:LOCALAPPDATA "SmartBamboo\MapPublisher" } else { $Override }
    New-Item -ItemType Directory -Path $directory -Force | Out-Null
    return [IO.Path]::GetFullPath($directory)
}

function Get-MaterialTypeLabel([string]$Kind) {
    switch ($Kind) {
        "orthophoto" { return "GeoTIFF 正射影像" }
        "dsm" { return "DSM 地表模型" }
        "dtm" { return "DTM 地形模型" }
        "tiles-b3dm" { return "DJI B3DM 实景模型" }
        "tiles-pnts" { return "PNTS 浏览点云（自动关联 LAS）" }
        "pointcloud-las" { return "LAS/LAZ 源数据（并入 PNTS）" }
        "dji-trajectory" { return "DJI 航迹与姿态侧车" }
        default { return $Kind }
    }
}

function Get-HistoryKey([string]$SourcePath, [string]$Kind, [string]$SourceStamp = "") {
    return "$($Kind.ToLowerInvariant())|$($SourcePath.ToLowerInvariant())|$SourceStamp"
}

function Get-SourceStamp([string]$SourcePath) {
    try {
        $source = Get-Item -LiteralPath $SourcePath -ErrorAction Stop
        [long]$size = if ($source.PSIsContainer) { Get-DirectorySize $source } else { $source.Length }
        return "$size|$($source.LastWriteTimeUtc.Ticks)"
    } catch { return "missing" }
}

function Get-PublishedAtText([string]$PublishedAt) {
    if ([string]::IsNullOrWhiteSpace($PublishedAt)) { return "—" }
    try { return ([datetimeoffset]$PublishedAt).LocalDateTime.ToString("yyyy-MM-dd HH:mm") } catch { return $PublishedAt }
}

function Save-PublisherHistory([object[]]$Records, [string]$StateRoot) {
    $historyPath = Join-Path $StateRoot "history.json"
    $temporaryPath = "$historyPath.$PID.tmp"
    $orderedRecords = @($Records | Sort-Object ProjectName, TypeLabel, SourcePath)
    $json = if ($orderedRecords.Count) { $orderedRecords | ConvertTo-Json -Depth 5 } else { "[]" }
    try {
        $json | Set-Content -LiteralPath $temporaryPath -Encoding UTF8
        Move-Item -LiteralPath $temporaryPath -Destination $historyPath -Force
    } finally {
        if (Test-Path -LiteralPath $temporaryPath) { Remove-Item -LiteralPath $temporaryPath -Force }
    }
}

function Read-PublisherHistory([string]$StateRoot) {
    $historyByKey = [ordered]@{}
    $historyPath = Join-Path $StateRoot "history.json"
    if (Test-Path -LiteralPath $historyPath -PathType Leaf) {
        try {
            $storedHistory = Get-Content -LiteralPath $historyPath -Raw -Encoding UTF8 | ConvertFrom-Json
            foreach ($record in $storedHistory) {
                $sourcePath = [string]$record.SourcePath
                $kind = [string]$record.Kind
                $platformPath = [string]$record.PlatformPath
                if ([string]::IsNullOrWhiteSpace($sourcePath) -or [string]::IsNullOrWhiteSpace($kind) -or [string]::IsNullOrWhiteSpace($platformPath)) { continue }
                $stampProperty = $record.PSObject.Properties["SourceStamp"]
                $storedStamp = if ($stampProperty) { [string]$stampProperty.Value } else { "" }
                $sourceStamp = if ([string]::IsNullOrWhiteSpace($storedStamp)) { Get-SourceStamp $sourcePath } else { $storedStamp }
                $historyByKey[(Get-HistoryKey $sourcePath $kind $sourceStamp)] = [pscustomobject]@{
                    SourcePath = $sourcePath
                    Kind = $kind
                    ProjectName = [string]$record.ProjectName
                    TypeLabel = if ([string]::IsNullOrWhiteSpace([string]$record.TypeLabel)) { Get-MaterialTypeLabel $kind } else { [string]$record.TypeLabel }
                    SizeText = if ([string]::IsNullOrWhiteSpace([string]$record.SizeText)) { "—" } else { [string]$record.SizeText }
                    PlatformPath = $platformPath
                    PublishedAt = [string]$record.PublishedAt
                    SourceStamp = $sourceStamp
                }
            }
        } catch {
            $backupPath = "$historyPath.invalid-$(Get-Date -Format yyyyMMdd-HHmmss)"
            Copy-Item -LiteralPath $historyPath -Destination $backupPath -Force
        }
    }

    $runtime = Join-Path $StateRoot "Runtime"
    foreach ($resultFile in @(Get-ChildItem -LiteralPath $runtime -File -Filter "*.result.json" -ErrorAction SilentlyContinue | Sort-Object LastWriteTime)) {
        try {
            $result = Get-Content -LiteralPath $resultFile.FullName -Raw -Encoding UTF8 | ConvertFrom-Json
            foreach ($item in $result.items) {
                $sourcePath = [string]$item.source
                $kind = [string]$item.kind
                $platformPath = [string]$item.platformPath
                if ([string]::IsNullOrWhiteSpace($sourcePath) -or [string]::IsNullOrWhiteSpace($kind) -or [string]::IsNullOrWhiteSpace($platformPath)) { continue }
                $sourceStamp = Get-SourceStamp $sourcePath
                $key = Get-HistoryKey $sourcePath $kind $sourceStamp
                $existing = $historyByKey[$key]
                $historyByKey[$key] = [pscustomobject]@{
                    SourcePath = $sourcePath
                    Kind = $kind
                    ProjectName = if (-not [string]::IsNullOrWhiteSpace([string]$item.projectName)) { [string]$item.projectName } elseif ($existing) { [string]$existing.ProjectName } else { "" }
                    TypeLabel = if ($existing -and -not [string]::IsNullOrWhiteSpace([string]$existing.TypeLabel)) { [string]$existing.TypeLabel } else { Get-MaterialTypeLabel $kind }
                    SizeText = if ($existing -and -not [string]::IsNullOrWhiteSpace([string]$existing.SizeText)) { [string]$existing.SizeText } else { "—" }
                    PlatformPath = $platformPath
                    PublishedAt = $resultFile.LastWriteTime.ToString("o")
                    SourceStamp = $sourceStamp
                }
            }
        } catch { continue }
    }
    $records = @($historyByKey.Values)
    Save-PublisherHistory $records $StateRoot
    return $records
}

function New-HistoryMapItem($Record) {
    [pscustomobject]@{
        IsSelected = $false
        ProjectName = [string]$Record.ProjectName
        TypeLabel = [string]$Record.TypeLabel
        Kind = [string]$Record.Kind
        SourcePath = [string]$Record.SourcePath
        SizeText = if ([string]::IsNullOrWhiteSpace([string]$Record.SizeText)) { "—" } else { [string]$Record.SizeText }
        Status = "已发布"
        PlatformPath = [string]$Record.PlatformPath
        HasPublishedPath = $true
        PublishPathAction = "查看并复制"
        PublishedAt = [string]$Record.PublishedAt
        PublishedAtText = Get-PublishedAtText ([string]$Record.PublishedAt)
        SourceStamp = [string]$Record.SourceStamp
    }
}

function Get-ProjectName([System.IO.FileSystemInfo]$Item) {
    $directory = if ($Item -is [System.IO.DirectoryInfo]) { [System.IO.DirectoryInfo]$Item } else { $Item.Directory }
    if ($directory.Name -eq "map" -and $directory.Parent) { return $directory.Parent.Name }
    if ($directory.Name -match '^terra_' -and $directory.Parent -and $directory.Parent.Name -eq "lidars" -and $directory.Parent.Parent) { return $directory.Parent.Parent.Name }
    if ($directory.Parent -and $directory.Parent.Name -eq "lidars" -and $directory.Parent.Parent) { return $directory.Parent.Parent.Name }
    if ($directory.Parent) { return $directory.Parent.Name }
    return $directory.Name
}

function New-MapItem([bool]$Selected, [string]$Kind, [string]$TypeLabel, [System.IO.FileSystemInfo]$Source, [long]$SizeBytes) {
    [pscustomobject]@{
        IsSelected = $Selected
        ProjectName = Get-ProjectName $Source
        TypeLabel = $TypeLabel
        Kind = $Kind
        SourcePath = $Source.FullName
        SizeText = if ($SizeBytes -ge 1GB) { "{0:N2} GB" -f ($SizeBytes / 1GB) } elseif ($SizeBytes -ge 1MB) { "{0:N1} MB" -f ($SizeBytes / 1MB) } else { "{0:N0} KB" -f ($SizeBytes / 1KB) }
        Status = "待发布"
        PlatformPath = ""
        HasPublishedPath = $false
        PublishPathAction = "未发布"
        PublishedAt = ""
        PublishedAtText = "—"
        SourceStamp = "$SizeBytes|$($Source.LastWriteTimeUtc.Ticks)"
    }
}

function Get-DirectorySize([System.IO.DirectoryInfo]$Directory) {
    [long](Get-ChildItem -LiteralPath $Directory.FullName -Recurse -File -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum
}

function Test-PublishablePath([string]$Path) {
    return $Path -notmatch '\\\.[^\\]+(\\|$)' -and $Path -notmatch '\\.smart-bamboo-publish-cache\\'
}

function Get-MapMaterials([string]$Root) {
    $rootItem = Get-Item -LiteralPath $Root -ErrorAction Stop
    if (-not $rootItem.PSIsContainer) { throw "请选择素材文件夹。" }
    $items = [System.Collections.Generic.List[object]]::new()
    $claimedDirectories = [System.Collections.Generic.List[string]]::new()

    $tilesets = @(Get-ChildItem -LiteralPath $rootItem.FullName -Recurse -File -Filter "tileset.json" -ErrorAction SilentlyContinue | Where-Object { Test-PublishablePath $_.FullName } | Sort-Object { $_.DirectoryName.Length })
    foreach ($tileset in $tilesets) {
        $directoryPath = $tileset.Directory.FullName
        $nested = $false
        foreach ($claimed in $claimedDirectories) {
            if ($directoryPath.StartsWith($claimed + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { $nested = $true; break }
        }
        if ($nested) { continue }
        $b3dm = Get-ChildItem -LiteralPath $directoryPath -Recurse -File -Filter "*.b3dm" -ErrorAction SilentlyContinue | Select-Object -First 1
        $pnts = Get-ChildItem -LiteralPath $directoryPath -Recurse -File -Filter "*.pnts" -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($b3dm -or $pnts) {
            $kind = if ($b3dm) { "tiles-b3dm" } else { "tiles-pnts" }
            $label = if ($b3dm) { "DJI B3DM 实景模型" } else { "PNTS 浏览点云（自动关联 LAS）" }
            $items.Add((New-MapItem $true $kind $label $tileset.Directory (Get-DirectorySize $tileset.Directory)))
            $claimedDirectories.Add($directoryPath)
        }
    }

    $tiffs = @(Get-ChildItem -LiteralPath $rootItem.FullName -Recurse -File -ErrorAction SilentlyContinue | Where-Object {
        $lowerName = $_.Name.ToLowerInvariant()
        $finalName = $lowerName -in @("result.tif", "result.tiff", "orthophoto.tif", "orthophoto.tiff", "dom.tif", "dom.tiff", "dsm.tif", "dsm.tiff", "dtm.tif", "dtm.tiff", "dem.tif", "dem.tiff")
        $_.Extension -in @(".tif", ".tiff") -and $finalName -and (Test-PublishablePath $_.FullName)
    })
    foreach ($file in $tiffs) {
        $name = $file.Name.ToLowerInvariant()
        $kind = if ($name -match '^(dsm|surface)') { "dsm" } elseif ($name -match '^(dtm|dem|terrain)') { "dtm" } else { "orthophoto" }
        $label = if ($kind -eq "dsm") { "DSM 地表模型" } elseif ($kind -eq "dtm") { "DTM 地形模型" } else { "GeoTIFF 正射影像" }
        $items.Add((New-MapItem $true $kind $label $file $file.Length))
    }

    $pointFiles = @(Get-ChildItem -LiteralPath $rootItem.FullName -Recurse -File -ErrorAction SilentlyContinue | Where-Object { $_.Extension -in @(".las", ".laz") -and (Test-PublishablePath $_.FullName) })
    foreach ($group in ($pointFiles | Group-Object DirectoryName)) {
        $directory = Get-Item -LiteralPath $group.Name
        [long]$size = ($group.Group | Measure-Object -Property Length -Sum).Sum
        $items.Add((New-MapItem $true "pointcloud-las" "LAS/LAZ 源数据（并入 PNTS）" $directory $size))
    }
    $trajectoryDirectories = @(Get-ChildItem -LiteralPath $rootItem.FullName -Recurse -Directory -Filter "terra_trajectory" -ErrorAction SilentlyContinue | Where-Object { Test-PublishablePath $_.FullName })
    foreach ($directory in $trajectoryDirectories) {
        $sidecars = @(Get-ChildItem -LiteralPath $directory.FullName -Recurse -File -ErrorAction SilentlyContinue | Where-Object {
            $lowerName = $_.Name.ToLowerInvariant()
            $_.Extension -in @(".csv", ".out", ".txt") -and ($lowerName.StartsWith("pos_") -or $lowerName.Contains("_sbet") -or $lowerName.Contains("_smrmsg"))
        })
        if ($sidecars.Count -gt 0) {
            [long]$size = ($sidecars | Measure-Object -Property Length -Sum).Sum
            $items.Add((New-MapItem $true "dji-trajectory" "DJI 航迹与姿态侧车" $directory $size))
        }
    }
    return @($items | Sort-Object ProjectName, TypeLabel, SourcePath)
}

function Get-SingleMaterial([string]$Path) {
    $item = Get-Item -LiteralPath $Path -ErrorAction Stop
    if ($item -isnot [System.IO.DirectoryInfo]) {
        if ($item.Extension -in @(".tif", ".tiff")) {
            $name = $item.Name.ToLowerInvariant()
            $kind = if ($name -match '^(dsm|surface)') { "dsm" } elseif ($name -match '^(dtm|dem|terrain)') { "dtm" } else { "orthophoto" }
            $label = if ($kind -eq "dsm") { "DSM 地表模型" } elseif ($kind -eq "dtm") { "DTM 地形模型" } else { "GeoTIFF 正射影像" }
            return New-MapItem $true $kind $label $item $item.Length
        }
        throw "手动文件仅支持 TIF/TIFF；点云和 3D Tiles 请添加文件夹。"
    }
    $tileset = Join-Path $item.FullName "tileset.json"
    if (Test-Path -LiteralPath $tileset -PathType Leaf) {
        $b3dm = Get-ChildItem -LiteralPath $item.FullName -Recurse -File -Filter "*.b3dm" -ErrorAction SilentlyContinue | Select-Object -First 1
        $pnts = Get-ChildItem -LiteralPath $item.FullName -Recurse -File -Filter "*.pnts" -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($b3dm) { return New-MapItem $true "tiles-b3dm" "DJI B3DM 实景模型" $item (Get-DirectorySize $item) }
        if ($pnts) { return New-MapItem $true "tiles-pnts" "PNTS 浏览点云（自动关联 LAS）" $item (Get-DirectorySize $item) }
    }
    if (Get-ChildItem -LiteralPath $item.FullName -Recurse -File -ErrorAction SilentlyContinue | Where-Object { $_.Extension -in @(".las", ".laz") } | Select-Object -First 1) {
        return New-MapItem $true "pointcloud-las" "LAS/LAZ 源数据（并入 PNTS）" $item (Get-DirectorySize $item)
    }
    if (Get-ChildItem -LiteralPath $item.FullName -Recurse -File -ErrorAction SilentlyContinue | Where-Object {
        $lowerName = $_.Name.ToLowerInvariant()
        $_.Extension -in @(".csv", ".out", ".txt") -and ($lowerName.StartsWith("pos_") -or $lowerName.Contains("_sbet") -or $lowerName.Contains("_smrmsg"))
    } | Select-Object -First 1) {
        return New-MapItem $true "dji-trajectory" "DJI 航迹与姿态侧车" $item (Get-DirectorySize $item)
    }
    throw "该文件夹没有根 tileset.json+B3DM/PNTS、LAS/LAZ 或 DJI POS/SBET/SMRMSG 轨迹资料。"
}

if ($ValidateOnly) {
    foreach ($command in @("ssh", "sftp", "scp", "tar")) {
        if (-not (Get-Command $command -ErrorAction SilentlyContinue)) { throw "缺少命令：$command" }
    }
    "SMART_BAMBOO_MAP_PUBLISHER_READY"
    return
}
if ($ScanPath) {
    @(Get-MapMaterials $ScanPath) | ConvertTo-Json -Depth 4
    return
}
if ($HistoryOnly) {
    $stateRoot = Get-PublisherStateRoot $HistoryStateRoot
    @(Read-PublisherHistory $stateRoot) | Sort-Object ProjectName, TypeLabel, SourcePath | ConvertTo-Json -Depth 5
    return
}

Add-Type -AssemblyName PresentationFramework, PresentationCore, WindowsBase, System.Windows.Forms
[xml]$xaml = @'
<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation" xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml" Title="智慧竹山地图发布助手" Width="1180" Height="780" MinWidth="980" MinHeight="680" WindowStartupLocation="CenterScreen" Background="#F3F7F5">
  <Window.Resources>
    <Style TargetType="Button"><Setter Property="Padding" Value="14,8"/><Setter Property="Margin" Value="0,0,8,0"/><Setter Property="Cursor" Value="Hand"/></Style>
    <Style TargetType="TextBox"><Setter Property="Padding" Value="8,6"/><Setter Property="VerticalContentAlignment" Value="Center"/></Style>
  </Window.Resources>
  <Grid Margin="20"><Grid.RowDefinitions><RowDefinition Height="Auto"/><RowDefinition Height="Auto"/><RowDefinition Height="*"/><RowDefinition Height="150"/><RowDefinition Height="Auto"/></Grid.RowDefinitions>
    <DockPanel Grid.Row="0" Margin="0,0,0,14"><StackPanel><TextBlock Text="智慧竹山地图发布助手" FontSize="25" FontWeight="Bold" Foreground="#123B2F"/><TextBlock Text="自动识别 GeoTIFF、LAS/LAZ、DJI 3D Tiles 与轨迹侧车，发布后返回平台登记路径" Foreground="#62776F" Margin="0,5,0,0"/></StackPanel><Button x:Name="HelpButton" Content="?" Width="42" Height="42" FontSize="20" FontWeight="Bold" DockPanel.Dock="Right" Margin="0" ToolTip="发布说明"/></DockPanel>
    <Border Grid.Row="1" Background="White" BorderBrush="#D3E0DA" BorderThickness="1" CornerRadius="8" Padding="14" Margin="0,0,0,12"><Grid><Grid.RowDefinitions><RowDefinition/><RowDefinition/></Grid.RowDefinitions><Grid.ColumnDefinitions><ColumnDefinition Width="Auto"/><ColumnDefinition Width="2*"/><ColumnDefinition Width="Auto"/><ColumnDefinition Width="*"/><ColumnDefinition Width="Auto"/><ColumnDefinition Width="90"/></Grid.ColumnDefinitions>
      <TextBlock Text="素材文件夹" VerticalAlignment="Center" Margin="0,0,8,0"/><TextBox x:Name="SourceRootBox" Grid.Column="1"/><Button x:Name="BrowseRootButton" Grid.Column="2" Content="选择文件夹" Margin="8,0"/><Button x:Name="ScanButton" Grid.Column="3" Content="自动检索并分类" HorizontalAlignment="Left"/><Button x:Name="ManualFileButton" Grid.Column="4" Content="手动添加文件"/><Button x:Name="ManualFolderButton" Grid.Column="5" Content="添加文件夹" Margin="0"/>
      <TextBlock Grid.Row="1" Text="发布地址" VerticalAlignment="Center" Margin="0,10,8,0"/><StackPanel Grid.Row="1" Grid.Column="1" Grid.ColumnSpan="5" Orientation="Horizontal" Margin="0,10,0,0"><TextBox x:Name="HostBox" Width="145"/><TextBox x:Name="UserBox" Width="80" Margin="8,0,0,0"/><TextBox x:Name="PortBox" Width="65" Margin="8,0,0,0"/><TextBox x:Name="KeyBox" Width="290" Margin="8,0,0,0"/><TextBox x:Name="RemoteBox" Width="310" Margin="8,0,0,0"/></StackPanel>
    </Grid></Border>
    <Border Grid.Row="2" Background="White" BorderBrush="#D3E0DA" BorderThickness="1" CornerRadius="8" Padding="8"><Grid><Grid.RowDefinitions><RowDefinition Height="Auto"/><RowDefinition Height="*"/></Grid.RowDefinitions>
      <DockPanel Grid.Row="0" Margin="0,0,0,7"><StackPanel Orientation="Horizontal"><Button x:Name="SelectAllButton" Content="全选" Padding="12,5"/><Button x:Name="ClearAllButton" Content="取消全选" Padding="12,5"/></StackPanel><TextBlock Text="默认全选，可按需批量切换；发布成功后可在最右侧查看并复制路径。" Foreground="#62776F" VerticalAlignment="Center" DockPanel.Dock="Right"/></DockPanel>
      <DataGrid x:Name="MaterialGrid" Grid.Row="1" AutoGenerateColumns="False" CanUserAddRows="False" IsReadOnly="False" SelectionMode="Extended" GridLinesVisibility="Horizontal" HeadersVisibility="Column"><DataGrid.Columns>
        <DataGridCheckBoxColumn Header="发布" Binding="{Binding IsSelected, Mode=TwoWay}" Width="55"/>
        <DataGridTextColumn Header="项目名" Binding="{Binding ProjectName, Mode=TwoWay, UpdateSourceTrigger=PropertyChanged}" Width="150"/>
        <DataGridTextColumn Header="分类" Binding="{Binding TypeLabel}" IsReadOnly="True" Width="170"/>
        <DataGridTextColumn Header="本地路径" Binding="{Binding SourcePath}" IsReadOnly="True" Width="*"/>
        <DataGridTextColumn Header="大小" Binding="{Binding SizeText}" IsReadOnly="True" Width="90"/>
        <DataGridTextColumn Header="状态" Binding="{Binding Status}" IsReadOnly="True" Width="90"/>
        <DataGridTextColumn Header="发布时间" Binding="{Binding PublishedAtText}" IsReadOnly="True" Width="125"/>
        <DataGridTemplateColumn Header="发布路径" Width="115"><DataGridTemplateColumn.CellTemplate><DataTemplate><Button x:Name="CopyRowPathButton" Content="{Binding PublishPathAction}" Tag="{Binding PlatformPath}" IsEnabled="{Binding HasPublishedPath}" Padding="8,2" Margin="3,1"/></DataTemplate></DataGridTemplateColumn.CellTemplate></DataGridTemplateColumn>
      </DataGrid.Columns></DataGrid>
    </Grid></Border>
    <Border Grid.Row="3" Background="#102F27" CornerRadius="8" Padding="12" Margin="0,12,0,12"><TextBox x:Name="LogBox" Background="Transparent" BorderThickness="0" Foreground="#D8EFE5" FontFamily="Consolas" IsReadOnly="True" TextWrapping="Wrap" VerticalScrollBarVisibility="Auto"/></Border>
    <DockPanel Grid.Row="4"><TextBlock x:Name="StatusText" Text="请选择素材文件夹并检索。" Foreground="#62776F" VerticalAlignment="Center"/><StackPanel DockPanel.Dock="Right" Orientation="Horizontal"><Button x:Name="CopyButton" Content="复制发布路径"/><Button x:Name="OpenPlatformButton" Content="打开影像管理"/><Button x:Name="PublishButton" Content="发布已勾选项" Background="#0F7658" Foreground="White" FontWeight="Bold" Margin="0"/></StackPanel></DockPanel>
  </Grid>
</Window>
'@
$reader = New-Object System.Xml.XmlNodeReader $xaml
$window = [Windows.Markup.XamlReader]::Load($reader)
$names = @("HelpButton","SourceRootBox","BrowseRootButton","ScanButton","ManualFileButton","ManualFolderButton","HostBox","UserBox","PortBox","KeyBox","RemoteBox","SelectAllButton","ClearAllButton","MaterialGrid","LogBox","StatusText","CopyButton","OpenPlatformButton","PublishButton")
$ui = @{}; foreach ($name in $names) { $ui[$name] = $window.FindName($name) }
$config = Read-PublisherConfig
$ui.SourceRootBox.Text = [string]$config.lastSourceRoot; $ui.HostBox.Text = [string]$config.serverHost; $ui.UserBox.Text = [string]$config.sshUser; $ui.PortBox.Text = [string]$config.sshPort; $ui.KeyBox.Text = [string]$config.sshKeyPath; $ui.RemoteBox.Text = [string]$config.remoteInbox
$script:historyStateRoot = Get-PublisherStateRoot $HistoryStateRoot
$historyRecords = @(Read-PublisherHistory $script:historyStateRoot)
$script:historyByKey = @{}
foreach ($record in $historyRecords) { $script:historyByKey[(Get-HistoryKey ([string]$record.SourcePath) ([string]$record.Kind) ([string]$record.SourceStamp))] = $record }
$collection = New-Object 'System.Collections.ObjectModel.ObservableCollection[object]'
$ui.MaterialGrid.ItemsSource = $collection
$script:lastResults = @($historyRecords | ForEach-Object { [pscustomobject]@{ source=$_.SourcePath; kind=$_.Kind; projectName=$_.ProjectName; platformPath=$_.PlatformPath } }); $script:process = $null; $script:resultPath = ""; $script:logPath = ""

function Add-Material($item) {
    $history = $script:historyByKey[(Get-HistoryKey ([string]$item.SourcePath) ([string]$item.Kind) ([string]$item.SourceStamp))]
    if ($history) {
        $item.IsSelected = $false
        $item.Status = "已发布"
        $item.PlatformPath = [string]$history.PlatformPath
        $item.HasPublishedPath = -not [string]::IsNullOrWhiteSpace($item.PlatformPath)
        $item.PublishPathAction = if ($item.HasPublishedPath) { "查看并复制" } else { "未返回路径" }
        $item.PublishedAt = [string]$history.PublishedAt
        $item.PublishedAtText = Get-PublishedAtText $item.PublishedAt
    }
    if (@($collection | Where-Object { $_.SourcePath -eq $item.SourcePath -and $_.Kind -eq $item.Kind }).Count -eq 0) { $collection.Add($item) }
}
function Show-Error([string]$Message) { [System.Windows.MessageBox]::Show($window, $Message, "地图发布助手", "OK", "Error") | Out-Null }
function Select-Folder([string]$Initial) { $dialog = New-Object System.Windows.Forms.FolderBrowserDialog; $dialog.Description = "选择地图成果文件夹"; if (Test-Path -LiteralPath $Initial -PathType Container) { $dialog.SelectedPath = $Initial }; if ($dialog.ShowDialog() -eq "OK") { return $dialog.SelectedPath }; return "" }

foreach ($record in @($historyRecords | Sort-Object ProjectName, TypeLabel, SourcePath)) { $collection.Add((New-HistoryMapItem $record)) }
if ($historyRecords.Count) { $ui.StatusText.Text = "已恢复 $($historyRecords.Count) 条发布记录；重新检索后会自动标记已发布成果。" }

$ui.BrowseRootButton.Add_Click({ $path = Select-Folder $ui.SourceRootBox.Text; if ($path) { $ui.SourceRootBox.Text = $path } })
$ui.ScanButton.Add_Click({ try { $ui.StatusText.Text = "正在扫描……"; $collection.Clear(); foreach ($item in @(Get-MapMaterials $ui.SourceRootBox.Text)) { Add-Material $item }; $publishedCount = @($collection | Where-Object HasPublishedPath).Count; $ui.StatusText.Text = if ($publishedCount) { "已识别 $($collection.Count) 个成果，其中 $publishedCount 个已发布并自动取消勾选。" } else { "已识别 $($collection.Count) 个可发布成果。" } } catch { Show-Error $_.Exception.Message } })
$ui.ManualFileButton.Add_Click({ $dialog = New-Object Microsoft.Win32.OpenFileDialog; $dialog.Filter = "GeoTIFF (*.tif;*.tiff)|*.tif;*.tiff"; $dialog.Multiselect = $true; if ($dialog.ShowDialog()) { foreach ($file in $dialog.FileNames) { try { Add-Material (Get-SingleMaterial $file) } catch { Show-Error $_.Exception.Message } } } })
$ui.ManualFolderButton.Add_Click({ $path = Select-Folder $ui.SourceRootBox.Text; if ($path) { try { Add-Material (Get-SingleMaterial $path) } catch { Show-Error $_.Exception.Message } } })
$ui.HelpButton.Add_Click({ $help = Get-Content -LiteralPath (Join-Path $PSScriptRoot "..\assets\发布说明.md") -Raw -Encoding UTF8; [System.Windows.MessageBox]::Show($window, $help, "发布说明", "OK", "Information") | Out-Null })
$ui.OpenPlatformButton.Add_Click({ Start-Process "$($config.platformBaseUrl)/v2/drone/imagery-assets" })
$ui.CopyButton.Add_Click({ if ($script:lastResults.Count) { Set-Clipboard -Value (($script:lastResults | ForEach-Object { $_.platformPath }) -join [Environment]::NewLine); $ui.StatusText.Text = "发布路径已复制。" } })
$ui.SelectAllButton.Add_Click({ foreach ($item in $collection) { $item.IsSelected = $true }; $ui.MaterialGrid.Items.Refresh(); $ui.StatusText.Text = "已全选 $($collection.Count) 个成果。" })
$ui.ClearAllButton.Add_Click({ foreach ($item in $collection) { $item.IsSelected = $false }; $ui.MaterialGrid.Items.Refresh(); $ui.StatusText.Text = "已取消全部勾选。" })
$ui.MaterialGrid.AddHandler([System.Windows.Controls.Button]::ClickEvent, [System.Windows.RoutedEventHandler]{
    param($sender, $eventArgs)
    $button = if ($eventArgs.OriginalSource -is [System.Windows.Controls.Button]) { $eventArgs.OriginalSource } else { $eventArgs.Source }
    if ($button -is [System.Windows.Controls.Button] -and $button.Name -eq "CopyRowPathButton") {
        $path = [string]$button.Tag
        if (-not [string]::IsNullOrWhiteSpace($path)) {
            Set-Clipboard -Value $path
            $ui.StatusText.Text = "已复制发布路径：$path"
            [System.Windows.MessageBox]::Show($window, "发布路径：`r`n$path`r`n`r`n已复制到剪贴板。", "发布路径", "OK", "Information") | Out-Null
            $eventArgs.Handled = $true
        }
    }
})

$timer = New-Object Windows.Threading.DispatcherTimer
$timer.Interval = [TimeSpan]::FromSeconds(1)
$timer.Add_Tick({
    if ($script:logPath -and (Test-Path -LiteralPath $script:logPath)) { $ui.LogBox.Text = Get-Content -LiteralPath $script:logPath -Raw -Encoding UTF8; $ui.LogBox.ScrollToEnd() }
    if ($script:process -and $script:process.HasExited) {
        $timer.Stop(); $ui.PublishButton.IsEnabled = $true; $ui.ScanButton.IsEnabled = $true; $ui.SelectAllButton.IsEnabled = $true; $ui.ClearAllButton.IsEnabled = $true
        if (Test-Path -LiteralPath $script:resultPath) {
            $result = Get-Content -LiteralPath $script:resultPath -Raw -Encoding UTF8 | ConvertFrom-Json
            $script:lastResults = @($result.items)
            $publishedAt = (Get-Item -LiteralPath $script:resultPath).LastWriteTime.ToString("o")
            foreach ($item in $collection) {
                $match = $script:lastResults | Where-Object { $_.source -eq $item.SourcePath } | Select-Object -First 1
                if ($match) {
                    $item.Status = "已发布"
                    $item.PlatformPath = [string]$match.platformPath
                    $item.HasPublishedPath = -not [string]::IsNullOrWhiteSpace($item.PlatformPath)
                    $item.PublishPathAction = if ($item.HasPublishedPath) { "查看并复制" } else { "未返回路径" }
                    $item.PublishedAt = $publishedAt
                    $item.PublishedAtText = Get-PublishedAtText $publishedAt
                    if ($item.HasPublishedPath) {
                        $historyRecord = [pscustomobject]@{
                            SourcePath = [string]$item.SourcePath
                            Kind = [string]$item.Kind
                            ProjectName = [string]$item.ProjectName
                            TypeLabel = [string]$item.TypeLabel
                            SizeText = [string]$item.SizeText
                            PlatformPath = [string]$item.PlatformPath
                            PublishedAt = $publishedAt
                            SourceStamp = [string]$item.SourceStamp
                        }
                        $script:historyByKey[(Get-HistoryKey $historyRecord.SourcePath $historyRecord.Kind $historyRecord.SourceStamp)] = $historyRecord
                    }
                } elseif ($item.Status -eq "发布中") {
                    $item.Status = "待续传"
                }
            }
            if ($script:lastResults.Count) { Save-PublisherHistory @($script:historyByKey.Values) $script:historyStateRoot }
            $ui.MaterialGrid.Items.Refresh()
            if ($result.success) { $ui.StatusText.Text = "发布完成，共 $($script:lastResults.Count) 项；可复制下方输出路径。"; $ui.LogBox.AppendText("`r`n`r`n发布路径：`r`n" + (($script:lastResults | ForEach-Object { $_.platformPath }) -join "`r`n")) } else { $ui.StatusText.Text = "发布中止：$($result.error)" }
        } else { $ui.StatusText.Text = "发布进程异常结束，请查看日志。" }
        $script:process.Dispose(); $script:process = $null
    }
})

$ui.PublishButton.Add_Click({
    try {
        $selected = @($collection | Where-Object IsSelected)
        if (-not $selected.Count) { throw "请至少勾选一个发布项。" }
        $port = 0; if (-not [int]::TryParse($ui.PortBox.Text, [ref]$port) -or $port -lt 1 -or $port -gt 65535) { throw "SSH 端口无效。" }
        foreach ($item in $selected) { if ($item.ProjectName -notmatch '^[\p{L}\p{Nd}][\p{L}\p{Nd}._-]{0,63}$') { throw "项目名不合法：$($item.ProjectName)" } }
        $currentConfig = [ordered]@{ serverHost=$ui.HostBox.Text.Trim(); sshUser=$ui.UserBox.Text.Trim(); sshPort=$port; sshKeyPath=$ui.KeyBox.Text.Trim(); remoteInbox=$ui.RemoteBox.Text.Trim(); platformInbox=[string]$config.platformInbox; platformBaseUrl=[string]$config.platformBaseUrl; lastSourceRoot=$ui.SourceRootBox.Text.Trim() }
        $currentConfig | ConvertTo-Json | Set-Content -LiteralPath (Get-ConfigPath) -Encoding UTF8
        $runtime = Join-Path $env:LOCALAPPDATA "SmartBamboo\MapPublisher\Runtime"; New-Item -ItemType Directory -Path $runtime -Force | Out-Null
        $id = [Guid]::NewGuid().ToString("N"); $manifestPath = Join-Path $runtime "$id.manifest.json"; $script:resultPath = Join-Path $runtime "$id.result.json"; $script:logPath = Join-Path $runtime "$id.log"
        $versionId = Get-Date -Format "yyyyMMdd-HHmmss"
        @{ config=$currentConfig; versionId=$versionId; items=@($selected | ForEach-Object { @{ sourcePath=$_.SourcePath; kind=$_.Kind; projectName=$_.ProjectName } }) } | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $manifestPath -Encoding UTF8
        "发布任务已创建，共 $($selected.Count) 项；多时期批次：$versionId。" | Set-Content -LiteralPath $script:logPath -Encoding UTF8
        $batch = Join-Path $PSScriptRoot "publish-batch.ps1"
        $script:process = Start-Process powershell.exe -ArgumentList @("-NoLogo","-NoProfile","-ExecutionPolicy","Bypass","-File",$batch,"-ManifestPath",$manifestPath,"-ResultPath",$script:resultPath,"-LogPath",$script:logPath) -WindowStyle Hidden -PassThru
        $ui.PublishButton.IsEnabled = $false; $ui.ScanButton.IsEnabled = $false; $ui.SelectAllButton.IsEnabled = $false; $ui.ClearAllButton.IsEnabled = $false; $ui.StatusText.Text = "正在发布批次 $versionId；每个成果状态会在日志中更新……"; foreach ($item in $selected) { $item.Status = "发布中" }; $ui.MaterialGrid.Items.Refresh(); $timer.Start()
    } catch { Show-Error $_.Exception.Message }
})

$window.Add_Closing({ if ($script:process -and -not $script:process.HasExited) { [System.Windows.MessageBox]::Show($window, "发布任务将在后台继续运行。稍后重新打开助手，会自动恢复已完成记录和发布路径。", "后台继续发布", "OK", "Information") | Out-Null } })
if ($ValidateUi) { "SMART_BAMBOO_MAP_PUBLISHER_UI_READY history=$($historyRecords.Count) rows=$($collection.Count)"; return }
$window.ShowDialog() | Out-Null
