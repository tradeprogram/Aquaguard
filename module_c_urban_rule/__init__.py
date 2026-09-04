"""module_c_urban_rule — 도로·지하차도 침수 경보 (§5 Module C, 규칙기반·모델 아님).

§4.2 표준 진입점 run(input: dict) -> dict 하나를 노출한다. Module O는
modules_client.py가 이 패키지를 import_module로 불러 run()을 호출한다.

계약(contracts/module_c.*)이 data에 허용하는 필드는 alert_level·underpass_id
둘뿐이라, 판정 근거·적용 계수·룰셋 출처는 data에 넣지 않고 계약 밖 explain()으로
노출한다 (§6.1 — data 필드 추가는 4인 합의 사안).
"""
from __future__ import annotations

import os
from typing import Any

from . import envelope as _envelope
from . import rules, ruleset
from .envelope import envelope as _make_envelope
from .rules import RuleDecision

__all__ = ["run", "run_many", "explain"]


def _strict_provenance() -> bool:
    """근거 미확정 행을 warnings로도 알릴지.

    기본 off인 이유: 계약 예시(contracts/module_c.example.json)의 정상 출력은
    warnings=[]이고, v1에도 PLACEHOLDER 행(배수·지정위험 가중)이 남아 있어
    기본 on이면 모든 정상 호출이 계약과 어긋나고 Module O의 warnings까지
    오염된다. 근거 상태는 explain()이 항상 완전하게 들고 있다.
    """
    return os.environ.get("AQUAGUARD_MODULE_C_STRICT_PROVENANCE", "0") == "1"


def _provenance_warnings(rs: ruleset.Ruleset) -> list[str]:
    if not _strict_provenance():
        return []
    unconfirmed = rs.unconfirmed_rows()
    if not unconfirmed:
        return []
    detail = ", ".join(f"{r.id}={r.status}" for r in unconfirmed)
    return [f"룰셋 {rs.version}에 근거 미확정 행이 있음: {detail}"]


def _decide(normalized: _envelope.NormalizedInput, rs: ruleset.Ruleset) -> RuleDecision:
    if normalized.rainfall_mm_h is None:
        return rules.evaluate_without_rainfall(normalized.known_risk, rs)
    return rules.evaluate(
        rainfall_mm_h=normalized.rainfall_mm_h,
        known_risk=normalized.known_risk,
        drainage_class=normalized.drainage_class,
        ruleset=rs,
    )


def run(input: dict) -> dict:  # noqa: A002 - §4.2 규약이 지정한 이름
    """§4.2 공통 봉투를 반환한다. 어떤 경우에도 예외를 밖으로 던지지 않는다."""
    normalized = None
    try:
        normalized = _envelope.normalize(input)
        if normalized.fatal:
            return _envelope.error_envelope(normalized.underpass_id, normalized.warnings)

        rs = ruleset.active_ruleset()
        decision = _decide(normalized, rs)
        warnings = normalized.warnings + _provenance_warnings(rs)

        return _make_envelope(
            status="ok" if normalized.fallback_tier == 1 else "degraded",
            fallback_tier=normalized.fallback_tier,
            data={"alert_level": decision.alert_level, "underpass_id": normalized.underpass_id},
            warnings=warnings,
        )
    except Exception as exc:  # noqa: BLE001 - §4.2: 모듈은 예외로 죽지 않는다
        underpass_id = normalized.underpass_id if normalized is not None else "UNKNOWN"
        prior = list(normalized.warnings) if normalized is not None else []
        return _envelope.error_envelope(
            underpass_id,
            prior + [f"Module C 내부 오류({type(exc).__name__}: {exc}) → error 봉투로 폴백"],
        )


def run_many(inputs: list[dict]) -> list[dict]:
    """계약 밖 편의 함수 — 지하차도 여러 개를 한 번에.

    계약(§5)은 지하차도 1개 단위인데 UI 타입은 road_flooding?: UnderpassAlert[]로
    배열을 기대한다(ui/src/lib/types.ts). 누가 순회할지가 아직 미정이라
    (Module O의 orchestrator.py는 현재 C를 호출하지 않는다) 여기 편의 함수만
    두고, 실제 연결 방식은 트랙③과 협의한다. 계약은 건드리지 않았다.
    """
    return [run(item) for item in inputs]


def explain(input: dict) -> dict[str, Any]:
    """계약 밖 판정 근거. UI의 '모델 아님' 신뢰도 배지(§6·§7)와 Provenance 배지(§6.1)용."""
    normalized = _envelope.normalize(input)
    rs = ruleset.active_ruleset()
    decision = None if normalized.fatal else _decide(normalized, rs)
    return {
        "normalized_input": {
            "underpass_id": normalized.underpass_id,
            "rainfall_intensity_1h_mm": normalized.rainfall_mm_h,
            "known_risk": normalized.known_risk,
            "drainage_capacity_class": normalized.drainage_class,
        },
        "fallback_tier": normalized.fallback_tier,
        "input_warnings": normalized.warnings,
        "decision": None
        if decision is None
        else {
            "alert_level": decision.alert_level,
            "effective_mm": decision.effective_mm,
            "applied_factors": decision.applied_factors,
            "decisive_rule": decision.decisive_rule,
            "trace": decision.trace,
        },
        "ruleset": rs.provenance_summary(),
        "is_model": False,
    }
