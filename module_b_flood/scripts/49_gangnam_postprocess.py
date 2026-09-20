"""
49_gangnam_postprocess.py — 강남 SFINCS 결과 → 침수심 래스터 + 깊이밴드 폴리곤

sfincs_map.nc 의 zsmax(최대 수위, 표고)에서 지반고를 빼 **침수심**을 만들고, 산청
(module_b_flood/fim.py)과 **같은 깊이 구간**으로 폴리곤화한다. 같은 구간을 써야
3D 지도에서 두 지역을 같은 범례로 그릴 수 있다.

  DEPTH_BANDS_M = (0.3, 1.0, 2.0, 5.0)

────────────────────────────────────────────────────────────────────────────
★ 2026-09-20 3차 수정 — 침수면적의 78% 가 허수였다

첫 판은 `zsmax - zb` 를 20m 계산격자에서 그대로 썼다. 세 가지가 잘못이었다.

  ① 수역을 침수로 셌다
     한강·탄천 수면이 "침수"로 잡혔다. 0.3m 이상 면적의 16% 가 수역이었다.
  ② 깊이를 셀의 최저점 기준으로 냈다
     subgrid 모형에서 `zb` 는 셀 **최저점**이다(5m 블록 최소와 중앙차 0.143m).
     20m 셀 안 5m 기복이 중앙 0.75m, p90 5.59m 라, 산지에서 "침수 5m" 는 셀 바닥
     한 구석 이야기였다. 2m 이상 밴드의 48% 가 숲이었다.
  ③ 직사각 도메인 전체를 집계했다
     도메인 10,700ha 인데 강남구는 3,922ha 다. 우면산·청계산이 통계에 들어왔다.

지금은
  ① WorldCover 수역(class 80)을 침수 판정에서 뺀다
  ② 수위 zsmax 를 **5m DEM 격자로 내려** depth = zs − dem5 로 계산한다.
     20m 에서 젖은 셀과 이어진 영역만 남겨 수위가 능선 너머로 새지 않게 한다.
  ③ 통계·폴리곤은 **강남구 경계 안**만 낸다. 버퍼는 계산에는 필요하지만(경계에서
     물이 드나들어야 한다) 보고 대상은 아니다. 도메인 전체 수치도 같이 찍어 둔다.

qinf=50 기준 0.3m 이상 면적: 1,228.5 → 1,033.6 → 672.1 → 269.6 ha

★ 지반고 타당성 검사
  그 전 실행에서 최대 침수심이 3,604m 로 나왔다. 입력 DEM 의 -9999 결측이 subgrid
  로 흘러들어 지반고가 -3,598m 까지 내려간 것이었다(47번에서 고쳤다). msk 만 보면
  안 걸러진다 — 그 셀들은 msk==1 이고 수위도 정상 5~6m 였다. 그래서 여기서 범위를
  따로 검사하고, 걸리면 통계를 내지 않고 멈춘다. 조용히 잘라내면 멀쩡해 보인다.

출력
  data/seoul/gangnam_maxdepth_5m.tif        침수심 래스터(5m, 도메인 전체)
  outputs/gangnam_inundation_5179.geojson   깊이밴드 폴리곤(EPSG:5179, 강남구 안)
  outputs/gangnam_flood_summary.json        통계·가정·한계

정직
  - 하수관망 미반영. 배수를 상수(qinf)로 대리했으므로 국지 병목·역류로 생기는
    실제 침수는 재현하지 못한다. 배수율 가정에 결과가 민감하다(50번 민감도 참조).
  - **미검증**이다. 서울시 침수흔적도로 대조해야 한다. 산청은 경호교 수위계로
    RMSE 1.42m 를 냈지만 여기에는 대응하는 참값이 아직 없다.
  - 0.3m 미만은 버린다(산청과 동일). 도로 물고임까지 그리면 도시 전역이 파랗다.
  - 5m 다운스케일은 수위를 셀 안에서 평평하다고 본다. 실제 수면 경사를 셀보다
    작은 규모로 재현하는 것이 아니라, **마른 곳을 마르게 하는** 보정이다.
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
from rasterio.features import rasterize
from rasterio.features import shapes as rio_shapes
from rasterio.transform import from_origin
from rasterio.warp import Resampling, reproject
from scipy import ndimage
from shapely.geometry import mapping, shape
from shapely.ops import unary_union

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(r"G:/연구/공모전/아쿠아가드")
SEOUL = ROOT / "data" / "seoul"
OUT = ROOT / "outputs"
ADM_LARD = Path(r"G:/연구/지역shp/LARD_ADM_SECT_SGG_서울/LARD_ADM_SECT_SGG_11_202405.shp")
GANGNAM_CODE = "11680"

DEPTH_BANDS_M = (0.3, 1.0, 2.0, 5.0)
MIN_AREA_M2 = 400.0          # 5m 픽셀 16개. 한두 픽셀짜리 파편 제거
SIMPLIFY_M = 5.0
WATER_CLASS = 80             # ESA WorldCover 영구수역 — 한강·탄천
ZB_MIN_M, ZB_MAX_M = -20.0, 700.0   # 강남 도메인 실표고 0.2~308.7m


def load_run(run_dir: Path):
    import xarray as xr

    ds = xr.open_dataset(run_dir / "sfincs_map.nc")
    zs = np.asarray(ds["zsmax"].values)
    if zs.ndim == 3:
        zs = np.nanmax(zs, axis=0)
    zb = np.asarray(ds["zb"].values)
    if zb.ndim == 3:
        zb = zb[0]
    msk = np.asarray(ds["msk"].values) if "msk" in ds else np.ones_like(zb)
    act = msk > 0
    bad = act & (~np.isfinite(zb) | (zb < ZB_MIN_M) | (zb > ZB_MAX_M))
    if bad.any():
        raise SystemExit(
            f"지반고 zb 가 타당 범위({ZB_MIN_M}~{ZB_MAX_M}m) 밖인 활성셀 "
            f"{int(bad.sum()):,}개가 있습니다 (예: {np.unique(zb[bad])[:5]}). "
            f"입력 DEM 에 결측(-9999)이 섞였을 때 나타나는 증상입니다 — "
            f"47번을 다시 돌려 DEM 결측이 0 인지 확인한 뒤 48번부터 재빌드하세요.")
    print(f"지반고 zb {np.nanmin(zb[act]):.2f}~{np.nanmax(zb[act]):.2f}m  "
          f"(활성셀 {int(act.sum()):,})")
    return zs, zb, act


def depth_5m(run_dir: Path):
    """보정된 5m 침수심을 만든다. 50번(민감도)도 이 함수를 그대로 쓴다 — 두 산출물이
    다른 방식으로 계산되면 표가 서로 어긋난다.

    반환 (dep, dep_aoi, dst_tr, res5, inp, n_water, aoi_ha)
      dep      도메인 전체 5m 침수심 (수역 제외)
      dep_aoi  강남구 경계 안만 남긴 것
    """
    zs, zb, act = load_run(run_dir)
    ny, nx = zs.shape
    inp = json.loads((run_dir / "_build_meta.json").read_text(encoding="utf-8"))
    dx = float(inp["격자"]["dx_m"])
    dom = json.loads((SEOUL / "gangnam_domain_meta.json").read_text(encoding="utf-8"))["도메인_5179"]
    x0, y0 = dom["x0"], dom["y0"]

    wet = act & np.isfinite(zs - zb) & (zs - zb > 0)
    # SFINCS n 축은 y0 에서 북쪽으로 증가한다 → 북쪽이 위인 래스터 순서로 뒤집는다
    src_tr = from_origin(x0, y0 + ny * dx, dx, dx)
    zs_n = np.flipud(np.where(wet, zs, np.nan)).astype("float32")
    d20_n = np.flipud(np.where(wet, zs - zb, np.nan)).astype("float32")

    with rasterio.open(SEOUL / "gangnam_dem_5m_5179.tif") as ds:
        dem = ds.read(1)
        dst_tr, crs = ds.transform, ds.crs
    H, W = dem.shape
    res5 = abs(dst_tr.a)

    def warp(a, rs):
        o = np.full((H, W), np.nan, "float32")
        reproject(a, o, src_transform=src_tr, src_crs=crs, dst_transform=dst_tr,
                  dst_crs=crs, src_nodata=np.nan, dst_nodata=np.nan, resampling=rs)
        return o

    # 수위는 이중선형으로 내린다(수면은 매끄럽다). 가장자리에서 비면 최근접으로 메운다.
    zs5 = warp(zs_n, Resampling.bilinear)
    zs5 = np.where(np.isfinite(zs5), zs5, warp(zs_n, Resampling.nearest))
    d20 = warp(d20_n, Resampling.nearest)

    dep = np.where(np.isfinite(zs5 - dem) & (zs5 - dem > 0), zs5 - dem, np.nan)
    # 연결성: 20m 에서 실제로 젖었던 영역과 이어진 곳만 남긴다. 이렇게 안 하면
    # 이중선형 보간된 수위가 능선 너머 낮은 땅에 얹혀 없는 침수를 만든다.
    lab, _ = ndimage.label(np.isfinite(dep))
    dep = np.where(np.isin(lab, np.unique(lab[(lab > 0) & np.isfinite(d20)])), dep, np.nan)

    with rasterio.open(SEOUL / "gangnam_worldcover_5m_5179.tif") as ds:
        wc = ds.read(1)
    n_water = int(np.nansum((dep >= DEPTH_BANDS_M[0]) & (wc == WATER_CLASS)))
    dep = np.where(wc == WATER_CLASS, np.nan, dep)          # ① 영구수역 제외

    g = gpd.read_file(ADM_LARD, encoding="cp949").to_crs(crs)
    aoi_geom = g[g["ADM_SECT_C"].astype(str) == GANGNAM_CODE].geometry.union_all()
    aoi = rasterize([(aoi_geom, 1)], out_shape=(H, W), transform=dst_tr, dtype="uint8") == 1

    cell = res5 * res5
    aoi_ha = float(aoi.sum() * cell / 1e4)
    tot_dom = float(np.nansum(dep >= DEPTH_BANDS_M[0]) * cell / 1e4)
    dep_aoi = np.where(aoi, dep, np.nan)                     # ③ 강남구 안만 집계
    return dep, dep_aoi, dst_tr, res5, inp, n_water, aoi_ha


def main(run_dir: Path) -> None:
    dep, dep_aoi, dst_tr, res5, inp, n_water, aoi_ha = depth_5m(run_dir)
    H, W = dep.shape
    crs = "EPSG:5179"
    cell = res5 * res5
    tot_dom = float(np.nansum(dep >= DEPTH_BANDS_M[0]) * cell / 1e4)
    tot_aoi = float(np.nansum(dep_aoi >= DEPTH_BANDS_M[0]) * cell / 1e4)

    print(f"수역 제외 {n_water:,}픽셀  |  도메인 {H}×{W} @{res5:.0f}m")
    print(f"0.3m 이상  도메인 {tot_dom:,.1f}ha  →  강남구 안 {tot_aoi:,.1f}ha "
          f"(강남구 {aoi_ha:,.0f}ha 의 {100*tot_aoi/aoi_ha:.1f}%)")
    if np.isfinite(dep_aoi).any():
        v = dep_aoi[np.isfinite(dep_aoi)]
        print(f"침수심(강남구) 중앙 {np.median(v):.2f}m  p90 {np.percentile(v,90):.2f}m  "
              f"최대 {v.max():.2f}m")

    prof = dict(driver="GTiff", height=H, width=W, count=1, dtype="float32",
                crs=crs, transform=dst_tr, nodata=np.nan, compress="deflate",
                tiled=True, blockxsize=256, blockysize=256)
    SEOUL.mkdir(parents=True, exist_ok=True)
    with rasterio.open(SEOUL / "gangnam_maxdepth_5m.tif", "w", **prof) as dst:
        dst.write(dep.astype("float32"), 1)

    # --- 깊이 밴드 폴리곤 (산청 fim.py 와 같은 구간), 강남구 안만
    edges = list(DEPTH_BANDS_M) + [np.inf]
    feats, band_stats = [], []
    for i, (lo, hi) in enumerate(zip(edges[:-1], edges[1:])):
        m = np.isfinite(dep_aoi) & (dep_aoi >= lo) & (dep_aoi < hi)
        n = int(m.sum())
        band_stats.append({"band": i, "min_m": lo, "max_m": None if np.isinf(hi) else hi,
                           "cells": n, "area_ha": round(n * cell / 1e4, 2)})
        if n == 0:
            continue
        geoms = [shape(s) for s, v in rio_shapes(m.astype("uint8"), mask=m,
                                                 transform=dst_tr) if v == 1]
        if not geoms:
            continue
        merged = unary_union(geoms).simplify(SIMPLIFY_M, preserve_topology=True)
        parts = [p for p in (merged.geoms if merged.geom_type == "MultiPolygon" else [merged])
                 if p.area >= MIN_AREA_M2]
        if not parts:
            continue
        geom = unary_union(parts)
        vals = dep_aoi[m]
        feats.append({
            "type": "Feature",
            "properties": {"band": i, "depth_min_m": lo,
                           "depth_max_m": None if np.isinf(hi) else hi,
                           "depth_mean_m": round(float(vals.mean()), 3),
                           "depth_p90_m": round(float(np.percentile(vals, 90)), 3),
                           "area_m2": round(float(geom.area), 1)},
            "geometry": json.loads(json.dumps(mapping(geom))),
        })
        print(f"  밴드{i} {lo}~{'∞' if np.isinf(hi) else hi}m : {n:,}픽셀 "
              f"{n*cell/1e4:7.2f}ha  평균 {vals.mean():.2f}m")

    limits = [
        inp["가정"], inp["검증"],
        "0.3m 미만은 폴리곤에서 제외(산청과 동일 기준).",
        "배수율 가정에 결과가 크게 좌우된다 — outputs/gangnam_drain_sensitivity.json 참조.",
        "강남역 사거리는 배수율을 어떻게 잡아도 얕게 나온다. 그 지점은 지형상 와지가 "
        "아니라(와지깊이 0.00m, 대치역 2.94m) 물이 지나가는 길목이고, 실제 2022-08-08 "
        "침수는 하수관망 통수능 초과·역류로 생긴 것이라 지표 모형이 만들 수 없다.",
        "영구수역(WorldCover class 80, 한강·탄천)은 침수에서 제외했다.",
        "침수심은 20m 수위를 5m DEM 에 내려 계산했다. 셀 안에서 수위를 평평하다고 "
        "보는 보정이므로, 5m 규모의 수면 경사를 재현하는 것은 아니다.",
        "통계·폴리곤은 강남구 경계 안만이다. 500m 버퍼는 계산에만 쓴다.",
        "2m 이상 깊은 물은 대부분 DEM 의 **폐합 저지(와지)** 에 갇힌 것이다. 20m DEM "
        "에서 와지 깊이 0.1m 초과 셀이 17.9%, 최대 14.21m 다. 지하차도·저지대처럼 "
        "실제로 물이 차는 곳도 있지만, 교량 하부·터널 입구 같은 DEM 인공 와지도 "
        "섞여 있다. 둘을 가르려면 암거·배수구 자료가 필요하다. 그래서 깊이 상위 "
        "구간은 그대로 쓰지 말고 위치를 확인해야 한다.",
    ]
    fc = {"type": "FeatureCollection",
          "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::5179"}},
          "properties": {"지역": "서울 강남구", "유형": "내수침수(강우 강제)",
                         "집계범위": "강남구 법정경계 안",
                         "강우": inp["강우"], "배수상수_mm_h": inp["배수상수_mm_h"],
                         "가정": inp["가정"], "검증": inp["검증"]},
          "features": feats}
    OUT.mkdir(exist_ok=True)
    (OUT / "gangnam_inundation_5179.geojson").write_text(
        json.dumps(fc, ensure_ascii=False), encoding="utf-8")

    summary = {"생성": __import__("datetime").datetime.now().isoformat(timespec="minutes"),
               "run": str(run_dir), "격자": inp["격자"], "강우": inp["강우"],
               "배수상수_mm_h": inp["배수상수_mm_h"],
               "집계범위": "강남구 법정경계 안 (LARD 11680)",
               "침수": {"area_ha_0.3m이상_강남구": round(tot_aoi, 2),
                      "area_ha_0.3m이상_도메인전체": round(tot_dom, 2),
                      "강남구_면적_ha": round(aoi_ha, 1),
                      "median_m": round(float(np.nanmedian(dep_aoi)), 3),
                      "p90_m": round(float(np.nanpercentile(dep_aoi, 90)), 3),
                      "max_m": round(float(np.nanmax(dep_aoi)), 3)},
               "밴드": band_stats, "feature수": len(feats),
               "보정": {"영구수역_제외_픽셀": n_water,
                      "해상도": "20m 수위 → 5m DEM 다운스케일",
                      "집계": "강남구 경계 클립"},
               "한계": limits}
    (OUT / "gangnam_flood_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n저장: {SEOUL/'gangnam_maxdepth_5m.tif'}")
    print(f"      {OUT/'gangnam_inundation_5179.geojson'}  feature {len(feats)}개")
    print(f"      {OUT/'gangnam_flood_summary.json'}")


if __name__ == "__main__":
    # 기본을 drain30 으로 둔다. 근거: 건설연(KICT) 2026-07 발표 실험·수치모의에서
    # 시간당 100mm 강우 시 강남역 일대 "수십 cm ~ 최대 1m" 침수. 우리 사건의 최대
    # 강우는 92.5mm/h 이고, qinf=30 에서 강남역 반경 100m 최대 0.87m 로 그 범위에
    # 든다(50: 0.48m, 75: 0.21m). 30mm/h 는 서울시 하수도 일반 설계빈도(10년) 하단대
    # 라는 점에서도 2022년 당시 관거 사정에 가깝다. 독립 연구와 맞물린 값이지 우리가
    # 맞춰 넣은 값이 아니지만, 여전히 **침수흔적도로 검증된 것은 아니다**.
    d = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
        r"C:/Users/user/AppData/Local/Temp/claude/aquaguard_work/sfincs_gangnam/drain30")
    main(d)
