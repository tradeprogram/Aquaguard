"""module_a_landslide.envelope — §4.2 공통 봉투 + 계약 입력 정규화 (Module A).

여기가 계약 경계다 — contracts/module_a.* 의 필드명을 아는 유일한 곳.
fos.py(물리)와 parameters.py(룩업)는 계약 필드명을 모른다.

폴백 계층(ARCHITECTURE §7):
  tier 1  InSAR + 실측강수 (정밀)
  tier 2  지형 + 실측강수
  tier 3  LDAPS 예보모드 (source="forecast", CI 확대)
  error   x_5179/y_5179 결측 → 위치 특정 불가
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

PRECURSOR_INSAR_MM_PER_DAY = 2.0  # 땅밀림 전조 임계(§2.4). 보정 대상 — DATA_SOURCES 참조
CRITICAL_PROB = 0.7               # hours_to_critical 판정 임계(§5)


def envelope(status: str, fallback_tier: int, data: dict[str, Any],
             warnings: list[str]) -> dict[str, Any]:
    """§4.2 공통 봉투. 키 순서까지 문서 예시와 맞춘다."""
    return {"status": status, "fallback_tier": fallback_tier, "data": data, "warnings": warnings}


@dataclass
class NormalizedInput:
    x_5179: float | None
    y_5179: float | None
    slope_deg: float
    dnbr_class: str
    days_since_fire: int | None
    dnbr: float | None
    rain_24h_mm: float | None
    rain_72h_mm: float | None
    api_index: float | None
    source: str            # "observed" | "forecast"
    insar_mm_per_day: float | None
    fallback_tier: int
    warnings: list[str] = field(default_factory=list)
    fatal: bool = False


def _num(v):
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def normalize(input: dict) -> NormalizedInput:
    warnings: list[str] = []
    x = _num(input.get("x_5179"))
    y = _num(input.get("y_5179"))
    static = input.get("static") or {}
    dynamic = input.get("dynamic") or {}

    slope = _num(static.get("slope_deg"))
    if slope is None:
        slope = 25.0
        warnings.append("slope_deg 결측 → 보수적 기본 25° 적용(지형 폴백)")

    dnbr_class = str(static.get("dnbr_class") or "none").lower()
    days_since_fire = static.get("days_since_fire")
    days_since_fire = int(days_since_fire) if isinstance(days_since_fire, (int, float)) else None

    source = str(dynamic.get("source") or "observed").lower()
    insar = _num(input.get("insar_displacement_mm_per_day"))

    # §7 폴백 계층 판정
    if source == "forecast":
        tier = 3
        warnings.append("source=forecast(LDAPS 예보모드) → 신뢰구간 확대")
    elif insar is not None:
        tier = 1
    else:
        tier = 2

    fatal = x is None or y is None
    if fatal:
        warnings.append("x_5179/y_5179 결측 → 위치 특정 불가, error 봉투")

    return NormalizedInput(
        x_5179=x, y_5179=y, slope_deg=slope, dnbr_class=dnbr_class,
        days_since_fire=days_since_fire, dnbr=_num(static.get("dnbr")),
        rain_24h_mm=_num(dynamic.get("rainfall_cumulative_24h_mm")),
        rain_72h_mm=_num(dynamic.get("rainfall_cumulative_72h_mm")),
        api_index=_num(dynamic.get("api_index")), source=source,
        insar_mm_per_day=insar, fallback_tier=tier, warnings=warnings, fatal=fatal,
    )


def error_envelope(x, y, warnings: list[str]) -> dict[str, Any]:
    return envelope("error", 3, {
        "landslide_prob": 0.0, "confidence_interval": [0.0, 1.0], "source": "observed",
        "amplification_factor": 1.0, "precursor_flag": False, "hours_to_critical": None,
        "location": {"x_5179": x, "y_5179": y},
    }, warnings)
