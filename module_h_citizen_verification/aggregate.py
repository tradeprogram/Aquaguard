"""집계 엔진 (Module H) — 이 모듈의 심장.

정규화된 신고 목록을 받아 verification_status / confidence_adjustment /
response_latency_min을 계산한다. 계약 필드명도 공통 봉투도 모르고, 숫자는 전부
Policy에서 온다.

confidence_adjustment 수식:

    raw = (w_목격·n_목격 + w_대피·n_대피 + w_오탐·n_오탐) / (n + k)
    adjustment = round(clamp(raw, -1, 1) × max_adjustment, digits)

분모의 +k(shrinkage)가 핵심이다. 1~2건으로는 최대 조정이 나오지 않고 건수가 늘수록
포화하는 곡선이 되어, §7 폴백 계층의 "응답 소수(낮은 가중치)"가 별도 분기 없이
수식에서 나온다. k=9는 계약 예시 역산값이며 검증된 신뢰도 모델이 아니다
(policies/v1_default.json의 shrinkage_k 참조).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from statistics import median
from typing import Any

from .policy import Policy
from .reports import Report


@dataclass
class Aggregate:
    report_count: int
    verification_status: str
    confidence_adjustment: float
    response_latency_min: float | None
    type_counts: dict[str, int] = field(default_factory=dict)
    weighted_positive: float = 0.0
    weighted_net: float = 0.0
    raw_ratio: float = 0.0
    photo_count: int = 0
    latency_stats: dict[str, float | None] = field(default_factory=dict)
    trace: list[str] = field(default_factory=list)


def _clamp(value: float, low: float, high: float) -> float:
    return min(max(value, low), high)


def _latency(reports: list[Report], policy: Policy) -> tuple[float | None, dict[str, float | None]]:
    """경보 발송 → 첫 유효 응답까지의 분.

    평균·중앙값이 아니라 최초 응답을 쓴다 — 골든타임 서사에서 의미 있는 값은
    "얼마나 빨리 첫 확인이 들어왔는가"이고, 평균은 늦은 응답으로 희석된다.
    경보 이전 신고(음수)는 제외한다.
    """
    after_alert = [r.minutes_from_alert for r in reports if r.minutes_from_alert is not None and r.minutes_from_alert >= 0]
    if not after_alert:
        return None, {"first": None, "median": None, "last": None}
    digits = policy.latency_digits
    return (
        round(min(after_alert), digits),
        {
            "first": round(min(after_alert), digits),
            "median": round(median(after_alert), digits),
            "last": round(max(after_alert), digits),
        },
    )


def aggregate(reports: list[Report], policy: Policy) -> Aggregate:
    weights = policy.type_weights
    counts = {report_type: 0 for report_type in weights}
    for report in reports:
        counts[report.report_type] += 1

    n = len(reports)
    trace: list[str] = []

    weighted_positive = (
        weights["이상징후_목격"] * counts["이상징후_목격"]
        + weights["이미_대피함"] * counts["이미_대피함"]
    )
    weighted_net = weighted_positive + weights["오탐_신고"] * counts["오탐_신고"]

    latency, latency_stats = _latency(reports, policy)
    photo_count = sum(1 for r in reports if r.has_photo)

    if n == 0:
        # §7 3순위: 응답 0건이면 Module O는 시민 확인 없이 원래 임계치 로직대로 진행한다.
        return Aggregate(
            report_count=0,
            verification_status="미확인",
            confidence_adjustment=0.0,
            response_latency_min=None,
            type_counts=counts,
            latency_stats=latency_stats,
            trace=["유효 신고 0건 → 미확인, confidence_adjustment=0.0 (§7 3순위 폴백)"],
        )

    raw_ratio = weighted_net / (n + policy.shrinkage_k)
    adjustment = round(
        _clamp(raw_ratio, -1.0, 1.0) * policy.max_adjustment, policy.adjustment_digits
    )
    trace.append(
        f"raw = {weighted_net:g} / ({n} + {policy.shrinkage_k:g}) = {raw_ratio:.4g}"
        f" → adjustment = {adjustment}"
    )

    false_count = counts["오탐_신고"]
    false_ratio = false_count / n
    if false_count >= policy.min_false_reports and false_ratio >= policy.min_false_ratio:
        status = "오탐판정"
        trace.append(
            f"오탐 {false_count}건(비율 {false_ratio:.2f}) ≥ 기준"
            f"({policy.min_false_reports}건, {policy.min_false_ratio}) → 오탐판정"
        )
    elif weighted_positive >= policy.min_weighted_positive:
        status = "현장확인"
        trace.append(
            f"가중 긍정 {weighted_positive:g} ≥ {policy.min_weighted_positive:g} → 현장확인"
        )
    else:
        status = "미확인"
        trace.append(
            f"가중 긍정 {weighted_positive:g} < {policy.min_weighted_positive:g}"
            " 이고 오탐 기준도 미달 → 미확인"
        )

    return Aggregate(
        report_count=n,
        verification_status=status,
        confidence_adjustment=adjustment,
        response_latency_min=latency,
        type_counts=counts,
        weighted_positive=weighted_positive,
        weighted_net=weighted_net,
        raw_ratio=raw_ratio,
        photo_count=photo_count,
        latency_stats=latency_stats,
        trace=trace,
    )


def fallback_tier(report_count: int, degraded: bool, policy: Policy) -> int:
    """§7 Module H 행 그대로 — 응답 다수 / 소수 / 0건."""
    if report_count == 0:
        return 3
    if report_count < policy.full_weight_min_reports or degraded:
        return 2
    return 1
