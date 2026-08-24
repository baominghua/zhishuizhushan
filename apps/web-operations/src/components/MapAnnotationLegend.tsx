import { ChevronDown, MapPinned } from "lucide-react";

import {
  MAP_ANNOTATION_GROUPS,
  MAP_ANNOTATION_LABELS,
  type MapAnnotation,
  type MapAnnotationKind,
} from "../maps/mapAnnotations";

export function MapAnnotationLegend({ annotations }: { annotations: MapAnnotation[] }) {
  const counts = annotations.reduce<Record<MapAnnotationKind, number>>((result, annotation) => {
    result[annotation.kind] += 1;
    return result;
  }, {
    camera: 0,
    helmet: 0,
    dock: 0,
    mission: 0,
    orthophoto: 0,
    pointcloud: 0,
    mesh: 0,
    demonstration: 0,
  });
  const groups = MAP_ANNOTATION_GROUPS.map((group) => ({
    ...group,
    kinds: group.kinds.filter((kind) => counts[kind] > 0),
  })).filter((group) => group.kinds.length > 0);
  if (groups.length === 0) return null;

  return (
    <details className="map-annotation-legend" open>
      <summary><MapPinned aria-hidden="true" /><span>地图图例</span><small>{annotations.length} 个点位</small><ChevronDown aria-hidden="true" /></summary>
      <div>
        {groups.map((group) => (
          <section key={group.label}>
            <strong>{group.label}</strong>
            <div>{group.kinds.map((kind) => (
              <span key={kind}><i className={`map-legend-symbol ${kind}`} /><em>{MAP_ANNOTATION_LABELS[kind]}</em><small>{counts[kind]}</small></span>
            ))}</div>
          </section>
        ))}
        <p>地图仅显示分类符号，点击符号查看名称与详情。</p>
      </div>
    </details>
  );
}
