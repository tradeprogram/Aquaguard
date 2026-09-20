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
# hours_to_critical·Module O 트리거 임계.
#
# 0.7 → 0.5 재유도. 1차 작업지시서 P0-1 의 선택지 (B) 이며, 근거는 둘이다.
#
# (1) 이론 — 0.5 는 확률축에서 유일하게 미보정 계수 k 에 불변인 점이다.
#     P(FoS) = 1/(1 + exp(k·(FoS − 1)))  이므로  FoS = 1 이면 k 와 무관하게 P = 0.5.
#     그 지점의 의미는 무한사면 파괴조건 **FoS < 1** 그 자체다.
#     종전 0.7 은 FoS ≤ 1 + ln(3/7)/k = 0.859 (k=6) 인데, 이 여유폭이 무엇을 뜻하는지는
#     전적으로 k 에 달려 있다. k 가 미보정인 상태에서 0.7 을 쓰는 것은 눈금이 안 맞는
#     자의 0.7 지점을 임계로 삼는 것이라 물리적 근거가 없다. k 를 어떻게 보정하든
#     FoS<1 의 의미는 변하지 않으므로, 이 임계는 보정 후에도 그대로 유효하다.
#
# (2) 실측 — 0.7 에서는 **산불–산사태 연쇄 데모가 성립하지 않는다.**
#     산청 5m 격자 실측(피크 습윤, 토양도 토성):
#       시천면 산불피해지(dNBR≥0.27) 최대 prob 0.622 · 0.7 이상 0 셀
#       시천면에서 0.7 을 넘는 48 셀은 dNBR −0.529, 즉 **불타지 않은 곳**이다
#       산청 전역 산불피해지 최대 0.798 (21 셀, 0.0001% 미만)
#     1차 지시서 P1-1 이 데모를 시천면으로 옮긴 이유가 산불 축을 살리는 것인데,
#     0.7 을 유지하면 그 좌표에서 트리거가 불가능하다. 0.5 에서는 시천면 산불피해지
#     4,162 셀이 임계를 넘는다.
#
# k 보정(선택지 A)은 발생부 좌표가 있어야 가능하다(산림청 요청 중) —
# backtest_sancheong/README.md §9.
#
# ⚠ Module O 의 LANDSLIDE_THRESHOLD 도 0.5 로 맞춰야 한다(트랙③ 소관).
CRITICAL_PROB = 0.5


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
        # 계약 required. 위치조차 특정 못 하는 error 봉투에서는 위험영역도 낼 수 없다.
        "risk_polygon_5179": None,
    }, warnings)
