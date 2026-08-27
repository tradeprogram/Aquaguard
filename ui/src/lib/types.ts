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

// HANDOFF.md §6.6 제안 — 차량/도보 이동수단을 따로 보여주기 위한 확장. 아직 4인
// 합의 전이라 contracts/module_e.schema.json엔 없음 — EvacuationPanel이 지금 쓰는
// 클라이언트 계산값(하버사인 근사)과 실제 API 응답을 같은 모양으로 받기 위한 준비용
// optional 필드. 합의되면 그때 module_e.schema.json에도 반영할 것.
export interface RouteModeEta {
  eta_min: number;
  route_confidence: "high" | "medium" | "low";
  source: string;
}

export interface ShelterRouteData {
  shelter_id: string | null;
  route_5179?: { type: "LineString"; coordinates: number[][] };
  eta_min: number | null;
  route_confidence: "high" | "medium" | "low";
  time_feasible: boolean;
  time_margin_min: number | null;
  fallback_used: boolean;
  modes?: { car: RouteModeEta; walk: RouteModeEta };
}

export interface DamageCostData {
  estimated_cost_krw: number;
  cost_range_krw: [number, number];
  basis_citation: string;
}

// Module C — 도로·지하차도 침수 (규칙기반, 모델 아님) — contracts/module_c.example.json.
// Module D — 노출자산 오버레이 — contracts/module_d.example.json.
// 둘 다 아직 module_o.schema.json/실제 orchestrator 출력엔 없음 — DashboardPanel의
// 하드코딩 UNDERPASSES/노출자산 텍스트를 실데이터로 교체할 때를 대비한 준비용 타입.
export interface UnderpassAlert {
  underpass_id: string;
  alert_level: "정상" | "주의" | "경계" | "위험";
}

export interface ExposedBuilding {
  building_id: string;
  risk_prob: number;
  use_type: string;
}

export interface ExposureData {
  exposed_buildings: ExposedBuilding[];
  exposed_farmland_ha: number;
}

export interface AlertPackage {
  landslide: LandslideData;
  flood: FloodData;
  shelter_route: ShelterRouteData | Record<string, never>;
  damage_cost: DamageCostData | Record<string, never>;
  // 아직 실제 orchestrator가 안 채워주는 준비용 필드 — 위 주석 참조.
  road_flooding?: UnderpassAlert[];
  exposure?: ExposureData;
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
