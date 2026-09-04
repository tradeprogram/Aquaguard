"""A. 계약 테스트 + 문서화된 출력 재현."""
from __future__ import annotations

import jsonschema
import pytest

from module_h_citizen_verification import run

from .conftest import payload, report, sightings


def test_contract_example_input_cannot_produce_its_own_output(contract):
    """0. 계약 예시의 input은 자기 output을 낼 수 없다 — 이 사실 자체를 고정해둔다.

    input의 citizen_reports는 1건인데 output은 report_count 6이다. 게다가 경보 발송
    시각 필드가 없어 response_latency_min 4.5도 어디서도 유도되지 않는다
    (alert_id의 09:15 기준이면 유일한 신고 09:22은 7분이다).
    Day 1 계약 회의 안건 7·8번(TRACK2_CONTRACT_AGENDA.md).
    """
    result = run(contract["input"])
    assert result["data"] != contract["output"]["data"]
    assert result["data"]["report_count"] == 1
    assert result["data"]["response_latency_min"] == 7.0


def test_documented_output_is_reproducible(documented_case, contract):
    """1. 신고 6건 + 첫 응답 4.5분 입력으로 계약이 문서화한 output data를 정확히 재현한다."""
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
