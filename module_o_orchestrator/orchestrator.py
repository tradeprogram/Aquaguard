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

from .exposure_layers import (
    building_footprints,
    coverage_warning,
    farmland_parcels,
    flood_depth_raster,
    resolve_aoi,
)
from .modules_client import call_explain, call_module, module_sources, resolve_source
from .store import Alert, alert_store

# 산사태 트리거 — landslide_prob >= 0.5.
#
# 0.7에서 내린 값이지만 "안 걸리니까 낮춘다"가 아니다. Module A의 확률은
# P = 1/(1+exp(k·(FoS-1)))로 안전율을 변환한 값이고, k는 아직 미보정이다
# (module_a_landslide/fos.py docstring, backtest RUN_LOG).
#
#   FoS = 1.0  ⟺  P = 0.5      k와 무관하게 항상 성립
#   FoS = 0.859 ⟺ P = 0.7      k=6일 때만. k가 바뀌면 이 대응도 바뀐다
#
# FoS=1은 사면이 버티는 힘과 무너뜨리는 힘이 같아지는 물리적 파괴 한계다. 그
# 지점이 시그모이드에서 유일하게 미보정 파라미터에 불변인 곳이므로, 지금 쓸 수
# 있는 임계 중 근거가 가장 단단하다. 0.7은 k=6이라는 임의값에 딸려 있을 뿐이다.
# (설계 실무는 보통 FoS 1.3~1.5를 요구하므로 FoS=1 발동은 이르기는커녕 늦다.)
#
# 과다 발동도 아니다 — 트랙①이 사전계산한 위험영역에서 P>=0.5는 산청 AOI 452km²
# 중 0.238km²(0.053%)뿐이다. 트랙① 자신도 이 값을 'warning' 레이어 기준으로 쓴다.
#
# k가 보정되면 이 값을 다시 유도할 것. 그때는 0.7이 맞을 수도 있다.
LANDSLIDE_THRESHOLD = 0.5

# 하천범람은 0.7 그대로다 — Module B의 flood_prob은 산사태와 달리 실측 수위·강우를
# 홍수특보 기준과 실측 사례(경호강 2025-07-19)로 보정한 값이라(module_b_flood 참조)
# 척도가 이미 의미를 갖는다. 두 숫자가 달라 보이는 이유는 두 확률이 다른 것이기
# 때문이며, 같은 값으로 맞추면 오히려 근거가 사라진다.
FLOOD_THRESHOLD = 0.7

# Module G가 실제로 참조하는 단가표 ID(policies/module_g.json의 policy_version).
# G는 이 값이 자기 표와 다르면 warning을 남기므로 임의 문자열을 넣으면 안 된다.
MODULE_G_UNIT_COST_TABLE = "module_g_v1"

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


def _risk_bounds_5179(risk_polygons: list[dict[str, Any]]) -> tuple[float, float, float, float] | None:
    """위험 폴리곤들을 감싸는 bbox(EPSG:5179). 좌표를 못 읽으면 None.

    노출자산 클립본 범위와 비교하기 위한 것이라 정밀한 합집합까지는 필요 없다.
    """
    xs: list[float] = []
    ys: list[float] = []

    def walk(node: Any) -> None:
        if isinstance(node, (int, float)):
            return
        if isinstance(node, (list, tuple)):
            if len(node) >= 2 and all(isinstance(v, (int, float)) for v in node[:2]):
                xs.append(float(node[0]))
                ys.append(float(node[1]))
                return
            for item in node:
                walk(item)

    for entry in risk_polygons:
        geometry = entry.get("geometry_5179")
        if not isinstance(geometry, dict):
            continue
        if "x_5179" in geometry and "y_5179" in geometry:
            try:
                xs.append(float(geometry["x_5179"]))
                ys.append(float(geometry["y_5179"]))
            except (TypeError, ValueError):
                pass
            continue
        if geometry.get("type") == "FeatureCollection":
            for feature in geometry.get("features") or []:
                walk((feature.get("geometry") or {}).get("coordinates"))
        else:
            walk(geometry.get("coordinates"))

    if not xs or not ys:
        return None
    return min(xs), min(ys), max(xs), max(ys)


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

    # 침수심 래스터는 어느 모듈의 출력도 아니라 O가 §10 데이터 접근 계층에서 경로를
    # 찾아 넘긴다(건물·농경지와 같은 원칙). 이게 없으면 Module B는 확률만 내고
    # 침수 폴리곤은 빈 FC가 되어 지도에 3D 침수 볼륨이 안 그려진다.
    trigger_aoi = resolve_aoi(trigger_location.get("x_5179"), trigger_location.get("y_5179"))
    if resolve_source("b") == "real" and "_terrain" not in module_b_input:
        depth_raster, depth_warning = flood_depth_raster(trigger_aoi)
        if depth_raster:
            module_b_input["_terrain"] = {"depth_raster": depth_raster}
        elif depth_warning:
            warnings.append(depth_warning)

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
    exposure: dict[str, Any] = {}
    # 계약 밖 판정 근거 — UI Provenance 배지(§6.1)가 이 값으로 가정 여부를 판단한다.
    explains: dict[str, Any] = {}
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
        # 건물·농경지는 어느 모듈의 출력도 아니라 O가 데이터에서 직접 읽어 넘긴다
        # (§10 데이터 접근 계층). 레이어를 못 읽어도 파이프라인은 계속 돌고, 대신
        # 그 사실이 경고로 올라온다 — 특히 농경지는 "0ha"와 "확인 불가"가 다르다.
        aoi = trigger_aoi  # 위에서 이미 해석했다
        # 위험영역 bbox를 함께 넘겨 그 밖의 건물·농경지는 읽어서 바로 버린다.
        # D가 어차피 위험 폴리곤과 교차시키므로 결과는 같고, 상주 메모리만 준다 —
        # 산청 농경지 전체를 들고 있으면 105MB라 908MB짜리 배포 서버에서 uvicorn이
        # OOM으로 죽었다(2026-09-20 dmesg 확인).
        risk_bounds = _risk_bounds_5179(risk_polygons)
        buildings, buildings_warning = building_footprints(aoi, risk_bounds)
        farmland, farmland_warning = farmland_parcels(aoi, risk_bounds)
        # 단, 목업 D는 입력을 무시하고 example.json의 출력(농경지 4.2ha 등)을 그대로
        # 돌려준다 — 그때 "레이어 미확보" 경고를 같이 내보내면 화면에 뜬 숫자와 어긋난다.
        # 이 경고는 그 레이어로 실제 계산이 일어날 때만 의미가 있다.
        if resolve_source("d") == "real":
            warnings.extend(w for w in (buildings_warning, farmland_warning) if w)
            # 위험영역이 클립본 밖으로 나가면 그만큼 노출자산이 빠진다 — 하한임을 알린다.
            coverage = coverage_warning(aoi, risk_bounds)
            if coverage:
                warnings.append(coverage)

        module_d_input = {
            "risk_polygons": risk_polygons,
            "building_footprints_5179": buildings,
            "farmland_parcels_5179": farmland,
        }
        exposure = _merge_module_result(
            "d", call_module("d", module_d_input), warnings, fallback_tier
        )
        explains["d"] = call_explain("d", module_d_input)
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
        module_g_input = {**exposure, "unit_cost_table_ref": MODULE_G_UNIT_COST_TABLE}
        damage_cost = _merge_module_result(
            "g",
            # "재해연보_2024_원단위"를 하드코딩하고 있었는데 G가 실제로 쓰는 표가 아니다
            # (G는 국토교통부고시 제2026-90호 주택침수 단가와 농림축산식품부고시 제2026-78호
            # 대파대를 policies/module_g.json = module_g_v1로 들고 있다). 그동안 G가 이
            # 불일치를 warning으로 흘려보내고 있었다 — 실제 표 ID를 넘겨 그 경고를 없앤다.
            call_module("g", module_g_input),
            warnings,
            fallback_tier,
        )
        explains["g"] = call_explain("g", module_g_input)

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
            # 같은 이유로 UI의 exposure?: ExposureData에 대응한다. Module D 출력은
            # 그동안 Module G 입력으로만 쓰이고 봉투에는 안 실렸는데, 화면이
            # "어느 건물이 위험구역에 걸렸는지"를 그리려면 이 값이 필요하다.
            "exposure": exposure,
        },
    }

    envelope = _envelope("ok" if fallback_tier[0] == 1 else "degraded", fallback_tier[0], data, warnings)
    # 계약(§4.2)의 4개 필드 밖에 붙는 부가 메타 — 어느 모듈이 실물로 돌았고 어느 것이
    # 아직 example.json 대체인지 UI가 알아야 Provenance 배지(§6.1)를 정직하게 찍는다.
    envelope["meta"] = {
        "module_sources": module_sources(),
        # 계약(§4.2)의 4개 필드 밖 부가 정보. 목업 모듈은 explain()이 없어 None이 온다.
        "explains": {k: v for k, v in explains.items() if v is not None},
    }

    # 임계 미달이어도 등록한다. 예전에는 초과했을 때만 저장해서, 확률이 0.7을 못 넘으면
    # /alerts/{id}/geojson이 404가 났다 — 그러면 화면은 "아직 대피 수준은 아니지만 Module B가
    # 계산한 침수는 이만큼"을 보여줄 방법이 없다. 승인 대상이 아니라는 사실은 상태값으로
    # 구분한다(감시중): escalation도 안 걸리고 approve()도 받지 않는다.
    #
    # 승인 대기 타임아웃은 재연 데모의 과거 이벤트 시각(timestamp)이 아니라
    # 이 알림이 실제로 등록된 현재 시각을 기준으로 흘러야 한다.
    alert_store.add(
        Alert(
            alert_id=alert_id,
            created_at=datetime.now(timestamp.tzinfo),
            escalation_timeout_min=escalation_timeout_min,
            envelope=envelope,
            trigger_input=input,
            triggered=triggered,
        )
    )
    envelope["data"]["approval_status"] = alert_store.get(alert_id).resolve_status()
    envelope["data"]["escalation_level"] = alert_store.get(alert_id).escalation_level

    return envelope
