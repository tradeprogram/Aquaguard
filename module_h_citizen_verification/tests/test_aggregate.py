"""B. 집계 판정 + C. 불변식."""
from __future__ import annotations

import pytest

from module_h_citizen_verification import explain, run

from .conftest import payload, report, sightings


def _data(reports, **kwargs):
    result = run(payload(reports, **kwargs))
    assert result["status"] in ("ok", "degraded"), result
    return result["data"]


def _mixed(sight=0, evac=0, false=0):
    out = []
    for i in range(sight):
        out.append(report(f"S{i:03d}", minutes_from_alert=5 + i, report_type="이상징후_목격"))
    for i in range(evac):
        out.append(report(f"E{i:03d}", minutes_from_alert=5 + i, report_type="이미_대피함"))
    for i in range(false):
        out.append(report(f"F{i:03d}", minutes_from_alert=5 + i, report_type="오탐_신고"))
    return out


# --- B. 판정 -----------------------------------------------------------------------


def test_no_reports_is_unverified_with_zero_adjustment():
    """4. 응답 0건 → 미확인 + 0.0 (§7 3순위: Module O는 원래 임계치 로직대로 진행)."""
    data = _data([])
    assert data["verification_status"] == "미확인"
    assert data["confidence_adjustment"] == 0.0
    assert data["response_latency_min"] is None


def test_few_reports_stay_unverified_with_small_adjustment():
    """5. 응답 소수(2건)는 현장확인 기준에 못 미치고 조정값도 작다."""
    data = _data(_mixed(sight=2))
    assert data["verification_status"] == "미확인"
    # 2 / (2 + 9) = 0.1818, × 0.3 = 0.05
    assert data["confidence_adjustment"] == 0.05


def test_enough_sightings_confirm_the_field():
    """6. 이상징후_목격 3건이면 가중 긍정 3.0 → 현장확인."""
    assert _data(_mixed(sight=3))["verification_status"] == "현장확인"


def test_majority_false_reports_flip_to_false_positive_with_negative_adjustment():
    """7. 오탐이 2건 이상이고 절반 이상이면 오탐판정 + 음수 조정."""
    data = _data(_mixed(sight=1, false=3))
    assert data["verification_status"] == "오탐판정"
    assert data["confidence_adjustment"] < 0


def test_single_false_report_cannot_flip_the_verdict():
    """7-b. 오탐 1건만으로는 뒤집히지 않는다 — 두 조건(건수·비율)을 함께 걸었다."""
    assert _data(_mixed(false=1))["verification_status"] == "미확인"
    assert _data(_mixed(sight=4, false=1))["verification_status"] == "현장확인"


def test_evacuation_reports_count_half():
    """8. 이미_대피함은 0.5 가중 — 현장 위험의 독립 확인이 아니라 경보 순응 신호다.

    목격 3건이면 현장확인이지만 대피 3건(1.5)만으로는 미확인, 6건(3.0)이면 현장확인.
    """
    assert _data(_mixed(evac=3))["verification_status"] == "미확인"
    assert _data(_mixed(evac=6))["verification_status"] == "현장확인"
    assert _data(_mixed(sight=2, evac=2))["verification_status"] == "현장확인"


def test_adjustment_matches_the_documented_formula():
    """9. raw = 가중합 / (n + k), × max_adjustment. explain()이 중간값을 그대로 보여준다."""
    detail = explain(payload(_mixed(sight=4, false=1)))["detail"]
    assert detail["weighted_positive"] == 4.0
    assert detail["weighted_net"] == 3.0
    assert detail["raw_ratio"] == pytest.approx(3.0 / (5 + 9))
    assert explain(payload(_mixed(sight=4, false=1)))["data"]["confidence_adjustment"] == 0.06


# --- C. 불변식 (상수가 바뀌어도 유지되어야 하는 성질) -------------------------------


@pytest.mark.parametrize("sight", [0, 1, 3, 10, 40])
@pytest.mark.parametrize("false", [0, 1, 5, 40])
def test_adjustment_always_within_contract_range(sight, false):
    """10. confidence_adjustment는 어떤 조합에서도 계약이 정한 [-0.3, 0.3] 안이다."""
    adjustment = _data(_mixed(sight=sight, false=false))["confidence_adjustment"]
    assert -0.3 <= adjustment <= 0.3


def test_more_sightings_never_lower_the_adjustment():
    """11. 목격이 늘면 조정값은 절대 낮아지지 않는다."""
    previous = -1.0
    for sight in range(0, 30):
        current = _data(_mixed(sight=sight))["confidence_adjustment"]
        assert current >= previous, f"목격 {sight}건에서 조정값 하락"
        previous = current


def test_more_false_reports_never_raise_the_adjustment():
    """12. 오탐이 늘면 조정값은 절대 높아지지 않는다."""
    previous = 1.0
    for false in range(0, 30):
        current = _data(_mixed(sight=5, false=false))["confidence_adjustment"]
        assert current <= previous, f"오탐 {false}건에서 조정값 상승"
        previous = current


@pytest.mark.parametrize("sight,evac,false", [(0, 0, 0), (1, 0, 0), (3, 2, 1), (10, 5, 5)])
def test_report_count_always_equals_valid_reports(sight, evac, false):
    """13. report_count는 항상 집계에 쓰인 유효 신고 수와 일치한다(2026-09-04 결정 1)."""
    reports = _mixed(sight=sight, evac=evac, false=false)
    detail = explain(payload(reports))["detail"]
    assert _data(reports)["report_count"] == len(reports) == detail["valid_count"]
    assert sum(detail["type_counts"].values()) == len(reports)
