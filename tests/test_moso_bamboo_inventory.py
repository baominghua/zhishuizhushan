from __future__ import annotations

from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin
from rasterio.warp import transform_geom

from server.modules.moso_bamboo_inventory import (
    analyze_rgb_orthophoto,
    estimate_from_rgb_metrics,
    merge_moso_estimate,
)


def synthetic_orthophoto(path: Path) -> dict:
    width = height = 256
    transform = from_origin(13_000_000, 3_200_000, 0.1, 0.1)
    rows, columns = np.ogrid[:height, :width]
    rgb = np.zeros((3, height, width), dtype=np.uint8)
    rgb[0] = 92
    rgb[1] = 76
    rgb[2] = 55
    for center_y in range(24, 240, 28):
        for center_x in range(24, 240, 28):
            crown = (rows - center_y) ** 2 + (columns - center_x) ** 2 <= 10**2
            rgb[0, crown] = 52 + (center_x % 20)
            rgb[1, crown] = 145 + (center_y % 30)
            rgb[2, crown] = 58
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=width,
        height=height,
        count=3,
        dtype="uint8",
        crs="EPSG:3857",
        transform=transform,
    ) as dataset:
        dataset.write(rgb)
    projected = {
        "type": "Polygon",
        "coordinates": [[
            [13_000_002, 3_199_998],
            [13_000_023, 3_199_998],
            [13_000_023, 3_199_977],
            [13_000_002, 3_199_977],
            [13_000_002, 3_199_998],
        ]],
    }
    return transform_geom("EPSG:3857", "EPSG:4326", projected)


def test_rgb_inventory_estimate_is_traceable_and_does_not_claim_volume(tmp_path: Path) -> None:
    raster_path = tmp_path / "moso.tif"
    geometry = synthetic_orthophoto(raster_path)
    metrics = analyze_rgb_orthophoto(raster_path, geometry)

    assert metrics["nativeResolutionM"] == 0.1
    assert metrics["validPixelCount"] > 10_000
    assert 10 < metrics["canopyClosurePct"] < 90
    assert metrics["crownEquivalentCount"] > 10

    estimate = estimate_from_rgb_metrics(
        {
            "id": "block-1",
            "blockCode": "GJ-001",
            "areaMu": metrics["projectedAreaM2"] / 666.6666667,
            "avgDbhCm": 9.2,
        },
        metrics,
        imagery_scene={"id": "scene-rgb", "name": "2026 正射"},
        point_cloud_scene={
            "id": "scene-las",
            "name": "2026 LAS",
            "pointCount": 1_000_000,
            "pointAttributes": ["RGB", "Intensity", "GpsTime", "ReturnNumber"],
        },
    )

    assert estimate["resourceStock"]["value"] > 0
    assert estimate["resourceStock"]["lower"] < estimate["resourceStock"]["upper"]
    assert estimate["abovegroundBiomass"]["dbhSource"] == "forest-inventory"
    assert estimate["standingVolume"]["value"] is None
    assert estimate["standingVolume"]["status"] == "requires-local-plot-calibration"
    assert estimate["pointCloudEvidence"]["available"] is True


def test_moso_estimate_history_is_preserved() -> None:
    previous = {"modelVersion": "old", "estimatedAt": "2026-01-01T00:00:00Z"}
    current = {"modelVersion": "new", "estimatedAt": "2026-08-26T00:00:00Z"}
    merged = merge_moso_estimate({"mosoInventory": previous, "other": {"kept": True}}, current)

    assert merged["mosoInventory"] == current
    assert merged["mosoInventoryHistory"][0] == previous
    assert merged["other"] == {"kept": True}


def test_estimate_endpoint_saves_trial_separately_from_formal_inventory(app_client, monkeypatch) -> None:
    created = app_client.post(
        "/api/v2/resources/forest-blocks",
        json={
            "blockCode": "MOSO-001",
            "name": "毛竹试算林班",
            "areaMu": 15,
            "standingDensity": 120,
            "avgDbhCm": 9.5,
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[117.0, 27.0], [117.01, 27.0], [117.01, 27.01], [117.0, 27.01], [117.0, 27.0]]],
            },
        },
        headers={"X-RS-Roles": "admin"},
    )
    assert created.status_code == 200, created.text
    block = created.json()
    trial = {
        "modelVersion": "test-0.1",
        "status": "trial",
        "resourceStock": {"value": 1800, "lower": 1400, "upper": 2200, "unit": "株"},
        "standingVolume": {"value": None, "unit": "m³", "status": "requires-local-plot-calibration"},
    }

    import server.app as app_module

    monkeypatch.setattr(app_module, "build_moso_inventory_estimate", lambda *_args, **_kwargs: trial)
    response = app_client.post(
        "/api/v2/ai/moso-inventory/estimate",
        json={"blockId": block["id"], "save": True},
        headers={"X-RS-Roles": "admin"},
    )
    assert response.status_code == 200, response.text
    updated = response.json()["block"]
    assert updated["yieldEstimate"]["mosoInventory"]["resourceStock"]["value"] == 1800
    assert updated["standingDensity"] == 120
    assert updated["avgDbhCm"] == 9.5
    assert response.json()["inferenceRun"]["status"] == "succeeded"
    assert response.json()["inferenceRun"]["blocks"][0]["code"] == "MOSO-001"

    model_card = app_client.get(
        "/api/v2/ai/moso-inventory/model-card",
        headers={"X-RS-Roles": "admin"},
    )
    assert model_card.status_code == 200, model_card.text
    assert model_card.json()["deploymentStatus"] == "active"

    assets = app_client.get(
        "/api/v2/ai/model-assets?q=毛竹",
        headers={"X-RS-Roles": "admin"},
    )
    assert assets.status_code == 200, assets.text
    assert {item["assetType"] for item in assets.json()["items"]} == {
        "dataset",
        "model-version",
        "deployment",
    }
