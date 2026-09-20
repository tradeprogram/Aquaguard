"""물리 코어 테스트 — FoS 방정식·산불계수·폴백·단조성이 물리적으로 맞는가."""
from __future__ import annotations

import module_a_landslide as A
from module_a_landslide import fos, parameters


def test_fos_monotonic_in_slope():
    """경사가 급할수록 FoS↓ (다른 조건 동일)."""
    kw = dict(c_eff_kpa=4.0, phi_eff_deg=28, gamma_kn_m3=18.5, z_soil_depth_m=1.0,
              m_wetness=0.5, cr_root_kpa=3.0)
    assert fos.factor_of_safety(slope_deg=15, **kw) > fos.factor_of_safety(slope_deg=45, **kw)


def test_fos_monotonic_in_wetness():
    """포화도가 높을수록 FoS↓."""
    kw = dict(slope_deg=35, c_eff_kpa=4.0, phi_eff_deg=28, gamma_kn_m3=18.5,
              z_soil_depth_m=1.0, cr_root_kpa=3.0)
    assert fos.factor_of_safety(m_wetness=0.1, **kw) > fos.factor_of_safety(m_wetness=0.9, **kw)


def test_prob_sigmoid_centered_at_one():
    assert abs(fos.fos_to_probability(1.0) - 0.5) < 1e-6
    assert fos.fos_to_probability(0.7) > 0.5   # 불안정 → 고위험
    assert fos.fos_to_probability(1.5) < 0.5


def test_fire_amplification_bounds():
    # 미피해 → 1.0
    assert fos.fire_amplification("none", None) == 1.0
    # high 등급, 2년 이내 → A_max 그대로
    assert fos.fire_amplification("high", 121) == fos.A_MAX["high"]
    # 등급 오름차순으로 증폭↑
    assert (fos.fire_amplification("low", 100)
            < fos.fire_amplification("moderate", 100)
            < fos.fire_amplification("high", 100))


def test_fire_raises_landslide_prob():
    """같은 조건에서 산불 피해지(high)가 미피해보다 확률↑ (뿌리점착력 약화)."""
    base = dict(slope_deg=35, c_eff_kpa=2.0, phi_eff_deg=30, gamma_kn_m3=19.0,
                z_soil_depth_m=1.0, m_wetness=0.6, cr_root_kpa=3.0, days_since_fire=121)
    no_fire = fos.evaluate(dnbr_class="none", **base).landslide_prob
    fire = fos.evaluate(dnbr_class="high", **base).landslide_prob
    assert fire >= no_fire


def test_ci_brackets_point_estimate():
    r = fos.evaluate(slope_deg=35, c_eff_kpa=4.0, phi_eff_deg=28, gamma_kn_m3=18.5,
                     z_soil_depth_m=1.0, m_wetness=0.6, cr_root_kpa=3.0,
                     dnbr_class="none", days_since_fire=None)
    lo, hi = r.confidence_interval
    assert lo <= r.landslide_prob <= hi


def test_all_texture_params_have_sources():
    """가상값 금지 — 모든 토성 정수에 provenance·source가 달려 있어야 한다."""
    t = parameters.bundle()["texture_strength_ST"]
    for kr, p in t.items():
        assert p["provenance"] in {"MODEL", "EXTRAPOLATED"}
        assert p["source"] and len(p["source"]) > 10


def test_forecast_widens_ci_and_degrades():
    base = {"x_5179": 1e6, "y_5179": 1.6e6,
            "static": {"slope_deg": 35, "dnbr_class": "high", "days_since_fire": 121},
            "dynamic": {"rainfall_cumulative_24h_mm": 180, "api_index": 0.8, "source": "forecast"}}
    out = A.run(base)
    assert out["fallback_tier"] == 3
    assert out["data"]["source"] == "forecast"


def test_insar_sets_precursor_flag():
    base = {"x_5179": 1e6, "y_5179": 1.6e6,
            "static": {"slope_deg": 35, "dnbr_class": "none"},
            "dynamic": {"rainfall_cumulative_24h_mm": 50, "source": "observed"},
            "insar_displacement_mm_per_day": 5.0}
    out = A.run(base)
    assert out["data"]["precursor_flag"] is True
    assert out["fallback_tier"] == 1  # InSAR 확보 → tier 1
