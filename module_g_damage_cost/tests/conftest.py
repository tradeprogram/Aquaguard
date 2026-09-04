"""Module G 테스트 공용 픽스처.

§4.2 - contracts/·policies/와 module_g_damage_cost만 읽고 다른 모듈은 import하지 않는다.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

CONTRACTS_DIR = Path(__file__).resolve().parent.parent.parent / "contracts"

HOUSING_UNIT = 3_500_000
FARMLAND_UNIT = 381
UNKNOWN_RATIO = 0.744
MIN_BAND = 0.3
TABLE_REF = "module_g_v1"


def building(building_id: str, use_type: str = "주거", risk_prob: float = 0.78) -> dict:
    return {"building_id": building_id, "risk_prob": risk_prob, "use_type": use_type}


def buildings(**counts) -> list[dict]:
    """buildings(주거=3, 미상=2) 형태로 use_type별 건물을 만든다."""
    out = []
    for use_type, n in counts.items():
        out.extend(building(f"{use_type}-{i:03d}", use_type) for i in range(n))
    return out


def payload(exposed_buildings=None, farmland_ha: float = 0.0, table_ref: str = TABLE_REF) -> dict:
    return {
        "exposed_buildings": exposed_buildings if exposed_buildings is not None else [],
        "exposed_farmland_ha": farmland_ha,
        "unit_cost_table_ref": table_ref,
    }


@pytest.fixture
def contract() -> dict:
    with open(CONTRACTS_DIR / "module_g.example.json", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def contract_schema() -> dict:
    with open(CONTRACTS_DIR / "module_g.schema.json", encoding="utf-8") as f:
        return json.load(f)
