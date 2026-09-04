"""A. 계약 테스트 + 문서화된 출력 재현."""
from __future__ import annotations

import jsonschema
import pytest

from module_h_citizen_verification import run

from .conftest import payload, report, sightings


def test_contract_example_input_reproduces_its_own_output(contract):
    """0. 계약 예시의 input이 자기 output을 그대로 재현한다 (Module C와 같은 기준).

    2026-09-04 4인 합의로 안건 7·8번이 해결되면서 example.json의 input에 신고 6건과
    alert_issued_at이 채워졌다(alert_issued_at은 스키마의 정식 입력 필드로 승격).
    그 전까지 이 자리에 있던 test_contract_example_input_cannot_produce_its_own_output —
    신고 1건 대 report_count 6의 불일치를 고정하던 테스트 — 는 역할이 끝나 이 재현
    테스트로 승격했다.
    """
    result = run(contract["input"])
    assert result == contract["output"]


def test_documented_output_is_reproducible(documented_case, contract):
    """1. 신고 6건 + 첫 응답 4.5분 입력으로 계약이 문서화한 output data를 정확히 재현한다.

    위 계약 재현 테스트와 입력이 같다(계약 input이 이 픽스처에서 왔다). 픽스처 쪽이
    깨지면 계약 파일이 아니라 헬퍼가 틀어진 것이므로 둘 다 남겨둔다.
    """
    result = run(documented_case)
    assert result["status"] == "ok"
    assert result["fallback_tier"] == 1
    assert result["warnings"] == []
    assert result["data"] == contract["output"]["data"]


def test_output_validates_against_contract_schema(documented_case, contract_schema):
    """2. run() 출력이 module_h.schema.json의 output 스키마를 통과한다."""
    jsonschema.validate(run(documented_case), contract_schema["properties"]["output"])


@pytest.mark.parametrize(
    "bad_input",
    [
        {},
        None,
        "not a dict",
        {"trigger_location": {"x_5179": 1.0, "y_5179": 2.0}, "trigger_radius_m": 500, "citizen_reports": "nope"},
        payload([]),
        payload(sightings(30)),
        payload([report("R1", report_type="오탐_신고"), report("R2", report_type="오탐_신고")]),
    ],
)
def test_every_path_validates_against_the_schema(bad_input, contract_schema):
    """2-b. 정상·폴백·에러 어느 경로의 봉투도 스키마를 만족해야 Module O가 받아먹는다."""
    jsonschema.validate(run(bad_input), contract_schema["properties"]["output"])


def test_data_exposes_exactly_the_contracted_keys(documented_case):
    """3. data에 계약 밖 필드(가중치·제외 내역·사진 건수 등)가 새어나가지 않는다."""
    result = run(documented_case)
    assert set(result["data"]) == {
        "report_count",
        "verification_status",
        "confidence_adjustment",
        "response_latency_min",
    }
    assert set(result) == {"status", "fallback_tier", "data", "warnings"}
