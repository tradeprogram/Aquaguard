"""§4.2 계약 준수·폴백 계층 테스트 (Module B).
contracts/module_b.schema.json 구조 + 모든 폴백 tier에서 봉투가 스키마를 만족.
"""
from __future__ import annotations

import module_b_flood as mb

VALID_KEYS = {"status", "fallback_tier", "data", "warnings"}
DATA_KEYS = {"flood_prob", "confidence_interval", "hours_to_critical", "inundation_extent_5179"}


def _assert_envelope(out):
    assert set(out.keys()) == VALID_KEYS
    assert out["status"] in ("ok", "degraded", "error")
    assert out["fallback_tier"] in (1, 2, 3)
    assert isinstance(out["warnings"], list)
    d = out["data"]
    assert DATA_KEYS <= set(d.keys())
    assert 0.0 <= d["flood_prob"] <= 1.0
    ci = d["confidence_interval"]
    assert isinstance(ci, list) and len(ci) == 2
    assert 0.0 <= ci[0] <= ci[1] <= 1.0
    assert d["hours_to_critical"] is None or d["hours_to_critical"] >= 0
    fc = d["inundation_extent_5179"]
    assert fc["type"] == "FeatureCollection" and isinstance(fc["features"], list)


def test_contract_example():
    """contracts/module_b.example.json 입력 → 스키마 만족 + 합리적 prob."""
    inp = {"reach_id": "GEUMHO_042",
           "static": {"drainage_area_km2": 58.2, "river_order": 3, "slope_pct": 1.8},
           "dynamic": {"rainfall_cumulative_24h_mm": [187.3], "river_level_m": 3.2},
           "sar_water_extent": None}
    out = mb.run(inp)
    _assert_envelope(out)
    assert out["fallback_tier"] == 2          # SAR 없음
    assert 0.5 <= out["data"]["flood_prob"] <= 0.72   # 예시 0.61 근방


def test_tier1_with_sar():
    inp = {"reach_id": "R1", "static": {"drainage_area_km2": 60, "river_order": 3, "slope_pct": 2},
           "dynamic": {"rainfall_cumulative_24h_mm": [120], "river_level_m": 4.0},
           "sar_water_extent": {"type": "FeatureCollection", "features": []}}
    out = mb.run(inp)
    _assert_envelope(out)
    assert out["fallback_tier"] == 1 and out["status"] == "ok"


def test_tier3_no_level():
    inp = {"reach_id": "R2", "static": {"river_order": 2},
           "dynamic": {"rainfall_cumulative_24h_mm": [90]}}
    out = mb.run(inp)
    _assert_envelope(out)
    assert out["fallback_tier"] == 3 and out["status"] == "degraded"


def test_error_no_reach_id():
    out = mb.run({"static": {}, "dynamic": {}})
    _assert_envelope(out)
    assert out["status"] == "error"


def test_never_raises_on_garbage():
    for bad in [{}, {"reach_id": "x"}, {"reach_id": "x", "dynamic": {"river_level_m": "NaN"}},
                {"reach_id": "x", "dynamic": {"rainfall_cumulative_24h_mm": "oops"}}, None.__class__]:
        try:
            out = mb.run(bad if isinstance(bad, dict) else {})
        except Exception as e:  # noqa: BLE001
            raise AssertionError(f"run() raised: {e}")
        _assert_envelope(out)


def test_major_flood_high_prob():
    """산청 경호강 실측 피크(수위 8.67m·강우~300mm) → 대홍수 확률."""
    inp = {"reach_id": "GYEONGHO", "static": {"river_order": 4},
           "dynamic": {"rainfall_cumulative_24h_mm": [300], "river_level_m": 8.67},
           "sar_water_extent": {"features": [1]}}
    out = mb.run(inp)
    assert out["data"]["flood_prob"] >= 0.95
    assert out["data"]["hours_to_critical"] == 0.0   # 이미 임계 초과
