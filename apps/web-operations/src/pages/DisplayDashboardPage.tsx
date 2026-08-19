import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import {
  Activity,
  Battery,
  Building2,
  Camera,
  Check,
  CircleDollarSign,
  Clock3,
  Expand,
  Globe2,
  HardHat,
  Leaf,
  Map as MapIcon,
  MapPinned,
  Minimize,
  MonitorCog,
  PanelLeftClose,
  PanelLeftOpen,
  PanelRightClose,
  PanelRightOpen,
  Plane,
  Play,
  Radio,
  RefreshCw,
  Route,
  Search,
  ShieldAlert,
  SlidersHorizontal,
  Trees,
  UsersRound,
  Warehouse,
  Wifi,
  X,
  type LucideIcon,
} from "lucide-react";
import { useEffect, useMemo, useState, type ReactNode } from "react";

import { api } from "../api/client";
import type { CockpitMetric, CockpitRankingItem, ForestBlockFeatureCollection, ForestBlockGeometry, ForestBlockOption, SituationAssetKind, SituationAssetRecord } from "../api/types";
import { MapCanvas, type MapSituationAsset } from "../components/MapCanvas";
import { createMapScene, DEFAULT_MAP_LAYERS, DEFAULT_MAP_VIEWPORT, type MapViewport, type MapViewMode } from "../maps/scene";

const EMPTY_FEATURES: ForestBlockFeatureCollection = {
  type: "FeatureCollection",
  meta: { total: 0, returned: 0, maxFeatures: 0, truncated: false, zoom: 10, geometryMode: "full", simplificationTolerance: 0 },
  features: [],
};

const OVERVIEW_METRICS: Array<[string, string, LucideIcon]> = [
  ["forestAreaMu", "竹林资源面积", Trees],
  ["forestBlockCount", "正式林班", MapPinned],
  ["annualYieldTons", "年度预测产量", Activity],
  ["annualOutputValue", "年度预计产值", CircleDollarSign],
];

const CARBON_METRICS: Array<[string, string, LucideIcon]> = [
  ["totalCarbonStock", "碳储量", Trees],
  ["annualSequestration", "年度碳汇量", Leaf],
  ["projectCount", "碳汇项目", Activity],
  ["ccerRegisteredAmount", "CCER 核证量", ShieldAlert],
];

const KIND_LABELS: Record<SituationAssetKind, string> = { camera: "高位卡口", helmet: "安全帽", dock: "无人机机巢", mission: "无人机任务" };

function geometryAnchor(geometry: ForestBlockGeometry | null): [number, number] | null {
  if (!geometry) return null;
  const polygons = geometry.type === "Polygon" ? [geometry.coordinates] : geometry.coordinates;
  const rings = polygons
    .map((polygon) => (polygon as unknown[][])[0] as unknown[] | undefined)
    .filter((ring): ring is unknown[] => Array.isArray(ring) && ring.length >= 3);
  let bestArea = 0;
  let bestLongitude: number | null = null;
  let bestLatitude: number | null = null;
  rings.forEach((ring) => {
    const points = ring.filter((point): point is number[] => Array.isArray(point) && point.length >= 2);
    let crossSum = 0;
    let longitudeSum = 0;
    let latitudeSum = 0;
    for (let index = 0; index < points.length; index += 1) {
      const current = points[index];
      const next = points[(index + 1) % points.length];
      const cross = current[0] * next[1] - next[0] * current[1];
      crossSum += cross;
      longitudeSum += (current[0] + next[0]) * cross;
      latitudeSum += (current[1] + next[1]) * cross;
    }
    if (Math.abs(crossSum) < 1e-12) return;
    const area = Math.abs(crossSum / 2);
    if (area > bestArea) {
      bestArea = area;
      bestLongitude = longitudeSum / (3 * crossSum);
      bestLatitude = latitudeSum / (3 * crossSum);
    }
  });
  return bestLongitude !== null && bestLatitude !== null ? [bestLongitude, bestLatitude] : null;
}

export function DisplayDashboardPage() {
  const [now, setNow] = useState(() => new Date());
  const [topic, setTopic] = useState<"overview" | "carbon">("overview");
  const [fullscreen, setFullscreen] = useState(Boolean(document.fullscreenElement));
  const [mode, setMode] = useState<MapViewMode>("2d");
  const [leftRailOpen, setLeftRailOpen] = useState(true);
  const [rightRailOpen, setRightRailOpen] = useState(true);
  const [filterOpen, setFilterOpen] = useState(false);
  const [searchDraft, setSearchDraft] = useState("");
  const [searchKeyword, setSearchKeyword] = useState("");
  const [visibleKinds, setVisibleKinds] = useState<Record<SituationAssetKind, boolean>>({ camera: true, helmet: true, dock: true, mission: true });
  const [selectedSituationAsset, setSelectedSituationAsset] = useState<SituationAssetRecord | null>(null);
  const [cameraPlaying, setCameraPlaying] = useState(true);
  const [selectedBlockId, setSelectedBlockId] = useState<string | null>(null);
  const [viewport, setViewport] = useState<MapViewport>(DEFAULT_MAP_VIEWPORT);
  const dashboard = useQuery({ queryKey: ["display-dashboard"], queryFn: api.leadershipCockpit, refetchInterval: 60_000 });
  const mapConfig = useQuery({ queryKey: ["map-config"], queryFn: api.mapConfig, staleTime: 60_000 });
  const situationLedger = useQuery({ queryKey: ["display-situation-assets"], queryFn: api.situationAssets, refetchInterval: 30_000 });
  const mapBlocks = useQuery({
    queryKey: ["display-map-blocks", viewport.bbox.join(","), viewport.zoom, searchKeyword],
    queryFn: () => api.forestBlockMap({ bbox: viewport.bbox.join(","), zoom: viewport.zoom, maxFeatures: 2500, q: searchKeyword || undefined }),
    enabled: mode === "3d",
    staleTime: 30_000,
    placeholderData: (previous) => previous,
  });
  const situationBlocks = useQuery({
    queryKey: ["display-situation-blocks", viewport.bbox.join(","), viewport.zoom],
    queryFn: () => api.forestBlockMap({ bbox: viewport.bbox.join(","), zoom: viewport.zoom, maxFeatures: 2500 }),
    staleTime: 30_000,
    placeholderData: (previous) => previous,
  });
  const selectedBlock = useQuery({
    queryKey: ["display-block", selectedBlockId],
    queryFn: () => api.forestBlockDetail(selectedBlockId!),
    enabled: Boolean(selectedBlockId),
  });
  const blockSearch = useQuery({
    queryKey: ["display-block-search", searchDraft],
    queryFn: () => api.forestBlocks({ q: searchDraft.trim(), limit: 8 }),
    enabled: filterOpen && searchDraft.trim().length > 0,
    staleTime: 30_000,
  });
  const scene = useMemo(() => createMapScene(null), []);
  const data = dashboard.data;
  const metrics = topic === "overview" ? OVERVIEW_METRICS : CARBON_METRICS;
  const ranking = (data?.carbon.districtRanking ?? []) as CockpitRankingItem[];
  const visibleSituationRecords = useMemo(
    () => (situationLedger.data?.items ?? []).filter((asset) => visibleKinds[asset.kind] && (!searchKeyword || `${asset.name} ${asset.subtitle} ${asset.blockCode} ${KIND_LABELS[asset.kind]}`.includes(searchKeyword))),
    [searchKeyword, situationLedger.data, visibleKinds],
  );
  const situationAssets = useMemo<MapSituationAsset[]>(() => {
    const featuresByCode = new Map(
      (situationBlocks.data?.features ?? []).map((feature) => [feature.properties.blockCode, feature]),
    );
    return visibleSituationRecords.flatMap((asset) => {
      const anchor = asset.longitude !== null && asset.latitude !== null
        ? [asset.longitude, asset.latitude] as [number, number]
        : geometryAnchor(featuresByCode.get(asset.blockCode)?.geometry ?? null);
      return anchor ? [{ id: asset.id, kind: asset.kind, label: asset.name, longitude: anchor[0], latitude: anchor[1] }] : [];
    });
  }, [situationBlocks.data, visibleSituationRecords]);

  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 1_000);
    const updateFullscreen = () => setFullscreen(Boolean(document.fullscreenElement));
    document.addEventListener("fullscreenchange", updateFullscreen);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener("fullscreenchange", updateFullscreen);
    };
  }, []);

  async function toggleFullscreen() {
    if (document.fullscreenElement) await document.exitFullscreen();
    else await document.documentElement.requestFullscreen();
  }

  function refreshAll() {
    dashboard.refetch();
    mapConfig.refetch();
  }

  function applySearch() {
    setSearchKeyword(searchDraft.trim());
  }

  function resetSearch() {
    setSearchDraft("");
    setSearchKeyword("");
    setVisibleKinds({ camera: true, helmet: true, dock: true, mission: true });
  }

  function selectSearchResult(block: ForestBlockOption) {
    setSelectedBlockId(block.id);
    setSearchDraft(block.name || block.code);
    setSearchKeyword(block.name || block.code);
    setFilterOpen(false);
  }

  return (
    <main className="display-dashboard">
      <header className="display-header">
        <Link className="display-brand" to="/workspace" aria-label="返回工作台"><span>竹</span><strong>南平市智慧竹山综合运营平台</strong></Link>
        <nav className="display-topic-tabs" aria-label="大屏专题">
          <button className={topic === "overview" ? "active" : ""} type="button" onClick={() => setTopic("overview")}>综合态势</button>
          <button className={topic === "carbon" ? "active" : ""} type="button" onClick={() => setTopic("carbon")}>碳汇专题</button>
        </nav>
        <div className="display-head-actions">
          <time><Clock3 aria-hidden="true" />{now.toLocaleString("zh-CN", { hour12: false })}</time>
          <span className={dashboard.isError ? "offline" : "online"}><i />{dashboard.isError ? "数据异常" : "数据在线"}</span>
          <Link className="display-admin-link" to="/workspace"><MonitorCog /><span>进入运营后台</span></Link>
          <button type="button" onClick={toggleFullscreen} title={fullscreen ? "退出全屏" : "进入全屏"} aria-label={fullscreen ? "退出全屏" : "进入全屏"}>{fullscreen ? <Minimize /> : <Expand />}</button>
          <button type="button" onClick={refreshAll} title="刷新数据" aria-label="刷新数据"><RefreshCw /></button>
        </div>
      </header>

      <section className={`display-body ${leftRailOpen ? "left-rail-open" : ""} ${rightRailOpen ? "right-rail-open" : ""}`}>
        <aside className={`display-rail display-left-rail ${leftRailOpen ? "" : "is-collapsed"}`} aria-hidden={!leftRailOpen}>
          <RailHeading action={<button type="button" onClick={() => setLeftRailOpen(false)} title="收起左侧看板" aria-label="收起左侧看板"><PanelLeftClose /></button>}>竹林资源概况</RailHeading>
          <div className="display-metrics">
            {metrics.map(([key, label, icon]) => <DisplayMetric key={key} icon={icon} label={label} metric={(topic === "overview" ? data?.overview[key] : data?.carbon[key]) as CockpitMetric | undefined} />)}
          </div>
          <div className="display-legend">
            <strong>图例</strong><span><i className="normal" />林班边界</span><span><i className="risk" />风险林班</span><span><i className="selected" />当前选中</span>
          </div>
        </aside>

        <section className="display-map" aria-label="竹林资源 GIS 态势图">
          {!leftRailOpen && <button className="display-rail-reopen left" type="button" onClick={() => setLeftRailOpen(true)} title="展开左侧看板" aria-label="展开左侧看板"><PanelLeftOpen /></button>}
          {!rightRailOpen && <button className="display-rail-reopen right" type="button" onClick={() => setRightRailOpen(true)} title="展开右侧看板" aria-label="展开右侧看板"><PanelRightOpen /></button>}
          <div className="display-map-mode" aria-label="地图视角">
            <button className={mode === "2d" ? "active" : ""} type="button" onClick={() => setMode("2d")} aria-pressed={mode === "2d"}><MapIcon /><span>二维</span></button>
            <button className={mode === "3d" ? "active" : ""} type="button" onClick={() => setMode("3d")} aria-pressed={mode === "3d"}><Globe2 /><span>三维</span></button>
          </div>
          <button className={`display-filter-trigger ${filterOpen ? "active" : ""}`} type="button" onClick={() => setFilterOpen((current) => !current)} aria-expanded={filterOpen} aria-controls="display-map-filter"><SlidersHorizontal /><span>搜索筛选</span>{searchKeyword && <i />}</button>
          {filterOpen && <section className="display-map-filter" id="display-map-filter" aria-label="地图搜索筛选">
            <header><strong>搜索与图层</strong><button type="button" onClick={() => setFilterOpen(false)} aria-label="关闭搜索筛选"><X /></button></header>
            <form onSubmit={(event) => { event.preventDefault(); applySearch(); }}>
              <label><Search /><input value={searchDraft} onChange={(event) => setSearchDraft(event.target.value)} placeholder="林班编号、名称、乡镇或设备" autoFocus /></label>
              <button type="submit">搜索</button>
            </form>
            {searchDraft.trim() && <div className="display-search-results">
              {blockSearch.isLoading && <span>正在检索正式林班</span>}
              {(blockSearch.data?.items ?? []).map((block) => <button key={block.id} type="button" onClick={() => selectSearchResult(block)}><span><strong>{block.name}</strong><small>{block.code} · {block.location || "区划待补"}</small></span><MapPinned /></button>)}
              {!blockSearch.isLoading && blockSearch.data?.items.length === 0 && <span>未找到匹配的正式林班</span>}
            </div>}
            <fieldset><legend>设备与任务图层</legend>{(Object.keys(KIND_LABELS) as SituationAssetKind[]).map((kind) => <label key={kind}><input type="checkbox" checked={visibleKinds[kind]} onChange={() => setVisibleKinds((current) => ({ ...current, [kind]: !current[kind] }))} /><span><Check />{KIND_LABELS[kind]}</span></label>)}</fieldset>
            <footer><button type="button" onClick={resetSearch}>重置</button><small>正式林班筛选会同步到 GIS 查询</small></footer>
          </section>}
          <MapCanvas
            config={mapConfig.data}
            loading={mapConfig.isLoading}
            mode={mode}
            scene={scene}
            layers={{ ...DEFAULT_MAP_LAYERS, imagery: true, labels: true, forestBlocks: true, droneImagery: false }}
            homeRequest={0}
            zoomRequest={{ sequence: 0, direction: "in" }}
            areaFocusRequest={{ sequence: 0, bbox: DEFAULT_MAP_VIEWPORT.bbox }}
            featureCollection={mode === "3d" ? mapBlocks.data ?? EMPTY_FEATURES : EMPTY_FEATURES}
            selectedBlockId={selectedBlockId}
            onSelectBlock={setSelectedBlockId}
            onViewportChange={setViewport}
            imageryAssets={[]}
            spatial3dAssets={[]}
            forestBlockFilterQuery={searchKeyword ? new URLSearchParams({ q: searchKeyword }).toString() : ""}
            situationAssets={situationAssets}
            onSelectSituationAsset={(id) => {
              const asset = visibleSituationRecords.find((item) => item.id === id);
              if (asset) {
                setSelectedSituationAsset(asset);
                setCameraPlaying(true);
              }
            }}
          />
          <div className="display-map-title"><span>竹林资源一张图</span><small>{mode === "3d" ? "三维地球" : "二维地图"} · 当前层级 {viewport.zoom} · 点击林班查看空间台账</small></div>
          <div className="display-demo-note"><Radio /><span>设备态势数据</span><small>{situationLedger.data?.total ?? 0} 条后台台账记录</small></div>
          {selectedBlockId && <article className="display-block-popover">
            <button type="button" onClick={() => setSelectedBlockId(null)} aria-label="关闭林班详情"><X /></button>
            {selectedBlock.isLoading ? <p>正在读取林班详情</p> : selectedBlock.data ? <>
              <small>当前林班</small><h2>{selectedBlock.data.name || selectedBlock.data.blockCode}</h2>
              <dl><div><dt>林班编号</dt><dd>{selectedBlock.data.blockCode}</dd></div><div><dt>行政区划</dt><dd>{[selectedBlock.data.townName, selectedBlock.data.villageName].filter(Boolean).join(" / ") || "未填写"}</dd></div><div><dt>面积</dt><dd>{selectedBlock.data.areaMu ?? "--"} 亩</dd></div><div><dt>风险等级</dt><dd>{selectedBlock.data.riskLevel || "未填写"}</dd></div></dl>
              <a href={`/v2/map?blockId=${encodeURIComponent(selectedBlock.data.id)}`}>进入 GIS 详情</a>
            </> : <p>该林班详情暂时无法读取</p>}
          </article>}
        </section>

        <aside className={`display-rail display-right-rail ${rightRailOpen ? "" : "is-collapsed"}`} aria-hidden={!rightRailOpen}>
          <RailHeading action={<button type="button" onClick={() => setRightRailOpen(false)} title="收起右侧看板" aria-label="收起右侧看板"><PanelRightClose /></button>}>运行监测</RailHeading>
          <div className="display-operations">
            <Operation icon={ShieldAlert} label="安全事件" metric={data?.operations.openSafetyEvents} tone="amber" />
            <Operation icon={Plane} label="无人机任务" metric={data?.operations.activeDroneMissions} tone="cyan" />
            <Operation icon={Leaf} label="年度碳汇量" metric={data?.carbon.annualSequestration as CockpitMetric | undefined} tone="green" />
          </div>
          <RailHeading>区划碳汇排名</RailHeading>
          {ranking.length ? <div className="display-ranking">{ranking.slice(0, 5).map((item, index) => <div key={item.name}><b>{String(index + 1).padStart(2, "0")}</b><span>{item.name}</span><em>{item.annualSequestration.toLocaleString("zh-CN")} tCO₂e</em></div>)}</div> : <div className="display-empty"><Leaf /><strong>暂无排名数据</strong><span>碳汇项目关联林班后自动汇总</span></div>}
        </aside>
      </section>

      {selectedSituationAsset && <SituationAssetDialog asset={selectedSituationAsset} playing={cameraPlaying} onTogglePlaying={() => setCameraPlaying((current) => !current)} onClose={() => setSelectedSituationAsset(null)} />}

      <footer className="display-footer">
        <strong>运行动态</strong><span className="display-ticker"><i />数据范围：{data?.scope.areas.includes("*") ? "全市" : data?.scope.areas.join("、") || "读取中"}</span><span>林班、经营、安全、碳汇数据统一汇聚</span><time>数据时间：{data ? new Date(data.asOf).toLocaleString("zh-CN", { hour12: false }) : "同步中"}</time>
      </footer>
    </main>
  );
}

function SituationAssetIcon({ kind }: { kind: SituationAssetKind }) {
  if (kind === "camera") return <Camera />;
  if (kind === "helmet") return <HardHat />;
  if (kind === "dock") return <Warehouse />;
  return <Plane />;
}

function SituationAssetDialog({ asset, playing, onTogglePlaying, onClose }: { asset: SituationAssetRecord; playing: boolean; onTogglePlaying: () => void; onClose: () => void }) {
  return <div className="display-device-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <section className="display-device-dialog" role="dialog" aria-modal="true" aria-labelledby="display-device-title">
      <header><span><SituationAssetIcon kind={asset.kind} /></span><div><small>{KIND_LABELS[asset.kind]} · 后台台账</small><h2 id="display-device-title">{asset.name}</h2><p>{asset.subtitle}</p></div><button type="button" onClick={onClose} aria-label="关闭设备详情"><X /></button></header>
      {asset.kind === "camera" && <div className={`display-camera-feed ${playing ? "is-playing" : "is-paused"}`}>
        <div className="camera-feed-scene"><Trees /><span className="camera-road" /><span className="camera-person"><UsersRound /></span></div>
        <div className="camera-feed-top"><span><i />LIVE</span><time>{new Date().toLocaleString("zh-CN", { hour12: false })}</time></div>
        <button type="button" onClick={onTogglePlaying}><Play />{playing ? "暂停画面" : "继续播放"}</button>
        <small>实时视频播放窗口为界面示范，接入 RTSP/GB28181 后替换为真实码流。</small>
      </div>}
      {asset.kind === "helmet" && <div className="display-track-preview"><Route /><div><strong>实时移动轨迹</strong><span>北向巡护路线 · 最近 28 分钟</span></div><svg viewBox="0 0 420 90" preserveAspectRatio="none" aria-hidden="true"><path d="M8 72 C65 28 112 64 165 38 S254 14 303 49 S361 76 412 18" /><circle cx="412" cy="18" r="6" /></svg></div>}
      {asset.kind === "mission" && <div className="display-mission-progress"><Plane /><span><i style={{ width: "68%" }} /></span><strong>68%</strong><small>任务航线持续回传中</small></div>}
      {asset.kind === "dock" && <div className="display-dock-status"><Warehouse /><div><strong>机巢待命正常</strong><span><Wifi />通信在线</span><span><Battery />充电 92%</span></div></div>}
      <dl>{asset.parameters.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>
      <footer><span className={`display-device-status ${asset.status === "在线" || asset.status === "作业中" || asset.status === "飞行中" ? "online" : ""}`}><i />{asset.status}</span><a href={asset.managementPath}>打开后台台账</a></footer>
    </section>
  </div>;
}

function RailHeading({ children, action }: { children: string; action?: ReactNode }) { return <div className="display-rail-heading"><h2>{children}</h2>{action}</div>; }
function DisplayMetric({ icon: Icon, label, metric }: { icon: LucideIcon; label: string; metric?: CockpitMetric }) { return <article className="display-metric"><Icon /><span>{label}</span><strong>{metric?.available ? Number(metric.value || 0).toLocaleString("zh-CN") : "暂无数据"}</strong><small>{metric?.available ? `${metric.unit} · ${metric.source}` : "等待正式数据源"}</small></article>; }
function Operation({ icon: Icon, label, metric, tone }: { icon: LucideIcon; label: string; metric?: CockpitMetric; tone: string }) { return <article className={`display-operation ${tone}`}><Icon /><span>{label}</span><strong>{metric?.available ? `${metric.value || 0} ${metric.unit}` : "暂无数据"}</strong><small>{metric?.source || "等待正式数据源"}</small></article>; }
