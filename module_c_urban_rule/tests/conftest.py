"""Module C 테스트 공용 픽스처.

§4.2 "각 모듈 폴더는 pytest로 독립 테스트 가능해야 한다" — 이 디렉토리의
테스트는 contracts/의 계약 파일과 module_c_urban_rule만 읽고, 다른 모듈은
import하지 않는다.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

CONTRACTS_DIR = Path(__file__).resolve().parent.parent.parent / "contracts"
RULESET_ENV = "AQUAGUARD_MODULE_C_RULESET"
STRICT_ENV = "AQUAGUARD_MODULE_C_STRICT_PROVENANCE"
ALL_RULESETS = ("v0_placeholder", "v1_kma_mois")


@pytest.fixture
def contract() -> dict:
    with open(CONTRACTS_DIR / "module_c.example.json", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def contract_schema() -> dict:
    with open(CONTRACTS_DIR / "module_c.schema.json", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch):
    """룰셋/strict 스위치가 테스트 간에 새지 않도록 매 테스트마다 기본값으로 되돌린다."""
    monkeypatch.delenv(RULESET_ENV, raising=False)
    monkeypatch.delenv(STRICT_ENV, raising=False)


@pytest.fixture(params=ALL_RULESETS)
def any_ruleset(request, monkeypatch) -> str:
    """v0/v1 두 룰셋 모두에서 같은 성질이 성립하는지 확인할 때 쓴다."""
    monkeypatch.setenv(RULESET_ENV, request.param)
    return request.param
