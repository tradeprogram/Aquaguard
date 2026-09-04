"""A. 계약 테스트 — 임계값이 바뀌어도 깨지면 안 되는 것들."""
from __future__ import annotations

import jsonschema
import pytest

from module_c_urban_rule import run


def test_example_input_reproduces_example_output(contract):
    """1. contracts/module_c.example.json의 input → output 봉투를 정확히 재현한다."""
    assert run(contract["input"]) == contract["output"]


def test_example_reproduced_under_every_ruleset(contract, any_ruleset):
    """1-b(추가). v0/v1 어느 룰셋에서도 계약 예시가 재현된다.

    45.0 × 1.30(low) × 1.15(known_risk) = 67.275 >= 50 → "위험".
    두 룰셋의 절단점·계수가 같으므로 근거 주입이 계약 예시를 깨지 않았다는 확인.
    """
    assert run(contract["input"]) == contract["output"], f"ruleset={any_ruleset}"


def test_output_validates_against_contract_schema(contract, contract_schema):
    """2. run() 출력이 module_c.schema.json의 output 스키마를 통과한다."""
    jsonschema.validate(run(contract["input"]), contract_schema["properties"]["output"])


@pytest.mark.parametrize(
    "bad_input",
    [
        {},
        {"underpass_id": "SC-UP-001"},
        {"underpass_id": "SC-UP-001", "rainfall_intensity_1h_mm": "많이"},
        {"underpass_id": None, "rainfall_intensity_1h_mm": 10.0},
        None,
    ],
)
def test_degraded_and_error_outputs_still_validate(bad_input, contract_schema):
    """2-b. 폴백·에러 경로의 봉투도 스키마를 만족해야 Module O가 받아먹을 수 있다."""
    jsonschema.validate(run(bad_input), contract_schema["properties"]["output"])


def test_data_exposes_exactly_the_contracted_keys(contract):
    """3. data에 계약 밖 필드(판정근거·룰셋버전 등)가 새어나가지 않는다."""
    assert set(run(contract["input"])["data"]) == {"alert_level", "underpass_id"}


def test_envelope_exposes_exactly_the_contracted_keys(contract):
    """3-b. 봉투 최상위도 §4.2의 네 키뿐."""
    assert set(run(contract["input"])) == {"status", "fallback_tier", "data", "warnings"}
