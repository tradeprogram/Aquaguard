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

// 사전계산된 데모 결과를 **프론트 자기 오리진**에서 읽는다(scripts/build_demo_snapshot.py가
// ui/public/demo/ 에 써 둔다).
//
// **왜 백엔드에서 안 받나**: 브라우저는 한 오리진에 동시 요청 수가 제한된다. 지도가
// EC2로 지형·벡터 타일을 수백 장 부르는 동안 경보 요청이 그 줄 뒤에 서면서, 서버가
// 0.013초에 답하는데도 화면에서는 200초가 걸렸다(2026-09-21 실측). 이미 계산해 둔
// 값을 그 줄에 세울 이유가 없다 — Vercel CDN은 오리진이 달라 타일과 경쟁하지 않는다.
//
// 정적 사본이 없거나(빌드 누락) 읽기에 실패하면 그대로 백엔드로 떨어진다.
async function fetchDemoAsset<T>(name: string): Promise<T | null> {
  try {
    // force-cache는 쓰지 않는다 — 스냅샷을 다시 만들어도 브라우저가 옛 파일을 계속
    // 들고 있어서, 실제로 markers가 빠진 낡은 사본이 화면에 남았다(2026-09-21).
    // no-cache는 "쓰기 전에 검증"이라 안 바뀌었으면 CDN이 304만 돌려준다 — 본문
    // 전송이 없으니 빠르고, 바뀌면 반드시 새 것을 받는다.
    const res = await fetch(`/demo/${name}`, { cache: "no-cache" });
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null;
  }
}

export async function getDemoEnvelope(): Promise<ModuleOEnvelope | null> {
  return fetchDemoAsset<ModuleOEnvelope>("envelope.json");
}

// 사전계산된 고립 분석. 도로망 그래프를 세우고 연결성을 푸는 계산이라 화면에서 누르면
// 수십 초가 걸린다(산청 8초, 강남은 77초였다) — 입력이 고정이면 결과도 고정이다.
//
// **bbox가 다르면 쓰지 않는다.** 산청을 군 전체로 넓히는 작업이 진행 중이라 범위가
// 바뀔 텐데, 그때 저장본을 그대로 쓰면 화면이 다른 범위의 고립 결과를 보여주게 된다.
// 안 맞으면 null을 돌려주고 호출부가 실제로 계산한다 — 느려질 뿐 틀리지는 않는다.
export async function getSnapshotIsolation(
  key: string,
  bbox: [number, number, number, number],
  shelterCount: number
): Promise<IsolationCheckResult | null> {
  const all = await fetchDemoAsset<
    Record<string, { bbox: number[]; shelter_count: number; result: IsolationCheckResult }>
  >("isolation.json");
  const entry = all?.[key];
  if (!entry) return null;
  const sameBbox =
    entry.bbox.length === 4 && entry.bbox.every((v, i) => Math.abs(v - bbox[i]) < 1e-6);
  if (!sameBbox || entry.shelter_count !== shelterCount) return null;
  return entry.result;
}

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
  // 데모 경보면 정적 사본을 먼저 본다(위 fetchDemoAsset 주석 참고).
  if (alertId === SANGCHEONG_DEMO_INPUT.alert_id) {
    const cached = await fetchDemoAsset<GeoJSON.FeatureCollection>("geojson.json");
    if (cached?.features?.length) return cached;
  }
  const res = await fetch(`${API_BASE}/alerts/${alertId}/geojson`, { cache: "no-store" });
  if (!res.ok) throw new Error(`get alert geojson failed: ${res.status}`);
  return res.json();
}

// §5 UI-3D 시간축 — "지금 화면이 언제의 예측인가"를 화면에 쓸 수 있게 하는 데이터.
// 프레임 39개 + 위험 폴리곤 한 자릿수라 한 번에 통째로 받아 두고, 시간 스크럽은
// arrival_hour로 클라이언트에서 거른다(스크럽마다 서버를 부르면 끊긴다).
export interface TimelineFrame {
  hour: number;
  time: string; // ISO8601 +09:00
  rn_mm: number; // 그 시각 시간강우
  cum24_mm: number; // 24시간 누적
}

export interface RiskLevelSummary {
  level: "warning" | "critical";
  prob_threshold: number | null;
  count: number;
  area_km2: number | null;
}

export interface AlertTimeline {
  available: boolean;
  reason?: string;
  scenario?: string;
  level?: string;
  // 두 임계(0.5 경고 / 0.7 위험)를 같이 받는다 — 화면이 "대응을 시작한 근거"인
  // 0.5 영역과 그 안의 0.7 영역을 함께 보여줄 수 있어야 한다.
  levels?: RiskLevelSummary[];
  // Module O가 대응을 시작하는 확률(LANDSLIDE_THRESHOLD).
  trigger_threshold?: number;
  frames: TimelineFrame[];
  risk: GeoJSON.FeatureCollection;
  markers: {
    detected?: string | null;
    alert_sent?: string | null;
    official_warning?: string | null;
    report_start?: string | null;
  };
  // 침수 시간축. SFINCS는 "최대" 침수심 한 장만 내지만 같은 모의가 경호교 시간별
  // 수위도 남겼고, 깊이(t) ≥ b ⟺ 최대깊이 ≥ b + 수위강하(t) 이므로 등고선 한 벌로
  // 모든 시각을 그릴 수 있다. available이 false면 최대 범위 고정으로 떨어진다.
  flood_series?: {
    available: boolean;
    contours?: GeoJSON.FeatureCollection;
    levels?: number[];
    observed_max_m?: number;
    peak_stage_m?: number;
    // 첨두 시각(ISO+09:00). 프레임 구간 밖일 수 있다 — 실제 SFINCS 첨두는 7/19 16:00,
    // 프레임은 14:00에서 끝난다. 구간 안에서 찾으면 국소 최대를 첨두로 오인한다.
    peak_time?: string;
    // 프레임 hour -> 첨두 대비 수위강하(m). 값이 없는 시각은 수위 자료가 없는 것이다.
    stage_drop_by_hour?: Record<string, number>;
    gauge?: string;
    한계?: string[];
  };
  // flood_series가 없을 때만 true — 그때는 "최대 범위"로만 표기하고 시간에 따라
  // 번지는 척하지 않는다.
  flood_is_max: boolean;
  limits?: string[];
  // 200이 아니었을 때의 상태코드. 화면 문구는 이걸 그대로 쓰지 않고 /health를 찔러
  // "배포가 뒤처짐 / 서버가 죽음 / 요청 자체 문제"를 구분해 만든다(backendDiagnosis).
  // 상태코드만 띄우면 2026-09-06 때처럼 진단이 헛돈다.
  httpStatus?: number;
}

// FastAPI가 등록한 라우트 문자열 그대로 — /health의 routes와 대조해야 해서 경로
// 파라미터가 치환되지 않은 형태여야 한다.
export const TIMELINE_ROUTE = "/alerts/{alert_id}/timeline";

const EMPTY_TIMELINE: AlertTimeline = {
  available: false,
  frames: [],
  risk: { type: "FeatureCollection", features: [] },
  markers: {},
  flood_is_max: true,
};

export async function getAlertTimeline(alertId: string): Promise<AlertTimeline> {
  // 시간축은 프레임·위험영역·침수 등고선 전부 사전계산물이라 백엔드를 안 거쳐도 된다.
  // 다만 탐지/발송/공식경보 시각은 경보에서 나오므로, 정적 사본으로 화면을 먼저 띄우고
  // 백엔드가 답하면 그때 마커를 채운다 — 지도가 뜨는 속도를 서버에 걸지 않는다.
  if (alertId === SANGCHEONG_DEMO_INPUT.alert_id) {
    const cached = await fetchDemoAsset<{
      frames?: TimelineFrame[];
      markers?: AlertTimeline["markers"];
      flood_series?: AlertTimeline["flood_series"];
      risk_display?: GeoJSON.FeatureCollection;
      meta?: Record<string, unknown>;
    }>("timeline.json");
    if (cached?.risk_display?.features?.length) {
      return {
        ...EMPTY_TIMELINE,
        available: true,
        scenario: "A_soilmap",
        level: "warning+critical",
        frames: cached.frames ?? [],
        markers: cached.markers ?? {},
        risk: cached.risk_display,
        flood_series: cached.flood_series,
        flood_is_max: !cached.flood_series?.available,
      };
    }
  }
  const res = await fetch(`${API_BASE}/alerts/${alertId}/timeline`, { cache: "no-store" });
  if (!res.ok) return { ...EMPTY_TIMELINE, httpStatus: res.status };
  const body = (await res.json()) as Partial<AlertTimeline>;
  return { ...EMPTY_TIMELINE, ...body };
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
