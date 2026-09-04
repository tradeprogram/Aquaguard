"""팜맵(농림축산식품 공간정보) SHP를 Module D의 farmland_parcels_5179 입력으로 변환한다.

Module D의 exposed_farmland_ha는 지금까지 목업 폴리곤으로만 검증됐다. 이 스크립트가
농정원 팜맵 원본을 D가 그대로 받아먹을 수 있는 GeoJSON(EPSG:5179)으로 바꾼다.

확인된 원본 스펙 (2026-09-05, 나정우):
    좌표계   EPSG:5179 그대로 - 재투영하지 않는다(§4.1: 내부 교환은 전부 5179)
    인코딩   EUC-KR (속성 문자열)
    폴리곤   산청군 73,935건
    필드     CLSF_NM(논/밭/과수/시설/비경지), AREA(㎡), PNU
    제외     비경지 895건 - 경작지가 아니므로 농경지 침수 피해 산정 대상이 아니다

준비:
    팜맵 zip에서 산청군 폴더(2025_경상남도_산청군, SHP 5종)를
    data/precomputed/farmmap/ 아래에 둔다. 이 디렉토리는 .gitignore 대상이다.

실행:
    python scripts/build_farmland_geojson.py [--region sancheong]

산출물:
    data/precomputed/{region}_farmland_5179.geojson       Module D 입력
    data/precomputed/{region}_farmland_5179.meta.json     출처·필터·집계
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import geopandas as gpd

REPO_ROOT = Path(__file__).resolve().parent.parent
PRECOMPUTED_DIR = REPO_ROOT / "data" / "precomputed"
FARMMAP_DIR = PRECOMPUTED_DIR / "farmmap"

SOURCE_ENCODING = "euc-kr"
SOURCE_EPSG = 5179

CLASS_FIELD = "CLSF_NM"
AREA_FIELD = "AREA"
PNU_FIELD = "PNU"
KEEP_FIELDS = (CLASS_FIELD, AREA_FIELD, PNU_FIELD)

# 경작지가 아니라 농경지 침수 피해 산정 대상이 아니다.
EXCLUDED_CLASSES = ("비경지",)

SQUARE_METERS_PER_HECTARE = 10_000.0

PROVENANCE = {
    "agency": "농림수산식품교육문화정보원(농정원)",
    "product": "팜맵(FarmMap) 경상남도",
    "published": "2025-12-31",
    "imagery_captured": "2024-12-31",
    "crs": f"EPSG:{SOURCE_EPSG}",
    "encoding": SOURCE_ENCODING,
}

REGIONS = {"sancheong": "산청"}


def find_shapefile(region: str) -> Path:
    """farmmap/ 아래에서 해당 시군 SHP를 찾는다."""
    if not FARMMAP_DIR.is_dir():
        raise SystemExit(
            f"{FARMMAP_DIR} 가 없다. 팜맵 zip에서 시군 폴더를 이 아래에 두고 다시 실행할 것."
        )
    needle = REGIONS[region]
    candidates = [p for p in FARMMAP_DIR.rglob("*.shp") if needle in str(p)]
    if not candidates:
        candidates = sorted(FARMMAP_DIR.rglob("*.shp"))
    if not candidates:
        raise SystemExit(f"{FARMMAP_DIR} 아래에서 .shp를 찾지 못했다.")
    if len(candidates) > 1:
        print(f"  [주의] .shp가 여러 개다. 첫 번째를 쓴다: {[p.name for p in candidates]}",
              file=sys.stderr)
    return candidates[0]


def load(path: Path) -> gpd.GeoDataFrame:
    gdf = gpd.read_file(path, encoding=SOURCE_ENCODING)
    if gdf.crs is None:
        # .prj가 없거나 못 읽은 경우 - 원본이 5179라는 확인된 사실에 기대되,
        # 재투영이 아니라 좌표계 '선언'만 한다(좌표값은 건드리지 않는다).
        print(f"  [주의] CRS 정보가 없어 EPSG:{SOURCE_EPSG}로 선언한다(재투영 아님).",
              file=sys.stderr)
        gdf = gdf.set_crs(SOURCE_EPSG, allow_override=True)
    elif gdf.crs.to_epsg() != SOURCE_EPSG:
        raise SystemExit(
            f"원본 좌표계가 EPSG:{gdf.crs.to_epsg()}다. 5179를 기대했다 - "
            f"§4.1에 따라 내부 교환은 5179여야 하므로 변환 규칙을 먼저 정할 것."
        )
    return gdf


def build(region: str) -> None:
    path = find_shapefile(region)
    print(f"읽는 중: {path}")
    gdf = load(path)
    total = len(gdf)
    print(f"  전체 {total:,} 폴리곤, 필드: {list(gdf.columns)}")

    missing = [f for f in KEEP_FIELDS if f not in gdf.columns]
    if missing:
        raise SystemExit(f"기대한 필드가 없다: {missing}")

    class_counts_before = gdf[CLASS_FIELD].value_counts().to_dict()
    kept = gdf[~gdf[CLASS_FIELD].isin(EXCLUDED_CLASSES)].copy()
    excluded = total - len(kept)
    print(f"  제외({', '.join(EXCLUDED_CLASSES)}): {excluded:,}건 -> 남은 {len(kept):,}건")

    kept["geometry"] = kept.geometry.make_valid()
    kept = kept[~kept.geometry.is_empty & kept.geometry.notna()]
    invalid_dropped = len(gdf) - excluded - len(kept)
    if invalid_dropped:
        print(f"  복구 불가능한 지오메트리 {invalid_dropped:,}건 제외")

    # AREA는 원본 제공값, geometry_area_m2는 실제 폴리곤 면적 - 둘을 비교할 수 있게 둘 다 남긴다.
    kept["geometry_area_m2"] = kept.geometry.area
    out = kept[[*KEEP_FIELDS, "geometry_area_m2", "geometry"]]

    out_path = PRECOMPUTED_DIR / f"{region}_farmland_5179.geojson"
    PRECOMPUTED_DIR.mkdir(parents=True, exist_ok=True)
    # to_file 대신 직접 쓴다 - GeoJSON 드라이버가 좌표계를 4326으로 강제하는 것을 피한다.
    out_path.write_text(out.to_json(), encoding="utf-8")

    declared_ha = float(out[AREA_FIELD].astype(float).sum()) / SQUARE_METERS_PER_HECTARE
    geometry_ha = float(out["geometry_area_m2"].sum()) / SQUARE_METERS_PER_HECTARE
    class_counts = out[CLASS_FIELD].value_counts().to_dict()

    meta = {
        "generated_by": "scripts/build_farmland_geojson.py",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "region": region,
        "source": PROVENANCE,
        "source_file": str(path.relative_to(REPO_ROOT)) if path.is_relative_to(REPO_ROOT) else str(path),
        "crs": f"EPSG:{SOURCE_EPSG}",
        "reprojected": False,
        "filters": {"excluded_classes": list(EXCLUDED_CLASSES), "excluded_count": excluded},
        "counts": {
            "source_polygons": total,
            "output_polygons": len(out),
            "class_counts_before": class_counts_before,
            "class_counts_after": class_counts,
        },
        "area_ha": {
            "declared_AREA_field": round(declared_ha, 2),
            "geometry_computed": round(geometry_ha, 2),
        },
        "consumer": "module_d_exposure_overlay - farmland_parcels_5179 입력",
    }
    meta_path = PRECOMPUTED_DIR / f"{region}_farmland_5179.meta.json"
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n저장: {out_path} ({out_path.stat().st_size / 1048576:.1f} MB)")
    print(f"  메타: {meta_path}")
    print(f"  폴리곤 {len(out):,}건 / 원본 AREA 합 {declared_ha:,.1f} ha / "
          f"지오메트리 면적 합 {geometry_ha:,.1f} ha")
    print(f"  분류별: {class_counts}")


def main() -> None:
    parser = argparse.ArgumentParser(description="팜맵 SHP -> Module D 농경지 GeoJSON(5179)")
    parser.add_argument("--region", default="sancheong", choices=list(REGIONS))
    build(parser.parse_args().region)


if __name__ == "__main__":
    main()
