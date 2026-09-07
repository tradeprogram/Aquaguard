"""module_g_damage_cost — 피해비용 추정 (§5 Module G).

§4.2 표준 진입점 run(input: dict) -> dict. Module O가 Module D의 출력을 그대로
펼쳐 넘긴다(orchestrator.py: call_module("g", {**exposure, ...})).

단가는 자연재난 '복구비 지원' 단가 고시라 실제 경제적 손실이 아니라 그 하한이다 —
basis_citation에 그 사실을 명시한다.

폴백 계층(§7에 Module G 행이 없어 트랙②가 신규 제안, Day 1 계약 회의 안건):
  tier 1  입력 정상
  tier 2  exposed_farmland_ha 결측·부적합, 건물 항목 일부 깨짐, use_type 어휘 밖
  tier 3  건물·농경지 둘 다 쓸 수 없음 -> 0원
  error   입력이 dict가 아니거나 exposed_buildings가 배열이 아님

unit_cost_table_ref가 우리 표와 다르면 status는 ok로 두되 warning을 남기고
basis_citation에 실제로 쓴 표를 밝힌다(2026-09-05 나정우 결정) — Module O가
"재해연보_2024_원단위"를 하드코딩해 넘기고 있어 상시 불일치 상태다.
"""
from __future__ import annotations

from typing import Any

from . import costs, policy
from .envelope import EMPTY_DATA, envelope, error_envelope

__all__ = ["run", "explain"]


class _InputError(ValueError):
    """복구 불가능한 입력 — error 봉투로 나간다."""


def _evaluate(raw: Any) -> tuple[dict[str, Any], int, list[str], dict[str, Any]]:
    pol = policy.active_policy()

    if not isinstance(raw, dict):
        raise _InputError(f"입력이 dict가 아님({type(raw).__name__}) → 산정 불가")
    buildings = raw.get("exposed_buildings")
    if not isinstance(buildings, list):
        raise _InputError(
            f"exposed_buildings가 배열이 아님({type(buildings).__name__}) → 산정 불가"
        )

    warnings: list[str] = []
    tier = 1

    # 농경지 — 결측·부적합은 0으로 내려앉히되 조용히 넘어가지 않는다.
    raw_ha = raw.get("exposed_farmland_ha")
    if isinstance(raw_ha, (int, float)) and not isinstance(raw_ha, bool) and raw_ha >= 0:
        farmland_ha = float(raw_ha)
    else:
        farmland_ha = 0.0
        tier = max(tier, 2)
        warnings.append(
            f"exposed_farmland_ha가 0 이상 숫자가 아님({raw_ha!r}) → 농경지 피해 0원으로 산정"
        )

    summary = costs.summarize_buildings(buildings, pol)
    if summary.invalid:
        tier = max(tier, 2)
        warnings.append(f"use_type을 읽을 수 없는 건물 {summary.invalid}건 제외")
    if summary.off_vocabulary:
        tier = max(tier, 2)
        unique = sorted(set(summary.off_vocabulary))
        warnings.append(
            f"use_type 어휘 밖 값 {len(summary.off_vocabulary)}건({', '.join(unique[:5])})"
            f" → '{pol.unknown_use_type}'과 같이 취급"
        )
    if not buildings and farmland_ha == 0.0:
        tier = 3
        warnings.append("건물·농경지 모두 산정할 수 없음 → 0원으로 반환(3순위 폴백)")

    area_m2 = costs.farmland_m2(farmland_ha)
    point = costs.point_estimate_krw(summary.housing, area_m2, pol)
    low, high = costs.cost_range_krw(point, summary.unknown, pol)

    basis = pol.basis_citation()
    requested_ref = raw.get("unit_cost_table_ref")
    if isinstance(requested_ref, str) and requested_ref != pol.module_g.version:
        # status는 ok로 둔다 - 요청한 표와 다른 표를 썼다는 사실만 정직하게 알린다.
        warnings.append(
            f"요청한 unit_cost_table_ref('{requested_ref}')를 쓰지 않았다 → "
            f"실제 사용: {pol.module_g.version}. basis_citation 참조"
        )
        basis = f"{basis} [요청 '{requested_ref}' 대신 {pol.module_g.version} 적용]"

    data = {
        "estimated_cost_krw": point,
        "cost_range_krw": [low, high],
        "basis_citation": basis,
    }
    detail = {
        "point_estimate_label": "노출 자산 기준 조건부 피해액 (risk_prob 미가중)",
        "buildings": {
            "counts": summary.counts,
            "housing_counted": summary.housing,
            "unknown_excluded": summary.unknown,
            "excluded_total": summary.excluded,
            "invalid": summary.invalid,
            "off_vocabulary": sorted(set(summary.off_vocabulary)),
            "excluded_use_types": pol.excluded_use_types,
        },
        "farmland": {
            "exposed_ha": farmland_ha,
            "area_m2": area_m2,
            "unit_krw_per_m2": pol.farmland_unit_krw_per_m2,
            "cost_krw": int(round(area_m2 * pol.farmland_unit_krw_per_m2)),
        },
        "housing": {
            "count": summary.housing,
            "unit_krw": pol.housing_unit_krw,
            "cost_krw": summary.housing * pol.housing_unit_krw,
            "assumption": "주거 건물 1동 = 1세대 (공동주택 세대수 미반영, hhldCnt 확보 시 해소)",
        },
        "range_basis": {
            "low": "점추정 고정",
            "high": "max(점추정x(1+min_upper_band_pct), 점추정 + 미상x주거비율x주택단가)",
            "min_upper_band_pct": pol.min_upper_band_pct,
            "unknown_housing_ratio": pol.unknown_housing_ratio,
        },
        "references_not_in_estimate": {
            "risk_weighted_expected_krw": costs.risk_weighted_krw(summary, area_m2, pol),
            "all_vegetable_sensitivity_krw": costs.vegetable_sensitivity_krw(
                summary.housing, area_m2, pol
            ),
            "landslide_unit_costs": pol.landslide_reference,
            "note": "산사태 시나리오 단가와 민감도 — 점추정에 반영하지 않았다",
        },
        "notice_review_years": pol.notice_review_years,
        "policy": pol.summary(),
        "is_model": False,
    }
    return data, tier, warnings, detail


def run(input: dict) -> dict:  # noqa: A002 - §4.2 규약이 지정한 이름
    try:
        data, tier, warnings, _ = _evaluate(input)
        return envelope(
            status="ok" if tier == 1 else "degraded",
            fallback_tier=tier,
            data=data,
            warnings=warnings,
        )
    except _InputError as exc:
        return error_envelope([str(exc)])
    except Exception as exc:  # noqa: BLE001 - §4.2: 모듈은 예외로 죽지 않는다
        return error_envelope(
            [f"Module G 내부 오류({type(exc).__name__}: {exc}) → error 봉투로 폴백"]
        )


def explain(input: dict) -> dict[str, Any]:
    """계약 밖 산정 근거 — 제외 건수, 위험도 가중 참고값, 산사태 단가, 정책 출처."""
    try:
        data, tier, warnings, detail = _evaluate(input)
    except _InputError as exc:
        return {"data": dict(EMPTY_DATA), "fallback_tier": 3, "warnings": [str(exc)], "detail": None}
    return {"data": data, "fallback_tier": tier, "warnings": warnings, "detail": detail}
