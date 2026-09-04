"""§4.2 공통 봉투 (Module G).

module_c/d/h와 같은 세 함수를 갖는다 — 공용 패키지로 올리지 않고 복제했다
(2026-09-04 나정우 승인). 공유 대상이 15줄뿐이고 입력 정규화는 모듈마다 완전히
다른데, 최상위 공용 패키지는 ARCHITECTURE §8 트리에 없어 4인 합의가 필요하다.
"""
from __future__ import annotations

from typing import Any

# 어떤 실패 경로에서도 이 값을 내면 contracts/module_g.schema.json을 만족한다.
EMPTY_DATA: dict[str, Any] = {
    "estimated_cost_krw": 0,
    "cost_range_krw": [0, 0],
    "basis_citation": "산정 불가 — 입력을 해석할 수 없어 비용을 계산하지 않았다",
}


def envelope(status: str, fallback_tier: int, data: dict[str, Any], warnings: list[str]) -> dict[str, Any]:
    return {"status": status, "fallback_tier": fallback_tier, "data": data, "warnings": warnings}


def error_envelope(warnings: list[str]) -> dict[str, Any]:
    """실패해도 스키마를 만족하는 봉투 — §4.2 '예외를 던져서 죽지 않는다'."""
    return envelope("error", 3, dict(EMPTY_DATA), warnings)
