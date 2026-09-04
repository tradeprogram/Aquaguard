import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from module_o_orchestrator.orchestrator import run
from module_o_orchestrator.store import Alert, AlertStore

CONTRACTS_DIR = Path(__file__).resolve().parent.parent.parent / "contracts"


def _load_example(name: str) -> dict:
    with open(CONTRACTS_DIR / f"module_{name}.example.json", encoding="utf-8") as f:
        return json.load(f)


def test_run_matches_contract_shape():
    example = _load_example("o")
    envelope = run(example["input"])

    assert envelope["status"] == "ok"
    assert envelope["fallback_tier"] == 1
    assert envelope["warnings"] == []

    data = envelope["data"]
    for key in ("timeline_actual", "timeline_agent", "golden_time_saved_min", "approval_status", "escalation_level", "citizen_verification", "alert_package"):
        assert key in data
    assert data["approval_status"] == "대기"
    for key in ("landslide", "flood", "shelter_route", "damage_cost"):
        assert key in data["alert_package"]


def test_golden_time_matches_documented_example():
    """contracts/module_o.example.json의 기본 입력값은 golden_time_saved_min=197을 문서화하고 있다."""
    example = _load_example("o")
    envelope = run(example["input"])
    assert envelope["data"]["golden_time_saved_min"] == 197.0


def test_alert_registered_for_approval():
    example = _load_example("o")
    alert_id = example["input"]["alert_id"]
    run(example["input"])

    from module_o_orchestrator.store import alert_store

    alert = alert_store.get(alert_id)
    assert alert is not None
    assert alert.approval_status == "대기"


def test_manual_approval_overrides_pending():
    store = AlertStore()
    now = datetime.now(timezone(timedelta(hours=9)))
    envelope = {
        "data": {"citizen_verification": {"verification_status": "미확인", "confidence_adjustment": 0}}
    }
    store.add(Alert(alert_id="X1", created_at=now, escalation_timeout_min=15, envelope=envelope))

    result = store.approve("X1", "거부", approver_id="tester")
    assert result.approval_status == "거부"
    assert result.resolve_status() == "거부"


def test_escalation_after_timeout_does_not_auto_approve():
    """2026-08-29: 무응답 시 자동승인은 삭제됐다 — 타임아웃이 지나도 상태는 "승인"이
    아니라 "권고중(escalation)"으로만 바뀐다(§5 Module O). 시스템이 대피명령을 독자
    발령하는 경로가 없다는 걸 코드 레벨로 보증하는 테스트."""
    store = AlertStore()
    past = datetime.now(timezone(timedelta(hours=9))) - timedelta(minutes=20)
    envelope = {
        "data": {"citizen_verification": {"verification_status": "미확인", "confidence_adjustment": 0}}
    }
    store.add(Alert(alert_id="X2", created_at=past, escalation_timeout_min=15, envelope=envelope))

    alert = store.get("X2")
    assert alert.resolve_status() == "권고중(escalation)"
    assert alert.escalation_level >= 1


def test_human_can_still_approve_after_escalation():
    """escalation은 판단을 가로채지 않는다 — 타임아웃이 지난 뒤에도 담당자가 승인/거부할 수 있어야 한다."""
    store = AlertStore()
    past = datetime.now(timezone(timedelta(hours=9))) - timedelta(minutes=20)
    envelope = {
        "data": {"citizen_verification": {"verification_status": "미확인", "confidence_adjustment": 0}}
    }
    store.add(Alert(alert_id="X4", created_at=past, escalation_timeout_min=15, envelope=envelope))
    store.get("X4").resolve_status()  # escalation 상태로 전이시킴

    result = store.approve("X4", "승인", approver_id="tester")
    assert result.approval_status == "승인"
    assert result.resolve_status() == "승인"


def test_no_escalation_when_false_positive():
    store = AlertStore()
    past = datetime.now(timezone(timedelta(hours=9))) - timedelta(minutes=20)
    envelope = {
        "data": {"citizen_verification": {"verification_status": "오탐판정", "confidence_adjustment": -0.2}}
    }
    store.add(Alert(alert_id="X3", created_at=past, escalation_timeout_min=15, envelope=envelope))

    alert = store.get("X3")
    assert alert.resolve_status() == "대기"


def test_mock_mode_replaces_every_module(monkeypatch):
    """기본값(AQUAGUARD_MOCK_MODE=1)에서는 설치된 모듈이 있어도 전부 example로 간다.

    §9 데모 리허설은 출력이 결정적이어야 해서 이 모드를 쓴다 — 실제 모듈이 들어왔다고
    조용히 real로 바뀌면 리허설 숫자가 흔들린다.
    """
    from module_o_orchestrator import modules_client

    monkeypatch.setenv("AQUAGUARD_MOCK_MODE", "1")
    assert set(modules_client.module_sources().values()) == {"example"}


def test_real_mode_falls_back_per_module(monkeypatch):
    """AQUAGUARD_MOCK_MODE=0은 설치된 모듈만 real로 돌리고 나머지는 example로 메운다.

    예전 구현은 0이면 전 모듈을 import해서, 아직 없는 module_a_landslide에서
    ModuleNotFoundError로 파이프라인 전체가 죽었다 — 트랙별 진도가 다른 동안
    real 모드를 아예 못 쓰는 상태였다.
    """
    from module_o_orchestrator import modules_client

    monkeypatch.setenv("AQUAGUARD_MOCK_MODE", "0")
    sources = modules_client.module_sources()

    for letter, package in modules_client.MODULE_PACKAGES.items():
        installed = modules_client._import_module(package) is not None
        assert sources[letter] == ("real" if installed else "example"), letter

    # 미설치 모듈이 섞여 있어도 파이프라인이 끝까지 돈다.
    envelope = run(_load_example("o")["input"])
    assert set(envelope) >= {"status", "fallback_tier", "data", "warnings"}
    assert envelope["meta"]["module_sources"] == sources


def test_exposure_layers_are_real_and_in_5179():
    """§10 데이터 접근 계층 — 커밋된 AOI 건축물 레이어가 실제로 읽히고 5179 미터다."""
    from module_o_orchestrator.exposure_layers import building_footprints, farmland_parcels

    buildings, warning = building_footprints()
    assert warning is None, warning
    assert buildings["type"] == "FeatureCollection"
    assert len(buildings["features"]) > 1000

    coords = buildings["features"][0]["geometry"]["coordinates"]
    while isinstance(coords[0], list):
        coords = coords[0]
    assert coords[0] > 100_000, "EPSG:4326이 그대로 들어왔다 — 5179 미터여야 한다"

    # 농경지는 아직 레이어가 없다. 빈 값을 조용히 넘기지 않고 이유를 함께 낸다.
    farmland, farmland_warning = farmland_parcels()
    assert farmland["features"] == []
    assert farmland_warning is not None


def test_real_mode_exposes_buildings_inside_risk_area(monkeypatch):
    """위험 폴리곤이 AOI 안이면 실제 건물이 노출자산으로 잡힌다.

    이전에는 Module O가 building_footprints_5179를 빈 dict로 넘겨서 어떤 위험영역을
    줘도 노출 0건이었다(§10 TODO).
    """
    pytest.importorskip("module_d_exposure_overlay")
    monkeypatch.setenv("AQUAGUARD_MOCK_MODE", "0")

    import module_d_exposure_overlay as module_d
    from module_o_orchestrator.exposure_layers import building_footprints, farmland_parcels

    buildings, _ = building_footprints()
    farmland, _ = farmland_parcels()
    x, y, half = 1_050_511.5, 1_706_245.2, 300  # §9 데모 trigger_location(생비량면) 주변
    risk = {
        "type": "Polygon",
        "coordinates": [[[x - half, y - half], [x + half, y - half],
                         [x + half, y + half], [x - half, y + half], [x - half, y - half]]],
    }
    result = module_d.run({
        "risk_polygons": [{"source_module": "A", "geometry_5179": risk, "risk_prob": 0.78}],
        "building_footprints_5179": buildings,
        "farmland_parcels_5179": farmland,
    })
    exposed = result["data"]["exposed_buildings"]
    assert exposed, "AOI 안 위험영역인데 노출 건물이 0건이면 레이어 배선이 끊긴 것"
    # building_id는 합성값(D-AUTO-*)이 아니라 실제 25자리 건물관리번호여야 한다 —
    # 건축물대장 주용도 조인키가 이 값이기 때문이다.
    assert all(len(b["building_id"]) == 25 and b["building_id"].isdigit() for b in exposed)
