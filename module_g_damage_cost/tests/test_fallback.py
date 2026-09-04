"""D. 폴백·봉투·예외 안전성."""
from __future__ import annotations

import pytest

from module_g_damage_cost import explain, run

from .conftest import HOUSING_UNIT, buildings, payload


@pytest.mark.parametrize("bad_ha", [None, -1.0, "많이", float("nan"), True])
def test_bad_farmland_degrades_but_keeps_the_building_estimate(bad_ha):
    """20. 농경지가 부적합해도 건물 산정은 살린다 — 부분 실패가 전체를 죽이지 않는다."""
    result = run({"exposed_buildings": buildings(주거=3),
                  "exposed_farmland_ha": bad_ha,
                  "unit_cost_table_ref": "module_g_v1"})
    assert result["status"] == "degraded"
    assert result["fallback_tier"] == 2
    assert result["data"]["estimated_cost_krw"] == 3 * HOUSING_UNIT
    assert any("exposed_farmland_ha" in w for w in result["warnings"])


def test_off_vocabulary_use_type_is_treated_as_unknown():
    """21. 7종 어휘 밖 use_type은 '미상'과 같이 취급하고 그 사실을 남긴다."""
    odd = [{"building_id": "X", "risk_prob": 0.5, "use_type": "정체불명"}]
    result = run(payload(odd))
    assert result["fallback_tier"] == 2
    assert result["data"]["estimated_cost_krw"] == 0
    assert any("어휘 밖" in w for w in result["warnings"])
    detail = explain(payload(odd))["detail"]
    assert detail["buildings"]["off_vocabulary"] == ["정체불명"]
    assert detail["buildings"]["unknown_excluded"] == 1


def test_malformed_building_items_are_dropped_individually():
    """22. 항목 하나가 깨져도 나머지는 산정한다."""
    mixed = ["not a dict", {"building_id": "A"}] + buildings(주거=2)
    result = run(payload(mixed))
    assert result["fallback_tier"] == 2
    assert result["data"]["estimated_cost_krw"] == 2 * HOUSING_UNIT
    assert any("읽을 수 없는 건물 2건" in w for w in result["warnings"])


def test_nothing_usable_falls_back_to_tier3():
    """23. 건물도 농경지도 없으면 0원 + tier 3."""
    result = run(payload([], farmland_ha=0.0))
    assert result["fallback_tier"] == 3
    assert result["data"]["estimated_cost_krw"] == 0
    assert result["data"]["cost_range_krw"] == [0, 0]
    assert any("모두 산정할 수 없음" in w for w in result["warnings"])


def test_table_ref_mismatch_stays_ok_but_says_so():
    """24. unit_cost_table_ref 불일치는 status ok + warning + basis_citation 명시.

    Module O가 재해연보_2024_원단위를 하드코딩해 넘기고 있어 상시 불일치다
    (TRACK2_CONTRACT_AGENDA.md 10번). 요청한 표를 쓴 척하지 않는 게 핵심이다.
    """
    result = run(payload(buildings(주거=1), table_ref="재해연보_2024_원단위"))
    assert result["status"] == "ok"
    assert result["fallback_tier"] == 1
    assert any("재해연보_2024_원단위" in w and "실제 사용" in w for w in result["warnings"])
    assert "재해연보_2024_원단위" in result["data"]["basis_citation"]
    assert "module_g_v1" in result["data"]["basis_citation"]


def test_matching_table_ref_is_silent():
    """24-b. 우리 표를 정확히 요청하면 경고가 없다."""
    assert run(payload(buildings(주거=1), table_ref="module_g_v1"))["warnings"] == []


@pytest.mark.parametrize(
    "bad_input", [None, "str", 42, {}, {"exposed_buildings": {}}, {"exposed_buildings": None}],
    ids=["none", "str", "int", "empty", "dict", "none-list"],
)
def test_structurally_broken_input_is_error_but_never_raises(bad_input):
    """25. 입력 구조가 깨지면 error 봉투 — 스키마는 만족하고 예외는 안 던진다."""
    result = run(bad_input)
    assert result["status"] == "error"
    assert result["fallback_tier"] == 3
    assert result["data"]["estimated_cost_krw"] == 0
    assert result["warnings"]


def test_unexpected_internal_error_becomes_error_envelope(monkeypatch):
    """26. 엔진 내부 예외도 봉투로 흡수한다."""
    import module_g_damage_cost as module_g

    def _boom(*args, **kwargs):
        raise RuntimeError("의도적 실패")

    monkeypatch.setattr(module_g.costs, "summarize_buildings", _boom)
    result = run(payload(buildings(주거=1)))
    assert result["status"] == "error"
    assert any("의도적 실패" in w for w in result["warnings"])


def test_explain_survives_broken_input():
    """27. explain()도 구조가 깨진 입력에서 죽지 않는다."""
    detail = explain(None)
    assert detail["detail"] is None
    assert detail["data"]["estimated_cost_krw"] == 0
