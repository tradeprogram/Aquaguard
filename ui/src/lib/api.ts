import type { ModuleOEnvelope } from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export interface TriggerInput {
  alert_id: string;
  trigger_location: { x_5179: number; y_5179: number };
  timestamp: string;
  auto_approve_timeout_min?: number;
  safety_margin_hours?: number;
}

// §9 데모 시나리오: 2025.7.19 산청 산사태 재연
export const SANGCHEONG_DEMO_INPUT: TriggerInput = {
  alert_id: "AL-20250719-0915",
  trigger_location: { x_5179: 1090452.3, y_5179: 1662188.7 },
  timestamp: "2025-07-19T08:00:00+09:00",
  auto_approve_timeout_min: 15,
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

export async function approveAlert(
  alertId: string,
  decision: "승인" | "거부",
  approverId: string
): Promise<{ alert_id: string; approval_status: string; approver_id: string }> {
  const res = await fetch(`${API_BASE}/approve/${alertId}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ decision, approver_id: approverId }),
  });
  if (!res.ok) throw new Error(`approve failed: ${res.status}`);
  return res.json();
}
