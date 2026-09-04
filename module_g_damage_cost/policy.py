"""policies/ 로더 (Module G).

단가와 산정 규칙은 저장소 최상위 policies/module_g.json에만 산다. use_type 어휘는
policies/use_type_vocabulary.json을 Module D와 공유한다 — D의 exposed_buildings가
그대로 G의 입력이 되므로(orchestrator.py가 {**exposure, ...}로 펼친다) 두 모듈이
같은 어휘를 봐야 한다.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

POLICIES_DIR = Path(__file__).resolve().parent.parent / "policies"
POLICY_SCHEMA_PATH = POLICIES_DIR / "policy.schema.json"

MODULE_G_POLICY = "module_g"
USE_TYPE_POLICY = "use_type_vocabulary"

SETTLED_STATUSES = frozenset({"CONFIRMED", "DERIVED", "TEAM_DECISION"})


class PolicyError(ValueError):
    """정책 JSON이 구조적으로 잘못됐을 때. run()이 잡아 error 봉투로 바꾼다."""


@dataclass(frozen=True)
class Row:
    id: str
    value: Any
    unit: str | None
    status: str
    source: dict[str, Any]
    note: str | None

    @property
    def is_settled(self) -> bool:
        return self.status in SETTLED_STATUSES


@dataclass(frozen=True)
class Policy:
    version: str
    description: str
    rows: dict[str, Row]

    def row(self, row_id: str) -> Row:
        try:
            return self.rows[row_id]
        except KeyError as exc:
            raise PolicyError(f"정책 {self.version}에 필수 행 '{row_id}'이 없다") from exc

    def value(self, row_id: str) -> Any:
        return self.row(row_id).value

    def summary(self) -> dict[str, Any]:
        counts: dict[str, int] = {}
        for row in self.rows.values():
            counts[row.status] = counts.get(row.status, 0) + 1
        return {
            "policy_version": self.version,
            "status_counts": counts,
            "rows": [
                {"id": r.id, "status": r.status, "source": r.source, "note": r.note}
                for r in self.rows.values()
            ],
        }


@lru_cache(maxsize=None)
def load(name: str) -> Policy:
    import jsonschema

    path = POLICIES_DIR / f"{name}.json"
    if not path.is_file():
        raise PolicyError(f"정책 파일을 찾을 수 없다: {path}")
    with open(path, encoding="utf-8") as f:
        doc = json.load(f)
    with open(POLICY_SCHEMA_PATH, encoding="utf-8") as f:
        schema = json.load(f)
    try:
        jsonschema.validate(doc, schema)
    except jsonschema.ValidationError as exc:
        raise PolicyError(f"정책 '{name}' 스키마 위반: {exc.message}") from exc

    rows = {
        r["id"]: Row(r["id"], r["value"], r["unit"], r["status"], r["source"], r["note"])
        for r in doc["rows"]
    }
    if len(rows) != len(doc["rows"]):
        raise PolicyError(f"정책 '{name}'에 중복된 행 id가 있다")
    return Policy(doc["policy_version"], doc["description"], rows)


@dataclass(frozen=True)
class CostPolicy:
    """G가 실제로 쓰는 값만 뽑아둔 뷰 — 엔진이 JSON 구조를 몰라도 되게 한다."""

    module_g: Policy
    use_type: Policy

    @property
    def housing_unit_krw(self) -> int:
        return int(self.module_g.value("housing_flood_unit_krw"))

    @property
    def farmland_unit_krw_per_m2(self) -> int:
        return int(self.module_g.value("farmland_replant_unit_krw_per_m2")["일반작물"])

    @property
    def farmland_vegetable_unit_krw_per_m2(self) -> int:
        return int(self.module_g.value("farmland_replant_unit_krw_per_m2")["채소_엽근채류"])

    @property
    def landslide_reference(self) -> dict[str, Any]:
        return dict(self.module_g.value("landslide_reference_unit_krw"))

    @property
    def unknown_housing_ratio(self) -> float:
        return float(self.module_g.value("unknown_use_type_housing_ratio"))

    @property
    def min_upper_band_pct(self) -> float:
        return float(self.module_g.value("min_upper_band_pct"))

    @property
    def excluded_use_types(self) -> list[str]:
        return list(self.module_g.value("excluded_use_types"))

    @property
    def notice_review_years(self) -> int:
        return int(self.module_g.value("notice_review_years"))

    @property
    def vocabulary(self) -> list[str]:
        return list(self.use_type.value("vocabulary"))

    @property
    def housing_use_type(self) -> str:
        return "주거"

    @property
    def unknown_use_type(self) -> str:
        return str(self.use_type.value("unmapped_use_type")["no_attribute"])

    def basis_citation(self) -> str:
        molit = self.module_g.row("housing_flood_unit_krw").source
        mafra = self.module_g.row("farmland_replant_unit_krw_per_m2").source
        return (
            f"{molit['document']} {molit['clause']}(시행 {molit['effective']}) · "
            f"{mafra['document']} {mafra['clause']}(시행 {mafra['effective']}) — "
            "복구비 지원 단가 기준, 경제적 손실의 하한"
        )

    def summary(self) -> dict[str, Any]:
        return {"module_g": self.module_g.summary(), "use_type": self.use_type.summary()}


def active_policy() -> CostPolicy:
    policy = CostPolicy(load(MODULE_G_POLICY), load(USE_TYPE_POLICY))
    _validate(policy)
    return policy


def _validate(policy: CostPolicy) -> None:
    if policy.housing_unit_krw <= 0:
        raise PolicyError("housing_flood_unit_krw는 양수여야 한다")
    if policy.farmland_unit_krw_per_m2 <= 0:
        raise PolicyError("farmland 대파대 단가는 양수여야 한다")
    if not 0.0 <= policy.unknown_housing_ratio <= 1.0:
        raise PolicyError("unknown_use_type_housing_ratio는 0.0~1.0이어야 한다")
    if policy.min_upper_band_pct < 0:
        raise PolicyError("min_upper_band_pct는 음수일 수 없다")
    if policy.housing_use_type not in policy.vocabulary:
        raise PolicyError("주거가 use_type 어휘에 없다")
