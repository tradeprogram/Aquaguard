"""A. 계약 테스트 + 문서화된 출력 재현."""
from __future__ import annotations

import jsonschema
import pytest

from module_d_exposure_overlay import run

from .conftest import collection, feature, offset_rect, risk


def test_contract_example_input_reproduces_its_own_output(contract):
    """0. 계약 예시의 input이 자기 output을 그대로 재현한다 (Module C와 같은 기준).

    2026-09-04 4인 합의로 안건 2번이 해결되면서 example.json의 input이 빈 값에서
    실좌표로 교체됐다(TRACK2_CONTRACT_AGENDA.md 2번). 그 전까지 이 자리에 있던
    test_contract_example_input_cannot_produce_its_own_output — 불일치 자체를 고정하던
    테스트 — 는 역할이 끝나 이 재현 테스트로 승격했다.
    """
    result = run(contract["input"])
    assert result == contract["output"]


def test_documented_output_is_reproducible_from_real_coordinates(documented_case, contract):
    """1. 픽스처 입력으로도 계약이 문서화한 output data를 정확히 재현한다.

    위 계약 재현 테스트와 좌표가 같다(계약 input이 이 픽스처에서 왔다). 픽스처 쪽이
    깨지면 계약 파일이 아니라 헬퍼가 틀어진 것이므로 둘 다 남겨둔다.
    """
    result = run(documented_case)
    assert result["status"] == "ok"
    assert result["fallback_tier"] == 1
    assert result["warnings"] == []
    assert result["data"] == contract["output"]["data"]


def test_output_validates_against_contract_schema(documented_case, contract_schema):
    """2. run() 출력이 module_d.schema.json의 output 스키마를 통과한다."""
    jsonschema.validate(run(documented_case), contract_schema["properties"]["output"])


@pytest.mark.parametrize(
    "bad_input",
    [
        {},
        None,
        "not a dict",
        {"risk_polygons": "nope"},
        {"risk_polygons": [{"geometry_5179": {}, "risk_prob": 2.5}]},
        {"risk_polygons": [risk(offset_rect(0, 0, 10, 10), 0.5)]},
    ],
)
def test_degraded_and_error_outputs_still_validate(bad_input, contract_schema):
    """2-b. 폴백·에러 경로의 봉투도 스키마를 만족해야 Module O가 받아먹을 수 있다."""
    jsonschema.validate(run(bad_input), contract_schema["properties"]["output"])


def test_data_exposes_exactly_the_contracted_keys(documented_case):
    """3. data에 계약 밖 필드(합집합 면적·버퍼 사용 여부 등)가 새어나가지 않는다."""
    assert set(run(documented_case)["data"]) == {"exposed_buildings", "exposed_farmland_ha"}
    assert set(run(documented_case)) == {"status", "fallback_tier", "data", "warnings"}


def test_survives_what_module_o_actually_sends():
    """4. Module O가 실모드에서 실제로 보내는 입력으로도 죽지 않는다.

    orchestrator.py는 Module A의 location(점 dict)과 빈 dict를 geometry_5179로,
    건물·농경지는 {}를 넘긴다. 계약 예시와 전혀 다른 모양이다.
    """
    result = run(
        {
            "risk_polygons": [
                {"source_module": "A", "geometry_5179": {"x_5179": 1090452.3, "y_5179": 1662188.7}, "risk_prob": 0.78},
                {"source_module": "B", "geometry_5179": {}, "risk_prob": 0.61},
            ],
            "building_footprints_5179": {},
            "farmland_parcels_5179": {},
        }
    )
    assert result["status"] == "degraded"
    assert result["fallback_tier"] == 2
    assert result["data"] == {"exposed_buildings": [], "exposed_farmland_ha": 0.0}
    assert any("버퍼링" in w for w in result["warnings"])
