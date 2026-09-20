"""module_a_landslide.parameters — 정밀토양도 → FoS 지반정수 룩업 로더.

data/fos_parameter_bundle.json(출처: DATA_SOURCES.md, 가상값 없음)을 읽어
토성→강도, 유효토심→z, 배수등급→선행습윤, 뿌리점착력 시나리오를 제공한다.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_DATA = Path(__file__).resolve().parent / "data" / "fos_parameter_bundle.json"

# 심토토성(ST) 코드 → 한글키 (fos_parameter_bundle.json의 texture_strength_ST 키)
ST_CODE_TO_KR = {
    1: "사질", 2: "사양질", 3: "미사사양질", 4: "식양질",
    5: "미사식양질", 6: "식질", 7: "역질", 8: "사력질",
}
AD_CODE_TO_KR = {1: "<20", 2: "20-50", 3: "50-100", 4: ">100"}
DC_CODE_TO_KR = {1: "매우양호", 2: "양호", 3: "약간양호", 4: "약간불량", 5: "불량", 6: "매우불량"}

# 소일맵 미샘플 시 국가 대표 폴백(전국 최빈 심토토성=식양질, 유효토심 50-100).
# 부지 실측이 아니므로 provenance=ASSUMPTION, fallback_tier↑, warnings로 알린다.
NATIONAL_DEFAULT_TEXTURE_KR = "식양질"
NATIONAL_DEFAULT_AD_KR = "50-100"
NATIONAL_DEFAULT_DC_KR = "약간양호"
ROOT_COHESION_HEALTHY_KPA = 3.0  # Frontiers 2026 뿌리점착력 0~5kPa 중앙값(건강 산림)


@lru_cache(maxsize=1)
def bundle() -> dict:
    with open(_DATA, encoding="utf-8") as f:
        return json.load(f)


def texture_strength(texture_kr: str) -> dict:
    """토성(한글) → {c_kpa, phi_deg, gamma_kn_m3, ksat_m_s, provenance, source}."""
    t = bundle()["texture_strength_ST"]
    return t.get(texture_kr) or t[NATIONAL_DEFAULT_TEXTURE_KR]


def depth_m(ad_kr: str) -> float:
    return bundle()["soil_depth_AD"].get(ad_kr) or bundle()["soil_depth_AD"][NATIONAL_DEFAULT_AD_KR]


def wetness_baseline(dc_kr: str) -> float:
    return bundle()["drainage_wetness_DC"].get(dc_kr, 0.30)


def wetness_from_rainfall(api_index: float | None, rain_24h_mm: float | None,
                          dc_kr: str, ksat_m_s: float) -> float:
    """선행습윤 기저값(배수등급) + 강우 기여로 동적 습윤도 m 추정(0~1).

    m = clip( m0(배수) + api_index_기여 + 24h강우 기여, 0, 1 ).
    강우→포화 반응은 Ksat이 낮을수록(배수 나쁠수록) 민감. 구조는 물리 근거이나
    계수는 산청 백테스트로 보정 예정 → provenance MODEL(미보정). 근거 §5, §9.3.
    """
    m0 = wetness_baseline(dc_kr)
    api_term = 0.0 if api_index is None else 0.25 * max(0.0, min(api_index, 1.0))
    # 24h 강우: 200mm에서 포화 근접. Ksat 낮으면 계수↑(1e-6 기준 정규화, 상한)
    if rain_24h_mm is None:
        rain_term = 0.0
    else:
        ksat_factor = min(2.0, max(0.5, (1e-5 / max(ksat_m_s, 1e-8)) ** 0.15))
        rain_term = min(0.6, (rain_24h_mm / 200.0) * 0.5 * ksat_factor)
    return max(0.0, min(m0 + api_term + rain_term, 1.0))
