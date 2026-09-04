"""Module D 테스트 공용 픽스처.

§4.2 "각 모듈 폴더는 pytest로 독립 테스트 가능해야 한다" — 이 디렉토리는
contracts/·policies/와 module_d_exposure_overlay만 읽고 다른 모듈은 import하지 않는다.

좌표는 산청 AOI 근처의 EPSG:5179 실좌표대(1,05x,xxx / 1,70x,xxx)를 쓰되 면적이
산술적으로 딱 떨어지게 잡았다 — data/vector/에 건축물·농경지 데이터가 없어서
합성 픽스처로 가야 하는데, 그럴 거면 기대 면적을 눈으로 검산할 수 있어야 한다.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

CONTRACTS_DIR = Path(__file__).resolve().parent.parent.parent / "contracts"

# 산청 AOI 부근 EPSG:5179 기준점 (module_o_orchestrator의 데모 대피소 좌표대와 같은 영역)
X0 = 1_050_000.0
Y0 = 1_707_000.0


def rect(x_min: float, y_min: float, x_max: float, y_max: float) -> dict:
    """EPSG:5179 미터 직사각형 Polygon."""
    return {
        "type": "Polygon",
        "coordinates": [
            [
                [x_min, y_min],
                [x_max, y_min],
                [x_max, y_max],
                [x_min, y_max],
                [x_min, y_min],
            ]
        ],
    }


def offset_rect(dx_min: float, dy_min: float, dx_max: float, dy_max: float) -> dict:
    """기준점(X0, Y0)에서의 상대 좌표로 직사각형을 만든다 — 면적 검산이 쉬워진다."""
    return rect(X0 + dx_min, Y0 + dy_min, X0 + dx_max, Y0 + dy_max)


def feature(geometry: dict, **properties) -> dict:
    return {"type": "Feature", "geometry": geometry, "properties": dict(properties)}


def collection(*features: dict) -> dict:
    return {"type": "FeatureCollection", "features": list(features)}


def risk(geometry: dict, risk_prob: float, source_module: str = "A") -> dict:
    return {"source_module": source_module, "geometry_5179": geometry, "risk_prob": risk_prob}


@pytest.fixture
def contract() -> dict:
    with open(CONTRACTS_DIR / "module_d.example.json", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def contract_schema() -> dict:
    with open(CONTRACTS_DIR / "module_d.schema.json", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def documented_case() -> dict:
    """contracts/module_d.example.json이 문서화한 output을 실제로 만들어내는 입력.

    example.json의 input은 전부 비어 있어(coordinates: [], features: []) 그 output을
    낼 수 없다 — 계약 파일은 4인 합의 없이 못 고치므로(§4.3) 여기서 실좌표 입력을
    만들어 문서가 말하는 출력을 재현한다.

      위험영역   x[0, 300]     y[0, 300]      (300m × 300m)
      농경지     x[90, 400]    y[100, 500]    → 교차 210m × 200m = 42,000㎡ = 4.2ha
      건물       x[50, 70]     y[50, 70]      → 위험영역 안, 주용도 '공동주택' → '주거'
    """
    return {
        "risk_polygons": [risk(offset_rect(0, 0, 300, 300), 0.78, "A")],
        "building_footprints_5179": collection(
            feature(offset_rect(50, 50, 70, 70), building_id="B12345", 주용도="공동주택")
        ),
        "farmland_parcels_5179": collection(feature(offset_rect(90, 100, 400, 500))),
    }
