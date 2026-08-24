from __future__ import annotations

import io
import json
import os
import re
import shutil
import subprocess
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from server.v2.tools import build_map_publisher_archive


ROOT = Path(__file__).resolve().parents[1]
WINDOWS_POWERSHELL = shutil.which("powershell.exe")


def test_map_publisher_archive_contains_runnable_windows_assistant():
    content = build_map_publisher_archive()
    assert len(content) > 10_000
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        names = set(archive.namelist())
        assert "智慧竹山地图发布助手/启动地图发布助手.cmd" in names
        assert "智慧竹山地图发布助手/发布说明.md" in names
        assert "智慧竹山地图发布助手/scripts/SmartBambooMapPublisher.ps1" in names
        assert "智慧竹山地图发布助手/scripts/publish-batch.ps1" in names
        assert "智慧竹山地图发布助手/scripts/publish-material.ps1" in names

        material_script = archive.read(
            "智慧竹山地图发布助手/scripts/publish-material.ps1"
        ).decode("utf-8")
        batch_script = archive.read(
            "智慧竹山地图发布助手/scripts/publish-batch.ps1"
        ).decode("utf-8")
        assistant_script = archive.read(
            "智慧竹山地图发布助手/scripts/SmartBambooMapPublisher.ps1"
        ).decode("utf-8")
        assert '$previousErrorActionPreference = $ErrorActionPreference' in material_script
        assert '$ErrorActionPreference = "Continue"' in material_script
        assert "$nativeExitCode = $LASTEXITCODE" in material_script
        assert "New-RemoteActivationScript" in material_script
        assert '"test -f \'$requiredPath/tileset.json\';"' in material_script
        assert "Get-ArchiveCacheRoot" in material_script
        assert '".smart-bamboo-publish-cache"' in material_script
        assert "Assert-ArchiveCacheSpace" in material_script
        assert "Get-PublishErrorMessage" in batch_script
        assert "error = $errorMessage" in batch_script
        assert 'x:Name="SelectAllButton"' in assistant_script
        assert 'x:Name="ClearAllButton"' in assistant_script
        assert 'Header="发布路径"' in assistant_script
        assert 'x:Name="CopyRowPathButton"' in assistant_script
        assert 'PlatformPath = ""' in assistant_script
        assert "Set-Clipboard -Value $path" in assistant_script
        assert "Read-PublisherHistory" in assistant_script
        assert 'Join-Path $StateRoot "history.json"' in assistant_script
        assert 'Header="发布时间"' in assistant_script
        assert "PublishedAtText" in assistant_script
        assert '"dji-trajectory"' in material_script
        assert '"DJI 航迹与姿态侧车"' in assistant_script
        assert '"_smrmsg"' in assistant_script

        xaml_match = re.search(r"\[xml\]\$xaml = @'\r?\n(.*?)\r?\n'@", assistant_script, re.DOTALL)
        assert xaml_match is not None
        ET.fromstring(xaml_match.group(1))


@pytest.mark.skipif(WINDOWS_POWERSHELL is None, reason="Windows PowerShell 5.1 is required")
def test_publisher_scan_detects_dji_trajectory_sidecars(tmp_path: Path):
    project = tmp_path / "邵武S2地块"
    trajectory = project / "terra_trajectory" / "merge"
    trajectory.mkdir(parents=True)
    (project / "terra_trajectory" / "POS_DJI_demo.csv").write_text("# time, x, y, z\n1,117,27,800\n", encoding="utf-8")
    (trajectory / "DJI_demo_sbet.txt").write_text("% Time Latitude Longitude\n", encoding="utf-8")

    script = ROOT / "plugins" / "smart-bamboo-map-publisher" / "scripts" / "SmartBambooMapPublisher.ps1"
    result = subprocess.run(
        [WINDOWS_POWERSHELL, "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), "-ScanPath", str(tmp_path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    materials = json.loads(result.stdout)
    if isinstance(materials, dict):
        materials = [materials]
    trajectory_item = next(item for item in materials if item["Kind"] == "dji-trajectory")
    assert trajectory_item["ProjectName"] == "邵武S2地块"
    assert trajectory_item["IsSelected"] is True


@pytest.mark.skipif(WINDOWS_POWERSHELL is None, reason="Windows PowerShell 5.1 is required")
def test_publisher_migrates_runtime_results_and_persists_history(tmp_path: Path):
    runtime = tmp_path / "Runtime"
    runtime.mkdir()
    first_result = runtime / "first.result.json"
    second_result = runtime / "second.result.json"
    first_result.write_text(
        json.dumps(
            {
                "success": True,
                "items": [
                    {
                        "source": r"D:\maps\block-a\tiles",
                        "kind": "tiles-b3dm",
                        "projectName": "block-a",
                        "platformPath": "/app/inbox/block-a/tiles-old",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    second_result.write_text(
        json.dumps(
            {
                "success": True,
                "items": [
                    {
                        "source": r"D:\maps\block-a\tiles",
                        "kind": "tiles-b3dm",
                        "projectName": "block-a",
                        "platformPath": "/app/inbox/block-a/tiles",
                    },
                    {
                        "source": r"D:\maps\block-b\orthophoto.tif",
                        "kind": "orthophoto",
                        "projectName": "block-b",
                        "platformPath": "/app/inbox/block-b/geotiff/orthophoto.tif",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    os.utime(first_result, (1_700_000_000, 1_700_000_000))
    os.utime(second_result, (1_700_000_100, 1_700_000_100))

    env = os.environ.copy()
    env["MAP_PUBLISHER_ASSISTANT_SCRIPT"] = str(
        ROOT / "plugins" / "smart-bamboo-map-publisher" / "scripts" / "SmartBambooMapPublisher.ps1"
    )
    env["MAP_PUBLISHER_TEST_STATE"] = str(tmp_path)
    command = (
        '[Console]::OutputEncoding = [Text.Encoding]::UTF8; '
        '& $env:MAP_PUBLISHER_ASSISTANT_SCRIPT -HistoryOnly '
        '-HistoryStateRoot $env:MAP_PUBLISHER_TEST_STATE'
    )
    result = subprocess.run(
        [
            WINDOWS_POWERSHELL,
            "-NoLogo",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            command,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    history = json.loads((tmp_path / "history.json").read_text(encoding="utf-8-sig"))
    assert len(history) == 2
    by_source = {item["SourcePath"]: item for item in history}
    assert by_source[r"D:\maps\block-a\tiles"]["PlatformPath"] == "/app/inbox/block-a/tiles"
    assert by_source[r"D:\maps\block-b\orthophoto.tif"]["TypeLabel"] == "GeoTIFF 正射影像"
    assert all(item["PublishedAt"] for item in history)

    ui_result = subprocess.run(
        [
            WINDOWS_POWERSHELL,
            "-NoLogo",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-STA",
            "-File",
            env["MAP_PUBLISHER_ASSISTANT_SCRIPT"],
            "-ValidateUi",
            "-HistoryStateRoot",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        check=False,
    )
    assert ui_result.returncode == 0, ui_result.stdout + ui_result.stderr
    assert "SMART_BAMBOO_MAP_PUBLISHER_UI_READY history=2 rows=2" in ui_result.stdout


@pytest.mark.skipif(WINDOWS_POWERSHELL is None, reason="Windows PowerShell 5.1 is required")
def test_native_stderr_banner_is_not_treated_as_publish_failure(tmp_path: Path):
    native_probe = tmp_path / "native-stderr-probe.cmd"
    native_probe.write_text(
        "@echo off\r\n"
        "echo Authorized users only. 1^>^&2\r\n"
        "echo NATIVE_PROBE_OK\r\n"
        "exit /b 0\r\n",
        encoding="ascii",
    )
    env = os.environ.copy()
    env["MAP_PUBLISHER_MATERIAL_SCRIPT"] = str(
        ROOT / "plugins" / "smart-bamboo-map-publisher" / "scripts" / "publish-material.ps1"
    )
    env["MAP_PUBLISHER_NATIVE_PROBE"] = str(native_probe)
    harness = r'''
$ErrorActionPreference = "Stop"
$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $env:MAP_PUBLISHER_MATERIAL_SCRIPT,
    [ref]$tokens,
    [ref]$parseErrors
)
if ($parseErrors.Count) { throw ($parseErrors | ForEach-Object Message | Out-String) }
$functionAst = $ast.Find({
    param($node)
    $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq "Invoke-Native"
}, $true)
if (-not $functionAst) { throw "Invoke-Native was not found." }
Invoke-Expression $functionAst.Extent.Text
$output = @(Invoke-Native $env:MAP_PUBLISHER_NATIVE_PROBE @() "probe failed" 2>&1 | ForEach-Object { $_.ToString() })
if ($output -notcontains "NATIVE_PROBE_OK") { throw "Native command output was not preserved." }
if ($output -contains "System.Management.Automation.RemoteException") { throw "Empty native stderr wrapper leaked into the log." }
'''
    result = subprocess.run(
        [WINDOWS_POWERSHELL, "-NoLogo", "-NoProfile", "-Command", harness],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.skipif(WINDOWS_POWERSHELL is None, reason="Windows PowerShell 5.1 is required")
def test_failed_archive_creation_removes_partial_same_drive_cache(tmp_path: Path):
    project = tmp_path / "block-a"
    dataset = project / "terra_b3dms"
    dataset.mkdir(parents=True)
    (dataset / "tileset.json").write_text("{}", encoding="utf-8")
    (dataset / "tile.b3dm").write_bytes(b"tile")
    key_path = tmp_path / "test-key"
    key_path.write_text("test", encoding="ascii")
    archive_cache = project / ".smart-bamboo-publish-cache"
    archive_cache.mkdir()
    (archive_cache / "abandoned.tar").write_bytes(b"abandoned")
    (archive_cache / "abandoned.tar.lock").write_text("2147483647", encoding="ascii")

    tools_dir = tmp_path / "tools"
    tools_dir.mkdir()
    marker = tmp_path / "fake-tar-invoked.txt"
    (tools_dir / "tar.cmd").write_text(
        "@echo off\r\n"
        "echo invoked>\"%MAP_PUBLISHER_FAKE_TAR_MARKER%\"\r\n"
        "> \"%~2\" echo partial-cache\r\n"
        "echo simulated tar write error 1^>^&2\r\n"
        "exit /b 1\r\n",
        encoding="ascii",
    )
    env = os.environ.copy()
    env["PATH"] = str(tools_dir) + os.pathsep + env["PATH"]
    env["MAP_PUBLISHER_FAKE_TAR_MARKER"] = str(marker)
    script = ROOT / "plugins" / "smart-bamboo-map-publisher" / "scripts" / "publish-material.ps1"
    result = subprocess.run(
        [
            WINDOWS_POWERSHELL,
            "-NoLogo",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-SourcePath",
            str(dataset),
            "-Kind",
            "tiles-b3dm",
            "-ProjectName",
            "block-a",
            "-ServerHost",
            "127.0.0.1",
            "-SshKeyPath",
            str(key_path),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        check=False,
    )
    assert result.returncode != 0
    assert marker.exists(), result.stdout + result.stderr
    assert archive_cache.is_dir()
    assert list(archive_cache.glob("*.tar")) == []
    assert list(archive_cache.glob("*.tar.lock")) == []


@pytest.mark.skipif(WINDOWS_POWERSHELL is None, reason="Windows PowerShell 5.1 is required")
def test_archive_cache_space_preflight_rejects_oversized_content(tmp_path: Path):
    env = os.environ.copy()
    env["MAP_PUBLISHER_MATERIAL_SCRIPT"] = str(
        ROOT / "plugins" / "smart-bamboo-map-publisher" / "scripts" / "publish-material.ps1"
    )
    env["MAP_PUBLISHER_TEST_CACHE"] = str(tmp_path)
    harness = r'''
$ErrorActionPreference = "Stop"
$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $env:MAP_PUBLISHER_MATERIAL_SCRIPT,
    [ref]$tokens,
    [ref]$parseErrors
)
if ($parseErrors.Count) { throw ($parseErrors | ForEach-Object Message | Out-String) }
foreach ($name in @("Format-StorageSize", "Assert-ArchiveCacheSpace")) {
    $functionAst = $ast.Find({
        param($node)
        $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq $name
    }, $true)
    if (-not $functionAst) { throw "$name was not found." }
    Invoke-Expression $functionAst.Extent.Text
}
$driveRoot = [IO.Path]::GetPathRoot([IO.Path]::GetFullPath($env:MAP_PUBLISHER_TEST_CACHE))
$available = [IO.DriveInfo]::new($driveRoot).AvailableFreeSpace
$rejected = $false
try {
    Assert-ArchiveCacheSpace $env:MAP_PUBLISHER_TEST_CACHE ($available + 1GB)
} catch {
    $rejected = $true
}
if (-not $rejected) { throw "Space preflight unexpectedly succeeded." }
'''
    result = subprocess.run(
        [WINDOWS_POWERSHELL, "-NoLogo", "-NoProfile", "-Command", harness],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.skipif(WINDOWS_POWERSHELL is None, reason="Windows PowerShell 5.1 is required")
def test_remote_activation_checks_the_expanded_stage_path():
    env = os.environ.copy()
    env["MAP_PUBLISHER_MATERIAL_SCRIPT"] = str(
        ROOT / "plugins" / "smart-bamboo-map-publisher" / "scripts" / "publish-material.ps1"
    )
    harness = r'''
$ErrorActionPreference = "Stop"
$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $env:MAP_PUBLISHER_MATERIAL_SCRIPT,
    [ref]$tokens,
    [ref]$parseErrors
)
if ($parseErrors.Count) { throw ($parseErrors | ForEach-Object Message | Out-String) }
$functionAst = $ast.Find({
    param($node)
    $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq "New-RemoteActivationScript"
}, $true)
if (-not $functionAst) { throw "New-RemoteActivationScript was not found." }
Invoke-Expression $functionAst.Extent.Text
$activation = New-RemoteActivationScript "/inbox/.incoming/project-dataset-time" "/inbox/.incoming/archive.tar" "/inbox/project/dataset" "/inbox/.releases/project/dataset-time" "terra_b3dms" "tiles-b3dm"
$expected = "test -f '/inbox/.incoming/project-dataset-time/terra_b3dms/tileset.json';"
if (-not $activation.Contains($expected)) { throw "Activation script does not check the expanded stage path: $activation" }
if ($activation.Contains("test -f '`$stage/")) { throw "Activation script still contains the literal stage variable bug." }
'''
    result = subprocess.run(
        [WINDOWS_POWERSHELL, "-NoLogo", "-NoProfile", "-Command", harness],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.skipif(WINDOWS_POWERSHELL is None, reason="Windows PowerShell 5.1 is required")
def test_blank_powershell_exception_gets_nonempty_publish_error():
    env = os.environ.copy()
    env["MAP_PUBLISHER_BATCH_SCRIPT"] = str(
        ROOT / "plugins" / "smart-bamboo-map-publisher" / "scripts" / "publish-batch.ps1"
    )
    harness = r'''
$ErrorActionPreference = "Stop"
$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $env:MAP_PUBLISHER_BATCH_SCRIPT,
    [ref]$tokens,
    [ref]$parseErrors
)
if ($parseErrors.Count) { throw ($parseErrors | ForEach-Object Message | Out-String) }
$functionAst = $ast.Find({
    param($node)
    $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq "Get-PublishErrorMessage"
}, $true)
if (-not $functionAst) { throw "Get-PublishErrorMessage was not found." }
Invoke-Expression $functionAst.Extent.Text
$record = [System.Management.Automation.ErrorRecord]::new(
    [System.Exception]::new(""),
    "NativeCommandError",
    [System.Management.Automation.ErrorCategory]::NotSpecified,
    $null
)
$message = Get-PublishErrorMessage $record
if ([string]::IsNullOrWhiteSpace($message)) { throw "Publish error message is blank." }
'''
    result = subprocess.run(
        [WINDOWS_POWERSHELL, "-NoLogo", "-NoProfile", "-Command", harness],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_map_publisher_download_endpoint_and_imagery_management_entry(app_client):
    response = app_client.get(
        "/api/v2/tools/map-publisher/download",
        headers={"X-RS-User": "publisher", "X-RS-Roles": "admin", "X-RS-Areas": "*"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert "smart-bamboo-map-publisher.zip" in response.headers["content-disposition"]

    page = (ROOT / "apps" / "web-operations" / "src" / "pages" / "ImageryAssetsPage.tsx").read_text(encoding="utf-8")
    assert "地图发布助手" in page
    assert "/api/v2/tools/map-publisher/download" in page
