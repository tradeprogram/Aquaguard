"""피해비용 산정 엔진 (Module G).

계약 필드명도 공통 봉투도 모른다. 단가는 전부 CostPolicy에서 오고 여기에 상수로
박히지 않는다.

점추정 = 주거 세대수 x 주택침수 단가 + 농경지 m2 x 대파대 단가
  - 비주거(상업/공업/공공/기타)는 공식 침수 단가가 없어 제외한다.
  - '미상'도 점추정에서 제외하되 상한 계산에는 반영한다.
  - risk_prob를 곱하지 않는다 - '침수되면 얼마'인 조건부 피해액이지 기대손실이 아니다.

구간 = [점추정, max(점추정 x (1+p), 점추정 + 미상 x 주거비율 x 주택단가)]
  하한은 점추정으로 고정한다. 상한의 첫 항(최소 불확실성 폭 p)이 없으면 '미상'이
  0건일 때 폭 0인 구간이 나오는데, 그건 완벽한 확신을 주장하는 셈이라 §6과 어긋난다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .policy import CostPolicy

SQUARE_METERS_PER_HECTARE = 10_000.0


@dataclass
class BuildingSummary:
    counts: dict[str, int] = field(default_factory=dict)
    housing: int = 0
    unknown: int = 0
    excluded: int = 0
    invalid: int = 0
    off_vocabulary: list[str] = field(default_factory=list)
    risk_weighted_housing: float = 0.0


def summarize_buildings(raw_buildings: list[Any], policy: CostPolicy) -> BuildingSummary:
    """use_type별로 센다. 어휘 밖 값은 '미상'과 같이 취급하고 그 사실을 남긴다."""
    summary = BuildingSummary()
    vocabulary = set(policy.vocabulary)

    for item in raw_buildings:
        if not isinstance(item, dict) or not isinstance(item.get("use_type"), str):
            summary.invalid += 1
            continue

        use_type = item["use_type"].strip()
        if use_type not in vocabulary:
            summary.off_vocabulary.append(use_type)
            use_type = policy.unknown_use_type

        summary.counts[use_type] = summary.counts.get(use_type, 0) + 1

        if use_type == policy.housing_use_type:
            summary.housing += 1
            raw_prob = item.get("risk_prob")
            if isinstance(raw_prob, (int, float)) and not isinstance(raw_prob, bool):
                summary.risk_weighted_housing += min(max(float(raw_prob), 0.0), 1.0)
        elif use_type == policy.unknown_use_type:
            summary.unknown += 1
            summary.excluded += 1
        else:
            summary.excluded += 1

    return summary


def farmland_m2(exposed_farmland_ha: float) -> float:
    return float(exposed_farmland_ha) * SQUARE_METERS_PER_HECTARE


def point_estimate_krw(housing_count: int, farmland_area_m2: float, policy: CostPolicy) -> int:
    """중간 반올림 없이 마지막에 한 번만 정수화한다(계약이 integer를 요구)."""
    total = housing_count * policy.housing_unit_krw + farmland_area_m2 * policy.farmland_unit_krw_per_m2
    return int(round(total))


def cost_range_krw(point: int, unknown_count: int, policy: CostPolicy) -> list[int]:
    band = int(round(point * (1.0 + policy.min_upper_band_pct)))
    unknown_add = point + int(round(unknown_count * policy.unknown_housing_ratio * policy.housing_unit_krw))
    return [point, max(band, unknown_add)]


def risk_weighted_krw(summary: BuildingSummary, farmland_area_m2: float, policy: CostPolicy) -> int:
    """참고값 — 건물만 risk_prob로 가중한다(농경지에는 위험도가 붙어 오지 않는다)."""
    total = (
        summary.risk_weighted_housing * policy.housing_unit_krw
        + farmland_area_m2 * policy.farmland_unit_krw_per_m2
    )
    return int(round(total))


def vegetable_sensitivity_krw(housing_count: int, farmland_area_m2: float, policy: CostPolicy) -> int:
    """농경지 전량이 채소(엽근채류)였다면 얼마인가 — 작물 구분이 없어 민감도로만 제시."""
    total = (
        housing_count * policy.housing_unit_krw
        + farmland_area_m2 * policy.farmland_vegetable_unit_krw_per_m2
    )
    return int(round(total))
