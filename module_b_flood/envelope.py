"""module_b_flood.envelope — §4.2 공통 봉투 + 계약 입력 정규화 (Module B).

여기가 계약 경계다 — contracts/module_b.* 의 필드명을 아는 유일한 곳.
flood.py(수문·물리)와 fim.py(침수 폴리곤)는 계약 필드명을 모른다.

폴백 계층(ARCHITECTURE §7, Module B):
  tier 1  실측강우 + 실측수위(river_level_m) + SAR (정밀)
  tier 2  SAR 없음 → 실측강우 + 실측수위
  tier 3  river_level_m 결측 → 실측강우만 (보수적, 신뢰구간 확대)
  error   reach_id 결측 → 어느 하천구간인지 특정 불가
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

CRITICAL_PROB = 0.7   # hours_to_critical 판정 임계(§5, A와 동일 기준)


def envelope(status: str, fallback_tier: int, data: dict[str, Any],
             warnings: list[str]) -> dict[str, Any]:
    """§4.2 공통 봉투. 키 순서까지 문서 예시와 맞춘다."""
    return {"status": status, "fallback_tier": fallback_tier, "data": data, "warnings": warnings}


def _empty_fc() -> dict[str, Any]:
    return {"type": "FeatureCollection", "features": []}


def error_envelope(reach_id: str | None, warnings: list[str]) -> dict[str, Any]:
    """실패해도 스키마를 만족하는 봉투 — §4.2 '예외로 죽지 않는다'."""
    return envelope(
        status="error", fallback_tier=3,
        data={"flood_prob": 0.0, "confidence_interval": [0.0, 1.0],
              "hours_to_critical": None, "inundation_extent_5179": _empty_fc(),
              "reach_id": reach_id},
        warnings=warnings,
    )


@dataclass
class NormalizedInput:
    reach_id: str | None
    drainage_area_km2: float | None
    river_order: int
    slope_pct: float | None
    rain_24h_mm: float | None
    river_level_m: float | None
    sar_present: bool
    fallback_tier: int
    warnings: list[str] = field(default_factory=list)
    fatal: bool = False


def _num(v):
    import math
    try:
        if v is None:
            return None
        f = float(v)
        return f if math.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def normalize(input: dict) -> NormalizedInput:  # noqa: A002
    warnings: list[str] = []
    reach_id = input.get("reach_id")
    static = input.get("static") or {}
    dynamic = input.get("dynamic") or {}

    drainage = _num(static.get("drainage_area_km2"))
    order_raw = static.get("river_order")
    river_order = int(order_raw) if isinstance(order_raw, (int, float)) else 3
    if not isinstance(order_raw, (int, float)):
        warnings.append("river_order 결측 → 기본 3차 하천 가정")
    slope_pct = _num(static.get("slope_pct"))

    # rainfall_cumulative_24h_mm 는 배열(계약) — 최신값(마지막) 사용
    rain = dynamic.get("rainfall_cumulative_24h_mm")
    rain_24h = None
    if isinstance(rain, (list, tuple)) and rain:
        rain_24h = _num(rain[-1])
    elif isinstance(rain, (int, float)):
        rain_24h = float(rain)

    river_level = _num(dynamic.get("river_level_m"))
    sar = input.get("sar_water_extent")
    sar_present = isinstance(sar, dict) and bool(sar)

    # §7 폴백 계층
    if river_level is None:
        tier = 3
        warnings.append("river_level_m 결측 → 실측강우만으로 추정(보수적, 신뢰구간 확대)")
    elif sar_present:
        tier = 1
    else:
        tier = 2
        warnings.append("SAR 미제공 → 실측강우+수위 기반(정밀도 tier2)")

    if rain_24h is None and river_level is None:
        warnings.append("강우·수위 모두 결측 → 판정근거 없음")

    fatal = not reach_id
    if fatal:
        warnings.append("reach_id 결측 → 하천구간 특정 불가, error 봉투")

    return NormalizedInput(
        reach_id=reach_id, drainage_area_km2=drainage, river_order=river_order,
        slope_pct=slope_pct, rain_24h_mm=rain_24h, river_level_m=river_level,
        sar_present=sar_present, fallback_tier=tier, warnings=warnings, fatal=fatal,
    )
