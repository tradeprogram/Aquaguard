"""
노출자산 레이어 접근 계층 (§10 TODO "Module O가 이 값을 어디서 가져올지").

Module D의 입력 중 risk_polygons는 Module A/B가 만들지만, building_footprints_5179와
farmland_parcels_5179는 어느 모듈의 출력도 아니다 — Module O가 데이터에서 직접
읽어와야 한다. 그동안 빈 dict를 넘기고 있어서 D가 항상 "FeatureCollection이 아님"
경고와 함께 노출 0건을 냈다.

건축물: data/vector/aoi_buildings_5179.geojson (커밋됨, 생비량면 2,410건, EPSG:5179).
원본인 data/precomputed/sancheong_buildings.geojson(57,681건)은 .gitignore라 배포
서버에 없어서, 데모가 실제로 도는 AOI만 잘라 커밋했다
(scripts/build_aoi_exposure_layers.py로 재생성).

농경지: 아직 없다. data/vector에는 행정경계·대피소·건축물뿐이고 농경지 레이어를
확보하지 못했다. 빈 FeatureCollection을 돌려주되 이유를 함께 내보내서, Module O가
"농경지 노출 0ha"를 사실처럼 보고하지 않고 미확보 상태로 경고하게 한다.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

DATA_VECTOR_DIR = Path(__file__).resolve().parent.parent / "data" / "vector"
AOI_BUILDINGS_PATH = DATA_VECTOR_DIR / "aoi_buildings_5179.geojson"

EMPTY_COLLECTION: dict[str, Any] = {"type": "FeatureCollection", "features": []}


@lru_cache(maxsize=1)
def _load_buildings() -> tuple[dict[str, Any], str | None]:
    """(FeatureCollection, 경고) — 파일이 없거나 깨져도 예외를 던지지 않는다.

    Module O는 §4.2대로 어떤 경우에도 봉투를 내야 하므로, 레이어를 못 읽는 것은
    파이프라인을 죽일 사유가 아니라 경고로 내려갈 사유다.
    """
    if not AOI_BUILDINGS_PATH.exists():
        return dict(EMPTY_COLLECTION), (
            f"건축물 레이어 없음({AOI_BUILDINGS_PATH.name}) — 노출 건물 0건으로 진행. "
            "scripts/build_aoi_exposure_layers.py로 생성할 것"
        )
    try:
        with open(AOI_BUILDINGS_PATH, encoding="utf-8") as f:
            collection = json.load(f)
    except (OSError, ValueError) as exc:
        return dict(EMPTY_COLLECTION), (
            f"건축물 레이어 로드 실패({type(exc).__name__}) — 노출 건물 0건으로 진행"
        )
    if not isinstance(collection, dict) or collection.get("type") != "FeatureCollection":
        return dict(EMPTY_COLLECTION), "건축물 레이어가 FeatureCollection이 아님 — 노출 건물 0건으로 진행"
    return collection, None


def building_footprints() -> tuple[dict[str, Any], str | None]:
    """AOI 건축물 footprint(EPSG:5179)와 문제가 있었다면 그 경고."""
    return _load_buildings()


def farmland_parcels() -> tuple[dict[str, Any], str | None]:
    """농경지 필지(EPSG:5179). 아직 레이어가 없어 항상 빈 컬렉션 + 경고다.

    빈 값을 조용히 넘기면 D가 exposed_farmland_ha=0을 내고 화면에는 "농경지 피해 없음"
    처럼 읽힌다. 실제로는 "확인 불가"이므로 그 차이를 경고로 남긴다(§7 불확실성 표기).
    """
    return dict(EMPTY_COLLECTION), (
        "농경지 레이어 미확보 — exposed_farmland_ha는 0이 아니라 '확인 불가'로 읽어야 한다"
    )
