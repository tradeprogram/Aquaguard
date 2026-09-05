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

농경지: 트랙②가 2026-09-05에 팜맵(농정원) 기반 레이어를 만들었다
(scripts/build_farmland_geojson.py → data/precomputed/sancheong_farmland_5179.geojson,
산청군 73,040 폴리곤, EPSG:5179). 다만 그 산출물도 .gitignore라 저장소에는 meta만
있으므로, 건축물과 같이 AOI 축소본을 커밋하기 전까지는 원본 경로를 그대로 읽는다.
파일이 없으면 빈 FeatureCollection + 경고로 내려간다 — "농경지 노출 0ha"와
"농경지를 확인하지 못함"은 다르고, 그 차이가 화면에 보여야 한다(§7 불확실성 표기).
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_VECTOR_DIR = REPO_ROOT / "data" / "vector"
PRECOMPUTED_DIR = REPO_ROOT / "data" / "precomputed"

AOI_BUILDINGS_PATH = DATA_VECTOR_DIR / "aoi_buildings_5179.geojson"
# 트랙②의 scripts/build_farmland_geojson.py 산출물. .gitignore라 없을 수 있다.
FARMLAND_PATH = PRECOMPUTED_DIR / "sancheong_farmland_5179.geojson"

EMPTY_COLLECTION: dict[str, Any] = {"type": "FeatureCollection", "features": []}


def _load_collection(path: Path, label: str, regenerate_hint: str) -> tuple[dict[str, Any], str | None]:
    """(FeatureCollection, 경고) — 파일이 없거나 깨져도 예외를 던지지 않는다.

    Module O는 §4.2대로 어떤 경우에도 봉투를 내야 하므로, 레이어를 못 읽는 것은
    파이프라인을 죽일 사유가 아니라 경고로 내려갈 사유다. 다만 조용히 빈 값을
    넘기면 "노출 0"이 사실처럼 읽히므로 반드시 이유를 함께 돌려준다.
    """
    if not path.exists():
        return dict(EMPTY_COLLECTION), (
            f"{label} 레이어 없음({path.name}) — 노출 0으로 계산되지만 이는 '없음'이 아니라 "
            f"'확인 불가'다. 재생성: {regenerate_hint}"
        )
    try:
        with open(path, encoding="utf-8") as f:
            collection = json.load(f)
    except (OSError, ValueError) as exc:
        return dict(EMPTY_COLLECTION), (
            f"{label} 레이어 로드 실패({type(exc).__name__}) — 노출 0으로 진행(확인 불가)"
        )
    if not isinstance(collection, dict) or collection.get("type") != "FeatureCollection":
        return dict(EMPTY_COLLECTION), f"{label} 레이어가 FeatureCollection이 아님 — 노출 0으로 진행(확인 불가)"
    return collection, None


@lru_cache(maxsize=1)
def _load_buildings() -> tuple[dict[str, Any], str | None]:
    return _load_collection(
        AOI_BUILDINGS_PATH, "건축물", "python scripts/build_aoi_exposure_layers.py"
    )


@lru_cache(maxsize=1)
def _load_farmland() -> tuple[dict[str, Any], str | None]:
    return _load_collection(
        FARMLAND_PATH, "농경지", "python scripts/build_farmland_geojson.py --region sancheong"
    )


def building_footprints() -> tuple[dict[str, Any], str | None]:
    """AOI 건축물 footprint(EPSG:5179)와 문제가 있었다면 그 경고."""
    return _load_buildings()


def farmland_parcels() -> tuple[dict[str, Any], str | None]:
    """농경지 필지(EPSG:5179)와 문제가 있었다면 그 경고."""
    return _load_farmland()
