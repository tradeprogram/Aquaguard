"""C. 폴백·봉투·예외 안전성 (§4.2 graceful degradation)."""
from __future__ import annotations

import pytest

from module_d_exposure_overlay import explain, run

from .conftest import collection, feature, offset_rect, risk


def test_missing_farmland_collection_degrades_but_keeps_buildings():
    """15. 농경지가 없어도 건물 노출은 그대로 살린다 — 부분 실패가 전체를 죽이지 않는다."""
    result = run(
        {
            "risk_polygons": [risk(offset_rect(0, 0, 300, 300), 0.78)],
            "building_footprints_5179": collection(
                feature(offset_rect(10, 10, 20, 20), building_id="B-001")
            ),
            "farmland_parcels_5179": {},
        }
    )
    assert result["status"] == "degraded"
    assert result["fallback_tier"] == 2
    assert [b["building_id"] for b in result["data"]["exposed_buildings"]] == ["B-001"]
    assert result["data"]["exposed_farmland_ha"] == 0.0
    assert any("farmland_parcels_5179" in w for w in result["warnings"])


def test_empty_but_wellformed_collections_are_not_degraded():
    """15-b. 형식이 맞는 빈 FeatureCollection은 '건물이 없다'는 정상 입력이다.

    형식 오류({})와 진짜 빈 목록(features: [])을 구분하지 않으면 정상 상황이
    계속 degraded로 보고돼 Module O의 fallback_tier가 오염된다.
    """
    result = run(
        {
            "risk_polygons": [risk(offset_rect(0, 0, 300, 300), 0.78)],
            "building_footprints_5179": collection(),
            "farmland_parcels_5179": collection(),
        }
    )
    assert result["status"] == "ok"
    assert result["fallback_tier"] == 1
    assert result["warnings"] == []


def test_point_geometry_is_buffered_loudly():
    """16. 점 좌표는 버퍼로 흡수하되 반드시 시끄럽게 — degraded + warning + ASSUMPTION."""
    payload = {
        "risk_polygons": [
            {"source_module": "A", "geometry_5179": {"x_5179": 1_050_000.0, "y_5179": 1_707_000.0}, "risk_prob": 0.78}
        ],
        "building_footprints_5179": collection(
            feature(offset_rect(10, 10, 20, 20), building_id="NEAR"),
            feature(offset_rect(500, 500, 510, 510), building_id="FAR"),
        ),
        "farmland_parcels_5179": collection(),
    }
    result = run(payload)
    assert result["status"] == "degraded"
    assert result["fallback_tier"] == 2
    assert [b["building_id"] for b in result["data"]["exposed_buildings"]] == ["NEAR"]
    assert any("반경 100.0m로 버퍼링" in w and "ASSUMPTION" in w for w in result["warnings"])

    detail = explain(payload)
    assert detail["used_point_buffer"] is True
    assert detail["buffer_is_assumption"] is True


def test_no_usable_risk_geometry_falls_back_to_tier3():
    """17. 쓸 수 있는 위험 지오메트리가 하나도 없으면 노출 0건 + tier 3."""
    result = run(
        {
            "risk_polygons": [
                {"source_module": "A", "geometry_5179": {}, "risk_prob": 0.78},
                {"source_module": "B", "geometry_5179": {"type": "Polygon", "coordinates": []}, "risk_prob": 0.61},
            ],
            "building_footprints_5179": collection(
                feature(offset_rect(10, 10, 20, 20), building_id="B-001")
            ),
            "farmland_parcels_5179": collection(feature(offset_rect(0, 0, 300, 300))),
        }
    )
    assert result["fallback_tier"] == 3
    assert result["data"] == {"exposed_buildings": [], "exposed_farmland_ha": 0.0}
    assert any("하나도 없음" in w for w in result["warnings"])


@pytest.mark.parametrize(
    "risk_prob,expected_tier,expected_exposed",
    [(1.4, 2, True), (-0.2, 2, True), ("높음", 2, False), (None, 2, False)],
    ids=["above-one", "negative", "string", "none"],
)
def test_out_of_range_risk_prob_is_clamped_and_bad_types_dropped(risk_prob, expected_tier, expected_exposed):
    """18. §4.1 확률 표기 위반은 보정하거나 버리되, 조용히 넘어가지 않는다."""
    result = run(
        {
            "risk_polygons": [{"source_module": "A", "geometry_5179": offset_rect(0, 0, 300, 300), "risk_prob": risk_prob}],
            "building_footprints_5179": collection(
                feature(offset_rect(10, 10, 20, 20), building_id="B-001")
            ),
            "farmland_parcels_5179": collection(),
        }
    )
    assert result["fallback_tier"] >= expected_tier
    assert bool(result["data"]["exposed_buildings"]) is expected_exposed
    if expected_exposed:
        assert 0.0 <= result["data"]["exposed_buildings"][0]["risk_prob"] <= 1.0


@pytest.mark.parametrize(
    "bad_input",
    [None, "not a dict", 42, {}, {"risk_polygons": {"type": "Polygon"}}],
    ids=["none", "str", "int", "empty-dict", "polygons-not-list"],
)
def test_structurally_broken_input_is_error_but_never_raises(bad_input):
    """19. 입력 구조가 깨지면 error 봉투 — 그래도 스키마를 만족하고 예외는 안 던진다."""
    result = run(bad_input)
    assert result["status"] == "error"
    assert result["fallback_tier"] == 3
    assert result["data"] == {"exposed_buildings": [], "exposed_farmland_ha": 0.0}
    assert result["warnings"]


def test_unexpected_internal_error_becomes_error_envelope(monkeypatch):
    """20. 엔진 내부에서 예상 못 한 예외가 나도 run()은 예외를 밖으로 던지지 않는다."""
    import module_d_exposure_overlay as module_d

    def _boom(*args, **kwargs):
        raise RuntimeError("의도적 실패")

    monkeypatch.setattr(module_d.overlay, "build_risk_union", _boom)
    result = run(
        {
            "risk_polygons": [risk(offset_rect(0, 0, 300, 300), 0.78)],
            "building_footprints_5179": collection(),
            "farmland_parcels_5179": collection(),
        }
    )
    assert result["status"] == "error"
    assert any("의도적 실패" in w for w in result["warnings"])


def test_broken_policy_file_becomes_error_envelope(monkeypatch):
    """20-b. 정책 파일을 못 읽어도 죽지 않고 error 봉투로 내려앉는다."""
    from module_d_exposure_overlay import policy

    monkeypatch.setattr(policy, "MODULE_D_POLICY", "does_not_exist")
    result = run({"risk_polygons": []})
    assert result["status"] == "error"
    assert any("does_not_exist" in w for w in result["warnings"])
