import { ScanSearch } from "lucide-react";

import type { ImageryAsset } from "../api/types";
import type { MapViewMetrics } from "../maps/scene";

function formatResolution(value: number) {
  if (!Number.isFinite(value) || value <= 0) return "待识别";
  if (value < 0.01) return `${Math.round(value * 1000)} 毫米/像素`;
  if (value < 1) return `${value.toFixed(2)} 米/像素`;
  return `${value.toFixed(value < 10 ? 1 : 0)} 米/像素`;
}

function clarityState(metrics: MapViewMetrics, asset?: ImageryAsset) {
  const source = Number(asset?.metresPerPixel || 0);
  if (!source) return { tone: "unknown", text: "原图分辨率待识别", ratio: 0 };
  const ratio = source / Math.max(metrics.metresPerPixel, 0.000001);
  if (ratio >= 1.15) return { tone: "overzoom", text: `数字放大 ${ratio.toFixed(1)}×，不会增加真实细节`, ratio };
  if (ratio >= 0.72) return { tone: "native", text: "已接近原图最佳细节", ratio };
  return { tone: "available", text: "仍有更高清层级可加载", ratio };
}

export function ImageClarityStatus({ metrics, asset }: { metrics: MapViewMetrics | null; asset?: ImageryAsset }) {
  if (!metrics) return null;
  const state = clarityState(metrics, asset);
  return (
    <div className={`image-clarity-status ${state.tone}`} aria-live="polite">
      <ScanSearch aria-hidden="true" />
      <div>
        <strong>Z {metrics.zoom.toFixed(1)}</strong>
        <span>当前 {formatResolution(metrics.metresPerPixel)}</span>
        {asset?.metresPerPixel ? <span>原图 {formatResolution(asset.metresPerPixel)}</span> : null}
        {asset?.maximumZoom != null ? <span>有效上限 Z {asset.maximumZoom}</span> : null}
      </div>
      <small>{state.text}</small>
    </div>
  );
}
