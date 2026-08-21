from __future__ import annotations

import io
import os
import shutil
import subprocess
import zipfile
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
        assert '$previousErrorActionPreference = $ErrorActionPreference' in material_script
        assert '$ErrorActionPreference = "Continue"' in material_script
        assert "$nativeExitCode = $LASTEXITCODE" in material_script
        assert "New-RemoteActivationScript" in material_script
        assert '"test -f \'$requiredPath/tileset.json\';"' in material_script
        assert "Get-PublishErrorMessage" in batch_script
        assert "error = $errorMessage" in batch_script


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
