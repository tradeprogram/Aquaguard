"""module_b_flood.flood — 하천범람 확률·골든타임 수문 모델 (계약 무관).

flood_prob 은 순수 ML이 아니라, 실측 수위·강우를 홍수특보 기준·실측 홍수사례로
보정한 로지스틱(설명가능). SFINCS/ANUGA 물리모형은 오프라인 보정·검증 근거
(README·DATA_SOURCES)이며, 여기서는 실시간 추론용 대리모형(surrogate)을 쓴다.

보정 근거:
- L_REF=3.0m  : 일반 하천 주의수위 수준(HRFCO 홍수특보 attwl 관례)
- R_REF=150mm : 24h 호우경보 수준(기상청 호우특보 기준)
- 검증: 산청 경호강 2025-07-19 실측 피크 수위 8.67m·강우≈300mm → prob≈0.99(대홍수)로 재현
- 계약 예시(river_level 3.2m, rain 187mm)와 prob≈0.61 일치
"""
from __future__ import annotations

import math
from dataclasses import dataclass

L_REF = 3.0        # m, 기준 수위
R_REF = 150.0      # mm/24h, 기준 강우
SLOPE_WL = 0.70    # 수위 민감도 (1/m)
SLOPE_R = 0.008    # 강우 민감도 (1/mm)
CRITICAL_PROB = 0.7
RISE_COEF = 0.02   # m 상승 per (mm/h) — 하천 응답계수(소하천 빠름), 차수로 보정

MC_N = 1000        # 몬테카를로 반복(SPEC §4)
MC_SEED = 42


def _sigmoid(x: float) -> float:
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    e = math.exp(x)
    return e / (1.0 + e)


def logit_score(river_level_m: float | None, rain_24h_mm: float | None) -> float:
    """로지스틱 선형결합 z. 결측은 기준값(중립)으로 대체."""
    lvl = L_REF if river_level_m is None else river_level_m
    rain = R_REF if rain_24h_mm is None else rain_24h_mm
    return SLOPE_WL * (lvl - L_REF) + SLOPE_R * (rain - R_REF)


def flood_probability(river_level_m: float | None, rain_24h_mm: float | None) -> float:
    return _sigmoid(logit_score(river_level_m, rain_24h_mm))


@dataclass
class FloodResult:
    flood_prob: float
    confidence_interval: tuple[float, float]
    hours_to_critical: float | None


def _rise_rate_m_per_h(rain_24h_mm: float | None, river_order: int) -> float:
    """진행 강우로 인한 수위 상승률(m/h). 소하천(저차수) 응답 빠름."""
    if rain_24h_mm is None or rain_24h_mm <= 0:
        return 0.0
    order_factor = max(0.5, 1.6 - 0.2 * river_order)  # 1차↑ 소하천 빠르게
    return (rain_24h_mm / 24.0) * RISE_COEF * order_factor


def hours_to_critical(prob: float, river_level_m: float | None,
                      rain_24h_mm: float | None, river_order: int) -> float | None:
    """임계확률(0.7) 도달까지 시간. 이미 초과=0.0, 근거부족=None."""
    if prob >= CRITICAL_PROB:
        return 0.0
    if river_level_m is None or rain_24h_mm is None:
        return None
    rate = _rise_rate_m_per_h(rain_24h_mm, river_order)
    if rate <= 1e-6:
        return None
    # 현재 강우 하에서 prob=0.7이 되는 수위 L_crit
    z_crit = math.log(CRITICAL_PROB / (1 - CRITICAL_PROB))   # ≈0.847
    rain_term = SLOPE_R * (rain_24h_mm - R_REF)
    l_crit = L_REF + (z_crit - rain_term) / SLOPE_WL
    dh = l_crit - river_level_m
    if dh <= 0:
        return 0.0
    return round(min(dh / rate, 72.0), 1)


def evaluate(river_level_m: float | None, rain_24h_mm: float | None,
             river_order: int, widen_ci: bool = False) -> FloodResult:
    """flood_prob + 몬테카를로 신뢰구간 + hours_to_critical."""
    import random
    prob = flood_probability(river_level_m, rain_24h_mm)

    # MC: 수위 ±0.3m, 강우 ±15% 섭동 → prob 분포 → [5%,95%]
    rng = random.Random(MC_SEED)
    samples = []
    for _ in range(MC_N):
        lvl = None if river_level_m is None else river_level_m + rng.gauss(0, 0.30)
        rn = None if rain_24h_mm is None else rain_24h_mm * (1 + rng.gauss(0, 0.15))
        samples.append(flood_probability(lvl, rn))
    samples.sort()
    lo = samples[int(0.05 * MC_N)]
    hi = samples[int(0.95 * MC_N) - 1]
    if widen_ci:   # tier 3: 예측 불확실성 확대
        lo = max(0.0, lo - 0.10)
        hi = min(1.0, hi + 0.10)

    htc = hours_to_critical(prob, river_level_m, rain_24h_mm, river_order)
    return FloodResult(flood_prob=round(prob, 3),
                       confidence_interval=(round(lo, 3), round(hi, 3)),
                       hours_to_critical=htc)
