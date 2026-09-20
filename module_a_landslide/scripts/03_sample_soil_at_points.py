"""
03_sample_soil_at_points.py  (AquaGuard 트랙① / Module A — A-1 소일 샘플러 + 검증셋 구성)

안동 실태조사 우려지역 299개(양성) + 안동 내 무작위 배경점(음성 대용)에 대해
정밀토양도(ST 심토토성·AD 유효토심·DC 배수·SL 경사)를 지점 샘플링한다.
→ presence-vs-background AUC로 Module A FoS의 R을 측정하기 위한 입력 테이블.

주의: 우려지역은 '전문가가 조사 대상으로 선정한 위험 후보지'이지 확인된 발생지가
아니다. 따라서 이 검증은 '물리 FoS가 우려지역을 배경보다 높게 평가하는가'이며,
'실제 붕괴 예측 정확도'로 과대주장하지 않는다.  (실데이터·정직 원칙)

입력 CRS 규칙: 정밀토양도는 .prj 없음 → EPSG:5174로 명시(메모 검증됨).
안동 경계·좌표는 EPSG:4326 → 5174로 변환해 샘플링, 산출은 5174 저장.
"""
from __future__ import annotations
import warnings; warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np
import pandas as pd
import geopandas as gpd
import pyogrio
from shapely.geometry import Point

SOIL_ROOT = Path(r"G:/연구/산사태/데이터/토양도")
BOUNDARY = Path(r"G:/연구/산사태/데이터/andong_boundary.geojson")
INVENTORY = Path(r"G:/연구/산사태/안동시_산사태_토석류_DB(2021-2025) (1).xlsx")
OUT = Path(r"G:/연구/공모전/아쿠아가드/outputs"); OUT.mkdir(parents=True, exist_ok=True)
SOIL_CRS = "EPSG:5174"
N_BACKGROUND = 600  # 배경점(양성 299의 ~2배)
SEED = 42

SOIL_LAYERS = {  # 속성명 : (폴더, shp, 코드컬럼 prefix)
    "ST": ("st", "ST_심토토성.shp"),
    "AD": ("ad", "AD_유효토심.shp"),
    "DC": ("dc", "DC_배수등급.shp"),
    "SL": ("sl", "SL_경사.shp"),
}


def load_boundary_5174():
    g = gpd.read_file(BOUNDARY).to_crs(SOIL_CRS)
    return g


def load_positives_5174():
    sc = pd.read_excel(INVENTORY, sheet_name="수치변환")
    sc = sc.dropna(subset=["위도", "경도"]).copy()
    gdf = gpd.GeoDataFrame(
        sc, geometry=[Point(xy) for xy in zip(sc["경도"], sc["위도"])], crs="EPSG:4326"
    ).to_crs(SOIL_CRS)
    gdf["label"] = 1
    gdf["kind"] = sc["조사대상지 구분"].values
    return gdf[["label", "kind", "geometry"]]


def make_background_5174(boundary, n, seed=SEED):
    rng = np.random.default_rng(seed)
    minx, miny, maxx, maxy = boundary.total_bounds
    poly = boundary.geometry.union_all()
    pts = []
    while len(pts) < n:
        xs = rng.uniform(minx, maxx, n * 2)
        ys = rng.uniform(miny, maxy, n * 2)
        for x, y in zip(xs, ys):
            p = Point(x, y)
            if poly.contains(p):
                pts.append(p)
                if len(pts) >= n:
                    break
    g = gpd.GeoDataFrame(
        {"label": [0] * len(pts), "kind": ["background"] * len(pts)},
        geometry=pts, crs=SOIL_CRS)
    return g


def sample_layer(points, folder, shp, code_prefix, bbox):
    path = SOIL_ROOT / folder / shp
    soil = pyogrio.read_dataframe(path, bbox=bbox, encoding="cp949")
    soil = soil.set_crs(SOIL_CRS, allow_override=True)
    codecol = [c for c in soil.columns if c.upper().startswith("CODE")][0]
    labelcol = [c for c in soil.columns
                if c not in ("AREA", "PERIMETER") and not c.upper().startswith("CODE")][0]
    soil = soil[[codecol, labelcol, "geometry"]].rename(
        columns={codecol: f"{code_prefix}_code", labelcol: f"{code_prefix}_class"})
    joined = gpd.sjoin(points, soil, how="left", predicate="within").drop(columns="index_right")
    joined = joined[~joined.index.duplicated(keep="first")]
    return joined


def main():
    boundary = load_boundary_5174()
    bbox = tuple(boundary.total_bounds)  # (minx,miny,maxx,maxy) in 5174
    print(f"안동 bbox(5174): {[round(b) for b in bbox]}")

    pos = load_positives_5174()
    bg = make_background_5174(boundary, N_BACKGROUND)
    pts = pd.concat([pos, bg], ignore_index=True)
    pts = gpd.GeoDataFrame(pts, geometry="geometry", crs=SOIL_CRS)
    print(f"points: 양성 {len(pos)} + 배경 {len(bg)} = {len(pts)}")

    for prefix, (folder, shp) in SOIL_LAYERS.items():
        pts = sample_layer(pts, folder, shp, prefix, bbox)
        got = pts[f"{prefix}_code"].notna().sum()
        print(f"  {prefix} 샘플됨: {got}/{len(pts)}")

    # 저장 (좌표 5174)
    pts["x_5174"] = pts.geometry.x
    pts["y_5174"] = pts.geometry.y
    csv = pts.drop(columns="geometry")
    csv.to_csv(OUT / "andong_points_soil.csv", index=False, encoding="utf-8-sig")
    pts.to_file(OUT / "andong_points_soil.gpkg", driver="GPKG")
    print(f"saved -> outputs/andong_points_soil.csv, .gpkg  ({len(pts)} pts)")
    # 양성/배경 토성 분포 요약
    print("\n[양성 vs 배경] 심토토성 분포:")
    print(pd.crosstab(pts["label"], pts["ST_class"]).to_string())


if __name__ == "__main__":
    main()
