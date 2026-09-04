"""§4.2 공통 봉투 + 계약 입력 정규화 (Module C).

여기가 계약 경계다 — 계약 필드명을 아는 유일한 곳이고, rules.py는 여기를 모른다.

폴백 계층(§7에 Module C 행이 없어 트랙②가 신규 제안, Day 1 계약 회의 안건):
  tier 1  입력 4개 정상
  tier 2  drainage_capacity_class / known_risk 결측·부적합 → 보수적 기본값
  tier 3  rainfall_intensity_1h_mm 결측·부적합 → known_risk만으로 최소 등급
  error   underpass_id 결측 → 어느 지하차도인지 특정 불가

D/G/H도 같은 봉투가 필요하다 — 공용 패키지로 승격할지는 D 착수 시점에 결정한다
(ARCHITECTURE §8 디렉토리 구조에 공용 패키지가 없어 4인 합의 사안).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

DRAINAGE_CLASSES = ("low", "medium", "high")

# 결측 시 보수적 기본값 (2026-09-04 나정우 결정 1 — 경보 누락 방지가 이 프로젝트의 존재 이유)
CONSERVATIVE_KNOWN_RISK = True
CONSERVATIVE_DRAINAGE_CLASS = "low"

_MISSING = object()


def envelope(
    status: str,
    fallback_tier: int,
    data: dict[str, Any],
    warnings: list[str],
) -> dict[str, Any]:
    """§4.2 공통 봉투. 키 순서까지 문서 예시와 맞춘다."""
    return {
        "status": status,
        "fallback_tier": fallback_tier,
        "data": data,
        "warnings": warnings,
    }


def error_envelope(underpass_id: str, warnings: list[str]) -> dict[str, Any]:
    """실패해도 스키마를 만족하는 봉투를 낸다 — §4.2 '예외를 던져서 죽지 않는다'."""
    return envelope(
        status="error",
        fallback_tier=3,
        data={"alert_level": "정상", "underpass_id": underpass_id},
        warnings=warnings,
    )


@dataclass
class NormalizedInput:
    underpass_id: str
    rainfall_mm_h: float | None
    known_risk: bool
    drainage_class: str
    fallback_tier: int = 1
    warnings: list[str] = field(default_factory=list)
    fatal: bool = False


def _is_real_number(value: Any) -> bool:
    # bool은 int의 서브클래스라 명시적으로 걸러낸다.
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def normalize(raw: Any) -> NormalizedInput:
    """계약 입력을 엔진이 쓸 값으로 정규화하고, 그 과정에서 폴백 tier를 매긴다."""
    if not isinstance(raw, dict):
        return NormalizedInput(
            underpass_id="UNKNOWN",
            rainfall_mm_h=None,
            known_risk=CONSERVATIVE_KNOWN_RISK,
            drainage_class=CONSERVATIVE_DRAINAGE_CLASS,
            fallback_tier=3,
            warnings=[f"입력이 dict가 아님({type(raw).__name__}) → 판정 불가"],
            fatal=True,
        )

    warnings: list[str] = []
    tier = 1
    fatal = False

    # underpass_id — 유일하게 복구 불가능한 필드. 어느 지하차도인지 모르면 경보가 무의미하다.
    raw_id = raw.get("underpass_id", _MISSING)
    if isinstance(raw_id, str) and raw_id.strip():
        underpass_id = raw_id
    else:
        underpass_id = "UNKNOWN"
        tier = 3
        fatal = True
        warnings.append(
            "underpass_id 결측·부적합 → 대상 지하차도를 특정할 수 없어 판정하지 않음"
            if raw_id is _MISSING
            else f"underpass_id가 비어 있거나 문자열이 아님({raw_id!r}) → 판정하지 않음"
        )

    # known_risk — 결측 시 보수적으로 true (결정 1)
    raw_known_risk = raw.get("known_risk", _MISSING)
    if isinstance(raw_known_risk, bool):
        known_risk = raw_known_risk
    else:
        known_risk = CONSERVATIVE_KNOWN_RISK
        tier = max(tier, 2)
        if raw_known_risk is _MISSING:
            warnings.append("known_risk 결측 → 보수적 가정 적용(known_risk=true)")
        else:
            warnings.append(
                f"known_risk가 bool이 아님({raw_known_risk!r}) → 보수적 가정 적용(known_risk=true)"
            )

    # drainage_capacity_class — 결측·오타 시 가장 불리한 등급으로
    raw_drainage = raw.get("drainage_capacity_class", _MISSING)
    if raw_drainage in DRAINAGE_CLASSES:
        drainage_class = str(raw_drainage)
    else:
        drainage_class = CONSERVATIVE_DRAINAGE_CLASS
        tier = max(tier, 2)
        label = "결측" if raw_drainage is _MISSING else f"부적합({raw_drainage!r})"
        warnings.append(
            f"drainage_capacity_class {label} → 보수적 가정 적용"
            f"(drainage_capacity_class={CONSERVATIVE_DRAINAGE_CLASS})"
        )

    # rainfall_intensity_1h_mm — 없으면 강우 기반 판정 자체가 불가(3순위 폴백)
    raw_rainfall = raw.get("rainfall_intensity_1h_mm", _MISSING)
    if _is_real_number(raw_rainfall) and raw_rainfall >= 0:
        rainfall_mm_h: float | None = float(raw_rainfall)
    else:
        rainfall_mm_h = None
        tier = max(tier, 3)
        label = "결측" if raw_rainfall is _MISSING else f"부적합({raw_rainfall!r})"
        warnings.append(
            f"rainfall_intensity_1h_mm {label} → 강우 기반 판정 불가,"
            " known_risk만으로 최소 등급 산출(3순위 폴백)"
        )

    return NormalizedInput(
        underpass_id=underpass_id,
        rainfall_mm_h=rainfall_mm_h,
        known_risk=known_risk,
        drainage_class=drainage_class,
        fallback_tier=tier,
        warnings=warnings,
        fatal=fatal,
    )
