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

from module_d_exposure_overlay import use_types

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


@pytest.fixture(autouse=True)
def isolated_repo_root(tmp_path, monkeypatch):
    """§4.2 - D의 테스트는 data/precomputed 산출물 없이도 돌아야 한다.

    건축물대장 주용도 매핑은 API 산출물이라 저장소에 없다(.gitignore). 테스트가
    개발자 머신에 그 파일이 있는지에 따라 달라지면 안 되므로 매번 빈 임시 루트를
    보게 하고, 조인을 테스트할 때만 write_parcel_mapping으로 채워 넣는다.
    """
    monkeypatch.setattr(use_types, "REPO_ROOT", tmp_path)
    use_types.load.cache_clear()
    yield tmp_path
    use_types.load.cache_clear()


def write_parcel_mapping(root, mapping: dict) -> None:
    """임시 루트에 소형 픽스처 매핑을 심는다 (실제 산출물과 같은 경로·형식)."""
    path = root / "data" / "precomputed" / "building_use_types.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(mapping, ensure_ascii=False), encoding="utf-8")
    use_types.load.cache_clear()
