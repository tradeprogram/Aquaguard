"""
Module O가 A/B/C/D/E/G/H를 호출하는 어댑터 계층.

모드는 AQUAGUARD_MOCK_MODE로 정한다:

  1 (기본값)  전 모듈을 contracts/module_X.example.json의 "output"으로 대체한다.
              팀원 모듈이 없어도 Module O/UI를 굴려볼 수 있게 하는 목업이고,
              §9 데모 리허설처럼 출력이 결정적이어야 할 때도 이 모드를 쓴다.

  0           설치된 모듈은 실제 run()을 부르고, 아직 없는 모듈만 example.json으로
              메운다. 전부 실물이길 요구하지 않는 이유는 트랙별 진도가 다르기
              때문이다 — 2026-09-04 기준 C/D/E/H는 들어왔고 A/B/G는 아직이라,
              예전처럼 "0이면 전부 import"로 두면 module_a_landslide에서
              ModuleNotFoundError로 파이프라인 전체가 죽는다. 그래서 모듈 단위로
              내려간다.

어느 모드든 orchestrator.py는 호출부를 바꾸지 않는다. 다만 화면에서 "이 숫자가
실제 모델 계산인지 예시값인지"를 구분해야 하므로(§6.1 Provenance 배지),
resolve_source()로 모듈별 출처를 따로 조회할 수 있게 해뒀다.
"""
from __future__ import annotations

import importlib
import json
import os
from functools import lru_cache
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

SOURCE_REAL = "real"
SOURCE_EXAMPLE = "example"


def _mock_mode() -> bool:
    return os.environ.get("AQUAGUARD_MOCK_MODE", "1") != "0"


@lru_cache(maxsize=None)
def _import_module(package_name: str):
    """§4.2 진입점 run()을 실제로 가진 모듈이면 그것을, 아니면 None을 돌려준다.

    import 성공만으로 "설치됨"으로 보면 안 된다. __init__.py 없이 __pycache__만 남은
    디렉토리도 파이썬이 네임스페이스 패키지로 import에 성공시키기 때문에, 그런
    껍데기가 example에서 real로 조용히 뒤집힌 뒤 호출 시점에 AttributeError로
    파이프라인을 죽인다(2026-09-05 트랙② 실측 보고, 재현 확인함). run()이 있는지까지
    봐야 그 디렉토리를 "아직 없는 모듈"로 정확히 취급한다.

    lru_cache를 건 이유는 Module O가 한 번 실행될 때 같은 모듈을 여러 번 물어보고
    (call_module + resolve_source), 없는 모듈은 매번 import 실패 비용을 치르기
    때문이다. 실행 중에 패키지가 새로 생기는 상황은 없다고 본다.
    """
    try:
        module = importlib.import_module(package_name)
    except ImportError:
        return None
    return module if callable(getattr(module, "run", None)) else None


def resolve_source(module_letter: str) -> str:
    """이 모듈이 지금 실물로 도는지("real") 예시값으로 대체되는지("example").

    UI가 Provenance 배지를 정직하게 찍으려면 파이프라인이 끝난 뒤가 아니라
    호출 전에도 알 수 있어야 해서 call_module과 분리해뒀다.
    """
    if _mock_mode():
        return SOURCE_EXAMPLE
    package_name = MODULE_PACKAGES[module_letter]
    return SOURCE_REAL if _import_module(package_name) is not None else SOURCE_EXAMPLE


def _load_example(module_letter: str) -> dict[str, Any]:
    path = CONTRACTS_DIR / f"module_{module_letter}.example.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def call_module(module_letter: str, input_data: dict[str, Any]) -> dict[str, Any]:
    """§4.2 공통 봉투({status, fallback_tier, data, warnings})를 반환한다."""
    if resolve_source(module_letter) == SOURCE_EXAMPLE:
        return _load_example(module_letter)["output"]

    module = _import_module(MODULE_PACKAGES[module_letter])
    return module.run(input_data)


def module_sources() -> dict[str, str]:
    """모듈 문자 -> "real"/"example" 전체 맵. Module O가 봉투 meta에 실어 보낸다."""
    return {letter: resolve_source(letter) for letter in MODULE_PACKAGES}
