"""Module E 정책 로더 — policies/module_e.json을 스키마로 검증해 읽는다.

Module D의 로더(module_d_exposure_overlay/policy.py)와 같은 형식이지만, 모듈 사이는
계약 파일로만 묶는다는 원칙 때문에 import하지 않고 따로 둔다.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
POLICY_PATH = REPO / "policies" / "module_e.json"
SCHEMA_PATH = REPO / "policies" / "policy.schema.json"


class PolicyError(RuntimeError):
    pass


@dataclass(frozen=True)
class Row:
    id: str
    value: Any
    unit: str | None
    status: str
    source: dict
    note: str | None


@dataclass(frozen=True)
class Policy:
    version: str
    rows: dict[str, Row]

    def row(self, row_id: str) -> Row:
        if row_id not in self.rows:
            raise PolicyError(f"module_e 정책에 '{row_id}' 행이 없다")
        return self.rows[row_id]

    def value(self, row_id: str) -> Any:
        return self.row(row_id).value


@lru_cache(maxsize=1)
def load() -> Policy:
    import jsonschema

    doc = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    try:
        jsonschema.validate(doc, schema)
    except jsonschema.ValidationError as exc:
        raise PolicyError(f"module_e 정책 스키마 위반: {exc.message}") from exc
    rows = {
        r["id"]: Row(r["id"], r["value"], r["unit"], r["status"], r["source"], r["note"])
        for r in doc["rows"]
    }
    if len(rows) != len(doc["rows"]):
        raise PolicyError("module_e 정책에 중복된 행 id가 있다")
    return Policy(doc["policy_version"], rows)
