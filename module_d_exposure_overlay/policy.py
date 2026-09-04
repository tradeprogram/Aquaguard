"""policies/ 로더 (Module D).

정책값과 출처는 전부 저장소 최상위 policies/*.json에만 산다. use_type 어휘는
Module G와 공유하는 파일이라 D 패키지 안에 두지 않았다 — 이유는 policies/README.md.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

POLICIES_DIR = Path(__file__).resolve().parent.parent / "policies"
POLICY_SCHEMA_PATH = POLICIES_DIR / "policy.schema.json"

MODULE_D_POLICY = "module_d"
USE_TYPE_POLICY = "use_type_vocabulary"

FULLY_CONFIRMED_STATUSES = frozenset({"CONFIRMED", "TEAM_DECISION"})


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
        """공식 출처가 확정됐거나 팀이 명시적으로 결정한 값."""
        return self.status in FULLY_CONFIRMED_STATUSES


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

    def unsettled_rows(self) -> list[Row]:
        return [r for r in self.rows.values() if not r.is_settled]

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
class ExposurePolicy:
    """D가 실제로 쓰는 값만 뽑아둔 뷰 — 엔진이 JSON 구조를 몰라도 되게 한다."""

    module_d: Policy
    use_type: Policy

    @property
    def buffer_enabled(self) -> bool:
        return bool(self.module_d.value("point_buffer_radius_m")["enabled"])

    @property
    def buffer_radius_m(self) -> float:
        return float(self.module_d.value("point_buffer_radius_m")["radius_m"])

    @property
    def min_risk_prob(self) -> float:
        return float(self.module_d.value("min_risk_prob"))

    @property
    def building_id_keys(self) -> list[str]:
        return list(self.module_d.value("building_id_keys"))

    @property
    def use_type_keys(self) -> list[str]:
        return list(self.module_d.value("use_type_keys"))

    @property
    def area_round_digits(self) -> int:
        return int(self.module_d.value("farmland_area_round_digits"))

    @property
    def vocabulary(self) -> list[str]:
        return list(self.use_type.value("vocabulary"))

    @property
    def source_value_mapping(self) -> dict[str, list[str]]:
        return dict(self.use_type.value("source_value_mapping"))

    @property
    def use_type_when_no_attribute(self) -> str:
        return str(self.use_type.value("unmapped_use_type")["no_attribute"])

    @property
    def use_type_when_unrecognized(self) -> str:
        return str(self.use_type.value("unmapped_use_type")["unrecognized_value"])

    def summary(self) -> dict[str, Any]:
        return {"module_d": self.module_d.summary(), "use_type": self.use_type.summary()}


def active_policy() -> ExposurePolicy:
    policy = ExposurePolicy(load(MODULE_D_POLICY), load(USE_TYPE_POLICY))
    _validate(policy)
    return policy


def _validate(policy: ExposurePolicy) -> None:
    if policy.buffer_radius_m <= 0:
        raise PolicyError("point_buffer_radius_m.radius_m은 양수여야 한다")
    if not 0.0 <= policy.min_risk_prob <= 1.0:
        raise PolicyError("min_risk_prob는 0.0~1.0이어야 한다")
    vocabulary = policy.vocabulary
    if len(set(vocabulary)) != len(vocabulary):
        raise PolicyError("use_type 어휘에 중복이 있다")
    unknown = set(policy.source_value_mapping) - set(vocabulary)
    if unknown:
        raise PolicyError(f"source_value_mapping에 어휘 밖 분류가 있다: {sorted(unknown)}")
    for fallback in (policy.use_type_when_no_attribute, policy.use_type_when_unrecognized):
        if fallback not in vocabulary:
            raise PolicyError(f"unmapped_use_type 값이 어휘 밖이다: {fallback}")
