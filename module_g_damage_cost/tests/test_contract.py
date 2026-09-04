"""A. 계약 테스트."""
from __future__ import annotations

import jsonschema
import pytest

from module_g_damage_cost import run

from .conftest import FARMLAND_UNIT, HOUSING_UNIT, buildings, payload


def test_contract_example_input_cannot_produce_its_own_output(contract):
    """0. 계약 예시의 input은 자기 output을 낼 수 없다 — 이 사실 자체를 고정해둔다.

    주거 1세대 x 3,500,000 + 4.2ha(42,000m2) x 381 = 19,502,000원인데 문서값은
    1,250,000,000원으로 약 64배다. 단가 고시(국토부 제2026-90호·농식품부 제2026-78호)를
    쓰는 한 재현할 수 없다. Day 1 계약 회의 안건 9번(TRACK2_CONTRACT_AGENDA.md).
    """
    result = run(contract["input"])
    assert result["data"]["estimated_cost_krw"] == 19_502_000
    assert contract["output"]["data"]["estimated_cost_krw"] == 1_250_000_000
    assert result["data"] != contract["output"]["data"]


def test_output_validates_against_contract_schema(contract, contract_schema):
    """1. run() 출력이 module_g.schema.json의 output 스키마를 통과한다."""
    jsonschema.validate(run(contract["input"]), contract_schema["properties"]["output"])


@pytest.mark.parametrize(
    "bad_input",
    [
        {},
        None,
        "not a dict",
        {"exposed_buildings": "nope"},
        payload(buildings(주거=2), farmland_ha=-1),
        payload([{"use_type": 5}], farmland_ha=1.0),
        payload(buildings(주거=1000), farmland_ha=99999.0),
    ],
)
def test_every_path_validates_against_the_schema(bad_input, contract_schema):
    """1-b. 정상·폴백·에러 어느 경로의 봉투도 스키마를 만족해야 O가 받아먹는다."""
    jsonschema.validate(run(bad_input), contract_schema["properties"]["output"])


def test_costs_are_integers_as_the_contract_requires():
    """2. estimated_cost_krw와 cost_range_krw 원소는 반드시 int다(float 금지)."""
    data = run(payload(buildings(주거=3), farmland_ha=1.23456))["data"]
    assert isinstance(data["estimated_cost_krw"], int)
    assert all(isinstance(v, int) for v in data["cost_range_krw"])
    assert not isinstance(data["estimated_cost_krw"], bool)


def test_data_exposes_exactly_the_contracted_keys():
    """3. data에 계약 밖 필드(제외 건수·참고 단가 등)가 새어나가지 않는다."""
    result = run(payload(buildings(주거=1), farmland_ha=1.0))
    assert set(result["data"]) == {"estimated_cost_krw", "cost_range_krw", "basis_citation"}
    assert set(result) == {"status", "fallback_tier", "data", "warnings"}


def test_module_d_output_can_be_spread_into_module_g_input():
    """4. O가 하는 대로 D의 data를 그대로 펼쳐 넘겨도 동작한다."""
    module_d_data = {"exposed_buildings": buildings(주거=2, 미상=1), "exposed_farmland_ha": 4.2}
    result = run({**module_d_data, "unit_cost_table_ref": "module_g_v1"})
    assert result["status"] == "ok"
    assert result["data"]["estimated_cost_krw"] == 2 * HOUSING_UNIT + 42_000 * FARMLAND_UNIT
