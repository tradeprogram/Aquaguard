"""
노출자산 레이어 접근 계층 (§10 TODO "Module O가 이 값을 어디서 가져올지").

Module D의 입력 중 risk_polygons는 Module A/B가 만들지만, building_footprints_5179와
farmland_parcels_5179는 어느 모듈의 출력도 아니다 — Module O가 데이터에서 직접
읽어와야 한다. 그동안 빈 dict를 넘기고 있어서 D가 항상 "FeatureCollection이 아님"
경고와 함께 노출 0건을 냈다.

원본(data/precomputed/*.geojson)은 전부 .gitignore라 배포 서버에 없다 — 서울 건물
원본만 504MB다. 그래서 데모가 실제로 도는 AOI만 잘라 data/vector/에 커밋하고
여기서는 그 클립본만 읽는다. 재생성은 scripts/build_aoi_exposure_layers.py.

  aoi_buildings_sancheong_5179.geojson   경보지점 반경 12km  18,032건    7.9MB
  aoi_buildings_seoul_5179.geojson       강남·서초           41,814건   27.6MB
  aoi_farmland_sancheong_5179.geojson    경보지점 반경 12km  23,288필지 21.9MB (2,587.5ha)

산청은 행정경계가 아니라 경보지점 반경으로 자른다 — 행정경계로 자르면 경계 근처
경보에서 위험영역이 밖으로 새고, 그만큼 노출자산이 조용히 빠지기 때문이다.
자세한 근거는 scripts/build_aoi_exposure_layers.py의 AOI_DEFS 주석.

농경지 원본은 트랙②의 팜맵(농정원) 산출물이다(scripts/build_farmland_geojson.py,
산청군 73,040필지). 강남·서초는 팜맵 대상이 아니라 농경지 레이어가 없다.

레이어를 못 읽어도 예외를 던지지 않고 빈 FeatureCollection + 경고로 내려간다 —
"노출 0ha"와 "확인하지 못함"은 다르고, 그 차이가 화면에 보여야 한다(§7 불확실성 표기).
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_VECTOR_DIR = REPO_ROOT / "data" / "vector"
PRECOMPUTED_DIR = REPO_ROOT / "data" / "precomputed"  # 원본(gitignore) — 클립본은 data/vector/

# AOI별 노출자산 레이어. 경보 좌표가 어느 AOI 안인지로 고른다 — 산청 경보에 서울
# 건물 4만 건을 메모리에 올릴 이유가 없고, 두 AOI는 서로 700km 떨어져 겹치지 않는다.
# bbox는 EPSG:5179 미터, 값은 scripts/build_aoi_exposure_layers.py의 AOI 정의와 같은
# 행정경계(생비량면 / 서초구+강남구)에서 뽑았다.
AOI_LAYERS = {
    "sancheong": {
        "bbox_5179": (1_038_511.5, 1_694_245.2, 1_062_511.5, 1_718_245.2),
        "buildings": DATA_VECTOR_DIR / "aoi_buildings_sancheong_5179.geojson",
        "farmland": DATA_VECTOR_DIR / "aoi_farmland_sancheong_5179.geojson",
        # 클립에 쓴 범위 — coverage_warning이 위험영역과 교차시킨다. 산청은 행정경계가
        # 아니라 경보지점 반경으로 잘랐다(이유는 scripts/build_aoi_exposure_layers.py).
        "clip_center_5179": (1_050_511.5, 1_706_245.2),
        "clip_radius_m": 12_000,
    },
    "seoul": {
        "bbox_5179": (950_684.0, 1_939_337.0, 963_484.0, 1_951_281.0),
        "buildings": DATA_VECTOR_DIR / "aoi_buildings_seoul_5179.geojson",
        # 팜맵 산출물이 산청만 있다. 강남·서초는 농경지가 거의 없어 우선순위도 낮다.
        "farmland": None,
        "boundary_level": "sigungu",
        "boundary_codes": ("11220", "11230"),
    },
}
DEFAULT_AOI = "sancheong"  # §9 메인 데모

EMPTY_COLLECTION: dict[str, Any] = {"type": "FeatureCollection", "features": []}


def resolve_aoi(x_5179: float | None = None, y_5179: float | None = None) -> str:
    """좌표가 속한 AOI 키. 어느 AOI에도 안 들어가면 메인 데모(산청)로 둔다."""
    if x_5179 is None or y_5179 is None:
        return DEFAULT_AOI
    for key, cfg in AOI_LAYERS.items():
        minx, miny, maxx, maxy = cfg["bbox_5179"]
        if minx <= x_5179 <= maxx and miny <= y_5179 <= maxy:
            return key
    return DEFAULT_AOI


@lru_cache(maxsize=len(AOI_LAYERS))
def _aoi_polygon(aoi: str):
    """클립본을 자를 때 쓴 행정경계 폴리곤(EPSG:5179). 못 읽으면 None."""
    from shapely.geometry import shape
    from shapely.ops import unary_union

    cfg = AOI_LAYERS[aoi]
    if "clip_center_5179" in cfg:
        from shapely.geometry import Point

        cx, cy = cfg["clip_center_5179"]
        return Point(cx, cy).buffer(cfg["clip_radius_m"])
    path = DATA_VECTOR_DIR / f"adm_{cfg['boundary_level']}_5179.geojson"
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            collection = json.load(f)
    except (OSError, ValueError):
        return None
    parts = [shape(f["geometry"]) for f in collection["features"]
             if f["properties"].get("code") in cfg["boundary_codes"]]
    return unary_union(parts) if parts else None


def coverage_warning(aoi: str, risk_bounds_5179: tuple[float, float, float, float] | None) -> str | None:
    """위험영역이 AOI 클립본 밖으로 나가면 경고. 나가는 만큼 노출자산이 누락된다.

    bbox끼리 비교하면 안 된다 — 생비량면은 44km²인데 그 bbox는 100km²라, 실제로는
    경계를 크게 벗어나는 위험영역도 bbox 안에는 들어와 경고를 놓친다(실측 확인).
    그래서 클립에 쓴 행정경계 폴리곤과 직접 교차시킨다. 예: 데모 좌표 기준 6km×6km
    위험영역은 36km² 중 29.6km²(82%)만 생비량면 안이고 나머지 18%의 건물·농경지가
    계산에서 빠진다. 조용히 과소평가되면 안 되는 값이다.
    """
    if risk_bounds_5179 is None:
        return None
    polygon = _aoi_polygon(aoi)
    if polygon is None:
        return None

    from shapely.geometry import box

    risk = box(*risk_bounds_5179)
    if risk.area <= 0:
        return None
    covered = risk.intersection(polygon).area / risk.area
    if covered >= 0.999:
        return None
    return (
        f"위험영역의 {(1 - covered) * 100:.0f}%가 {aoi} 노출자산 클립본 밖이다 — 그 부분의 "
        "건물·농경지는 계산에서 빠지므로 노출 규모와 피해액은 하한으로 읽어야 한다. "
        "클립 범위를 넓히려면 scripts/build_aoi_exposure_layers.py의 AOI 정의를 조정할 것"
    )


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


@lru_cache(maxsize=len(AOI_LAYERS))
def _load_buildings(aoi: str) -> tuple[dict[str, Any], str | None]:
    return _load_collection(
        AOI_LAYERS[aoi]["buildings"],
        f"{aoi} 건축물",
        f"python scripts/build_aoi_exposure_layers.py --aoi {aoi}",
    )


@lru_cache(maxsize=len(AOI_LAYERS))
def _load_farmland(aoi: str) -> tuple[dict[str, Any], str | None]:
    path = AOI_LAYERS[aoi]["farmland"]
    if path is None:
        return dict(EMPTY_COLLECTION), (
            f"{aoi} 농경지 레이어 없음 — 노출 0으로 계산되지만 이는 '없음'이 아니라 '확인 불가'다"
        )
    return _load_collection(
        path, f"{aoi} 농경지", f"python scripts/build_farmland_geojson.py --region {aoi}"
    )


def building_footprints(aoi: str = DEFAULT_AOI) -> tuple[dict[str, Any], str | None]:
    """AOI 건축물 footprint(EPSG:5179)와 문제가 있었다면 그 경고."""
    return _load_buildings(aoi)


def farmland_parcels(aoi: str = DEFAULT_AOI) -> tuple[dict[str, Any], str | None]:
    """농경지 필지(EPSG:5179)와 문제가 있었다면 그 경고."""
    return _load_farmland(aoi)
