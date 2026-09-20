"""module_a_landslide.forecast — LDAPS 예보 시계열 → hours_to_critical (§5 Module A).

`hours_to_critical`은 "지금부터 몇 시간 뒤 위험임계(landslide_prob ≥ 0.7)를 넘는가"다.
관측값만으로는 미래 시각을 알 수 없다 — 이미 넘었으면 0, 아니면 판단불가(null)가
전부였다. 이 모듈이 **시간별 예보강우 시계열**을 받아 그 공백을 채운다.

물리 연쇄(fos.py·parameters.py와 동일, 새 물리 없음):
    예보 시간강우 → 24h 이동누적 → m(t) 습윤도 → FoS(t) → landslide_prob(t)
첫 초과 시각을 찾아 시간(h) 단위로 반환한다.

24h 이동누적은 과거 24시간 시간별 강우가 있어야 정확하다. 계약 input의
dynamic.rainfall_1h_mm(관측 이력)이 있으면 그대로 쓰고, 없으면
rainfall_cumulative_24h_mm을 24시간에 균등분배해 채운다(ASSUMPTION → warning).

정직: 예보강우 자체의 불확실성은 여기서 전파하지 않는다. 예보모드(tier 3)의
CI 확대는 __init__.run()이 이미 처리하며, hours_to_critical은 예보 시나리오
하나에 대한 결정론적 도달시각이다. 예보가 빗나가면 이 값도 빗나간다.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Any

from . import fos as _fos
from . import parameters as _params

# 예보 지평 상한. LDAPS 운영 예보가 +48h까지라 그 밖은 외삽하지 않는다(§5).
MAX_HORIZON_H = 48


@dataclass
class CriticalArrival:
    """hours_to_critical 산출 결과 + 판단 근거."""

    hours_to_critical: float | None
    peak_prob: float            # 예보 지평 내 최대 landslide_prob
    peak_hour: int | None       # 그 최대값이 나오는 시각(h)
    horizon_h: int              # 실제로 전진시킨 시간 수
    warnings: list[str]


def _past_window(rain_1h_mm: Any, rain_24h_mm: float | None) -> tuple[deque, list[str]]:
    """최근 24시간 시간별 강우 창(window)을 만든다. 없으면 균등분배 폴백."""
    warns: list[str] = []
    window: deque = deque(maxlen=24)

    values: list[float] = []
    if isinstance(rain_1h_mm, (list, tuple)):
        for v in rain_1h_mm:
            try:
                values.append(max(0.0, float(v)))
            except (TypeError, ValueError):
                continue

    if values:
        for v in values[-24:]:
            window.append(v)
    elif rain_24h_mm is not None and rain_24h_mm > 0:
        for _ in range(24):
            window.append(rain_24h_mm / 24.0)
        warns.append("과거 시간별 강우 미제공 → 24h 누적을 균등분배로 근사(ASSUMPTION). "
                     "이동누적 창이 부정확할 수 있음")
    else:
        for _ in range(24):
            window.append(0.0)

    while len(window) < 24:  # 24시간에 못 미치면 앞을 0으로 채움
        window.appendleft(0.0)
    return window, warns


def extract_series(input: dict, source: str) -> tuple[list[float], str | None]:
    """계약 input에서 미래 시간강우 시계열을 뽑는다. (series, provenance)

    우선순위 (_soil·_terrain 주입 관례와 동일):
      1) input["_forecast"]["rain_1h_mm"]   — LDAPS 등 명시 주입
      2) dynamic.source=="forecast"이면 dynamic.rainfall_1h_mm 자체가 예보 시계열
      그 외 → 빈 리스트(미래 없음)
    """
    fc = input.get("_forecast") or {}
    raw = fc.get("rain_1h_mm")
    if isinstance(raw, (list, tuple)) and len(raw) > 0:
        return _clean(raw), str(fc.get("source") or "forecast_injected")

    if source == "forecast":
        dynamic = input.get("dynamic") or {}
        raw = dynamic.get("rainfall_1h_mm")
        if isinstance(raw, (list, tuple)) and len(raw) > 0:
            return _clean(raw), "dynamic.rainfall_1h_mm(source=forecast)"

    return [], None


def _clean(raw) -> list[float]:
    out: list[float] = []
    for v in raw:
        try:
            out.append(max(0.0, float(v)))
        except (TypeError, ValueError):
            out.append(0.0)
    return out[:MAX_HORIZON_H]


def time_to_critical(
    *,
    future_rain_1h_mm: list[float],
    past_rain_1h_mm: Any,
    rain_24h_mm: float | None,
    api_index: float | None,
    dc_kr: str,
    m0: float | None,
    strength: dict,
    z_soil_depth_m: float,
    slope_deg: float,
    cr_eff_kpa: float,
    critical_prob: float,
    current_prob: float,
) -> CriticalArrival:
    """예보 시계열을 1시간씩 전진시키며 landslide_prob이 임계를 넘는 첫 시각을 찾는다."""
    warns: list[str] = []

    if current_prob >= critical_prob:
        return CriticalArrival(0.0, current_prob, 0, 0, warns)

    if not future_rain_1h_mm:
        return CriticalArrival(None, current_prob, None, 0, warns)

    window, w = _past_window(past_rain_1h_mm, rain_24h_mm)
    warns.extend(w)

    peak_prob = current_prob
    peak_hour: int | None = 0
    hit: float | None = None

    for h, rain_h in enumerate(future_rain_1h_mm, start=1):
        window.append(rain_h)                    # 24h 이동창: 가장 오래된 시간이 빠진다
        cum24 = float(sum(window))
        m = _params.wetness_from_rainfall(api_index, cum24, dc_kr,
                                          strength["ksat_m_s"], m0=m0)
        fos_t = _fos.factor_of_safety(slope_deg, strength["c_kpa"], strength["phi_deg"],
                                      strength["gamma_kn_m3"], z_soil_depth_m, m, cr_eff_kpa)
        prob_t = _fos.fos_to_probability(fos_t)

        if prob_t > peak_prob:
            peak_prob, peak_hour = prob_t, h
        if hit is None and prob_t >= critical_prob:
            hit = float(h)
            break                                # 첫 초과 시각이면 충분 — 더 볼 필요 없음

    horizon = len(future_rain_1h_mm) if hit is None else int(hit)
    if hit is None:
        warns.append(f"예보 지평 +{horizon}h 내 위험임계(P≥{critical_prob}) 미도달 "
                     f"→ hours_to_critical=null (지평 내 최대 P={round(peak_prob, 3)})")

    return CriticalArrival(hit, round(peak_prob, 3), peak_hour, horizon, warns)
