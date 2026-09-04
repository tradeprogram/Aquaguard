"""Module C 판정 엔진 (§5 — 규칙기반, 모델 아님).

이 파일은 dict도 공통 봉투(§4.2)도 계약 필드명도 모른다. 정규화된 값을 받아
RuleDecision을 돌려주는 순수 함수 하나가 전부이며, 계약 I/O는 __init__.py가 맡는다.
숫자는 전부 Ruleset에서 오고 여기에 상수로 박히지 않는다 — 근거를 주입해도
이 파일은 바뀌지 않는다는 게 설계 목적이다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .ruleset import Ruleset

# §5 계약이 못박은 4단계. 인덱스가 곧 심각도 순서다.
LEVELS: tuple[str, ...] = ("정상", "주의", "경계", "위험")


def level_index(level: str) -> int:
    return LEVELS.index(level)


def max_level(a: str, b: str) -> str:
    return a if level_index(a) >= level_index(b) else b


@dataclass(frozen=True)
class RuleDecision:
    """판정 결과 + 근거. 계약(data)에 나가는 건 alert_level 하나뿐이고,
    나머지는 explain()과 테스트만 본다 (§6.1 — data에 필드 추가는 4인 합의 사안)."""

    alert_level: str
    raw_rainfall_mm_h: float | None
    effective_mm: float | None
    applied_factors: dict[str, float] = field(default_factory=dict)
    decisive_rule: str = "cutpoint"
    ruleset_version: str = ""
    trace: list[str] = field(default_factory=list)


def evaluate(
    rainfall_mm_h: float,
    known_risk: bool,
    drainage_class: str,
    ruleset: Ruleset,
) -> RuleDecision:
    """정규화된 입력에 대한 4단계 판정.

    순서:
      1) extreme_override — 계수 적용 전 원시 강우강도로 비교, 넘으면 즉시 "위험"
      2) effective_mm = 원시강우 × 배수능력계수 × (지정위험계수 if known_risk)
      3) 절단점 비교로 등급 결정
      4) known_risk_min_level — 지정 위험 지하차도의 최소 등급 하한
    """
    trace: list[str] = []

    drainage_factor = ruleset.drainage_factor(drainage_class)
    known_risk_factor = ruleset.known_risk_factor() if known_risk else 1.0
    effective_mm = rainfall_mm_h * drainage_factor * known_risk_factor
    factors = {"drainage_factor": drainage_factor, "known_risk_factor": known_risk_factor}

    # 1) 극한호우 단독 기준 — 배수능력이 아무리 좋아도 우회하지 못한다.
    override_mm = ruleset.extreme_override_mm()
    if override_mm is not None and rainfall_mm_h >= override_mm:
        trace.append(f"extreme_override: 원시 {rainfall_mm_h}mm/h >= {override_mm}mm/h → 위험")
        return RuleDecision(
            alert_level="위험",
            raw_rainfall_mm_h=rainfall_mm_h,
            effective_mm=effective_mm,
            applied_factors=factors,
            decisive_rule="extreme_override",
            ruleset_version=ruleset.version,
            trace=trace,
        )

    # 2~3) 가중 강우강도를 절단점과 비교 (경계 포함, >= 로 통일)
    level = "정상"
    matched: str | None = None
    for candidate_level, cutpoint in ruleset.cutpoints():
        if effective_mm >= cutpoint:
            level = candidate_level
            matched = f"cutpoint_{candidate_level}({cutpoint}mm/h)"
    trace.append(
        f"effective_mm = {rainfall_mm_h} × {drainage_factor}(배수 {drainage_class})"
        f" × {known_risk_factor}(지정위험 {known_risk}) = {effective_mm:.4g}"
    )
    trace.append(f"절단점 판정 → {level}" + (f" ({matched})" if matched else " (절단점 미도달)"))
    decisive_rule = "cutpoint"

    # 4) 지정 위험 지하차도 하한 — 있는 신호를 "정상"으로 흘려보내지 않기 위한 정책.
    policy = ruleset.min_level_policy()
    if policy["enabled"] and known_risk and rainfall_mm_h > policy["requires_rainfall_gt_mm"]:
        floored = max_level(level, policy["level"])
        if floored != level:
            trace.append(
                f"known_risk_min_level: 지정 위험 + 강수 {rainfall_mm_h}mm/h"
                f" > {policy['requires_rainfall_gt_mm']} → {level}에서 {floored}로 상향"
            )
            decisive_rule = "known_risk_min_level"
            level = floored

    return RuleDecision(
        alert_level=level,
        raw_rainfall_mm_h=rainfall_mm_h,
        effective_mm=effective_mm,
        applied_factors=factors,
        decisive_rule=decisive_rule,
        ruleset_version=ruleset.version,
        trace=trace,
    )


def evaluate_without_rainfall(known_risk: bool, ruleset: Ruleset) -> RuleDecision:
    """3순위 폴백 — 강우강도를 못 믿을 때 known_risk만으로 최소 등급을 낸다.

    min_level 정책은 원래 '강수 > 0'을 요구하지만 여기서는 그 조건을 확인할 수
    없다. 결정 1(경보 누락 방지)의 취지대로 보수적으로 하한을 적용한다.
    """
    policy = ruleset.min_level_policy()
    if policy["enabled"] and known_risk:
        level = policy["level"]
        trace = [f"강우강도 불명 → known_risk={known_risk} 기준 보수적 하한 {level} 적용"]
    else:
        level = "정상"
        trace = [f"강우강도 불명 + known_risk={known_risk} → 하한 없음, 정상"]
    return RuleDecision(
        alert_level=level,
        raw_rainfall_mm_h=None,
        effective_mm=None,
        decisive_rule="rainfall_unavailable",
        ruleset_version=ruleset.version,
        trace=trace,
    )
