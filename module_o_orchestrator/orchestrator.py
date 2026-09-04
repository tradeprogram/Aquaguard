"""
module_o_orchestrator — 골든타임 오케스트레이션 (§5 Module O).

역할: Module A/B/C를 감시 → 임계치 초과 시 D/E/G 순차 호출 → Module H로
시민 역검증 트리거 → 경보 패키지 생성 → AlertStore에 등록(원클릭 승인 대기).

지금은 AQUAGUARD_MOCK_MODE=1(기본값)로 contracts/의 example.json을 통해
A~H를 목업 호출한다 — 팀원 모듈이 실제로 들어오면 modules_client.py의
MODULE_PACKAGES만 통하면 되고, 이 파일은 수정할 필요가 없다.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from .modules_client import call_module
from .store import Alert, alert_store

LANDSLIDE_THRESHOLD = 0.7
FLOOD_THRESHOLD = 0.7

# 산청 2025 실제 타임라인(§0, §9 데모 시나리오) — timeline_actual_override가 없을 때 기본값
DEFAULT_TIMELINE_ACTUAL = {
    "advisory": "2025-07-17T00:00:00+09:00",
    "report_start": "2025-07-19T08:00:00+09:00",
    "warning_escalated": "2025-07-19T12:37:00+09:00",
}

# 데모 AOI(산청군 생비량면, data/vector/saengbiryang_myeon_5179.geojson) 폴리곤 내부의
# 실좌표 — 호출측이 대피소 후보를 안 넘기면 데모용으로 이 값을 사용한다 (지도 표시용).
# contracts/module_e.example.json의 x_5179/y_5179는 문서가 명시한 "예시 값"이라 실제
# 지리 위치가 아니므로(§5), 여기서는 AOI 폴리곤 내부의 실제 좌표로 대체했다.
DEFAULT_SHELTER_CANDIDATES = [
    {"shelter_id": "S001", "x_5179": 1051711.5, "y_5179": 1707045.2, "capacity": 200}
]


def _envelope(status: str, fallback_tier: int, data: dict[str, Any], warnings: list[str]) -> dict[str, Any]:
    return {"status": status, "fallback_tier": fallback_tier, "data": data, "warnings": warnings}


def _merge_module_result(
    module_letter: str,
    result: dict[str, Any],
    warnings: list[str],
    fallback_tier: list[int],
) -> dict[str, Any]:
    if result["status"] != "ok":
        warnings.append(f"Module {module_letter.upper()} status={result['status']} (fallback_tier={result['fallback_tier']})")
    fallback_tier[0] = max(fallback_tier[0], result["fallback_tier"])
    warnings.extend(result.get("warnings", []))
    return result["data"]


def run(input: dict[str, Any]) -> dict[str, Any]:  # noqa: A002 - §4.2 규약이 지정한 이름
    warnings: list[str] = []
    fallback_tier = [1]

    alert_id: str = input["alert_id"]
    trigger_location: dict[str, float] = input["trigger_location"]
    timestamp = datetime.fromisoformat(input["timestamp"])
    escalation_timeout_min: int = input.get("escalation_timeout_min", 15)
    safety_margin_hours: float = input.get("safety_margin_hours", 0.5)
    # 실제 모드에서 A/B가 필요로 하는 static/dynamic 관측값 — 목업 모드에서는 무시됨.
    # TODO(§10): 실제 연동 시 Module O가 이 값을 어디서 가져올지(별도 데이터 접근 계층) 정의 필요.
    module_a_input = {
        "x_5179": trigger_location["x_5179"],
        "y_5179": trigger_location["y_5179"],
        "timestamp": input["timestamp"],
        **input.get("module_a_extra", {}),
    }
    module_b_input = {"reach_id": input.get("reach_id"), **input.get("module_b_extra", {})}

    # 1. 관측 → 예측: Module A/B/C
    landslide = _merge_module_result("a", call_module("a", module_a_input), warnings, fallback_tier)
    flood = _merge_module_result("b", call_module("b", module_b_input), warnings, fallback_tier)

    # Module C는 지하차도 1건 단위 계약인데 UI는 배열(road_flooding)을 기대한다 —
    # 누가 순회할지가 미정이었고(TRACK2_CONTRACT_AGENDA.md 5번) 감시 주체인 O가 맡는 것으로
    # 정했다. C가 계약 밖 편의함수 run_many()를 갖고 있지만 그걸 쓰면 modules_client의
    # 어댑터 경계를 우회하게 되므로, 여기서 call_module을 건별로 돌린다(한 건이 degraded여도
    # 나머지는 그대로 남는다). 입력이 없으면 호출 자체를 건너뛴다.
    road_flooding: list[dict[str, Any]] = []
    for underpass in input.get("underpasses", []):
        road_flooding.append(_merge_module_result("c", call_module("c", underpass), warnings, fallback_tier))

    hours_candidates = [h for h in (landslide.get("hours_to_critical"), flood.get("hours_to_critical")) if h is not None]
    hours_to_critical = min(hours_candidates) if hours_candidates else None
    time_budget_hours = max(hours_to_critical - safety_margin_hours, 0.0) if hours_to_critical is not None else None

    triggered = landslide["landslide_prob"] >= LANDSLIDE_THRESHOLD or flood["flood_prob"] >= FLOOD_THRESHOLD

    # 2. 1차권고: 임계치 초과 시에만 D/E/G 진행 (§5 Module O 역할)
    shelter_route: dict[str, Any] = {}
    damage_cost: dict[str, Any] = {}
    if triggered:
        # A는 risk_polygon_5179, B는 inundation_extent_5179가 실제 위험영역이다
        # (TRACK2_CONTRACT_AGENDA.md 1번, 2026-09-04 합의로 A 계약에 폴리곤 필드 추가).
        # A의 폴리곤이 null이면 — FoS 격자에서 영역을 못 뽑은 경우 — location(점)으로
        # 폴백하고, 그때 D가 반경 버퍼로 흡수하면서 status: degraded로 내린다(ASSUMPTION 표기).
        risk_polygons = [
            {
                "source_module": "A",
                "geometry_5179": landslide.get("risk_polygon_5179") or landslide.get("location", {}),
                "risk_prob": landslide["landslide_prob"],
            },
            {
                "source_module": "B",
                "geometry_5179": flood.get("inundation_extent_5179") or {},
                "risk_prob": flood["flood_prob"],
            },
        ]
        exposure = _merge_module_result(
            "d",
            call_module("d", {"risk_polygons": risk_polygons, "building_footprints_5179": {}, "farmland_parcels_5179": {}}),
            warnings,
            fallback_tier,
        )
        shelter_route = _merge_module_result(
            "e",
            call_module(
                "e",
                {
                    "origin": trigger_location,
                    "risk_polygons": risk_polygons,
                    "shelter_candidates": input.get("shelter_candidates") or DEFAULT_SHELTER_CANDIDATES,
                    "road_graph_source": "standard_node_link_v1",
                    "time_budget_hours": time_budget_hours,
                },
            ),
            warnings,
            fallback_tier,
        )
        damage_cost = _merge_module_result(
            "g",
            call_module("g", {**exposure, "unit_cost_table_ref": "재해연보_2024_원단위"}),
            warnings,
            fallback_tier,
        )

    # 3. 시민 역검증(Module H, precursor_flag가 뜬 경우에만 병렬 트리거 — §5 Module H)
    if landslide.get("precursor_flag"):
        citizen = _merge_module_result(
            "h",
            call_module(
                "h",
                {
                    "alert_id": alert_id,
                    "trigger_location": trigger_location,
                    "trigger_radius_m": 500,
                    "citizen_reports": input.get("citizen_reports", []),
                    # H의 response_latency_min은 "경보 발송 → 시민 응답" 시간이라 경보 시각이
                    # 없으면 계산이 안 된다. 계약에 그 필드가 없어서 H가 alert_id 문자열을
                    # 파싱하고 degraded로 내려가고 있었는데(TRACK2_CONTRACT_AGENDA.md 7번),
                    # O는 그 값을 이미 갖고 있으므로 그대로 넘긴다. 스키마가 추가 속성을 막지
                    # 않아 계약 위반이 아니고, 정식 필드 승격은 4인 합의 사안으로 남아 있다.
                    "alert_issued_at": input["timestamp"],
                },
            ),
            warnings,
            fallback_tier,
        )
    else:
        citizen = {"report_count": 0, "verification_status": "미확인", "confidence_adjustment": 0, "response_latency_min": None}

    # 4. 골든타임 계산 — timeline_agent는 이 run()이 호출된 시점을 "탐지"로 본다
    detection_lag_min = input.get("detection_lag_min", 75)
    dispatch_lag_min = input.get("dispatch_lag_min", 5)
    detected = timestamp + timedelta(minutes=detection_lag_min)
    alert_sent = detected + timedelta(minutes=dispatch_lag_min)
    timeline_actual = input.get("timeline_actual_override", DEFAULT_TIMELINE_ACTUAL)
    warning_escalated = datetime.fromisoformat(timeline_actual["warning_escalated"])
    golden_time_saved_min = (warning_escalated - alert_sent).total_seconds() / 60

    data = {
        "timeline_actual": timeline_actual,
        "timeline_agent": {
            "detected": detected.isoformat(),
            "alert_sent": alert_sent.isoformat(),
        },
        "golden_time_saved_min": round(golden_time_saved_min, 1),
        "approval_status": "대기",
        "escalation_level": 0,
        "citizen_verification": {
            "verification_status": citizen["verification_status"],
            "confidence_adjustment": citizen["confidence_adjustment"],
        },
        "alert_package": {
            "landslide": landslide,
            "flood": flood,
            "shelter_route": shelter_route,
            "damage_cost": damage_cost,
            # UI의 ModuleOData.alert_package.road_flooding?: UnderpassAlert[]에 대응.
            # module_o.schema.json의 alert_package는 additionalProperties를 막지 않아
            # 계약 위반이 아니다. 입력에 underpasses가 없으면 빈 배열이다.
            "road_flooding": road_flooding,
        },
    }

    envelope = _envelope("ok" if fallback_tier[0] == 1 else "degraded", fallback_tier[0], data, warnings)

    if triggered:
        # 승인 대기 타임아웃은 재연 데모의 과거 이벤트 시각(timestamp)이 아니라
        # 이 알림이 실제로 등록된 현재 시각을 기준으로 흘러야 한다.
        alert_store.add(
            Alert(
                alert_id=alert_id,
                created_at=datetime.now(timestamp.tzinfo),
                escalation_timeout_min=escalation_timeout_min,
                envelope=envelope,
                trigger_input=input,
            )
        )
        envelope["data"]["approval_status"] = alert_store.get(alert_id).resolve_status()
        envelope["data"]["escalation_level"] = alert_store.get(alert_id).escalation_level

    return envelope
