"""
노출자산 레이어 접근 계층 (§10 TODO "Module O가 이 값을 어디서 가져올지").

Module D의 입력 중 risk_polygons는 Module A/B가 만들지만, building_footprints_5179와
farmland_parcels_5179는 어느 모듈의 출력도 아니다 — Module O가 데이터에서 직접
읽어와야 한다. 그동안 빈 dict를 넘기고 있어서 D가 항상 "FeatureCollection이 아님"
경고와 함께 노출 0건을 냈다.

원본(data/precomputed/*.geojson)은 전부 .gitignore라 배포 서버에 없다 — 서울 건물
원본만 504MB다. 그래서 데모가 실제로 도는 AOI만 잘라 data/vector/에 커밋하고
여기서는 그 클립본만 읽는다. 재생성은 scripts/build_aoi_exposure_layers.py.

  aoi_buildings_sancheong_5179.ndjson    산청군 ∪ 반경12km   51,040건   22.6MB
  aoi_buildings_seoul_5179.geojson       강남·서초           41,814건   27.6MB
  aoi_farmland_sancheong_5179.ndjson     산청군 ∪ 반경12km   72,875필지 70.9MB (7,267.2ha)

산청은 **행정경계 ∪ 경보지점 반경**으로 자른다. 행정경계만 쓰면 경계 근처 경보에서
위험영역이 밖으로 새고(데모 좌표 기준 12%), 반경만 쓰면 군의 24%밖에 못 덮어서
고립마을·대피소를 군 전체로 넓혔을 때 나머지가 "건물 없음"이 된다. 자세한 근거는
scripts/build_aoi_exposure_layers.py의 AOI_DEFS 주석.

**산청 레이어는 .ndjson(한 줄에 feature 하나)이다.** 군 전체로 넓히면서 농경지가
70.9MB가 됐는데 json.load로 올리면 파싱 피크가 +339MB고, 배포 서버는 RAM 908MB에
기준선이 560MB라 그 자리에서 OOM이다(실제로 죽은 전력 있음). 한 줄씩 읽으며
위험영역에 닿는 것만 남기면 피크가 +0MB로 내려간다 — _stream_clipped 참조.
.geojson만 있는 환경은 종전 _load_clipped 경로로 폴백한다.

농경지 원본은 트랙②의 팜맵(농정원) 산출물이다(scripts/build_farmland_geojson.py,
산청군 73,040필지). 강남·서초는 팜맵 대상이 아니라 농경지 레이어가 없다.

레이어를 못 읽어도 예외를 던지지 않고 빈 FeatureCollection + 경고로 내려간다 —
"노출 0ha"와 "확인하지 못함"은 다르고, 그 차이가 화면에 보여야 한다(§7 불확실성 표기).
"""
from __future__ import annotations

import gc
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
        # 산청군 total_bounds ∪ 경보지점 반경 12km. resolve_aoi가 경보 좌표를
        # 어느 AOI로 보낼지 고르는 데 쓴다.
        "bbox_5179": (1_017_000.0, 1_691_000.0, 1_063_000.0, 1_732_000.0),
        "buildings": DATA_VECTOR_DIR / "aoi_buildings_sancheong_5179.geojson",
        "farmland": DATA_VECTOR_DIR / "aoi_farmland_sancheong_5179.geojson",
        # 클립에 쓴 범위 — coverage_warning이 위험영역과 교차시킨다.
        #
        # 2026-09-21: 예선 범위가 산청군 전체로 바뀌면서(고립마을·대피소) 클립도
        # **행정경계 ∪ 반경**으로 넓혔다. 반경만 쓰면 군의 24%밖에 못 덮고, 행정경계만
        # 쓰면 데모 좌표가 군 동쪽 경계에서 5.4km라 위험영역이 함양·진주 쪽으로 새어
        # 나간다. 둘 다 있어야 구멍이 안 생긴다 — 자세한 근거는 build_aoi_exposure_layers.py.
        "boundary_level": "sigungu",
        "boundary_codes": ("38570",),  # 경상남도 산청군
        "clip_center_5179": (1_050_511.5, 1_706_245.2),
        "clip_radius_m": 12_000,
        # Module B가 침수 폴리곤을 만들 때 쓰는 최대침수심 래스터(50m, EPSG:5179).
        # 트랙①의 SFINCS 산출물이며 ANUGA 대체본도 같은 디렉터리에 있다 — 두 엔진
        # 교차 IoU 0.775, 경호교 수위 RMSE는 SFINCS 1.42m / ANUGA 2.48m라 SFINCS를
        # 기본으로 둔다(module_v_validation/data/module_b_engine_comparison.json).
        "flood_depth_raster": REPO_ROOT / "module_b_flood" / "data" / "sfincs_maxdepth_50m.tif",
    },
    "seoul": {
        "bbox_5179": (950_684.0, 1_939_337.0, 963_484.0, 1_951_281.0),
        "buildings": DATA_VECTOR_DIR / "aoi_buildings_seoul_5179.geojson",
        # 팜맵 산출물이 산청만 있다. 강남·서초는 농경지가 거의 없어 우선순위도 낮다.
        "farmland": None,
        "boundary_level": "sigungu",
        "boundary_codes": ("11220", "11230"),
        # 수리모형을 산청 유역에만 구축했다 — 강남·서초는 침수심 래스터가 없다.
        "flood_depth_raster": None,
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
    parts = []

    # 행정경계와 반경을 **둘 다** 반영한다. 클립본을 만들 때 합집합으로 잘랐으므로
    # (scripts/build_aoi_exposure_layers.py의 AOI_DEFS), 여기서 한쪽만 보면 실제로는
    # 자료가 있는 영역을 "클립본 밖"이라고 경고하게 된다.
    if cfg.get("boundary_codes"):
        path = DATA_VECTOR_DIR / f"adm_{cfg['boundary_level']}_5179.geojson"
        if path.exists():
            try:
                with open(path, encoding="utf-8") as f:
                    collection = json.load(f)
                parts += [shape(f["geometry"]) for f in collection["features"]
                          if f["properties"].get("code") in cfg["boundary_codes"]]
            except (OSError, ValueError):
                pass

    if "clip_center_5179" in cfg:
        from shapely.geometry import Point

        cx, cy = cfg["clip_center_5179"]
        parts.append(Point(cx, cy).buffer(cfg["clip_radius_m"]))

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


def _feature_bounds(geometry: Any) -> tuple[float, float, float, float] | None:
    """지오메트리의 bbox. 좌표 중첩 깊이에 무관하게 [x, y] 쌍을 찾아 내려간다.

    요청마다 건물 18,032 + 농경지 23,288개를 전부 훑으므로 여기가 그대로 응답시간이
    된다. 예전엔 좌표 하나하나에 재귀 + isinstance를 돌려 호출이 69만 번 났고
    1.47초를 썼다(2026-09-20 프로파일). 실제 데이터는 거의 전부 Polygon/MultiPolygon
    이므로 그 두 경우만 리스트 컴프리헨션으로 바로 처리하고, 나머지 타입만 종전
    재귀로 떨어뜨린다 — 결과는 같고 이상한 형태가 와도 죽지 않는다.
    """
    if not isinstance(geometry, dict):
        return None
    coordinates = geometry.get("coordinates")
    kind = geometry.get("type")

    try:
        if kind == "Polygon":
            rings = coordinates
        elif kind == "MultiPolygon":
            rings = [ring for part in coordinates for ring in part]
        else:
            rings = None
        if rings:
            xs = [c[0] for ring in rings for c in ring]
            ys = [c[1] for ring in rings for c in ring]
            return min(xs), min(ys), max(xs), max(ys)
    except (TypeError, IndexError, ValueError):
        pass  # 형태가 예상과 다르면 아래 일반 경로로

    xs_any: list[float] = []
    ys_any: list[float] = []

    def walk(node: Any) -> None:
        if isinstance(node, (list, tuple)):
            if len(node) >= 2 and all(isinstance(v, (int, float)) for v in node[:2]):
                xs_any.append(float(node[0]))
                ys_any.append(float(node[1]))
                return
            for item in node:
                walk(item)

    walk(coordinates)
    if not xs_any:
        return None
    return min(xs_any), min(ys_any), max(xs_any), max(ys_any)


# 위험영역 격자 한 칸의 크기(m). 작을수록 더 촘촘히 걸러내지만 칸 수가 제곱으로
# 늘어난다. 200m에서 산청 데모 기준 1,471칸(58.8km²)으로, 격자를 만드는 비용은
# 무시할 만하면서 걸러내는 효과는 거의 최대치였다(2026-09-20 실측).
RISK_CELL_M = 200.0

# 격자 칸 수 상한. 칸 수는 bbox **면적**에 비례하므로 좌표가 하나라도 깨지면
# (5179 미터 자리에 0이나 위경도가 섞이는 경우) 한 폴리곤이 4,470만 칸을 요구한다 —
# 그 루프가 도는 동안 서버는 수 GB를 먹고 통째로 멈춘다. RAM 908MB짜리 배포 서버에서
# 이건 곧 정지다. 산청 AOI 전체가 452km²(≈11,300칸)이고 실제 데모는 1,471칸을 쓰므로
# 50,000칸(2,000km²)이면 정상 데이터에는 절대 안 걸린다.
MAX_RISK_CELLS = 50_000


def risk_cells(geometries: list[dict[str, Any]]) -> set[tuple[int, int]] | None:
    """위험 지오메트리들이 실제로 덮는 격자 칸 집합.

    **왜 bbox 하나로는 부족한가**: 침수범위(Module B)는 하천을 따라 길게 뻗은
    547개 폴리곤이고 산사태(Module A)는 그 반대편 산비탈에 있다. 둘을 감싸는
    bbox 하나를 쓰면 363km²가 되는데, 실제 위험영역을 다 합쳐도 58km²다 —
    그 사이의 빈 들판까지 전부 "위험영역 근처"로 잡혀서 Module D가 건물 8,026동·
    농경지 13,037필지를 받아 기하 연산을 돌리고 있었다. 격자로 바꾸면 500동·
    724필지(6%)로 줄고, 걸러낸 건 애초에 위험영역과 겹칠 수 없는 것들뿐이다.

    **누락되지 않는 이유**: 폴리곤과 feature가 실제로 겹치면 두 bbox가 겹치고,
    겹치는 bbox는 반드시 같은 칸을 공유한다. 즉 이 판정은 실제 교차의 상위집합이라
    Module D의 결과는 바뀌지 않는다(격자는 조금 넉넉하게 잡을 뿐이다).
    """
    cells: set[tuple[int, int]] = set()
    for geometry in geometries:
        for box in _subgeometry_bounds(geometry):
            x0, y0, x1, y1 = box
            gx0, gx1 = int(x0 // RISK_CELL_M), int(x1 // RISK_CELL_M)
            gy0, gy1 = int(y0 // RISK_CELL_M), int(y1 // RISK_CELL_M)
            # 세기 전에 칸 수를 먼저 계산한다 — 만들면서 세면 이미 늦는다.
            if (gx1 - gx0 + 1) * (gy1 - gy0 + 1) + len(cells) > MAX_RISK_CELLS:
                # 격자를 포기하고 종전 bbox 필터로 돌아간다. 느려질 뿐 결과는 같다 —
                # 여기서 무리하게 만들다가 서버가 멈추는 쪽이 비교할 수 없이 나쁘다.
                return None
            for gx in range(gx0, gx1 + 1):
                for gy in range(gy0, gy1 + 1):
                    cells.add((gx, gy))
    return cells or None


def _subgeometry_bounds(geometry: Any) -> list[tuple[float, float, float, float]]:
    """폴리곤 하나하나의 bbox. 전체를 감싸는 bbox 하나가 아니다.

    Module B는 위험영역을 FeatureCollection으로 주고 Module A는 MultiPolygon으로
    주므로 둘 다 받아서 개별 폴리곤까지 내려간다. 점 좌표({x_5179, y_5179})는
    면적이 없어 격자에 넣지 않는다 — 그건 호출부가 버퍼링해서 폴리곤으로 만든다.
    """
    if not isinstance(geometry, dict):
        return []
    kind = geometry.get("type")
    if kind == "FeatureCollection":
        out: list[tuple[float, float, float, float]] = []
        for feature in geometry.get("features") or []:
            out += _subgeometry_bounds((feature or {}).get("geometry"))
        return out
    if kind == "Feature":
        return _subgeometry_bounds(geometry.get("geometry"))

    coordinates = geometry.get("coordinates")
    parts: list[Any]
    if kind == "MultiPolygon":
        parts = list(coordinates or [])
    elif kind == "Polygon":
        parts = [coordinates or []]
    else:
        box = _feature_bounds(geometry)
        return [box] if box else []

    out = []
    for part in parts:
        box = _feature_bounds({"coordinates": part})
        if box:
            out.append(box)
    return out


def _clip_to_bounds(collection: dict[str, Any],
                    bounds: tuple[float, float, float, float] | None,
                    cells: set[tuple[int, int]] | None = None) -> dict[str, Any]:
    """위험영역에 닿지 않는 feature를 버린다.

    bbox가 안 겹치는 feature는 위험 폴리곤과도 절대 안 겹치므로 Module D의 결과는
    그대로다. 목적은 메모리와 시간이다 — 산청 농경지 23,288필지를 통째로 들고 있으면
    105MB고, 배포 서버(RAM 908MB)가 OOM으로 uvicorn을 죽이던 주원인이었다.

    cells를 주면 전체 bbox 대신(정확히는 그와 함께) 격자로 거른다. 위험영역이 서로
    멀리 떨어져 있을 때 bbox 하나는 사실상 안 거르기 때문이다 — risk_cells 참고.
    """
    if bounds is None and cells is None:
        return collection
    min_x, min_y, max_x, max_y = bounds if bounds else (-1e18, -1e18, 1e18, 1e18)
    kept = []
    for feature in collection.get("features") or []:
        box = _feature_bounds((feature or {}).get("geometry"))
        if box is None:
            kept.append(feature)  # 판단 불가면 버리지 않는다 — 누락보다 낫다
            continue
        if box[2] < min_x or box[0] > max_x or box[3] < min_y or box[1] > max_y:
            continue
        if cells is not None and not _touches_cells(box, cells):
            continue
        kept.append(feature)
    return {**collection, "features": kept}


def _touches_cells(box: tuple[float, float, float, float],
                   cells: set[tuple[int, int]]) -> bool:
    x0, y0, x1, y1 = box
    for gx in range(int(x0 // RISK_CELL_M), int(x1 // RISK_CELL_M) + 1):
        for gy in range(int(y0 // RISK_CELL_M), int(y1 // RISK_CELL_M) + 1):
            if (gx, gy) in cells:
                return True
    return False


def _stream_clipped(path: Path, label: str, regenerate_hint: str,
                    bounds: tuple[float, float, float, float] | None,
                    cells: set[tuple[int, int]] | None
                    ) -> tuple[dict[str, Any], str | None]:
    """.ndjson을 한 줄씩 읽으면서 위험영역에 닿는 것만 남긴다.

    **왜 통째로 안 읽나**: 산청이 군 전체로 넓어지면서 농경지가 72,875필지 70.8MB가
    됐는데, json.load로 올리면 파싱 피크가 +339MB다(2026-09-21 실측). 배포 서버는
    RAM 908MB에 기준선이 이미 560MB라 그 자리에서 OOM이고, 실제로 죽은 전력이 있다.
    한 줄이 feature 하나라서 읽는 즉시 판정하고 버리면, 피크가 파일 크기가 아니라
    **남긴 것**의 크기로 내려간다.

    한 줄이 깨져 있어도 그 줄만 버리고 계속한다 — 파일 하나 때문에 노출자산 전체를
    "확인 불가"로 떨어뜨리는 것보다 낫다. 대신 몇 줄을 버렸는지 경고로 올린다.
    """
    if not path.exists():
        return dict(EMPTY_COLLECTION), (
            f"{label} 레이어 없음({path.name}) — 노출 0으로 계산되지만 이는 '없음'이 아니라 "
            f"'확인 불가'다. 재생성: {regenerate_hint}"
        )

    min_x, min_y, max_x, max_y = bounds if bounds else (-1e18, -1e18, 1e18, 1e18)
    kept: list[dict[str, Any]] = []
    broken = 0
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    feature = json.loads(line)
                except ValueError:
                    broken += 1
                    continue
                box = _feature_bounds((feature or {}).get("geometry"))
                if box is None:
                    kept.append(feature)  # 판단 불가면 버리지 않는다 — 누락보다 낫다
                    continue
                if box[2] < min_x or box[0] > max_x or box[3] < min_y or box[1] > max_y:
                    continue
                if cells is not None and not _touches_cells(box, cells):
                    continue
                kept.append(feature)
    except OSError as exc:
        return dict(EMPTY_COLLECTION), (
            f"{label} 레이어 로드 실패({type(exc).__name__}) — 노출 0으로 진행(확인 불가)"
        )

    warning = None
    if broken:
        warning = f"{label} 레이어에서 깨진 줄 {broken}개를 건너뜀 — 그만큼 노출이 과소 계상됐을 수 있다"
    return {"type": "FeatureCollection", "features": kept}, warning


def _load_clipped(loader, aoi: str,
                  bounds: tuple[float, float, float, float] | None,
                  cells: set[tuple[int, int]] | None = None) -> tuple[dict[str, Any], str | None]:
    """전체를 읽어 bbox로 자른 뒤 원본을 즉시 버린다(.geojson 폴백 경로).

    .ndjson이 있으면 위의 _stream_clipped가 쓰이고 여기는 안 온다. 옛 .geojson만
    남은 환경을 위해 남겨 둔다 — 전체 컬렉션을 캐시하지 않는 이유는 그대로다.
    """
    collection, warning = loader(aoi)
    clipped = _clip_to_bounds(collection, bounds, cells)
    del collection
    gc.collect()
    return clipped, warning


def _read_buildings(aoi: str) -> tuple[dict[str, Any], str | None]:
    return _load_collection(
        AOI_LAYERS[aoi]["buildings"],
        f"{aoi} 건축물",
        f"python scripts/build_aoi_exposure_layers.py --aoi {aoi}",
    )


def _read_farmland(aoi: str) -> tuple[dict[str, Any], str | None]:
    path = AOI_LAYERS[aoi]["farmland"]
    if path is None:
        return dict(EMPTY_COLLECTION), (
            f"{aoi} 농경지 레이어 없음 — 노출 0으로 계산되지만 이는 '없음'이 아니라 '확인 불가'다"
        )
    return _load_collection(
        path, f"{aoi} 농경지", f"python scripts/build_farmland_geojson.py --region {aoi}"
    )


def _ndjson_path(path: Path) -> Path:
    """같은 이름의 .ndjson. 있으면 스트리밍으로 읽는다."""
    return path.with_suffix(".ndjson")


def building_footprints(aoi: str = DEFAULT_AOI,
                        bounds_5179: tuple[float, float, float, float] | None = None,
                        cells: set[tuple[int, int]] | None = None
                        ) -> tuple[dict[str, Any], str | None]:
    """AOI 건축물 footprint(EPSG:5179)와 문제가 있었다면 그 경고.

    bounds_5179/cells를 주면 위험영역에 닿지 않는 건물은 빼고 돌려준다
    (결과 동일, 메모리·시간 절감 — risk_cells 참고).
    """
    path = AOI_LAYERS[aoi]["buildings"]
    hint = f"python scripts/build_aoi_exposure_layers.py --aoi {aoi}"
    ndjson = _ndjson_path(path)
    if ndjson.exists():
        return _stream_clipped(ndjson, f"{aoi} 건축물", hint, bounds_5179, cells)
    return _load_clipped(_read_buildings, aoi, bounds_5179, cells)


def farmland_parcels(aoi: str = DEFAULT_AOI,
                     bounds_5179: tuple[float, float, float, float] | None = None,
                     cells: set[tuple[int, int]] | None = None
                     ) -> tuple[dict[str, Any], str | None]:
    """농경지 필지(EPSG:5179)와 문제가 있었다면 그 경고. 인자는 위와 같다."""
    path = AOI_LAYERS[aoi]["farmland"]
    if path is None:
        return dict(EMPTY_COLLECTION), (
            f"{aoi} 농경지 레이어 없음 — 노출 0으로 계산되지만 이는 '없음'이 아니라 '확인 불가'다"
        )
    hint = f"python scripts/build_aoi_exposure_layers.py --aoi {aoi}"
    ndjson = _ndjson_path(path)
    if ndjson.exists():
        return _stream_clipped(ndjson, f"{aoi} 농경지", hint, bounds_5179, cells)
    return _load_clipped(_read_farmland, aoi, bounds_5179, cells)


def flood_depth_raster(aoi: str = DEFAULT_AOI) -> tuple[str | None, str | None]:
    """Module B에 넘길 최대침수심 래스터 경로와, 없다면 그 경고.

    건물·농경지와 달리 Module B는 파일을 직접 읽으므로 경로만 돌려준다.
    래스터가 없으면 Module B가 빈 FeatureCollection + 경고로 내려가고,
    지도에는 침수 3D 볼륨이 그려지지 않는다 — "침수 없음"이 아니라
    "계산하지 못함"이므로 그 구분이 경고로 올라가야 한다.
    """
    path = AOI_LAYERS.get(aoi, {}).get("flood_depth_raster")
    if path is None:
        return None, (f"{aoi} 침수심 래스터 없음 — 수리모형 미구축 지역이라 "
                      "침수범위를 산출하지 않는다(침수 없음과 다름)")
    if not path.exists():
        return None, (f"{aoi} 침수심 래스터를 찾을 수 없음({path.name}) → 침수범위 미산출. "
                      "재생성: python module_b_flood/scripts/34_sfincs_run_validate.py")
    return str(path), None
