"""E. 경보 시각 3단 폴백 + §7 폴백 계층 + 예외 안전성."""
from __future__ import annotations

import pytest

from module_h_citizen_verification import explain, run

from .conftest import ALERT_AT, ORIGIN_X, ORIGIN_Y, payload, report, sightings


def test_latency_uses_alert_issued_at_when_present():
    """21. 1순위 — alert_issued_at이 있으면 그것 기준, degraded 아님."""
    result = run(payload(sightings(3, first_at=4.5)))
    assert result["status"] == "ok"
    assert result["fallback_tier"] == 1
    assert result["data"]["response_latency_min"] == 4.5
    assert explain(payload(sightings(3, first_at=4.5)))["detail"]["alert_time"]["source"] == "alert_issued_at"


def test_latency_falls_back_to_alert_id_pattern():
    """22. 2순위 — alert_id의 네이밍 관습에서 뽑되 반드시 degraded로 내린다.

    관습은 계약이 아니다. AL-20250719-0915 → 09:15 KST.
    """
    body = payload(sightings(3, first_at=4.5), with_alert_issued_at=False)
    result = run(body)
    assert result["status"] == "degraded"
    assert result["fallback_tier"] == 2
    assert result["data"]["response_latency_min"] == 4.5
    assert any("alert_id 네이밍 관습" in w for w in result["warnings"])
    assert explain(body)["detail"]["alert_time"]["source"] == "alert_id_pattern"


def test_latency_is_null_when_the_alert_time_is_unknowable():
    """23. 3순위 — 둘 다 없으면 null. 스키마가 null을 허용하는 이유가 이것이다."""
    body = payload(sightings(3), with_alert_issued_at=False)
    body["alert_id"] = "정체불명-경보"
    result = run(body)
    assert result["data"]["response_latency_min"] is None
    assert result["fallback_tier"] == 2
    assert any("경보 발송 시각을 알 수 없음" in w for w in result["warnings"])
    # 시간창 필터를 적용할 수 없으므로 신고는 전부 살아남는다.
    assert result["data"]["report_count"] == 3


def test_time_window_is_skipped_when_the_alert_time_is_unknown():
    """23-b. 경보 시각을 모르면 시간창으로 신고를 버리지 않는다 — 기준이 없으니까."""
    body = payload([report("LATE", minutes_from_alert=600)], with_alert_issued_at=False)
    body["alert_id"] = "정체불명-경보"
    assert run(body)["data"]["report_count"] == 1


@pytest.mark.parametrize(
    "count,expected_tier",
    [(0, 3), (1, 2), (2, 2), (3, 1), (10, 1)],
)
def test_fallback_tier_follows_the_response_volume(count, expected_tier):
    """24. §7 Module H 행 그대로 — 응답 다수(1) / 소수(2) / 0건(3)."""
    assert run(payload(sightings(count)))["fallback_tier"] == expected_tier


def test_zero_reports_keeps_module_o_on_its_original_threshold():
    """25. 응답 0건이면 조정값 0.0 — §7이 명시한 '원래 임계치 로직 유지'."""
    result = run(payload([]))
    assert result["fallback_tier"] == 3
    assert result["status"] == "degraded"
    assert result["data"] == {
        "report_count": 0,
        "verification_status": "미확인",
        "confidence_adjustment": 0.0,
        "response_latency_min": None,
    }


@pytest.mark.parametrize(
    "bad_input",
    [
        None,
        "not a dict",
        42,
        {},
        {"trigger_location": {"x_5179": 1.0}, "trigger_radius_m": 500, "citizen_reports": []},
        {"trigger_location": {"x_5179": 1.0, "y_5179": 2.0}, "trigger_radius_m": 500, "citizen_reports": {}},
        {"trigger_location": {"x_5179": 1.0, "y_5179": 2.0}, "trigger_radius_m": -1, "citizen_reports": []},
    ],
    ids=["none", "str", "int", "empty", "no-y", "reports-not-list", "negative-radius"],
)
def test_structurally_broken_input_is_error_but_never_raises(bad_input):
    """26. 입력 구조가 깨지면 error 봉투 — 그래도 스키마를 만족하고 예외는 안 던진다."""
    result = run(bad_input)
    assert result["status"] == "error"
    assert result["fallback_tier"] == 3
    assert result["data"]["confidence_adjustment"] == 0.0
    assert result["data"]["verification_status"] == "미확인"
    assert result["warnings"]


def test_unexpected_internal_error_becomes_error_envelope(monkeypatch):
    """27. 집계 내부에서 예상 못 한 예외가 나도 run()은 예외를 밖으로 던지지 않는다."""
    import module_h_citizen_verification as module_h

    def _boom(*args, **kwargs):
        raise RuntimeError("의도적 실패")

    monkeypatch.setattr(module_h.aggregate_module, "aggregate", _boom)
    result = run(payload(sightings(3)))
    assert result["status"] == "error"
    assert any("의도적 실패" in w for w in result["warnings"])


def test_broken_policy_name_becomes_error_envelope(monkeypatch):
    """27-b. 존재하지 않는 정책을 가리켜도 죽지 않고 error 봉투로 내려앉는다."""
    monkeypatch.setenv("AQUAGUARD_MODULE_H_POLICY", "does_not_exist")
    result = run(payload(sightings(3)))
    assert result["status"] == "error"
    assert any("does_not_exist" in w for w in result["warnings"])


def test_explain_reports_the_error_path_too():
    """28. explain()도 구조가 깨진 입력에서 죽지 않는다."""
    detail = explain(None)
    assert detail["detail"] is None
    assert detail["fallback_tier"] == 3
    assert detail["data"]["confidence_adjustment"] == 0.0
