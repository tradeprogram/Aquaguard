"""flood.py 수문모델 단위테스트 — 단조성·경계·MC 신뢰구간·골든타임."""
from __future__ import annotations

from module_b_flood import flood


def test_prob_monotonic_in_level():
    p1 = flood.flood_probability(1.0, 100)
    p2 = flood.flood_probability(4.0, 100)
    p3 = flood.flood_probability(8.0, 100)
    assert p1 < p2 < p3


def test_prob_monotonic_in_rain():
    assert flood.flood_probability(3.0, 50) < flood.flood_probability(3.0, 200)


def test_prob_bounds():
    assert 0.0 <= flood.flood_probability(-5, 0) <= 1.0
    assert flood.flood_probability(20, 500) > 0.99


def test_example_calibration():
    """계약 예시 3.2m·187mm → 0.61 근방."""
    p = flood.flood_probability(3.2, 187.3)
    assert 0.55 <= p <= 0.66


def test_mc_ci_brackets_prob():
    r = flood.evaluate(3.5, 160, river_order=3)
    lo, hi = r.confidence_interval
    assert lo <= r.flood_prob <= hi
    assert lo >= 0 and hi <= 1


def test_mc_reproducible():
    a = flood.evaluate(4.0, 150, 3).confidence_interval
    b = flood.evaluate(4.0, 150, 3).confidence_interval
    assert a == b   # seed 고정


def test_htc_zero_when_critical():
    r = flood.evaluate(8.0, 300, river_order=3)
    assert r.flood_prob >= 0.7 and r.hours_to_critical == 0.0


def test_htc_positive_when_rising():
    r = flood.evaluate(3.0, 180, river_order=3)
    assert r.hours_to_critical is None or r.hours_to_critical >= 0


def test_tier3_widens_ci():
    narrow = flood.evaluate(3.5, 160, 3, widen_ci=False).confidence_interval
    wide = flood.evaluate(3.5, 160, 3, widen_ci=True).confidence_interval
    assert wide[0] <= narrow[0] and wide[1] >= narrow[1]
