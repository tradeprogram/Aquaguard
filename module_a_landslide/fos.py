"""module_a_landslide.fos — 무한사면 안전율(FoS) 물리 코어 (§5 Module A).

TRIGRS와 동일한 물리원리(강우침투 → 포화도/간극수압 → Factor of Safety)의
Infinite Slope 구현. landslide_prob은 이 FoS를 변환한 값이며, 순수 ML 확률이
아니다(ARCHITECTURE §5 Module A 방법론 확정 준수).

지반정수는 전부 출판 문헌값(module_a_landslide/DATA_SOURCES.md):
  P1 Frontiers Forests & Global Change 2026, DOI 10.3389/ffgc.2026.1842027, Table 1
  P2 PSU GEOL 615 'Some Useful Numbers' (Waltham/Holtz&Kovacs 계열)
  P3 Hwangryeong Mt., Busan, MDPI Sustainability 2020, 12(7):2839
가상값 없음. 모델 구조(FoS→확률 시그모이드, 몬테카를로 CI)는 산청 백테스트로
보정 예정(HANDOFF §9.3) — 미보정 구간은 provenance로 표기한다.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

GAMMA_W_KN_M3 = 9.81  # 물 단위중량

# f(dNBR, Δt) 산불 증폭계수 — ARCHITECTURE §2.5 (Key&Benson 2006 dNBR 등급)
A_MAX = {"none": 1.0, "low": 1.2, "moderate": 2.0, "high": 3.75}  # high 3.5~4.0 중앙값
FIRE_DECAY_DAYS = 730  # Δt<2년 감쇠없음(§2.5). 이후는 NDVI 회복곡선(미확보 → 선형 taper, ASSUMPTION)


def fire_amplification(dnbr_class: str, days_since_fire: int | None) -> float:
    """f(dNBR, Δt) = 1 + (A_max(class) - 1) × decay(Δt).  근거: ARCHITECTURE §2.5."""
    a_max = A_MAX.get((dnbr_class or "none").lower(), 1.0)
    if a_max <= 1.0 or days_since_fire is None:
        return max(a_max, 1.0) if days_since_fire is not None else 1.0
    if days_since_fire <= FIRE_DECAY_DAYS:
        decay = 1.0
    else:
        # 2년 이후 선형 taper(3년에 걸쳐 1.0→0), NDVI 회복곡선 확보 시 교체 — ASSUMPTION
        decay = max(0.0, 1.0 - (days_since_fire - FIRE_DECAY_DAYS) / (3 * 365))
    return 1.0 + (a_max - 1.0) * decay


def factor_of_safety(
    slope_deg: float,
    c_eff_kpa: float,
    phi_eff_deg: float,
    gamma_kn_m3: float,
    z_soil_depth_m: float,
    m_wetness: float,
    cr_root_kpa: float = 0.0,
) -> float:
    """무한사면 안전율.

    FoS = [c' + Cr + (γ − m·γ_w)·z·cos²β·tanφ'] / [γ·z·sinβ·cosβ]
    m_wetness = 지하수위/토심 (0~1). β=slope. FoS<1 → 붕괴.
    """
    beta = math.radians(max(0.1, min(slope_deg, 89.0)))
    z = max(z_soil_depth_m, 1e-3)
    driving = gamma_kn_m3 * z * math.sin(beta) * math.cos(beta)
    if driving <= 0:
        return float("inf")
    m = max(0.0, min(m_wetness, 1.0))
    resisting = (c_eff_kpa + cr_root_kpa
                 + (gamma_kn_m3 - m * GAMMA_W_KN_M3) * z * math.cos(beta) ** 2
                 * math.tan(math.radians(phi_eff_deg)))
    return resisting / driving


def fos_to_probability(fos: float, k: float = 6.0) -> float:
    """FoS → landslide_prob 시그모이드(FoS=1에서 0.5). k는 산청 백테스트로 보정 예정.

    P = 1 / (1 + exp(k·(FoS − 1)))  — FoS<1이면 P>0.5. 구조는 MODEL,
    기울기 k는 미보정(기본 6.0, 문헌 관행 범위). 근거: HANDOFF §9.3 보정 대상.
    """
    fos = max(0.0, min(fos, 5.0))
    return 1.0 / (1.0 + math.exp(k * (fos - 1.0)))


@dataclass
class FoSResult:
    fos: float
    landslide_prob: float
    confidence_interval: tuple[float, float]
    amplification_factor: float


def evaluate(
    slope_deg: float,
    c_eff_kpa: float,
    phi_eff_deg: float,
    gamma_kn_m3: float,
    z_soil_depth_m: float,
    m_wetness: float,
    cr_root_kpa: float,
    dnbr_class: str,
    days_since_fire: int | None,
    n_mc: int = 500,
    seed: int = 42,
) -> FoSResult:
    """FoS 계산 + 산불 증폭(뿌리점착력 감소) + 몬테카를로 신뢰구간.

    산불 결합(§2.5): burned 셀은 뿌리점착력이 f배로 약화 → Cr_eff = Cr / f.
    (불이 뿌리를 죽인다는 물리. amplification_factor = f를 계약 output에 보고.)
    """
    import random
    f = fire_amplification(dnbr_class, days_since_fire)
    cr_eff = cr_root_kpa / f  # 산불 피해 → 뿌리점착력 약화

    base_fos = factor_of_safety(slope_deg, c_eff_kpa, phi_eff_deg,
                                gamma_kn_m3, z_soil_depth_m, m_wetness, cr_eff)
    base_prob = fos_to_probability(base_fos)

    # 몬테카를로: 문헌 불확실성(±)으로 c',phi',z 섭동 → 확률 분포 → [5%,95%]
    rng = random.Random(seed)
    probs = []
    for _ in range(n_mc):
        c_s = max(0.0, rng.gauss(c_eff_kpa, 0.30 * max(c_eff_kpa, 1.0)))   # ±30%
        phi_s = rng.gauss(phi_eff_deg, 2.5)                                # ±2.5°
        z_s = max(0.05, rng.gauss(z_soil_depth_m, 0.20 * z_soil_depth_m))  # ±20%
        fos_s = factor_of_safety(slope_deg, c_s, phi_s, gamma_kn_m3, z_s, m_wetness, cr_eff)
        probs.append(fos_to_probability(fos_s))
    probs.sort()
    lo = probs[int(0.05 * len(probs))]
    hi = probs[int(0.95 * len(probs)) - 1]
    return FoSResult(
        fos=round(base_fos, 3),
        landslide_prob=round(base_prob, 3),
        confidence_interval=(round(lo, 3), round(hi, 3)),
        amplification_factor=round(f, 3),
    )
