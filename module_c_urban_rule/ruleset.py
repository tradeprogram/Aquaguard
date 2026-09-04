"""임계값 룰셋 로더 (Module C).

임계값과 그 출처는 전부 rulesets/*.json에만 산다 — 이 파일도 rules.py도
숫자를 상수로 갖지 않는다. 공식 근거를 주입한다는 것은 곧 해당 JSON 행의
source를 채우고 status를 뒤집는 것이고, 파이썬 코드는 한 줄도 바뀌지 않는다.

활성 룰셋은 환경변수 AQUAGUARD_MODULE_C_RULESET로 고른다(기본 v1_kma_mois).
기존 AQUAGUARD_MOCK_MODE(§4.2 목업 스위치)와 같은 네이밍 규칙을 따랐다.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

RULESETS_DIR = Path(__file__).resolve().parent / "rulesets"
# 룰셋 디렉토리와 분리해 둔다 — 테스트가 RULESETS_DIR를 다른 곳으로 돌려도
# 검증 스키마는 항상 패키지 안의 것을 쓴다.
RULESET_SCHEMA_PATH = RULESETS_DIR / "ruleset.schema.json"
DEFAULT_RULESET = "v1_kma_mois"

# 근거가 완전히 확정된 상태. 나머지 status는 전부 "가정이 섞여 있다"는 뜻이며
# explain()과 strict provenance 경고가 그 사실을 밖으로 드러낸다.
FULLY_CONFIRMED_STATUS = "CONFIRMED"

CUTPOINT_ROW_IDS = {
    "주의": "cutpoint_주의",
    "경계": "cutpoint_경계",
    "위험": "cutpoint_위험",
}


class RulesetError(ValueError):
    """룰셋 JSON이 구조적으로 잘못됐을 때. run()은 이걸 잡아 error 봉투로 바꾼다."""


@dataclass(frozen=True)
class Row:
    id: str
    value: Any
    unit: str | None
    status: str
    source: dict[str, Any]
    note: str | None
    # 1차 자료(기관 원문) URL이 아직 없을 때의 보도 확인 근거. source를 대체하지 않는다.
    corroborating_sources: tuple[dict[str, Any], ...] = ()

    @property
    def is_fully_confirmed(self) -> bool:
        return self.status == FULLY_CONFIRMED_STATUS


@dataclass(frozen=True)
class Ruleset:
    version: str
    description: str
    rows: dict[str, Row]

    def row(self, row_id: str) -> Row:
        try:
            return self.rows[row_id]
        except KeyError as exc:
            raise RulesetError(f"룰셋 {self.version}에 필수 행 '{row_id}'이 없다") from exc

    def optional_row(self, row_id: str) -> Row | None:
        return self.rows.get(row_id)

    # --- 엔진이 실제로 쓰는 접근자 -------------------------------------------------
    def cutpoints(self) -> list[tuple[str, float]]:
        """[( '주의', 20.0 ), ( '경계', 30.0 ), ( '위험', 50.0 )] — 오름차순 보장."""
        return [(level, float(self.row(rid).value)) for level, rid in CUTPOINT_ROW_IDS.items()]

    def drainage_factor(self, drainage_class: str) -> float:
        table = self.row("drainage_factor").value
        try:
            return float(table[drainage_class])
        except (KeyError, TypeError) as exc:
            raise RulesetError(f"drainage_factor에 '{drainage_class}' 등급이 없다") from exc

    def known_risk_factor(self) -> float:
        return float(self.row("known_risk_factor").value)

    def min_level_policy(self) -> dict[str, Any]:
        return dict(self.row("known_risk_min_level").value)

    def extreme_override_mm(self) -> float | None:
        """v0처럼 이 행이 없는 룰셋도 있으므로 optional."""
        row = self.optional_row("extreme_override")
        return None if row is None else float(row.value)

    # --- provenance ---------------------------------------------------------------
    def unconfirmed_rows(self) -> list[Row]:
        return [r for r in self.rows.values() if not r.is_fully_confirmed]

    def provenance_summary(self) -> dict[str, Any]:
        return {
            "ruleset_version": self.version,
            "status_counts": _count_by_status(self.rows.values()),
            "rows": [
                {
                    "id": r.id,
                    "status": r.status,
                    "source": r.source,
                    "corroborating_sources": list(r.corroborating_sources),
                    "note": r.note,
                }
                for r in self.rows.values()
            ],
        }


def _count_by_status(rows: Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        counts[row.status] = counts.get(row.status, 0) + 1
    return counts


def _validate_document(doc: Any, name: str) -> None:
    """rulesets/ruleset.schema.json으로 검증. jsonschema는 requirements.txt에 이미 있다."""
    import jsonschema

    with open(RULESET_SCHEMA_PATH, encoding="utf-8") as f:
        schema = json.load(f)
    try:
        jsonschema.validate(doc, schema)
    except jsonschema.ValidationError as exc:
        raise RulesetError(f"룰셋 '{name}' 스키마 위반: {exc.message}") from exc


def _validate_semantics(ruleset: Ruleset) -> None:
    cutpoints = ruleset.cutpoints()
    values = [v for _, v in cutpoints]
    if values != sorted(values) or len(set(values)) != len(values):
        raise RulesetError(f"룰셋 {ruleset.version}의 절단점이 오름차순이 아니다: {cutpoints}")

    table = ruleset.row("drainage_factor").value
    if not isinstance(table, dict) or set(table) != {"low", "medium", "high"}:
        raise RulesetError("drainage_factor는 low/medium/high 세 등급을 모두 가져야 한다")
    for cls, factor in table.items():
        if not isinstance(factor, (int, float)) or factor <= 0:
            raise RulesetError(f"drainage_factor[{cls}]는 양수여야 한다: {factor!r}")

    if ruleset.known_risk_factor() <= 0:
        raise RulesetError("known_risk_factor는 양수여야 한다")

    policy = ruleset.min_level_policy()
    if not isinstance(policy.get("enabled"), bool):
        raise RulesetError("known_risk_min_level.enabled는 bool이어야 한다")
    if policy["level"] not in CUTPOINT_ROW_IDS:
        raise RulesetError(f"known_risk_min_level.level이 유효한 등급이 아니다: {policy['level']!r}")

    override = ruleset.extreme_override_mm()
    if override is not None and override <= values[-1]:
        raise RulesetError(
            f"extreme_override({override})는 최고 절단점({values[-1]})보다 커야 의미가 있다"
        )


@lru_cache(maxsize=None)
def load(name: str) -> Ruleset:
    path = RULESETS_DIR / f"{name}.json"
    if not path.is_file():
        raise RulesetError(f"룰셋 파일을 찾을 수 없다: {path}")
    with open(path, encoding="utf-8") as f:
        doc = json.load(f)

    _validate_document(doc, name)

    rows = {
        r["id"]: Row(
            id=r["id"],
            value=r["value"],
            unit=r["unit"],
            status=r["status"],
            source=r["source"],
            note=r["note"],
            corroborating_sources=tuple(r.get("corroborating_sources", ())),
        )
        for r in doc["rows"]
    }
    if len(rows) != len(doc["rows"]):
        raise RulesetError(f"룰셋 '{name}'에 중복된 행 id가 있다")

    ruleset = Ruleset(version=doc["ruleset_version"], description=doc["description"], rows=rows)
    _validate_semantics(ruleset)
    return ruleset


def active_ruleset_name() -> str:
    return os.environ.get("AQUAGUARD_MODULE_C_RULESET", DEFAULT_RULESET)


def active_ruleset() -> Ruleset:
    return load(active_ruleset_name())
