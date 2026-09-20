"""hours_to_critical(a-htc) — 예보 시계열 전진적분 테스트.

단조성(비가 셀수록 빨리 도달)·경계(미도달 null·이미초과 0)·계약 타입을 본다.
FoS 물리는 test_fos.py가, 봉투는 test_contract.py가 이미 검증하므로 여기서는
'예보 → 도달시각' 변환만 좁게 확인한다.
"""
from __future__ import annotations

import json
from pathlib import Path

import module_a_landslide as A
from module_a_landslide import envelope as _env, forecast

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = json.loads((ROOT / "contracts" / "module_a.example.json").read_text(encoding="utf-8"))

# 조립질(사질) 급사면 — 포화 시 실제로 FoS<1이 되는 재료. 식양질은 포화해도
# FoS≈1.9라 도달시각이 영영 안 나와서 이 테스트의 대상이 아니다(물리대로).
SANDY = {"texture_kr": "사질", "ad_kr": "50-100", "dc_kr": "약간양호"}

# 기준 경사 30°: 이 조합의 무강우 기저 prob 이 0.348 로 임계(CRITICAL_PROB=0.5) 아래라
# "예보를 넣어야 비로소 도달한다"를 시험할 수 있다. 35°는 기저 0.587 로 이미 임계를
# 넘어 htc 가 항상 0 이 되어 예보 로직을 못 시험한다. (임계 재유도로 바뀐 값)
BASE_SLOPE = 30.0


def _input(slope=BASE_SLOPE, rain=None, soil=SANDY, api=0.3, cum24=20.0, source="observed"):
    i = json.loads(json.dumps(EXAMPLE["input"]))
    i["static"]["slope_deg"] = slope
    i["dynamic"]["api_index"] = api
    i["dynamic"]["rainfall_cumulative_24h_mm"] = cum24
    i["dynamic"]["rainfall_1h_mm"] = [1.0] * 24
    i["dynamic"]["source"] = source
    if soil:
        i["_soil"] = soil
    if rain is not None:
        i["_forecast"] = {"source": "LDAPS", "rain_1h_mm": rain}
    return i


def _htc(**kw):
    return A.run(_input(**kw))["data"]["hours_to_critical"]


def test_heavy_rain_reaches_critical():
    h = _htc(rain=[30.0] * 12)
    assert h is not None and 0 < h <= 12


def test_no_rain_never_reaches():
    assert _htc(rain=[0.0] * 12) is None


def test_heavier_rain_arrives_no_later():
    """단조성: 같은 사면에서 비가 더 세면 도달이 늦어질 수 없다."""
    fast = _htc(rain=[40.0] * 12)
    slow = _htc(rain=[10.0] * 12)
    assert fast is not None
    assert slow is None or fast <= slow


def test_gentle_slope_does_not_reach():
    assert _htc(slope=20.0, rain=[30.0] * 12) is None


def test_missing_forecast_keeps_null():
    """예보 미주입이면 종전 거동(관측만으로는 판단불가)."""
    assert _htc(rain=None) is None


def test_already_critical_returns_zero():
    """현재 이미 임계 초과면 0.0 — 미래를 볼 것도 없다."""
    out = A.run(_input(slope=45.0, rain=[30.0] * 6, api=1.0, cum24=300.0))
    d = out["data"]
    if d["landslide_prob"] >= _env.CRITICAL_PROB:
        assert d["hours_to_critical"] == 0.0


def test_contract_type_is_number_or_null():
    for rain in ([30.0] * 12, [0.0] * 6, None):
        h = _htc(rain=rain)
        assert h is None or isinstance(h, (int, float))


def test_forecast_mode_series_is_used():
    """source=forecast면 dynamic.rainfall_1h_mm 자체가 예보 시계열(_forecast 없이도)."""
    i = _input(rain=None, source="forecast")
    i["dynamic"]["rainfall_1h_mm"] = [35.0] * 12
    out = A.run(i)
    assert out["fallback_tier"] == 3
    assert out["data"]["hours_to_critical"] is not None


def test_horizon_is_capped():
    series, _ = forecast.extract_series(
        {"_forecast": {"rain_1h_mm": [1.0] * 200}}, "observed")
    assert len(series) == forecast.MAX_HORIZON_H


def test_series_never_raises_on_garbage():
    series, _ = forecast.extract_series(
        {"_forecast": {"rain_1h_mm": [None, "x", -5, 3.0]}}, "observed")
    assert series == [0.0, 0.0, 0.0, 3.0]


def test_warning_explains_null():
    out = A.run(_input(rain=[0.0] * 6))
    assert any("미도달" in w for w in out["warnings"])
