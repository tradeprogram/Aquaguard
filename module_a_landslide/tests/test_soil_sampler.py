"""토양격자 샘플러(a-1) + 원시 지반정수 주입 경로 테스트.

여기서 지키려는 것은 딱 두 가지다.
  1) 산청 AOI 안에서는 격자값이 실제로 쓰여서 위험 판정이 **나온다**
     (전국 폴백만 쓰던 시절엔 어떤 비가 와도 prob 이 0.7 을 못 넘어
      Module O 트리거가 영영 안 걸렸다 — 그 회귀를 막는다)
  2) AOI 밖에서는 격자를 쓰지 **않는다** — 조용히 남의 지역 토양을 쓰면
     안 되므로 폴백으로 돌아가야 한다
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import module_a_landslide as A
from module_a_landslide import parameters, soil_sampler

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = json.loads((ROOT / "contracts" / "module_a.example.json").read_text(encoding="utf-8"))

# 산청 AOI 안, 급사면 + 산불 high 인 실제 격자 셀(45번 산출에서 확인된 고위험 지점)
SANCHEONG_HIGH = (1030226.0, 1729619.0)
OUTSIDE_AOI = (956000.0, 1950000.0)   # 서울 부근 — 격자 밖


def _input(x, y, slope=37.6, dnbr=0.49, cls="high", soil=None):
    i = json.loads(json.dumps(EXAMPLE["input"]))
    i["x_5179"], i["y_5179"] = x, y
    i["static"].update(slope_deg=slope, dnbr=dnbr, dnbr_class=cls, days_since_fire=121)
    i["dynamic"].update(rainfall_cumulative_24h_mm=187.3, api_index=0.81,
                        rainfall_1h_mm=[30.0] * 24, source="observed")
    if soil is not None:
        i["_soil"] = soil
    return i


grid_required = pytest.mark.skipif(not soil_sampler.available(),
                                   reason="토양격자 npz 미탑재")


@grid_required
def test_sample_inside_aoi_returns_geotech():
    s = soil_sampler.sample(*SANCHEONG_HIGH)
    assert s is not None
    for k in ("c_kpa", "phi_deg", "gamma_kn_m3", "z_m", "m0"):
        assert isinstance(s[k], float)
    assert 0.0 < s["c_kpa"] < 50.0 and 0.0 < s["phi_deg"] < 60.0
    assert 0.0 <= s["m0"] <= 1.0 and s["z_m"] > 0
    assert s["provenance"] == "MEASURED"


def test_sample_outside_aoi_is_none():
    assert soil_sampler.sample(*OUTSIDE_AOI) is None


def test_sample_missing_coords_is_none():
    assert soil_sampler.sample(None, None) is None


@grid_required
def test_grid_lifts_prob_above_trigger():
    """격자를 쓰면 위험 판정이 나온다 — Module O 트리거(0.7)를 넘는다."""
    out = A.run(_input(*SANCHEONG_HIGH))
    assert out["data"]["landslide_prob"] >= 0.7


@grid_required
def test_national_fallback_cannot_trigger():
    """같은 조건이라도 전국 폴백 토양이면 임계를 못 넘는다(그래서 격자가 필요했다)."""
    out = A.run(_input(*SANCHEONG_HIGH,
                       soil={"texture_kr": parameters.NATIONAL_DEFAULT_TEXTURE_KR,
                             "ad_kr": parameters.NATIONAL_DEFAULT_AD_KR,
                             "dc_kr": parameters.NATIONAL_DEFAULT_DC_KR}))
    assert out["data"]["landslide_prob"] < 0.7


def test_outside_aoi_falls_back_with_warning():
    out = A.run(_input(*OUTSIDE_AOI))
    assert out["status"] in {"ok", "degraded"}
    assert any("폴백" in w for w in out["warnings"])


@grid_required
def test_grid_use_is_reported_in_warnings():
    out = A.run(_input(*SANCHEONG_HIGH))
    assert any("샘플링" in w for w in out["warnings"])


def test_raw_geotech_injection_overrides_grid():
    """_soil 에 원시 지반정수를 직접 주면 그 값이 쓰인다(시나리오 B 같은 격자 밖 재료)."""
    weathered = {"c_kpa": 2.0, "phi_deg": 36.0, "gamma_kn_m3": 19.0, "z_m": 1.0, "m0": 0.2}
    out = A.run(_input(*SANCHEONG_HIGH, soil=weathered))
    ex = A.explain(_input(*SANCHEONG_HIGH, soil=weathered))
    assert out["status"] in {"ok", "degraded"}
    assert ex["inputs"]["soil"]["c_kpa"] == 2.0
    assert ex["inputs"]["soil"]["phi_deg"] == 36.0
    assert ex["inputs"]["z_soil_depth_m"] == 1.0


def test_raw_geotech_partial_is_rejected():
    """c'/φ' 중 하나만 오면 원시 경로를 쓰지 않는다 — 반쪽 값으로 계산하면 안 된다."""
    assert parameters.strength_from_raw({"c_kpa": 2.0}) is None
    assert parameters.strength_from_raw({"phi_deg": 36.0}) is None
    assert parameters.strength_from_raw({"c_kpa": "x", "phi_deg": 1}) is None


def test_m0_override_changes_wetness():
    """m0 를 직접 주면 배수등급 룩업 대신 그 값이 기저가 된다."""
    st = parameters.texture_strength("사질")
    dry = parameters.wetness_from_rainfall(0.0, 0.0, "약간양호", st["ksat_m_s"], m0=0.05)
    wet = parameters.wetness_from_rainfall(0.0, 0.0, "약간양호", st["ksat_m_s"], m0=0.90)
    assert dry < wet
    assert abs(dry - 0.05) < 1e-6


def test_still_never_raises():
    for bad in [{}, {"x_5179": 1}, {"x_5179": 1, "y_5179": 2, "_soil": {"c_kpa": None}}]:
        assert A.run(bad)["status"] in {"ok", "degraded", "error"}


# --- 경사 격자 (2차 작업지시서) -------------------------------------------

slope_required = pytest.mark.skipif(not soil_sampler.slope_available(),
                                    reason="경사격자 npz 미탑재")


@slope_required
def test_slope_at_inside_aoi():
    s = soil_sampler.slope_at(*SANCHEONG_HIGH)
    assert s is not None and 0.0 <= s <= 80.0


def test_slope_at_outside_aoi_is_none():
    """AOI 밖에서 남의 지역 지형을 쓰지 않는다 — sample() 과 같은 규약."""
    assert soil_sampler.slope_at(*OUTSIDE_AOI) is None


@slope_required
def test_slope_at_matches_source_within_quantization():
    """uint8 × 0.3° 양자화라 원본과의 차이가 0.15°(=step/2)를 넘으면 안 된다."""
    # 5m 원본에서 확인해 둔 값 — 격자를 다시 만들어도 이 관계는 유지돼야 한다
    for (x, y), src in (((1028621.7, 1696861.2), 52.53),
                        ((1050511.5, 1706245.2), 32.67)):
        got = soil_sampler.slope_at(x, y)
        assert got is not None and abs(got - src) <= 0.15 + 1e-9, (x, y, got, src)


@slope_required
def test_slope_drives_trigger_across_boundary():
    """경사가 판정을 가른다 — 0.5° 차이로 임계를 넘나든다(지시서 표 재현)."""
    import json
    lo = A.run(_input(*SANCHEONG_HIGH, slope=32.5))["data"]["landslide_prob"]
    hi = A.run(_input(*SANCHEONG_HIGH, slope=33.5))["data"]["landslide_prob"]
    assert hi > lo


@slope_required
def test_slope_row_cache_is_consistent():
    """행 캐시를 타도 같은 값 — 차분 복원이 상태에 의존하지 않는다."""
    x, y = SANCHEONG_HIGH
    first = soil_sampler.slope_at(x, y)
    for dx in (0.0, 5.0, 10.0, 0.0):
        soil_sampler.slope_at(x + dx, y)
    assert soil_sampler.slope_at(x, y) == first
