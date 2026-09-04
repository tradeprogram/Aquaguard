"""module_a_landslide — 산사태 예측 (§5 Module A, Infinite Slope/FoS).

§4.2 표준 진입점 run(input: dict) -> dict 하나를 노출한다. Module O는
modules_client.py가 이 패키지를 import_module로 불러 run()을 호출한다.

방법론(ARCHITECTURE §5 확정): landslide_prob은 순수 ML이 아니라 TRIGRS 원리의
Infinite Slope FoS(안전율)를 먼저 계산해 변환한 값. 지반정수는 전부 출판 문헌값
(DATA_SOURCES.md), 가상값 없음.

지반정수 출처: 계약 input(static/dynamic)에는 토성·토심이 없다 — Module A가 위치
(x_5179,y_5179)에서 정밀토양도를 내부 샘플링해 얻는 게 원칙이다. 전국 토양도
shapefile은 대용량이라 저장소에 넣지 않았으므로, 부지 샘플이 주입되지 않으면
(input["_soil"]) 전국 대표 폴백값을 쓰고 fallback_tier·warnings로 알린다.
(module_c의 PLACEHOLDER 처리와 같은 정직성 원칙.)
"""
from __future__ import annotations

from typing import Any

from . import envelope as _env
from . import fos, parameters
from .envelope import envelope as _make

__all__ = ["run", "explain"]


def _resolve_soil(input: dict, norm) -> tuple[dict, str, str, list[str]]:
    """부지 토양 정수 확정. input['_soil']={texture_kr,ad_kr,dc_kr} 주입 우선,
    없으면 전국 대표 폴백(ASSUMPTION)."""
    warns: list[str] = []
    soil = input.get("_soil") or {}
    texture_kr = soil.get("texture_kr")
    ad_kr = soil.get("ad_kr")
    dc_kr = soil.get("dc_kr")
    if not texture_kr:
        texture_kr = parameters.NATIONAL_DEFAULT_TEXTURE_KR
        ad_kr = ad_kr or parameters.NATIONAL_DEFAULT_AD_KR
        dc_kr = dc_kr or parameters.NATIONAL_DEFAULT_DC_KR
        warns.append("부지 토양 미샘플 → 전국 대표 지반정수 폴백(ASSUMPTION). "
                     "정밀토양도 샘플러 연결 시 부지값으로 대체")
    return parameters.texture_strength(texture_kr), ad_kr, dc_kr, warns


def run(input: dict) -> dict:  # noqa: A002 - §4.2 규약이 지정한 이름
    """§4.2 공통 봉투를 반환한다. 어떤 경우에도 예외를 밖으로 던지지 않는다."""
    norm = None
    try:
        norm = _env.normalize(input)
        if norm.fatal:
            return _env.error_envelope(norm.x_5179, norm.y_5179, norm.warnings)

        strength, ad_kr, dc_kr, soil_warns = _resolve_soil(input, norm)
        z = parameters.depth_m(ad_kr)
        m = parameters.wetness_from_rainfall(norm.api_index, norm.rain_24h_mm,
                                             dc_kr, strength["ksat_m_s"])

        res = fos.evaluate(
            slope_deg=norm.slope_deg, c_eff_kpa=strength["c_kpa"],
            phi_eff_deg=strength["phi_deg"], gamma_kn_m3=strength["gamma_kn_m3"],
            z_soil_depth_m=z, m_wetness=m, cr_root_kpa=parameters.ROOT_COHESION_HEALTHY_KPA,
            dnbr_class=norm.dnbr_class, days_since_fire=norm.days_since_fire,
        )

        ci = list(res.confidence_interval)
        if norm.source == "forecast":  # tier 3: 예보 불확실성 → CI 확대(±0.1 clamp)
            ci = [max(0.0, ci[0] - 0.1), min(1.0, ci[1] + 0.1)]

        precursor = norm.insar_mm_per_day is not None and \
            norm.insar_mm_per_day >= _env.PRECURSOR_INSAR_MM_PER_DAY

        # hours_to_critical: 관측만이면 '이미 임계 초과(0)' 또는 '판단불가(null)'.
        # 미래 시각은 LDAPS 예보 시계열이 있어야 산출(§5) — 연결 시 확장.
        if res.landslide_prob >= _env.CRITICAL_PROB:
            htc = 0.0
        else:
            htc = None

        warnings = norm.warnings + soil_warns
        return _make(
            status="ok" if norm.fallback_tier == 1 else "degraded",
            fallback_tier=norm.fallback_tier,
            data={
                "landslide_prob": res.landslide_prob,
                "confidence_interval": [round(ci[0], 3), round(ci[1], 3)],
                "source": "forecast" if norm.source == "forecast" else "observed",
                "amplification_factor": res.amplification_factor,
                "precursor_flag": precursor,
                "hours_to_critical": htc,
                "location": {"x_5179": norm.x_5179, "y_5179": norm.y_5179},
            },
            warnings=warnings,
        )
    except Exception as exc:  # noqa: BLE001 - §4.2: 모듈은 예외로 죽지 않는다
        x = norm.x_5179 if norm else None
        y = norm.y_5179 if norm else None
        prior = list(norm.warnings) if norm else []
        return _env.error_envelope(x, y, prior + [
            f"Module A 내부 오류({type(exc).__name__}: {exc}) → error 봉투로 폴백"])


def explain(input: dict) -> dict[str, Any]:
    """계약 밖 판정 근거 — UI Provenance 배지(§6.1)·설명가능성용."""
    norm = _env.normalize(input)
    strength, ad_kr, dc_kr, soil_warns = _resolve_soil(input, norm)
    z = parameters.depth_m(ad_kr)
    m = parameters.wetness_from_rainfall(norm.api_index, norm.rain_24h_mm, dc_kr, strength["ksat_m_s"])
    f = fos.fire_amplification(norm.dnbr_class, norm.days_since_fire)
    cr_eff = parameters.ROOT_COHESION_HEALTHY_KPA / f
    fos_val = fos.factor_of_safety(norm.slope_deg, strength["c_kpa"], strength["phi_deg"],
                                   strength["gamma_kn_m3"], z, m, cr_eff)
    return {
        "method": "Infinite Slope / Factor of Safety (TRIGRS 원리)",
        "inputs": {"slope_deg": norm.slope_deg, "soil_texture": ad_kr and dc_kr and strength,
                   "z_soil_depth_m": z, "m_wetness": round(m, 3),
                   "dnbr_class": norm.dnbr_class, "days_since_fire": norm.days_since_fire},
        "factor_of_safety": round(fos_val, 3),
        "fire_amplification_f": round(f, 3),
        "fallback_tier": norm.fallback_tier,
        "provenance": strength.get("provenance"),
        "source_citation": strength.get("source"),
        "warnings": norm.warnings + soil_warns,
        "is_model": True,
    }
