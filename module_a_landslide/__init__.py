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
from dataclasses import dataclass

from . import forecast, fos, parameters, soil_sampler
from .envelope import envelope as _make

__all__ = ["run", "explain"]


@dataclass
class _ResolvedSoil:
    """부지 지반정수 확정 결과. m0 가 None 이면 배수등급(dc_kr) 룩업을 쓴다."""

    strength: dict
    z_m: float
    dc_kr: str
    m0: float | None
    warnings: list[str]


def _resolve_soil(input: dict, norm) -> _ResolvedSoil:
    """부지 토양 정수 확정. 우선순위 3단계.

      1) input["_soil"] 원시 지반정수(c_kpa·phi_deg·…)  — 격자 샘플러가 쓰는 경로
      2) input["_soil"] 토성 카테고리(texture_kr·ad_kr·dc_kr)
      3) 좌표로 산청 토양격자 자동 샘플링 (soil_sampler)
      4) 전국 대표 폴백(ASSUMPTION)

    3)이 없으면 4)의 식양질 폴백이 걸리는데, 그 조합은 완전포화에서도 FoS≈1.9라
    landslide_prob 이 0.7 을 못 넘는다 — Module O 트리거가 영영 안 걸려 하류
    모듈이 멈추는 원인이었다(README §3-2).
    """
    warns: list[str] = []
    soil = dict(input.get("_soil") or {})

    if not soil:
        sampled = soil_sampler.sample(norm.x_5179, norm.y_5179)
        if sampled:
            soil = sampled
            warns.append("부지 토양: 산청 토양격자 25m 자동 샘플링(MEASURED)")

    raw = parameters.strength_from_raw(soil)
    if raw is not None:
        z = soil.get("z_m")
        if z is None:
            z = parameters.depth_m(soil.get("ad_kr") or parameters.NATIONAL_DEFAULT_AD_KR)
        else:
            z = max(0.05, float(z))
        m0 = soil.get("m0")
        return _ResolvedSoil(raw, z, soil.get("dc_kr") or parameters.NATIONAL_DEFAULT_DC_KR,
                             None if m0 is None else float(m0), warns)

    texture_kr = soil.get("texture_kr")
    ad_kr = soil.get("ad_kr")
    dc_kr = soil.get("dc_kr")
    if not texture_kr:
        texture_kr = parameters.NATIONAL_DEFAULT_TEXTURE_KR
        ad_kr = ad_kr or parameters.NATIONAL_DEFAULT_AD_KR
        dc_kr = dc_kr or parameters.NATIONAL_DEFAULT_DC_KR
        warns.append("부지 토양 미샘플 → 전국 대표 지반정수 폴백(ASSUMPTION). "
                     "이 폴백은 완전포화에서도 FoS≈1.9라 위험 판정이 나오지 않는다 — "
                     "산청 AOI 밖이거나 격자 미탑재 상태")
    else:
        ad_kr = ad_kr or parameters.NATIONAL_DEFAULT_AD_KR
        dc_kr = dc_kr or parameters.NATIONAL_DEFAULT_DC_KR
    return _ResolvedSoil(parameters.texture_strength(texture_kr),
                         parameters.depth_m(ad_kr), dc_kr, None, warns)


def _resolve_hours_to_critical(input: dict, norm, res, strength: dict,
                               z: float, dc_kr: str, m0: float | None = None):
    """예보 시계열이 주입되면 도달시각을 적분하고, 없으면 관측 기준 0/null.

    산불로 약화된 뿌리점착력(Cr/f)을 전진 적분에도 그대로 써서 run()의 현재값과
    같은 물리를 쓴다 — 현재 P와 미래 P가 다른 모형이면 안 된다.
    """
    series, provenance = forecast.extract_series(input, norm.source)
    cr_eff = parameters.ROOT_COHESION_HEALTHY_KPA / max(res.amplification_factor, 1e-6)

    arrival = forecast.time_to_critical(
        future_rain_1h_mm=series,
        past_rain_1h_mm=(input.get("dynamic") or {}).get("rainfall_1h_mm"),
        rain_24h_mm=norm.rain_24h_mm,
        api_index=norm.api_index,
        dc_kr=dc_kr,
        m0=m0,
        strength=strength,
        z_soil_depth_m=z,
        slope_deg=norm.slope_deg,
        cr_eff_kpa=cr_eff,
        critical_prob=_env.CRITICAL_PROB,
        current_prob=res.landslide_prob,
    )
    if series and arrival.hours_to_critical is not None:
        arrival.warnings.append(
            f"hours_to_critical={arrival.hours_to_critical}h — 예보강우 시계열"
            f"({provenance}, +{len(series)}h) 전진적분 결과")
    return arrival


def run(input: dict) -> dict:  # noqa: A002 - §4.2 규약이 지정한 이름
    """§4.2 공통 봉투를 반환한다. 어떤 경우에도 예외를 밖으로 던지지 않는다."""
    norm = None
    try:
        norm = _env.normalize(input)
        if norm.fatal:
            return _env.error_envelope(norm.x_5179, norm.y_5179, norm.warnings)

        soil = _resolve_soil(input, norm)
        strength, z = soil.strength, soil.z_m
        m = parameters.wetness_from_rainfall(norm.api_index, norm.rain_24h_mm,
                                             soil.dc_kr, strength["ksat_m_s"], m0=soil.m0)

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

        # hours_to_critical: 예보 시간강우 시계열이 있으면 1시간씩 전진시켜 첫
        # 임계초과 시각을 구한다. 없으면 '이미 초과(0)'/'판단불가(null)' (§5).
        arrival = _resolve_hours_to_critical(input, norm, res, strength, z,
                                             soil.dc_kr, soil.m0)
        htc = arrival.hours_to_critical

        warnings = norm.warnings + soil.warnings + arrival.warnings
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
    soil = _resolve_soil(input, norm)
    strength, z = soil.strength, soil.z_m
    m = parameters.wetness_from_rainfall(norm.api_index, norm.rain_24h_mm,
                                         soil.dc_kr, strength["ksat_m_s"], m0=soil.m0)
    f = fos.fire_amplification(norm.dnbr_class, norm.days_since_fire)
    cr_eff = parameters.ROOT_COHESION_HEALTHY_KPA / f
    fos_val = fos.factor_of_safety(norm.slope_deg, strength["c_kpa"], strength["phi_deg"],
                                   strength["gamma_kn_m3"], z, m, cr_eff)
    return {
        "method": "Infinite Slope / Factor of Safety (TRIGRS 원리)",
        "inputs": {"slope_deg": norm.slope_deg, "soil": strength,
                   "z_soil_depth_m": z, "m_wetness": round(m, 3),
                   "dnbr_class": norm.dnbr_class, "days_since_fire": norm.days_since_fire},
        "factor_of_safety": round(fos_val, 3),
        "fire_amplification_f": round(f, 3),
        "fallback_tier": norm.fallback_tier,
        "provenance": strength.get("provenance"),
        "source_citation": strength.get("source"),
        "warnings": norm.warnings + soil.warnings,
        "is_model": True,
    }
