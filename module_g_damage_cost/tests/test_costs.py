"""B. 계산 + C. 불변식 + 출처 표기."""
from __future__ import annotations

import pytest

from module_g_damage_cost import explain, run

from .conftest import (FARMLAND_UNIT, HOUSING_UNIT, MIN_BAND, UNKNOWN_RATIO,
                       buildings, payload)


def _cost(*args, **kwargs) -> int:
    return run(payload(*args, **kwargs))["data"]["estimated_cost_krw"]


# --- B. 계산 -----------------------------------------------------------------------


@pytest.mark.parametrize("n", [0, 1, 5, 100])
def test_housing_count_times_unit_cost(n):
    """5. 주거 세대수 x 3,500,000원."""
    assert _cost(buildings(주거=n)) == n * HOUSING_UNIT


@pytest.mark.parametrize("ha,expected_m2", [(0.0, 0), (4.2, 42_000), (624.5, 6_245_000)])
def test_farmland_hectares_convert_to_square_meters(ha, expected_m2):
    """6. ha를 m2로 바꿔 대파대 단가를 곱한다."""
    assert _cost(farmland_ha=ha) == expected_m2 * FARMLAND_UNIT


def test_housing_and_farmland_are_summed():
    """7. 두 항을 더한다."""
    assert _cost(buildings(주거=3), farmland_ha=4.2) == 3 * HOUSING_UNIT + 42_000 * FARMLAND_UNIT


def test_rounding_happens_once_at_the_end():
    """8. 중간 반올림이 없어야 소수 ha에서 오차가 누적되지 않는다."""
    ha = 1.2345
    assert _cost(farmland_ha=ha) == round(ha * 10_000 * FARMLAND_UNIT)


@pytest.mark.parametrize("use_type", ["상업", "공업", "공공", "기타"])
def test_non_residential_is_excluded_from_the_point_estimate(use_type):
    """9. 비주거는 공식 침수 단가가 없어 점추정에서 제외한다."""
    assert _cost(buildings(**{use_type: 10})) == 0
    detail = explain(payload(buildings(**{use_type: 10})))["detail"]
    assert detail["buildings"]["excluded_total"] == 10
    assert detail["buildings"]["housing_counted"] == 0


def test_unknown_is_excluded_from_the_point_estimate_but_widens_the_range():
    """10. '미상'은 점추정에서 빠지고 상한에만 반영된다."""
    data = run(payload(buildings(주거=2, 미상=10)))["data"]
    assert data["estimated_cost_krw"] == 2 * HOUSING_UNIT
    assert data["cost_range_krw"][1] == 2 * HOUSING_UNIT + round(10 * UNKNOWN_RATIO * HOUSING_UNIT)


def test_lower_bound_is_the_point_estimate():
    """11. 하한은 점추정으로 고정한다(2026-09-05 결정 ①)."""
    for case in ([], buildings(주거=1), buildings(주거=5, 미상=3)):
        data = run(payload(case, farmland_ha=2.0))["data"]
        assert data["cost_range_krw"][0] == data["estimated_cost_krw"]


def test_minimum_band_keeps_the_range_from_collapsing():
    """12. '미상'이 0건이어도 폭 0인 구간이 나오지 않는다(§6 불확실성 표기)."""
    data = run(payload(buildings(주거=4)))["data"]
    point = data["estimated_cost_krw"]
    assert data["cost_range_krw"][1] == round(point * (1 + MIN_BAND))
    assert data["cost_range_krw"][1] > point


def test_unknown_term_wins_when_it_exceeds_the_minimum_band():
    """12-b. 미상이 많으면 최소 폭 대신 미상 항이 상한을 정한다."""
    data = run(payload(buildings(주거=1, 미상=50)))["data"]
    point = data["estimated_cost_krw"]
    assert data["cost_range_krw"][1] == point + round(50 * UNKNOWN_RATIO * HOUSING_UNIT)
    assert data["cost_range_krw"][1] > round(point * (1 + MIN_BAND))


# --- C. 불변식 (단가가 바뀌어도 유지되어야 하는 성질) -------------------------------


@pytest.mark.parametrize("housing", [0, 1, 7, 50])
@pytest.mark.parametrize("unknown", [0, 1, 20])
@pytest.mark.parametrize("ha", [0.0, 4.2])
def test_range_always_brackets_the_point_estimate(housing, unknown, ha):
    """13. low <= 점추정 <= high 가 항상 성립한다."""
    data = run(payload(buildings(주거=housing, 미상=unknown), farmland_ha=ha))["data"]
    low, high = data["cost_range_krw"]
    assert low <= data["estimated_cost_krw"] <= high


def test_more_housing_never_lowers_the_cost():
    """14. 주거 건물이 늘면 비용은 절대 낮아지지 않는다."""
    previous = -1
    for n in range(0, 20):
        current = _cost(buildings(주거=n), farmland_ha=1.0)
        assert current >= previous
        previous = current


def test_more_farmland_never_lowers_the_cost():
    """15. 농경지가 늘면 비용은 절대 낮아지지 않는다."""
    previous = -1
    for tenth in range(0, 200, 7):
        current = _cost(buildings(주거=2), farmland_ha=tenth / 10)
        assert current >= previous
        previous = current


def test_costs_are_never_negative():
    """16. 어떤 조합에서도 음수가 나오지 않는다."""
    for case in ([], buildings(상업=5), buildings(주거=1, 미상=3, 기타=2)):
        data = run(payload(case, farmland_ha=0.0))["data"]
        assert data["estimated_cost_krw"] >= 0
        assert all(v >= 0 for v in data["cost_range_krw"])


# --- 출처 표기 ---------------------------------------------------------------------


def test_basis_citation_names_both_notices_and_calls_itself_a_floor():
    """17. basis_citation에 고시명·호수·시행일과 '하한'이 들어간다."""
    basis = run(payload(buildings(주거=1)))["data"]["basis_citation"]
    assert "국토교통부고시 제2026-90호" in basis
    assert "농림축산식품부고시 제2026-78호" in basis
    assert "2026-02-19" in basis and "2026-07-30" in basis
    assert "복구비 지원 단가 기준" in basis and "하한" in basis


def test_explain_exposes_references_that_are_not_in_the_estimate():
    """18. 위험도 가중값·채소 민감도·산사태 단가는 explain()에만 나온다."""
    detail = explain(payload(buildings(주거=4), farmland_ha=4.2))["detail"]
    assert detail["point_estimate_label"] == "노출 자산 기준 조건부 피해액 (risk_prob 미가중)"

    refs = detail["references_not_in_estimate"]
    point = run(payload(buildings(주거=4), farmland_ha=4.2))["data"]["estimated_cost_krw"]
    # risk_prob 0.78이 기본이라 가중값은 점추정보다 작아야 한다.
    assert refs["risk_weighted_expected_krw"] < point
    # 채소 단가(530)가 일반작물(381)보다 비싸므로 민감도는 더 크다.
    assert refs["all_vegetable_sensitivity_krw"] > point
    assert refs["landslide_unit_costs"]["농경지_유실_per_m2"] == 7528
    assert refs["landslide_unit_costs"]["건물_소파_per_dong"] == 900000


def test_housing_assumption_is_stated_in_explain():
    """19. 1동=1세대 가정이 explain()에 남는다."""
    detail = explain(payload(buildings(주거=2)))["detail"]
    assert "1동 = 1세대" in detail["housing"]["assumption"]
    assert "hhldCnt" in detail["housing"]["assumption"]
