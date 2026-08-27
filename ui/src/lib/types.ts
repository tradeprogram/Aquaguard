// contracts/module_o.schema.json 과 1:1 대응 (§5 Module O)

export interface Timeline {
  advisory?: string;
  report_start?: string;
  warning_escalated?: string;
}

export interface TimelineAgent {
  detected: string;
  alert_sent: string;
}

export type ApprovalStatus = "대기" | "승인" | "거부" | "자동승인(timeout)";
export type VerificationStatus = "미확인" | "현장확인" | "오탐판정";

export interface LandslideData {
  landslide_prob: number;
  confidence_interval: [number, number];
  source: "observed" | "forecast";
  amplification_factor: number;
  precursor_flag: boolean;
  hours_to_critical: number | null;
  location: { x_5179: number; y_5179: number };
}

export interface FloodData {
  flood_prob: number;
  confidence_interval: [number, number];
  hours_to_critical: number | null;
  inundation_extent_5179: { type: "FeatureCollection"; features: unknown[] };
}

export interface ShelterRouteData {
  shelter_id: string | null;
  route_5179?: { type: "LineString"; coordinates: number[][] };
  eta_min: number | null;
  route_confidence: "high" | "medium" | "low";
  time_feasible: boolean;
  time_margin_min: number | null;
  fallback_used: boolean;
}

export interface DamageCostData {
  estimated_cost_krw: number;
  cost_range_krw: [number, number];
  basis_citation: string;
}

export interface AlertPackage {
  landslide: LandslideData;
  flood: FloodData;
  shelter_route: ShelterRouteData | Record<string, never>;
  damage_cost: DamageCostData | Record<string, never>;
}

export interface ModuleOData {
  timeline_actual: Timeline;
  timeline_agent: TimelineAgent;
  golden_time_saved_min: number;
  approval_status: ApprovalStatus;
  citizen_verification: {
    verification_status: VerificationStatus;
    confidence_adjustment: number;
  };
  alert_package: AlertPackage;
}

export interface Envelope<T> {
  status: "ok" | "degraded" | "error";
  fallback_tier: 1 | 2 | 3;
  data: T;
  warnings: string[];
}

export interface AlertMeta {
  created_at: string;
  auto_approve_timeout_min: number;
}

export type ModuleOEnvelope = Envelope<ModuleOData> & { meta?: AlertMeta };
