import type { ModuleOEnvelope } from "./types";

export const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export interface TriggerInput {
  alert_id: string;
  trigger_location: { x_5179: number; y_5179: number };
  timestamp: string;
  escalation_timeout_min?: number;
  safety_margin_hours?: number;
}

// §9 데모 시나리오: 2025.7.19 산청 산사태 재연
// trigger_location은 contracts/module_a.example.json의 x_5179/y_5179(문서가 명시한
// "예시 값", 실제 지리 위치 아님)와 달리, data/vector/saengbiryang_myeon_5179.geojson
// (행정동 경계 실데이터, EPSG:5179)으로 확인한 산청군 생비량면 AOI 내부 실좌표다.
export const SANGCHEONG_DEMO_INPUT: TriggerInput = {
  alert_id: "AL-20250719-0915",
  trigger_location: { x_5179: 1050511.5, y_5179: 1706245.2 },
  timestamp: "2025-07-19T08:00:00+09:00",
  escalation_timeout_min: 15,
  safety_margin_hours: 0.5,
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
