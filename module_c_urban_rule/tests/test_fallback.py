"""D. 폴백·봉투·예외 안전성 (§4.2 graceful degradation, §7 폴백 계층 제안안)."""
from __future__ import annotations

import pytest

from module_c_urban_rule import run

BASE = {
    "underpass_id": "SC-UP-003",
    "rainfall_intensity_1h_mm": 45.0,
    "known_risk": True,
    "drainage_capacity_class": "low",
}


def _without(*keys):
    return {k: v for k, v in BASE.items() if k not in keys}


@pytest.mark.parametrize(
    "payload",
    [_without("drainage_capacity_class"), {**BASE, "drainage_capacity_class": "LOW"}],
    ids=["missing", "typo"],
)
def test_drainage_class_falls_back_to_worst_case(payload):
    """10. drainage_capacity_class 결측·오타 → tier 2 + 보수적(low) 대체 + warning."""
    result = run(payload)
    assert result["status"] == "degraded"
    assert result["fallback_tier"] == 2
    assert any("drainage_capacity_class" in w for w in result["warnings"])
    # low로 대체됐으므로 계약 예시와 같은 판정이 나와야 한다.
    assert result["data"]["alert_level"] == "위험"


def test_missing_known_risk_uses_conservative_true():
    """11. known_risk 결측 → tier 2 + 보수적 true (결정 1) + 지정된 warning 문구."""
    result = run(_without("known_risk"))
    assert result["status"] == "degraded"
    assert result["fallback_tier"] == 2
    assert "known_risk 결측 → 보수적 가정 적용(known_risk=true)" in result["warnings"]


def test_invalid_known_risk_type_also_conservative():
    """11-b. bool이 아닌 값(문자열 'true' 등)도 보수적 가정으로 흡수한다."""
    result = run({**BASE, "known_risk": "true"})
    assert result["fallback_tier"] == 2
    assert any("보수적 가정 적용" in w for w in result["warnings"])


def test_conservative_known_risk_actually_raises_level():
    """11-c. 보수적 가정이 실제로 등급을 올리는지 — 결측이 조용히 무시되면 안 된다."""
    missing = run({"underpass_id": "SC-UP-009", "rainfall_intensity_1h_mm": 10.0,
                   "drainage_capacity_class": "low"})
    explicit_false = run({**BASE, "underpass_id": "SC-UP-009",
                          "rainfall_intensity_1h_mm": 10.0, "known_risk": False})
    assert missing["data"]["alert_level"] == "주의"
    assert explicit_false["data"]["alert_level"] == "정상"


@pytest.mark.parametrize(
    "rainfall",
    [None, -1.0, float("nan"), float("inf"), "45", True],
    ids=["none", "negative", "nan", "inf", "string", "bool"],
)
def test_bad_rainfall_degrades_to_tier3_but_still_answers(rainfall):
    """12. 강우 결측·부적합 → tier 3, 그래도 유효한 alert_level을 낸다.

    bool은 int 서브클래스라 True가 1.0으로 조용히 통과하면 안 된다 — 명시적으로 막았다.
    """
    payload = dict(BASE)
    if rainfall is None:
        payload.pop("rainfall_intensity_1h_mm")
    else:
        payload["rainfall_intensity_1h_mm"] = rainfall

    result = run(payload)
    assert result["status"] == "degraded"
    assert result["fallback_tier"] == 3
    # known_risk=True이므로 min_level 정책에 따라 보수적으로 최소 '주의'
    assert result["data"]["alert_level"] == "주의"
    assert result["data"]["underpass_id"] == "SC-UP-003"
    assert any("rainfall_intensity_1h_mm" in w for w in result["warnings"])


def test_tier3_without_known_risk_stays_normal():
    """12-b. 강우 불명 + 비지정 지하차도는 근거가 없으니 '정상'."""
    result = run({**BASE, "known_risk": False, "rainfall_intensity_1h_mm": None})
    assert result["fallback_tier"] == 3
    assert result["data"]["alert_level"] == "정상"


@pytest.mark.parametrize("payload", [_without("underpass_id"), {**BASE, "underpass_id": "  "},
                                     {**BASE, "underpass_id": 123}, None, "not a dict"],
                         ids=["missing", "blank", "not-str", "none", "str"])
def test_missing_underpass_id_is_error_but_never_raises(payload):
    """13. underpass_id 결측 → status error, 그래도 유효한 봉투. 예외는 안 던진다."""
    result = run(payload)
    assert result["status"] == "error"
    assert result["fallback_tier"] == 3
    assert result["data"]["underpass_id"] == "UNKNOWN"
    assert result["data"]["alert_level"] == "정상"
    assert result["warnings"]


def test_unexpected_internal_error_becomes_error_envelope(monkeypatch):
    """14. 엔진 내부에서 예상 못 한 예외가 나도 run()은 예외를 밖으로 던지지 않는다."""
    import module_c_urban_rule as module_c

    def _boom(*args, **kwargs):
        raise RuntimeError("의도적 실패")

    monkeypatch.setattr(module_c.rules, "evaluate", _boom)
    result = run(BASE)
    assert result["status"] == "error"
    assert result["data"]["underpass_id"] == "SC-UP-003"
    assert any("의도적 실패" in w for w in result["warnings"])


def test_broken_ruleset_name_becomes_error_envelope(monkeypatch):
    """14-b. 존재하지 않는 룰셋을 가리켜도 죽지 않고 error 봉투로 내려앉는다."""
    monkeypatch.setenv("AQUAGUARD_MODULE_C_RULESET", "does_not_exist")
    result = run(BASE)
    assert result["status"] == "error"
    assert any("does_not_exist" in w for w in result["warnings"])


def test_run_many_is_independent_per_underpass():
    """추가. 배치 편의 함수는 한 건이 망가져도 나머지를 보존한다(§4.2의 취지)."""
    from module_c_urban_rule import run_many

    results = run_many([BASE, {"rainfall_intensity_1h_mm": 45.0}, {**BASE, "underpass_id": "SC-UP-004"}])
    assert [r["status"] for r in results] == ["ok", "error", "ok"]
    assert [r["data"]["underpass_id"] for r in results] == ["SC-UP-003", "UNKNOWN", "SC-UP-004"]
