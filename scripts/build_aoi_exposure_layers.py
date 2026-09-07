"""
데모 AOI 안의 건축물 footprint를 EPSG:5179로 잘라 Module D 입력으로 커밋하는
1회성 배치 스크립트.

왜 별도 파일로 커밋하는가:
Module O가 Module D에 넘겨야 할 building_footprints_5179를 그동안 빈 dict로
비워두고 있었다(§10 "데이터 접근 계층" TODO). 원본
data/precomputed/{region}_buildings.geojson은 .gitignore라 배포 서버에 없고,
서울 원본은 504MB라 그대로 커밋할 수도 없다. 그래서 데모가 실제로 도는 범위만
잘라 커밋한다.

AOI 2개 (2026-09-05 확정):
    sancheong  산청군 생비량면 1개 읍면동 (44km²)   — §9 메인 데모의 trigger_location이
               속한 행정동. 재해연쇄 서사가 실제로 도는 곳이라 동 단위까지 좁혔다.
    seoul      강남구 + 서초구 (84km²)              — 전국 확장성 보조 데모. 시 전역
               (605km², bbox에 경기 18개 시군구까지 걸림)에서 좁힌 결과다.

좌표계: 원본은 EPSG:4326이고 Module D 계약은 5179 미터를 요구하므로 여기서
변환해 저장한다(§4.1 — 재투영은 UI 출력 직전에만 하되, 이건 UI가 아니라
모듈 입력이라 5179로 맞추는 게 맞다).

농경지(farmland_parcels_5179)는 이 스크립트가 만들지 않는다 —
scripts/build_farmland_geojson.py(트랙②)가 담당한다.

실행: python scripts/build_aoi_exposure_layers.py [--aoi sancheong seoul]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pyproj import Transformer
from shapely.geometry import mapping, shape
from shapely.ops import unary_union
from shapely.prepared import prep

REPO_ROOT = Path(__file__).resolve().parent.parent
VECTOR_DIR = REPO_ROOT / "data" / "vector"
PRECOMPUTED_DIR = REPO_ROOT / "data" / "precomputed"
TILE_CACHE_DIR = PRECOMPUTED_DIR / "_tile_cache"

_TO_5179 = Transformer.from_crs("EPSG:4326", "EPSG:5179", always_xy=True)

# AOI별 경계 정의. level은 어느 행정경계 파일에서 코드를 찾을지, codes는 그 코드다.
# 클립 범위는 행정경계가 아니라 경보 지점 기준 반경으로 잡는다.
#
# 처음에는 생비량면(44km²)으로 잘랐는데 6km×6km 위험영역의 18%가 경계 밖이라
# 노출자산이 그만큼 조용히 빠졌다. 산청군 전체(790km², 92MB)로 넓혀봤지만 12%가
# 여전히 밖이었다 — 데모 좌표가 군 동쪽 경계에서 5.4km 지점이라 위험영역이 함양·진주
# 쪽으로 넘어가기 때문이다. 행정경계로 자르는 한 경계 근처 경보에서는 누락이 남는다.
#
# 우리가 답해야 할 질문은 "어디까지가 산청군인가"가 아니라 "위험영역을 담을 만큼
# 넓은가"이므로, 경보 지점 반경으로 자른다. 반경 12km면 6km 위험영역을 100% 담고
# 인접 시군 건물도 자연히 들어오며, 군 전체의 37%(18,033건) 크기다.
AOI_DEFS = {
    "sancheong": {"center_5179": (1_050_511.5, 1_706_245.2), "radius_m": 12_000},
    # 강남·서초는 두 구를 함께 보여주는 게 목적이라 행정경계 그대로 쓴다.
    "seoul": {"level": "sigungu", "codes": ("11220", "11230")},
}

# 농경지 원본(트랙②의 scripts/build_farmland_geojson.py 산출물, 이미 EPSG:5179).
# 건물과 달리 재투영이 필요 없다. 산청만 있다 — 강남·서초는 팜맵 대상이 아니다.
FARMLAND_SOURCES = {
    "sancheong": PRECOMPUTED_DIR / "sancheong_farmland_5179.geojson",
}
# 팜맵 산출물의 실제 속성(2026-09-05 확인): CLSF_NM(지목 밭/논/과수/시설),
# AREA(신고면적 ㎡), PNU(필지고유번호 19자리), geometry_area_m2(지오메트리 실측면적).
# Module D는 면적을 지오메트리에서 직접 재므로 AREA는 참고값이고, PNU는 다른
# 필지 기반 데이터와 붙일 때 필요해 남긴다.
FARMLAND_KEPT_PROPERTIES = ("CLSF_NM", "AREA", "PNU")

# 원본(VWorld LT_C_SPBD)에서 실어 나를 속성만 남긴다 — 나머지는 Module D가 안 쓴다.
# bd_mgt_sn은 건축물대장 주용도를 붙일 조인키라 반드시 유지한다
# (scripts/fetch_building_use_types.py, module_d_exposure_overlay/use_types.py).
KEPT_PROPERTIES = ("bd_mgt_sn", "buld_nm", "gro_flo_co", "height_m", "sigungu", "gu")

# 좌표 소수점 자릿수. EPSG:5179는 미터라 소수점은 그대로 밀리미터 이하 정밀도이고,
# 원본이 들고 있는 소수점 10자리는 파일 크기만 키운다. 다만 무작정 줄이면 작은
# 폴리곤이 자기교차로 무효가 되므로(실측: 건물을 10cm로 반올림하면 3,000건 중 2건이
# 무효가 됐다 — 원본은 0건) 레이어별로 안전한 선까지만 줄인다.
#
#   건물   3자리(1mm)  중앙값 56m². 2자리면 무효는 안 생기지만 단일 최대오차가 9.3%
#                      까지 벌어진다. 3자리에서 0.80%.
#   농경지 2자리(1cm)  중앙값 598m²로 훨씬 커서 여유가 있다. 무효 0건, 최대오차 0.24%.
#
# 아래 build 함수가 반올림 뒤 유효성을 실제로 검사하고, 무효가 하나라도 생기면
# 멈춘다 — 이 값들이 다른 지역·다른 원본에서도 안전하다고 가정하지 않기 위해서다.
COORD_DECIMALS = {"buildings": 3, "farmland": 2}


def _round_coords(node, nd: int):
    """좌표만 재귀적으로 반올림한다(속성은 건드리지 않는다)."""
    if isinstance(node, float):
        return round(node, nd)
    if isinstance(node, list):
        return [_round_coords(v, nd) for v in node]
    return node


def _rounded_geometry(geom, layer: str, label: str) -> dict:
    """mapping(geom)을 레이어별 정밀도로 반올림하되, 그 때문에 무효가 되면 멈춘다.

    파일 크기를 줄이자고 지오메트리를 망가뜨리면 Module D가 make_valid로 복구하며
    fallback_tier를 올리고, 그러면 화면의 "정상" Provenance 배지가 사라진다.
    """
    from shapely.geometry import shape as _shape

    raw = mapping(geom)
    nd = COORD_DECIMALS[layer]
    raw = {**raw, "coordinates": _round_coords(raw["coordinates"], nd)}
    if not _shape(raw).is_valid:
        raise SystemExit(
            f"{label}: 좌표를 소수점 {nd}자리로 반올림하니 지오메트리가 무효가 됐다. "
            f"COORD_DECIMALS['{layer}']를 늘릴 것"
        )
    return raw


def load_aoi(region: str):
    """AOI 폴리곤(EPSG:5179)과 표시용 이름을 돌려준다.

    center_5179+radius_m가 있으면 그 원, 없으면 행정경계 코드로 찾는다.
    """
    cfg = AOI_DEFS[region]
    if "center_5179" in cfg:
        from shapely.geometry import Point

        cx, cy = cfg["center_5179"]
        radius = cfg["radius_m"]
        return Point(cx, cy).buffer(radius), f"경보지점 반경 {radius / 1000:.0f}km"

    path = VECTOR_DIR / f"adm_{cfg['level']}_5179.geojson"
    with open(path, encoding="utf-8") as f:
        collection = json.load(f)
    matched = [f for f in collection["features"] if f["properties"].get("code") in cfg["codes"]]
    if len(matched) != len(cfg["codes"]):
        found = [f["properties"].get("code") for f in matched]
        raise SystemExit(f"{region}: 코드 {cfg['codes']} 중 {found}만 {path.name}에서 찾음")
    geom = unary_union([shape(f["geometry"]) for f in matched])
    names = ", ".join(f["properties"].get("full_nm") or f["properties"].get("name", "") for f in matched)
    return geom, names


def iter_source_features(region: str):
    """원본 건물 feature를 하나씩 흘려보낸다(EPSG:4326).

    1순위는 fetch_aoi_data.py의 타일 캐시다 — 타일 하나씩만 메모리에 올리므로 서울
    규모(652,026건 / 504MB)에서도 안전하다. 병합본을 json.load하면 MemoryError가 난다.
    타일 캐시가 없으면 병합본으로 폴백한다. 중복 판정은 fetch_aoi_data와 같은 규칙
    (feature id, 없으면 properties 직렬화)을 쓴다.
    """
    tile_dir = TILE_CACHE_DIR / region / "buildings"
    seen: set[str] = set()

    if tile_dir.is_dir():
        for tile in sorted(tile_dir.glob("tile_*.json")):
            for feature in json.loads(tile.read_text(encoding="utf-8")):
                key = feature.get("id") or json.dumps(feature.get("properties", {}), sort_keys=True)
                if key in seen:
                    continue
                seen.add(key)
                yield feature
        return

    # fetch_aoi_data.py가 2026-09-05부터 _4326을 파일명에 넣는다. 기존 머신의 옛
    # 이름도 그대로 받아준다.
    merged = next(
        (PRECOMPUTED_DIR / n for n in (f"{region}_buildings_4326.geojson", f"{region}_buildings.geojson")
         if (PRECOMPUTED_DIR / n).exists()),
        PRECOMPUTED_DIR / f"{region}_buildings_4326.geojson",
    )
    if not merged.exists():
        print(f"  [건너뜀] {tile_dir} 와 {merged} 둘 다 없음 — "
              f"scripts/fetch_aoi_data.py로 먼저 생성", file=sys.stderr)
        return
    with open(merged, encoding="utf-8") as f:
        yield from json.load(f)["features"]


def build(region: str) -> None:
    aoi_geom, aoi_name = load_aoi(region)
    prepared = prep(aoi_geom)
    print(f"[{region}] AOI: {aoi_name} ({aoi_geom.area / 1e6:.0f}km²)")

    kept: list[dict] = []
    scanned = skipped_invalid = 0
    for feature in iter_source_features(region):
        scanned += 1
        try:
            geom_5179 = shape(feature["geometry"])
            geom_5179 = _reproject(geom_5179)
        except Exception:  # noqa: BLE001 - 깨진 지오메트리는 버리되 세어둔다
            skipped_invalid += 1
            continue
        # 폴리곤 전체가 아니라 대표점으로 판정한다 — 경계에 걸친 건물을 인접 AOI가
        # 중복으로 갖지 않게 하고, 큰 폴리곤과의 교차 연산도 아낀다.
        if not prepared.contains(geom_5179.representative_point()):
            continue
        props = feature.get("properties") or {}
        kept.append({
            "type": "Feature",
            "geometry": _rounded_geometry(geom_5179, "buildings", f"건물 {props.get('bd_mgt_sn')}"),
            "properties": {k: props.get(k) for k in KEPT_PROPERTIES if k in props},
        })

    if not scanned:
        return

    out_path = VECTOR_DIR / f"aoi_buildings_{region}_5179.geojson"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": kept}, f, ensure_ascii=False, separators=(",", ":"))

    size_mb = out_path.stat().st_size / 1e6
    print(f"[{region}] 원본 {scanned:,}건 → AOI 내부 {len(kept):,}건"
          + (f" (지오메트리 오류 {skipped_invalid:,}건 제외)" if skipped_invalid else ""))
    print(f"[{region}] 저장: {out_path.relative_to(REPO_ROOT)} ({size_mb:.1f}MB, EPSG:5179)")


def _reproject(geom):
    """4326 → 5179. shapely.ops.transform은 좌표마다 파이썬 호출이라 느려서 직접 돈다."""
    from shapely.ops import transform as shapely_transform

    return shapely_transform(_TO_5179.transform, geom)


def build_farmland(region: str) -> None:
    """농경지 원본을 AOI로 자른다. 이미 EPSG:5179라 재투영하지 않는다."""
    source = FARMLAND_SOURCES.get(region)
    if source is None:
        print(f"[{region}] 농경지 원본 정의 없음 — 건너뜀")
        return
    if not source.exists():
        print(f"[{region}] 농경지 원본 없음({source.name}) — "
              f"scripts/build_farmland_geojson.py --region {region}로 생성", file=sys.stderr)
        return

    aoi_geom, aoi_name = load_aoi(region)
    prepared = prep(aoi_geom)
    with open(source, encoding="utf-8") as f:
        features = json.load(f)["features"]

    kept: list[dict] = []
    area_m2 = 0.0
    for feature in features:
        try:
            geom = shape(feature["geometry"])
        except Exception:  # noqa: BLE001
            continue
        if not prepared.contains(geom.representative_point()):
            continue
        props = feature.get("properties") or {}
        kept.append({
            "type": "Feature",
            # 이미 5179라 재투영은 없고 좌표 정밀도만 줄인다.
            "geometry": _rounded_geometry(geom, "farmland", f"농경지 {props.get('PNU')}"),
            "properties": {k: props.get(k) for k in FARMLAND_KEPT_PROPERTIES if k in props},
        })
        area_m2 += geom.area

    out_path = VECTOR_DIR / f"aoi_farmland_{region}_5179.geojson"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": kept}, f, ensure_ascii=False, separators=(",", ":"))
    size_mb = out_path.stat().st_size / 1e6
    print(f"[{region}] 농경지 원본 {len(features):,}필지 → AOI 내부 {len(kept):,}필지 "
          f"({area_m2 / 10_000:.1f}ha)")
    print(f"[{region}] 저장: {out_path.relative_to(REPO_ROOT)} ({size_mb:.1f}MB, EPSG:5179)")


def main() -> None:
    parser = argparse.ArgumentParser(description="AOI 노출자산 레이어(건축물·농경지) 생성")
    parser.add_argument("--aoi", nargs="*", default=list(AOI_DEFS), choices=list(AOI_DEFS))
    parser.add_argument("--layer", nargs="*", default=["buildings", "farmland"],
                        choices=["buildings", "farmland"])
    args = parser.parse_args()
    for region in args.aoi:
        if "buildings" in args.layer:
            build(region)
        if "farmland" in args.layer:
            build_farmland(region)


if __name__ == "__main__":
    main()
