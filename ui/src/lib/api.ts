import type { ModuleOEnvelope } from "./types";

export const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

// 정적 AOI 타일(위성·벡터)의 호스트. Vercel 배포 용량 때문에 `ui/public/tiles`와
// `ui/public/satellite`(합계 744MB)는 `.vercelignore`로 배포에서 빼고 백엔드(EC2 Caddy)가
// 대신 서빙한다 — Vercel은 배포할 때마다 정적 파일을 통째로 새로 저장하기 때문에,
// 같은 744MB가 배포 횟수만큼 쌓여 10GB 한도를 넘겼다(2026-09-19).
// 미설정이면 같은 오리진(= `ui/public` 그대로)을 쓰므로 로컬 `npm run dev`는 그대로 돈다.
export function tileBase(): string {
  return process.env.NEXT_PUBLIC_TILE_BASE ?? window.location.origin;
}

export interface TriggerInput {
  alert_id: string;
  trigger_location: { x_5179: number; y_5179: number };
  timestamp: string;
  escalation_timeout_min?: number;
  safety_margin_hours?: number;
  // 실모듈이 붙은 뒤로 A/B는 좌표만으로는 계산하지 못한다 — 관측 static/dynamic이
  // 있어야 FoS와 수위가 나온다. 서버의 TriggerRequest도 같은 필드를 받는다.
  module_a_extra?: Record<string, unknown>;
  module_b_extra?: Record<string, unknown>;
  reach_id?: string;
  underpasses?: Record<string, unknown>[];
  detection_lag_min?: number;
}

// §9 데모 시나리오: 2025.7.19 산청 산사태 재연.
// contracts/module_o.example.json의 input과 같은 값이다 — 한쪽만 고치면 화면과
// 계약 예시가 어긋나므로 둘을 함께 바꿀 것.
//
// trigger_location은 트랙①이 사전계산한 위험영역(A_soilmap critical)에서 가장 큰
// 폴리곤의 대표지점이다(risk_landslide_index.json). 임의 좌표가 아니라 모형이 실제로
// 위험하다고 판정한 지점이며, 안정 지반을 찍으면 확률이 0.002로 떨어져 아무것도
// 트리거되지 않는다.
// detection_lag_min=60은 트랙①의 산청 백테스트가 실측한 T_agent(09:00)에 맞춘 값
// (backtest_sancheong/outputs/backtest_leadtime_summary.json).
export const SANGCHEONG_DEMO_INPUT: TriggerInput = {
  alert_id: "AL-20250719-0915",
  trigger_location: { x_5179: 1046783.0, y_5179: 1707543.0 },
  timestamp: "2025-07-19T08:00:00+09:00",
  escalation_timeout_min: 15,
  safety_margin_hours: 0.5,
  detection_lag_min: 60,
  module_a_extra: {
    static: {
      slope_deg: 32.5,
      curvature: -0.02,
      twi: 6.8,
      aspect_deg: 210,
      dnbr: 0.62,
      dnbr_class: "high",
      days_since_fire: 121,
    },
    dynamic: {
      rainfall_1h_mm: [12.0, 18.5, 24.0],
      rainfall_cumulative_24h_mm: 187.3,
      rainfall_cumulative_72h_mm: 245.0,
      api_index: 0.81,
      source: "observed",
    },
    insar_displacement_mm_per_day: null,
  },
  reach_id: "GEUMHO_042",
  module_b_extra: {
    static: { drainage_area_km2: 58.2, river_order: 3, slope_pct: 1.8 },
    dynamic: { rainfall_cumulative_24h_mm: [187.3], river_level_m: 3.2 },
    sar_water_extent: null,
  },
  underpasses: [
    {
      underpass_id: "SC-UP-003",
      rainfall_intensity_1h_mm: 45.0,
      known_risk: true,
      drainage_capacity_class: "low",
    },
  ],
};

export async function triggerAlert(input: TriggerInput): Promise<ModuleOEnvelope> {
  const res = await fetch(`${API_BASE}/alerts/trigger`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!res.ok) throw new Error(`trigger failed: ${res.status}`);
  return res.json();
}

export async function getAlert(alertId: string): Promise<ModuleOEnvelope> {
  const res = await fetch(`${API_BASE}/alerts/${alertId}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`get alert failed: ${res.status}`);
  return res.json();
}

export type AdminLevel = "sido" | "sigungu" | "dong";

export interface AdminSearchResult {
  level: AdminLevel;
  code: string;
  name: string;
  full_name: string;
  center: [number, number];
  bbox: [number, number, number, number];
}

export type BoundariesByLevel = Record<AdminLevel, GeoJSON.FeatureCollection>;

// bbox: [minLon, minLat, maxLon, maxLat] — 시도/시군구/읍면동 3계층 모두 한 번에 받는다
export async function getBoundaries(bbox: [number, number, number, number]): Promise<BoundariesByLevel> {
  const res = await fetch(`${API_BASE}/boundaries?bbox=${bbox.join(",")}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`get boundaries failed: ${res.status}`);
  return res.json();
}

export async function getVWorldBuildings(bbox: [number, number, number, number]): Promise<GeoJSON.FeatureCollection> {
  const res = await fetch(`${API_BASE}/vworld/buildings?bbox=${bbox.join(",")}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`get vworld buildings failed: ${res.status}`);
  return res.json();
}

export async function getVWorldRoads(bbox: [number, number, number, number]): Promise<GeoJSON.FeatureCollection> {
  const res = await fetch(`${API_BASE}/vworld/roads?bbox=${bbox.join(",")}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`get vworld roads failed: ${res.status}`);
  return res.json();
}

// 2026-08-28 신규 — 실폭하천 폴리곤(riv_nm 하천명·cat_nam 등급 포함)
export async function getVWorldRivers(bbox: [number, number, number, number]): Promise<GeoJSON.FeatureCollection> {
  const res = await fetch(`${API_BASE}/vworld/rivers?bbox=${bbox.join(",")}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`get vworld rivers failed: ${res.status}`);
  return res.json();
}

export async function searchAdmin(q: string): Promise<AdminSearchResult[]> {
  if (!q.trim()) return [];
  const res = await fetch(`${API_BASE}/search?q=${encodeURIComponent(q)}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`search failed: ${res.status}`);
  return res.json();
}

export async function getAlertGeojson(alertId: string): Promise<GeoJSON.FeatureCollection> {
  const res = await fetch(`${API_BASE}/alerts/${alertId}/geojson`, { cache: "no-store" });
  if (!res.ok) throw new Error(`get alert geojson failed: ${res.status}`);
  return res.json();
}

export interface ChatHistoryTurn {
  role: "user" | "bot";
  text: string;
}

export async function sendChatMessage(
  message: string,
  alertId?: string,
  history?: ChatHistoryTurn[]
): Promise<string> {
  const res = await fetch(`${API_BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, alert_id: alertId, history }),
  });
  if (!res.ok) throw new Error(`chat failed: ${res.status}`);
  const data: { reply: string } = await res.json();
  return data.reply;
}

export interface EvacuationRouteResult {
  shelter_id: string;
  route_5179: { type: "LineString"; coordinates: number[][] };
  route_lonlat: [number, number][];
  eta_min: number;
  route_confidence: "high" | "medium" | "low";
  time_feasible: boolean;
  time_margin_min: number | null;
  fallback_used: boolean;
  modes: { car: { eta_min: number; source: string }; walk: { eta_min: number; source: string } };
}

export async function getEvacuationRoutes(
  origin: { lon: number; lat: number },
  shelterCandidates: { shelter_id: string; lon: number; lat: number; capacity: number }[],
  timeBudgetHours = 2.0
): Promise<{ results: EvacuationRouteResult[]; warnings: string[] }> {
  const res = await fetch(`${API_BASE}/evacuation-route`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ origin, shelter_candidates: shelterCandidates, time_budget_hours: timeBudgetHours }),
  });
  if (!res.ok) throw new Error(`evacuation route failed: ${res.status}`);
  return res.json();
}

export interface IsolationCheckResult {
  isolated_areas: GeoJSON.FeatureCollection;
  isolated_buildings: GeoJSON.FeatureCollection;
  isolated_building_count: number;
  // 위험영역과 겹쳐 도로망 그래프에서 제거된 구간 — 지도에 빨간색으로 그린다.
  // 고립 판정의 부산물이지만 "어느 길이 끊기는가"는 그 자체로 대피 정보다.
  blocked_roads: GeoJSON.FeatureCollection;
  warnings: string[];
}

export async function checkIsolation(
  bbox: [number, number, number, number],
  shelterCandidates: { lon: number; lat: number }[],
  hazardPolygon?: GeoJSON.Polygon | GeoJSON.MultiPolygon
): Promise<IsolationCheckResult> {
  const res = await fetch(`${API_BASE}/isolation-check`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ bbox, shelter_candidates: shelterCandidates, hazard_polygon: hazardPolygon ?? null }),
  });
  if (!res.ok) throw new Error(`isolation check failed: ${res.status}`);
  return res.json();
}

export async function approveAlert(
  alertId: string,
  decision: "승인" | "거부",
  approverId: string
): Promise<{ alert_id: string; approval_status: string; escalation_level: number; approver_id: string }> {
  const res = await fetch(`${API_BASE}/approve/${alertId}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ decision, approver_id: approverId }),
  });
  if (!res.ok) throw new Error(`approve failed: ${res.status}`);
  return res.json();
}
