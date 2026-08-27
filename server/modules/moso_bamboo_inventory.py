from __future__ import annotations

import math
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from PIL import Image, ImageFilter
from rasterio.enums import Resampling
from rasterio.features import geometry_mask, geometry_window
from rasterio.transform import Affine
from rasterio.warp import transform as transform_coordinates, transform_geom
from shapely.geometry import shape


MODEL_VERSION = "moso-uav-rgb-baseline-0.1"
MODEL_CODE = "moso-bamboo-uav-inventory"
MODEL_DATASET_ASSET_NO = "DS-MOSO-UAV-EVIDENCE"
MODEL_VERSION_ASSET_NO = "MV-MOSO-UAV-BASELINE-01"
MODEL_DEPLOYMENT_ASSET_NO = "DP-MOSO-UAV-PRODUCTION"
SPECIES_SCIENTIFIC_NAME = "Phyllostachys edulis"
MAX_ANALYSIS_DIMENSION = 1600
MIN_VALID_PIXELS = 256

MODEL_REFERENCES = [
    {
        "title": "Estimation method of Phyllostachys edulis forest canopy density based on UAV visible image",
        "url": "https://zlxb.zafu.edu.cn/en/article/doi/10.11833/j.issn.2095-0756.20210576",
        "use": "RGB 多尺度分割与郁闭度证据",
    },
    {
        "title": "Estimating canopy structure and biomass in bamboo forests using airborne LiDAR data",
        "url": "https://www.sciencedirect.com/science/article/pii/S0924271618303344",
        "use": "点云高度分位数与毛竹地上生物量证据",
    },
    {
        "title": "An improved YOLOv7 network achieved precise mapping of Moso bamboo stem density",
        "url": "https://www.sciencedirect.com/science/article/pii/S1470160X25013214",
        "use": "无人机单株识别及密度制图精度边界",
    },
    {
        "title": "Culm height development, biomass accumulation and carbon storage in moso bamboo",
        "url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC5430563/",
        "use": "胸径—地上生物量异速生长关系",
    },
]


class MosoInventoryError(ValueError):
    pass


def _asset_by_number(asset_no: str) -> dict[str, Any] | None:
    from server.modules.ai_model_assets import list_assets

    return next(
        (
            item
            for item in list_assets(include_deleted=True)
            if str(item.get("assetNo") or "") == asset_no
        ),
        None,
    )


def _ensure_asset(definition: dict[str, Any], *, actor: str) -> dict[str, Any]:
    from server.modules.ai_model_assets import (
        create_asset,
        set_asset_deleted,
        update_asset,
        utc_now,
    )

    existing = _asset_by_number(str(definition["assetNo"]))
    now = utc_now()
    if existing:
        if existing.get("deletedAt"):
            set_asset_deleted(str(existing["id"]), deleted=False)
            existing["deletedAt"] = None
        desired = {
            **existing,
            **definition,
            "id": str(existing["id"]),
            "createdBy": str(existing.get("createdBy") or actor),
            "createdAt": str(existing.get("createdAt") or now),
            "deletedAt": None,
        }
        compared_fields = {
            "assetType", "name", "code", "version", "status", "parentId",
            "framework", "runtimeTarget", "description", "metrics", "metadata",
        }
        if any(existing.get(field) != desired.get(field) for field in compared_fields):
            return update_asset(desired)
        return existing
    return create_asset(
        {
            **definition,
            "id": str(uuid.uuid4()),
            "createdBy": actor,
            "createdAt": now,
            "updatedAt": now,
            "deletedAt": None,
        }
    )


def ensure_moso_model_assets(*, actor: str = "system") -> dict[str, dict[str, Any]]:
    """Idempotently expose the built-in baseline in the AI model lifecycle ledger."""

    dataset = _ensure_asset(
        {
            "assetNo": MODEL_DATASET_ASSET_NO,
            "assetType": "dataset",
            "name": "毛竹无人机资源试算证据集",
            "code": f"{MODEL_CODE}-evidence",
            "version": "2026.08",
            "status": "ready",
            "parentId": "",
            "framework": "GeoTIFF / COG / LAS / COPC",
            "runtimeTarget": "智慧竹山影像资源库",
            "description": "平台现有正射影像、林班边界与同区域点云构成的可追溯试算证据集；不等同于已完成外业标注的正式训练集。",
            "metrics": {
                "evidenceTypes": ["RGB 正射", "林班边界", "点云结构证据"],
                "groundTruthStatus": "pending-local-plots",
            },
            "metadata": {
                "builtin": True,
                "species": SPECIES_SCIENTIFIC_NAME,
                "legalStatus": "trial",
            },
        },
        actor=actor,
    )
    model = _ensure_asset(
        {
            "assetNo": MODEL_VERSION_ASSET_NO,
            "assetType": "model-version",
            "name": "毛竹资源蓄积试算模型",
            "code": MODEL_CODE,
            "version": MODEL_VERSION,
            "status": "active",
            "parentId": str(dataset["id"]),
            "framework": "Rasterio / NumPy / Shapely",
            "runtimeTarget": "CPU 影像批处理",
            "description": "以 RGB 冠层分割、竹冠等价峰值和点云证据融合估算毛竹株数、密度、郁闭度与地上生物量。正式立木蓄积量仍需本地样地材积表标定。",
            "metrics": {
                "outputUnits": {"resourceStock": "株", "density": "株/亩", "biomass": "t"},
                "confidenceCeiling": 0.8,
                "standingVolume": "requires-local-plot-calibration",
            },
            "metadata": {
                "builtin": True,
                "taskType": "moso-bamboo-inventory",
                "endpoint": "/api/v2/ai/moso-inventory/estimate-batch",
                "references": MODEL_REFERENCES,
                "disclaimer": "科研试算值，不替代森林资源调查或法定蓄积量。",
            },
        },
        actor=actor,
    )
    deployment = _ensure_asset(
        {
            "assetNo": MODEL_DEPLOYMENT_ASSET_NO,
            "assetType": "deployment",
            "name": "毛竹资源试算生产部署",
            "code": f"{MODEL_CODE}-production",
            "version": MODEL_VERSION,
            "status": "active",
            "parentId": str(model["id"]),
            "framework": "FastAPI background task",
            "runtimeTarget": "智慧竹山 V2 / CPU",
            "description": "随平台应用部署的内置批处理实例，按林班裁切 COG 并将试算值回填林班档案，同时登记 AI 推理任务。",
            "metrics": {"mode": "batch", "maxBlocksPerRequest": 1000},
            "metadata": {
                "builtin": True,
                "healthEndpoint": "/api/v2/ai/moso-inventory/model-card",
                "rollback": "随应用版本回滚",
            },
        },
        actor=actor,
    )
    return {"dataset": dataset, "model": model, "deployment": deployment}


def create_moso_inference_run(
    blocks: list[dict[str, Any]],
    scenes: list[dict[str, Any]],
    *,
    actor: str,
) -> dict[str, Any]:
    from server.modules.ai_inference_runs import create_run, utc_now

    assets = ensure_moso_model_assets(actor=actor)
    now = utc_now()
    return create_run(
        {
            "id": str(uuid.uuid4()),
            "runNo": f"IR-MOSO-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}",
            "title": f"毛竹资源批量试算（{len(blocks)} 个林班）",
            "status": "queued",
            "modelAssetId": str(assets["model"]["id"]),
            "deploymentAssetId": str(assets["deployment"]["id"]),
            "findingId": "",
            "parameters": {
                "modelVersion": MODEL_VERSION,
                "blockCount": len(blocks),
                "imagerySceneCount": len(scenes),
                "mode": "existing-resource-batch",
            },
            "output": {},
            "errorMessage": "",
            "requestedAt": now,
            "startedAt": None,
            "completedAt": None,
            "durationMs": None,
            "createdBy": actor,
            "createdAt": now,
            "updatedAt": now,
            "deletedAt": None,
            "blocks": [
                {"id": str(block["id"]), "code": str(block.get("blockCode") or block["id"])}
                for block in blocks
            ],
        }
    )


def update_moso_inference_run(
    run_id: str,
    *,
    status: str,
    output: dict[str, Any] | None = None,
    error_message: str = "",
) -> dict[str, Any] | None:
    from server.modules.ai_inference_runs import run_by_id, update_run, utc_now

    record = run_by_id(run_id, include_deleted=False)
    if not record:
        return None
    now = utc_now()
    started_at = record.get("startedAt") or (now if status == "running" else None)
    completed_at = now if status in {"succeeded", "failed", "cancelled"} else None
    duration_ms = record.get("durationMs")
    if completed_at and started_at:
        try:
            completed_value = datetime.fromisoformat(completed_at)
            started_value = datetime.fromisoformat(str(started_at))
            if completed_value.tzinfo is None:
                completed_value = completed_value.replace(tzinfo=timezone.utc)
            if started_value.tzinfo is None:
                started_value = started_value.replace(tzinfo=timezone.utc)
            duration_ms = max(
                0,
                int(
                    (completed_value - started_value).total_seconds()
                    * 1000
                ),
            )
        except ValueError:
            duration_ms = None
    return update_run(
        {
            **record,
            "status": status,
            "startedAt": started_at,
            "completedAt": completed_at,
            "durationMs": duration_ms,
            "output": output if output is not None else record.get("output") or {},
            "errorMessage": error_message[:2000],
        }
    )


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def otsu_threshold(values: np.ndarray) -> float:
    finite = values[np.isfinite(values)]
    if finite.size < MIN_VALID_PIXELS:
        raise MosoInventoryError("有效 RGB 像素不足，无法进行冠层分割")
    low, high = np.percentile(finite, [1, 99])
    if not math.isfinite(float(low)) or not math.isfinite(float(high)) or high <= low:
        return float(np.median(finite))
    histogram, edges = np.histogram(np.clip(finite, low, high), bins=256, range=(low, high))
    probability = histogram.astype(np.float64) / max(1, histogram.sum())
    centers = (edges[:-1] + edges[1:]) / 2
    cumulative_probability = np.cumsum(probability)
    cumulative_mean = np.cumsum(probability * centers)
    total_mean = cumulative_mean[-1]
    denominator = cumulative_probability * (1 - cumulative_probability)
    between = np.zeros_like(denominator)
    valid = denominator > 1e-12
    between[valid] = (
        (total_mean * cumulative_probability[valid] - cumulative_mean[valid]) ** 2
        / denominator[valid]
    )
    return float(centers[int(np.argmax(between))])


def _scaled_transform(dataset: rasterio.io.DatasetReader, window: Any, width: int, height: int) -> Affine:
    return dataset.window_transform(window) * Affine.scale(window.width / width, window.height / height)


def _rgb_canopy_score(rgb: np.ndarray) -> np.ndarray:
    red, green, blue = (band.astype(np.float32) for band in rgb[:3])
    denominator = red + green + blue
    return np.divide(
        2 * green - red - blue,
        denominator,
        out=np.zeros_like(green),
        where=denominator > 1,
    )


def _crown_equivalent_peaks(
    score: np.ndarray,
    canopy_mask: np.ndarray,
    *,
    pixel_size_x: float,
    pixel_size_y: float,
    threshold: float,
) -> tuple[int, list[tuple[int, int, float]]]:
    if not np.any(canopy_mask):
        return 0, []
    finite_score = np.where(np.isfinite(score), score, threshold)
    low, high = np.percentile(finite_score[canopy_mask], [2, 98])
    scaled = np.zeros(score.shape, dtype=np.uint8)
    if high > low:
        scaled = np.clip((finite_score - low) / (high - low) * 255, 0, 255).astype(np.uint8)
    blurred = np.asarray(Image.fromarray(scaled).filter(ImageFilter.GaussianBlur(radius=1.0)))
    # The baseline operates on crown-texture peaks, not stem spacing. A 1.8 m neighbourhood
    # preserves separate Moso crown centres in the current 2--3 cm DJI orthomosaics while still
    # suppressing leaf-level texture. This parameter must be replaced by a locally fitted crown
    # diameter after field/crown labels are available.
    expected_spacing_m = 1.8
    filter_size = max(
        3,
        int(round(expected_spacing_m / max(pixel_size_x, pixel_size_y, 0.01))),
    )
    filter_size = min(filter_size, 31)
    if filter_size % 2 == 0:
        filter_size += 1
    local_maximum = np.asarray(
        Image.fromarray(blurred).filter(ImageFilter.MaxFilter(size=filter_size))
    )
    peak_floor = max(16, int(np.percentile(blurred[canopy_mask], 55)))
    candidates = canopy_mask & (blurred == local_maximum) & (blurred >= peak_floor)
    y, x = np.where(candidates)
    if not len(x):
        return 0, []
    cell_x = max(1, int(round(expected_spacing_m / max(pixel_size_x, 0.01))))
    cell_y = max(1, int(round(expected_spacing_m / max(pixel_size_y, 0.01))))
    cell_ids = (y // cell_y).astype(np.int64) * (score.shape[1] // cell_x + 2) + (x // cell_x)
    _, representative_indices = np.unique(cell_ids, return_index=True)
    total = int(len(representative_indices))
    # Keep every detected peak. A forest-block estimate normally contains only a few
    # thousand points and the evidence viewer can render them as a batched vector
    # layer. Sampling here made the map disagree with the traceable detector total.
    locations = [
        (
            int(y[index]),
            int(x[index]),
            float(np.clip((float(blurred[y[index], x[index]]) - peak_floor) / max(1, 255 - peak_floor), 0, 1)),
        )
        for index in representative_indices
    ]
    return total, locations


def analyze_rgb_orthophoto(
    raster_path: Path,
    block_geometry: dict[str, Any],
    *,
    max_dimension: int = MAX_ANALYSIS_DIMENSION,
) -> dict[str, Any]:
    if not raster_path.exists():
        raise MosoInventoryError(f"正射影像不存在：{raster_path}")
    if not block_geometry:
        raise MosoInventoryError("林班缺少空间边界")
    with rasterio.open(raster_path) as dataset:
        if dataset.count < 3:
            raise MosoInventoryError("正射影像至少需要 RGB 三个波段")
        if dataset.crs is None:
            raise MosoInventoryError("正射影像缺少坐标系")
        projected_geometry = transform_geom(
            "EPSG:4326",
            dataset.crs,
            block_geometry,
            precision=7,
        )
        try:
            window = geometry_window(dataset, [projected_geometry], pad_x=0.01, pad_y=0.01)
        except Exception as exc:
            raise MosoInventoryError("林班边界与正射影像没有有效交集") from exc
        if window.width <= 0 or window.height <= 0:
            raise MosoInventoryError("林班边界与正射影像没有有效交集")
        scale = max(1.0, window.width / max_dimension, window.height / max_dimension)
        output_width = max(1, int(round(window.width / scale)))
        output_height = max(1, int(round(window.height / scale)))
        rgb = dataset.read(
            [1, 2, 3],
            window=window,
            out_shape=(3, output_height, output_width),
            resampling=Resampling.average,
            masked=True,
        )
        output_transform = _scaled_transform(dataset, window, output_width, output_height)
        inside = geometry_mask(
            [projected_geometry],
            out_shape=(output_height, output_width),
            transform=output_transform,
            invert=True,
        )
        band_valid = ~np.any(np.ma.getmaskarray(rgb), axis=0)
        valid = inside & band_valid
        if int(valid.sum()) < MIN_VALID_PIXELS:
            raise MosoInventoryError("林班内有效 RGB 像素不足")
        score = _rgb_canopy_score(np.asarray(rgb.filled(0)))
        threshold = float(np.clip(otsu_threshold(score[valid]), -0.08, 0.18))
        canopy = valid & (score >= threshold)
        closure = float(canopy.sum() / valid.sum())
        pixel_size_x = abs(float(output_transform.a))
        pixel_size_y = abs(float(output_transform.e))
        crown_count, crown_peak_pixels = _crown_equivalent_peaks(
            score,
            canopy,
            pixel_size_x=pixel_size_x,
            pixel_size_y=pixel_size_y,
            threshold=threshold,
        )
        crown_locations: list[dict[str, float]] = []
        if crown_peak_pixels:
            rows = [row for row, _, _ in crown_peak_pixels]
            columns = [column for _, column, _ in crown_peak_pixels]
            projected_x, projected_y = rasterio.transform.xy(
                output_transform,
                rows,
                columns,
                offset="center",
            )
            longitude, latitude = transform_coordinates(
                dataset.crs,
                "EPSG:4326",
                list(projected_x),
                list(projected_y),
            )
            crown_locations = [
                {
                    "longitude": round(float(lon), 8),
                    "latitude": round(float(lat), 8),
                    "score": round(float(crown_peak_pixels[index][2]), 3),
                }
                for index, (lon, lat) in enumerate(zip(longitude, latitude, strict=True))
            ]
        projected_area_m2 = float(shape(projected_geometry).area)
        analyzed_area_m2 = float(valid.sum()) * pixel_size_x * pixel_size_y
        image_coverage_pct = min(100.0, analyzed_area_m2 / max(projected_area_m2, 1e-9) * 100)
        native_resolution = math.sqrt(abs(float(dataset.transform.a * dataset.transform.e)))
        analysis_resolution = math.sqrt(max(1e-12, pixel_size_x * pixel_size_y))
        return {
            "validPixelCount": int(valid.sum()),
            "analysisWidth": output_width,
            "analysisHeight": output_height,
            "nativeResolutionM": round(native_resolution, 4),
            "analysisResolutionM": round(analysis_resolution, 4),
            "projectedAreaM2": round(projected_area_m2, 2),
            "analyzedAreaM2": round(analyzed_area_m2, 2),
            "imageCoveragePct": round(image_coverage_pct, 2),
            "canopyClosurePct": round(closure * 100, 2),
            "canopyThreshold": round(threshold, 4),
            "crownEquivalentCount": crown_count,
            "crownCandidateLocations": crown_locations,
            "crownCandidateLocationCount": len(crown_locations),
            "crownCandidateLocationsComplete": len(crown_locations) == crown_count,
        }


def estimate_from_rgb_metrics(
    block: dict[str, Any],
    rgb_metrics: dict[str, Any],
    *,
    imagery_scene: dict[str, Any],
    point_cloud_scene: dict[str, Any] | None = None,
) -> dict[str, Any]:
    area_mu = float(block.get("areaMu") or 0)
    if area_mu <= 0:
        area_mu = float(rgb_metrics.get("projectedAreaM2") or 0) / 666.6666667
    if area_mu <= 0:
        raise MosoInventoryError("林班面积无效")
    area_ha = area_mu / 15
    raw_crown_count = max(0, int(rgb_metrics.get("crownEquivalentCount") or 0))
    image_coverage_ratio = min(1.0, max(0.0, float(rgb_metrics.get("imageCoveragePct") or 100) / 100))
    if image_coverage_ratio < 0.5:
        raise MosoInventoryError("正射影像有效覆盖不足林班面积的 50%，请补齐影像后再试算")
    crown_count = int(round(raw_crown_count / image_coverage_ratio)) if image_coverage_ratio else 0
    raw_density_ha = crown_count / area_ha if area_ha else 0
    # The detector is intentionally bounded to a broad managed/natural Moso range. Values outside
    # this interval signal that the RGB-only baseline needs local labels rather than being reported
    # as implausible precision.
    density_ha = min(7000.0, max(500.0, raw_density_ha)) if crown_count else 0.0
    estimated_culms = int(round(density_ha * area_ha))
    lower_culms = int(round(estimated_culms * 0.72))
    upper_culms = int(round(estimated_culms * 1.28))

    avg_dbh = block.get("avgDbhCm")
    dbh_source = "forest-inventory" if avg_dbh not in (None, "") else "research-prior"
    dbh_cm = float(avg_dbh) if avg_dbh not in (None, "") else 8.9
    biomass_per_culm_kg = 0.0171 * (dbh_cm**3.03)
    biomass_tonnes = estimated_culms * biomass_per_culm_kg / 1000
    biomass_low = lower_culms * 0.0171 * ((dbh_cm * (0.92 if dbh_source == "forest-inventory" else 0.80)) ** 3.03) / 1000
    biomass_high = upper_culms * 0.0171 * ((dbh_cm * (1.08 if dbh_source == "forest-inventory" else 1.20)) ** 3.03) / 1000

    closure = float(rgb_metrics.get("canopyClosurePct") or 0)
    point_evidence = point_cloud_scene is not None
    confidence_score = 0.38
    confidence_reasons = ["使用林班内 RGB 有效像素进行冠层分割"]
    if float(rgb_metrics.get("nativeResolutionM") or 99) <= 0.05:
        confidence_score += 0.14
        confidence_reasons.append("正射地面分辨率优于 5 cm")
    if image_coverage_ratio < 0.95:
        confidence_score -= 0.10
        confidence_reasons.append(f"影像仅覆盖林班约 {image_coverage_ratio * 100:.1f}%，按覆盖区外推")
    if point_evidence:
        confidence_score += 0.10
        confidence_reasons.append("存在同区域 RGB/多回波点云，可用于后续结构校准")
    if dbh_source == "forest-inventory":
        confidence_score += 0.12
        confidence_reasons.append("林班已有平均胸径调查值")
    else:
        confidence_reasons.append("平均胸径暂用科研先验，尚未本地样地标定")
    if 35 <= closure <= 100:
        confidence_score += 0.06
    confidence_score = min(0.80, confidence_score)
    confidence_level = "中" if confidence_score >= 0.58 else "低"

    point_attributes = []
    if point_cloud_scene:
        point_attributes = list(
            point_cloud_scene.get("pointAttributes")
            or point_cloud_scene.get("attributeModes")
            or point_cloud_scene.get("dimensions")
            or []
        )
    return {
        "modelVersion": MODEL_VERSION,
        "status": "trial",
        "species": "毛竹",
        "scientificName": SPECIES_SCIENTIFIC_NAME,
        "estimatedAt": utc_now_iso(),
        "blockArea": {"value": round(area_mu, 2), "unit": "亩"},
        "canopyClosure": {"value": round(closure, 2), "unit": "%"},
        "crownEquivalentCount": {"value": crown_count, "raw": raw_crown_count, "unit": "个"},
        "crownCandidateLocations": list(rgb_metrics.get("crownCandidateLocations") or []),
        "crownCandidateLocationCount": int(rgb_metrics.get("crownCandidateLocationCount") or 0),
        "crownCandidateLocationsComplete": bool(rgb_metrics.get("crownCandidateLocationsComplete", False)),
        "resourceStock": {
            "value": estimated_culms,
            "lower": lower_culms,
            "upper": upper_culms,
            "unit": "株",
            "label": "毛竹资源株数模型估算",
            "basis": "由正射影像竹冠等价峰值、有效覆盖率和林班面积推算；不是外业逐株清点",
        },
        "stemDensity": {
            "value": round(density_ha / 15, 1),
            "lower": round(density_ha * 0.72 / 15, 1),
            "upper": round(density_ha * 1.28 / 15, 1),
            "unit": "株/亩",
        },
        "abovegroundBiomass": {
            "value": round(biomass_tonnes, 2),
            "lower": round(biomass_low, 2),
            "upper": round(biomass_high, 2),
            "unit": "t",
            "dbhCm": round(dbh_cm, 2),
            "dbhSource": dbh_source,
        },
        "standingVolume": {
            "value": None,
            "unit": "m³",
            "status": "requires-local-plot-calibration",
            "reason": "毛竹为空心竹秆，RGB 无法直接反演胸径和竹壁厚；需用本地样地材积表或竹秆形数标定后计算正式蓄积量。",
        },
        "confidence": {
            "score": round(confidence_score, 2),
            "level": confidence_level,
            "reasons": confidence_reasons,
        },
        "imageryEvidence": {
            "sceneId": imagery_scene.get("id"),
            "name": imagery_scene.get("name"),
            "capturedAt": imagery_scene.get("capturedAt") or None,
            **rgb_metrics,
        },
        "pointCloudEvidence": {
            "available": point_evidence,
            "sceneId": point_cloud_scene.get("id") if point_cloud_scene else None,
            "name": point_cloud_scene.get("name") if point_cloud_scene else None,
            "pointCount": point_cloud_scene.get("pointCount") if point_cloud_scene else None,
            "attributes": point_attributes,
            "heightNormalized": False,
            "note": "当前 DJI LAS 分类码未区分地面/植被；需 SMRF/CSF 地面分类后再生成冠层高度模型。"
            if point_evidence
            else "未匹配到同区域点云。",
        },
        "method": {
            "name": "RGB 多尺度冠层分割 + 竹冠等价峰值 + 点云证据融合基线",
            "assumption": "当前纳入试算的林班已由业务确认主要竹种为毛竹。",
            "references": MODEL_REFERENCES,
        },
        "disclaimer": "科研试算值，不替代森林资源二类调查、样地每木检尺或法定蓄积量。",
    }


def merge_moso_estimate(existing_yield_estimate: Any, estimate: dict[str, Any]) -> dict[str, Any]:
    merged = dict(existing_yield_estimate) if isinstance(existing_yield_estimate, dict) else {}
    history = list(merged.get("mosoInventoryHistory") or [])
    previous = merged.get("mosoInventory")
    if isinstance(previous, dict):
        history.insert(0, previous)
    merged["mosoInventory"] = estimate
    merged["mosoInventoryHistory"] = history[:12]
    return merged
