"""
Module O가 A/B/C/D/E/G/H를 호출하는 어댑터 계층.

AQUAGUARD_MOCK_MODE=1(기본값)이면 contracts/module_X.example.json의
"output" 필드를 그대로 반환한다 (팀원 모듈이 아직 없어도 Module O/UI를
먼저 굴려볼 수 있게 하는 목업). 0으로 바꾸면 실제 module_X_yyyy 패키지의
run(input)을 import해서 호출한다 — 이 파일 밖의 호출부(orchestrator.py)는
어느 쪽이든 신경 쓰지 않아도 되도록 인터페이스를 동일하게 유지한다.
"""
from __future__ import annotations

import importlib
import json
import os
from pathlib import Path
from typing import Any

CONTRACTS_DIR = Path(__file__).resolve().parent.parent / "contracts"

# module 문자(A/B/...) -> 실제 모듈 패키지명 (§8 디렉토리 구조와 일치)
MODULE_PACKAGES = {
    "a": "module_a_landslide",
    "b": "module_b_flood",
    "c": "module_c_urban_rule",
    "d": "module_d_exposure_overlay",
    "e": "module_e_routing",
    "g": "module_g_damage_cost",
    "h": "module_h_citizen_verification",
}


def _mock_mode() -> bool:
    return os.environ.get("AQUAGUARD_MOCK_MODE", "1") != "0"


def _load_example(module_letter: str) -> dict[str, Any]:
    path = CONTRACTS_DIR / f"module_{module_letter}.example.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def call_module(module_letter: str, input_data: dict[str, Any]) -> dict[str, Any]:
    """§4.2 공통 봉투({status, fallback_tier, data, warnings})를 반환한다."""
    if _mock_mode():
        example = _load_example(module_letter)
        return example["output"]

    package_name = MODULE_PACKAGES[module_letter]
    module = importlib.import_module(package_name)
    return module.run(input_data)
