"""정책 로더 (Module H).

집계 규칙과 그 근거는 전부 policies/*.json에만 산다 — aggregate.py도 reports.py도
숫자를 상수로 갖지 않는다. 파일럿 데이터로 재보정한다는 것은 그 JSON을 고치는
것이고 파이썬 코드는 바뀌지 않는다.

Module D의 정책은 저장소 최상위 policies/에 있지만 H의 정책은 패키지 안에 둔다 —
최상위는 D와 G가 use_type 어휘를 공유해야 해서 만든 자리이고, H는 다른 모듈과
공유할 정책이 없다(Module C의 rulesets/와 같은 방식).
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

POLICIES_DIR = Path(__file__).resolve().parent / "policies"
POLICY_SCHEMA_PATH = POLICIES_DIR / "policy.schema.json"
DEFAULT_POLICY = "v1_default"

# 근거가 확정됐거나 팀이 명시적으로 결정한 값. 나머지(PLACEHOLDER)는 재보정 대상이다.
SETTLED_STATUSES = frozenset({"CONFIRMED", "DERIVED", "TEAM_DECISION"})

REPORT_TYPES = ("이상징후_목격", "이미_대피함", "오탐_신고")
VERIFICATION_STATUSES = ("미확인", "현장확인", "오탐판정")


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

    # --- 엔진이 실제로 쓰는 접근자 -------------------------------------------------
    @property
    def type_weights(self) -> dict[str, float]:
        return {k: float(v) for k, v in self.value("report_type_weights").items()}

    @property
    def shrinkage_k(self) -> float:
        return float(self.value("shrinkage_k"))

    @property
    def max_adjustment(self) -> float:
        return float(self.value("max_adjustment"))

    @property
    def min_weighted_positive(self) -> float:
        return float(self.value("confirm_threshold")["min_weighted_positive"])

    @property
    def min_false_reports(self) -> int:
        return int(self.value("false_positive_threshold")["min_false_reports"])

    @property
    def min_false_ratio(self) -> float:
        return float(self.value("false_positive_threshold")["min_false_ratio"])

    @property
    def full_weight_min_reports(self) -> int:
        return int(self.value("full_weight_min_reports"))

    @property
    def valid_window_min(self) -> float:
        return float(self.value("valid_window_min"))

    @property
    def photo_weight_bonus(self) -> float:
        return float(self.value("photo_weight_bonus"))

    @property
    def alert_id_pattern(self) -> str:
        return str(self.value("alert_id_pattern"))

    @property
    def adjustment_digits(self) -> int:
        return int(self.value("rounding")["adjustment_digits"])

    @property
    def latency_digits(self) -> int:
        return int(self.value("rounding")["latency_digits"])

    # --- provenance ---------------------------------------------------------------
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

    policy = Policy(doc["policy_version"], doc["description"], rows)
    _validate(policy)
    return policy


def _validate(policy: Policy) -> None:
    weights = policy.type_weights
    if set(weights) != set(REPORT_TYPES):
        raise PolicyError(f"report_type_weights는 계약의 3개 유형을 모두 가져야 한다: {REPORT_TYPES}")
    if weights["오탐_신고"] >= 0:
        raise PolicyError("오탐_신고 가중치는 음수여야 한다")
    if weights["이상징후_목격"] <= 0:
        raise PolicyError("이상징후_목격 가중치는 양수여야 한다")
    if policy.shrinkage_k < 0:
        raise PolicyError("shrinkage_k는 음수일 수 없다")
    if not 0.0 < policy.max_adjustment <= 0.3:
        raise PolicyError("max_adjustment는 계약이 정한 0.3을 넘을 수 없다")
    if not 0.0 <= policy.min_false_ratio <= 1.0:
        raise PolicyError("min_false_ratio는 0.0~1.0이어야 한다")
    if policy.full_weight_min_reports < 1:
        raise PolicyError("full_weight_min_reports는 1 이상이어야 한다")
    if policy.valid_window_min <= 0:
        raise PolicyError("valid_window_min은 양수여야 한다")


def active_policy_name() -> str:
    return os.environ.get("AQUAGUARD_MODULE_H_POLICY", DEFAULT_POLICY)


def active_policy() -> Policy:
    return load(active_policy_name())
