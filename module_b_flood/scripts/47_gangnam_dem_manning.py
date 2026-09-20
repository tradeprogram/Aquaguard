"""
47_gangnam_dem_manning.py — 강남구 침수모형 입력 ①② (DEM 클립 + Manning 조도)

서울 강남구 내수침수(빗물) SFINCS 모형의 지형·조도 입력을 만든다.
산청은 하천 유입·수위 경계로 푸는 **하천범람**이었는데, 강남역 침수는 하수도 용량
초과로 생기는 **내수침수**라 강제 방식이 다르다(48번에서 강우 강제로 푼다).

여기서 만드는 것
  data/seoul/gangnam_dem_5m_5179.tif       강남구 + 버퍼 DEM
  data/seoul/gangnam_worldcover_5m_5179.tif 토지피복
  data/seoul/gangnam_manning_5m_5179.tif    Manning n
  data/seoul/gangnam_domain_meta.json       경계·격자 제원

버퍼를 두는 이유: 구 경계에서 물이 들고 나는데 경계에 딱 맞춰 자르면 가장자리에서
인위적인 벽이 생긴다. 500m 여유를 준다.

조도계수는 23번(산청)과 같은 출처·같은 룩업을 쓴다 — ESA WorldCover 10m 를
Planetary Computer 에서 받아 DEM 격자에 재투영. 도시(class 50)가 지배적이라
산청과 분포가 크게 다르며, 그 분포를 meta 에 기록해 둔다.

★ DEM 은 도별 원본 타일을 직접 모자이크한다 (2026-09-20 수정)
  처음에는 data/dem/서울_dem_5m_5179.tif 를 썼는데 두 가지 문제가 있었다.
  ① 그 파일은 원본 `dem_5m_서울특별시.tif` 와 배열이 완전히 같은데 transform 만
     서쪽 163m · 북쪽 1,646m 어긋나 있었다(같은 6065x7411, 같은 해상도).
     즉 지오레퍼런스가 깨진 복사본이다. 쓰지 않는다.
  ② 서울 타일만으로는 강남 남단(세곡·자곡·율현)과 서초 남단이 비어 도메인의
     16% 가 결측이었다. 그 결측이 -9999 인 채로 SFINCS 에 들어가 subgrid 지반고를
     -3598m 까지 끌어내렸고, 후처리 침수심이 3,604m 로 나왔다.
  도별 타일은 행정경계에서 정확히 상보적이라 서울특별시 + 경기도 두 장을 겹치면
  이 도메인의 결측이 0% 가 된다. 남는 결측이 있으면 여기서 막고 넘기지 않는다.
"""
from __future__ import annotations

import json
import sys
import warnings

warnings.filterwarnings("ignore")
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
import requests
from rasterio.warp import Resampling, reproject, transform_bounds
from rasterio.windows import from_bounds

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(r"G:/연구/공모전/아쿠아가드")
# 도별 5m DEM 원본(EPSG:5179). 행정경계에서 상보적이라 겹쳐서 모자이크한다.
DEM_SRC_DIR = Path(r"G:/연구/데이터/DEM_5m_5179/DEM_5m_5179")
DEM_TILES = ("서울특별시", "경기도")
DEM_NODATA_BELOW = -10.0      # 이 값 미만은 결측(-9999)으로 본다. 서울은 해발 0m 이상
# 경계는 국토부 법정 시군구(LARD, EPSG:5186)를 1순위로 쓴다 — 행정동 병합보다
# 공식 경계에 가깝다. 없으면 행정동(adm_dong)을 sggnm 으로 묶어 폴백한다.
ADM_LARD = Path(r"G:/연구/지역shp/LARD_ADM_SECT_SGG_서울/LARD_ADM_SECT_SGG_11_202405.shp")
ADM_DONG = ROOT / "data" / "vector" / "adm_dong_5179.geojson"
GANGNAM_CODE = "11680"
OUT = ROOT / "data" / "seoul"
OUT.mkdir(parents=True, exist_ok=True)

BUFFER_M = 500.0
STAC = "https://planetarycomputer.microsoft.com/api/stac/v1/search"
SIGN = "https://planetarycomputer.microsoft.com/api/sas/v1/sign?href="

# 토지피복 → Manning n. 23번(산청)과 동일 룩업 — 두 지역 결과를 비교하려면
# 같은 표를 써야 한다. 출처: Chow 1959 Table 5-6, Arcement&Schneider 1989.
LC2N = {10: 0.120, 20: 0.060, 30: 0.035, 40: 0.040, 50: 0.050,
        60: 0.025, 70: 0.025, 80: 0.030, 90: 0.050, 95: 0.080, 100: 0.030}
LC_NAME = {10: "수목", 20: "관목", 30: "초지", 40: "경작지", 50: "시가지",
           60: "나지", 70: "설빙", 80: "수역", 90: "초본습지", 95: "맹그로브", 100: "이끼"}
N_DEFAULT = 0.040


def sign(href: str) -> str:
    return requests.get(SIGN + requests.utils.quote(href, safe=""), timeout=30).json()["href"]


def main() -> None:
    if ADM_LARD.exists():
        gdf = gpd.read_file(ADM_LARD, encoding="cp949").to_crs(f"EPSG:{5179}")
        gn = gdf[gdf["ADM_SECT_C"].astype(str) == GANGNAM_CODE]
        src_name = f"LARD 법정 시군구 {ADM_LARD.name} (코드 {GANGNAM_CODE})"
    else:
        gdf = gpd.read_file(ADM_DONG)
        gn = gdf[gdf["sggnm"].astype(str).str.strip() == "강남구"]
        src_name = "adm_dong_5179 행정동 병합(폴백)"
    if gn.empty:
        raise SystemExit("강남구 경계를 찾지 못했습니다")
    print(f"경계 출처: {src_name}")
    geom = gn.geometry.union_all() if hasattr(gn.geometry, "union_all") else gn.geometry.unary_union
    minx, miny, maxx, maxy = geom.bounds
    # 격자 정렬: 5m 배수로 맞춰 둬야 subgrid 가 깔끔하다
    x0 = np.floor((minx - BUFFER_M) / 5) * 5
    y0 = np.floor((miny - BUFFER_M) / 5) * 5
    x1 = np.ceil((maxx + BUFFER_M) / 5) * 5
    y1 = np.ceil((maxy + BUFFER_M) / 5) * 5
    print(f"강남구 면적 {geom.area/1e6:.1f} km²")
    print(f"도메인(버퍼 {BUFFER_M:.0f}m) x[{x0:.0f},{x1:.0f}] y[{y0:.0f},{y1:.0f}] "
          f"= {(x1-x0)/1000:.2f} × {(y1-y0)/1000:.2f} km")

    dem = None
    tile_fill = {}
    for name in DEM_TILES:
        src = DEM_SRC_DIR / f"dem_5m_{name}.tif"
        if not src.exists():
            print(f"  [경고] {src.name} 없음 — 건너뜀")
            continue
        with rasterio.open(src) as ds:
            win = from_bounds(x0, y0, x1, y1, transform=ds.transform)
            arr = ds.read(1, window=win, boundless=True,
                          fill_value=-9999).astype("float32")
            tr, crs = ds.window_transform(win), ds.crs
        ok = arr > DEM_NODATA_BELOW
        if dem is None:
            dem, gap = arr, ~ok
        else:
            gap = dem <= DEM_NODATA_BELOW
            dem = np.where(gap, arr, dem)
        tile_fill[name] = int((ok & gap).sum()) if len(tile_fill) else int(ok.sum())
        print(f"  타일 {name}: 유효 {100*ok.mean():5.1f}%  → 누적 결측 "
              f"{100*(dem <= DEM_NODATA_BELOW).mean():.3f}%")
    if dem is None:
        raise SystemExit("DEM 원본 타일을 하나도 열지 못했습니다")

    h, w = dem.shape
    bad = ~np.isfinite(dem) | (dem <= DEM_NODATA_BELOW)
    n_bad = int(bad.sum())
    if n_bad:
        # 여기서 막는다. -9999 를 그대로 흘리면 SFINCS subgrid 지반고가 붕괴한다.
        raise SystemExit(
            f"DEM 결측 {n_bad:,}셀 ({100*n_bad/dem.size:.2f}%) 이 남았습니다. "
            f"도별 타일을 더 추가하거나 보간 방침을 정한 뒤 다시 실행하세요.")
    dem = dem.astype("float32")
    print(f"DEM 모자이크 {w}×{h} @5m  결측 0  표고 {dem.min():.1f}~{dem.max():.1f} m")
    fin = np.ones_like(dem, dtype=bool)

    prof = dict(driver="GTiff", height=h, width=w, count=1, crs=crs, transform=tr,
                compress="deflate", tiled=True, blockxsize=256, blockysize=256)
    with rasterio.open(OUT / "gangnam_dem_5m_5179.tif", "w", dtype="float32", nodata=np.nan, **prof) as ds:
        ds.write(dem.astype("float32"), 1)

    # --- 토지피복 → Manning
    bbox4326 = list(transform_bounds(crs, "EPSG:4326", x0, y0, x1, y1))
    print(f"WorldCover 조회 bbox(4326) {[round(v,4) for v in bbox4326]}")
    feats = requests.post(STAC, json={"collections": ["esa-worldcover"],
                                      "bbox": bbox4326, "limit": 10}, timeout=60).json()["features"]
    feats = sorted(feats, key=lambda f: f["properties"].get("start_datetime", ""), reverse=True)
    print(f"  타일 {len(feats)}개: {[f['id'] for f in feats[:4]]}")

    acc = np.zeros((h, w), dtype="uint8")
    for f in feats:
        asset = f["assets"].get("map") or list(f["assets"].values())[0]
        with rasterio.open(sign(asset["href"])) as src:
            b = transform_bounds("EPSG:4326", src.crs, *bbox4326)
            try:
                sw = from_bounds(*b, transform=src.transform)
                arr = src.read(1, window=sw)
                st, sc = src.window_transform(sw), src.crs
            except Exception:
                continue
        if arr.size == 0:
            continue
        dst = np.zeros((h, w), dtype="uint8")
        reproject(arr, dst, src_transform=st, src_crs=sc,
                  dst_transform=tr, dst_crs=crs, resampling=Resampling.nearest)
        acc = np.where(acc == 0, dst, acc)

    vals, cnts = np.unique(acc[acc > 0], return_counts=True)
    dist = {int(v): int(c) for v, c in zip(vals, cnts)}
    tot = sum(dist.values()) or 1
    print("토지피복 분포:")
    for v, c in sorted(dist.items(), key=lambda kv: -kv[1]):
        print(f"   {LC_NAME.get(v, v):8s}({v:3d}) {c:>9,}px {100*c/tot:5.1f}%  n={LC2N.get(v, N_DEFAULT)}")

    n = np.full((h, w), N_DEFAULT, dtype="float32")
    for code, nv in LC2N.items():
        n[acc == code] = nv
    n[acc == 0] = N_DEFAULT

    with rasterio.open(OUT / "gangnam_worldcover_5m_5179.tif", "w", dtype="uint8", nodata=0, **prof) as ds:
        ds.write(acc, 1)
    with rasterio.open(OUT / "gangnam_manning_5m_5179.tif", "w", dtype="float32", nodata=0, **prof) as ds:
        ds.write(n, 1)

    meta = {
        "생성": __import__("datetime").datetime.now().isoformat(timespec="minutes"),
        "대상": "서울 강남구 내수침수 SFINCS 입력",
        "행정구역": {"name": "강남구", "code": GANGNAM_CODE, "source": src_name,
                 "area_km2": round(geom.area / 1e6, 2)},
        "도메인_5179": {"x0": x0, "y0": y0, "x1": x1, "y1": y1,
                     "width_px": w, "height_px": h, "res_m": 5},
        "dem": {"source": "국토정보플랫폼 5m DEM 도별 원본 모자이크: "
                          + " + ".join(f"dem_5m_{t}.tif" for t in DEM_TILES),
                "min_m": round(float(dem.min()), 2), "max_m": round(float(dem.max()), 2),
                "nodata_cells": 0,
                "타일별_기여셀": tile_fill,
                "주의": "data/dem/서울_dem_5m_5179.tif 는 transform 이 서쪽163m·북쪽1646m "
                      "어긋난 손상본이고 서울 경계 밖이 비어 있다. 쓰지 말 것."},
        "landcover": {"source": "ESA WorldCover 2021 v200 (10m) via MS Planetary Computer",
                      "distribution_px": dist,
                      "시가지_비율_%": round(100 * dist.get(50, 0) / tot, 1)},
        "manning": {"ref": "Chow 1959 Table5-6; Arcement&Schneider 1989 USGS WSP2339",
                    "lc2n": LC2N, "n_default": N_DEFAULT,
                    "mean": round(float(np.nanmean(n)), 4)},
        "주의": "내수침수 모형이다. 하수관망을 넣지 않으므로 배수 상수를 별도로 빼지 "
              "않으면 침수를 과대평가한다 — 48번에서 처리한다.",
    }
    (OUT / "gangnam_domain_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n저장: {OUT}")
    for f in sorted(OUT.glob("gangnam_*")):
        print(f"   {f.name}  {f.stat().st_size/1e6:.1f} MB")


if __name__ == "__main__":
    main()
