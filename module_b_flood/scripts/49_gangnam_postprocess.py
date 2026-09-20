"""
49_gangnam_postprocess.py — 강남 SFINCS 결과 → 침수심 래스터 + 깊이밴드 폴리곤

sfincs_map.nc 의 zsmax(최대 수위, 표고)에서 지반고 zb 를 빼 **침수심**을 만들고,
산청(module_b_flood/fim.py)과 **같은 깊이 구간**으로 폴리곤화한다. 같은 구간을 써야
3D 지도에서 두 지역을 같은 범례로 그릴 수 있다.

  DEPTH_BANDS_M = (0.3, 1.0, 2.0, 5.0)

출력
  data/seoul/gangnam_maxdepth_20m.tif              침수심 래스터
  outputs/gangnam_inundation_5179.geojson          깊이밴드 폴리곤(EPSG:5179)
  outputs/gangnam_flood_summary.json               통계·가정·한계

정직
  - 하수관망 미반영. 배수를 상수(qinf)로 대리했으므로 국지 병목으로 생기는 실제
    침수는 재현하지 못한다. 배수율 가정에 결과가 민감하다(민감도 실행 권장).
  - **미검증**이다. 서울시 침수흔적도를 확보하면 대조해야 한다. 산청은 경호교
    수위계로 RMSE 1.42m 를 냈지만 여기에는 대응하는 참값이 아직 없다.
  - 0.3m 미만은 버린다(산청과 동일). 도로 물고임 수준까지 그리면 도시 전역이
    파랗게 칠해져 의미가 없다.

★ 지반고 타당성 검사 (2026-09-20 추가)
  처음 실행에서 최대 침수심이 3,604m 로 나왔다. 원인은 입력 DEM 의 -9999 결측이
  subgrid 로 흘러들어 지반고 zb 가 -3,598m 까지 내려간 것이었다(47번에서 고쳤다).
  msk 만 보면 이런 셀이 걸러지지 않으므로 — 그 셀들은 msk==1 이고 zs 도 정상
  5~6m 였다 — 여기서 zb 범위를 따로 검사한다. 걸리면 통계를 내지 않고 멈춘다.
  침수심을 조용히 잘라내면 모형이 멀쩡해 보이기 때문이다.
"""
from __future__ import annotations

import json
import sys
import warnings

warnings.filterwarnings("ignore")
from pathlib import Path

import numpy as np
import rasterio
from rasterio.features import shapes as rio_shapes
from rasterio.transform import from_origin
from shapely.geometry import mapping, shape
from shapely.ops import unary_union

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(r"G:/연구/공모전/아쿠아가드")
SEOUL = ROOT / "data" / "seoul"
OUT = ROOT / "outputs"
DEPTH_BANDS_M = (0.3, 1.0, 2.0, 5.0)
MIN_AREA_M2 = 400.0          # 20m 격자 1개 = 400m². 한 칸짜리 파편 제거
SIMPLIFY_M = 10.0
# 강남 도메인 실제 표고는 0.2~308.7m. 여유를 둬 이 밖이면 입력이 오염된 것이다.
ZB_MIN_M, ZB_MAX_M = -20.0, 700.0


def main(run_dir: Path) -> None:
    import xarray as xr

    ds = xr.open_dataset(run_dir / "sfincs_map.nc")
    zsmax = np.asarray(ds["zsmax"].values)
    if zsmax.ndim == 3:
        zsmax = np.nanmax(zsmax, axis=0)
    zb = np.asarray(ds["zb"].values)
    if zb.ndim == 3:
        zb = zb[0]
    msk = np.asarray(ds["msk"].values) if "msk" in ds else np.ones_like(zb)

    act = msk > 0
    zb_bad = act & (~np.isfinite(zb) | (zb < ZB_MIN_M) | (zb > ZB_MAX_M))
    if zb_bad.any():
        v = zb[zb_bad]
        raise SystemExit(
            f"지반고 zb 가 타당 범위({ZB_MIN_M}~{ZB_MAX_M}m) 밖인 활성셀 "
            f"{int(zb_bad.sum()):,}개가 있습니다 (예: {np.unique(v)[:5]}). "
            f"입력 DEM 에 결측(-9999)이 섞였을 때 나타나는 증상입니다 — "
            f"47번을 다시 돌려 DEM 결측이 0 인지 확인한 뒤 48번부터 재빌드하세요.")
    print(f"지반고 zb {np.nanmin(zb[act]):.2f}~{np.nanmax(zb[act]):.2f}m  (활성셀 {int(act.sum()):,})")

    dep = zsmax - zb
    dep = np.where(np.isfinite(dep) & act, dep, np.nan)
    dep = np.where(dep > 0, dep, np.nan)

    inp = json.loads((run_dir / "_build_meta.json").read_text(encoding="utf-8"))
    g = inp["격자"]
    dx = float(g["dx_m"])
    meta = json.loads((SEOUL / "gangnam_domain_meta.json").read_text(encoding="utf-8"))
    x0 = meta["도메인_5179"]["x0"]
    y0 = meta["도메인_5179"]["y0"]
    ny, nx = dep.shape
    # SFINCS n 축은 y0 에서 위로 증가한다 → 북쪽이 위인 GeoTIFF 로 뒤집는다
    dep_img = np.flipud(dep)
    transform = from_origin(x0, y0 + ny * dx, dx, dx)

    fin = np.isfinite(dep_img)
    print(f"격자 {nx}×{ny} @{dx:.0f}m")
    print(f"침수 셀 {int(fin.sum()):,} ({fin.sum()*dx*dx/1e6:.3f} km²)")
    if fin.any():
        v = dep_img[fin]
        print(f"침수심  중앙 {np.median(v):.2f}m  p90 {np.percentile(v,90):.2f}m  "
              f"p99 {np.percentile(v,99):.2f}m  최대 {v.max():.2f}m")

    prof = dict(driver="GTiff", height=ny, width=nx, count=1, dtype="float32",
                crs="EPSG:5179", transform=transform, nodata=np.nan, compress="deflate")
    (SEOUL).mkdir(parents=True, exist_ok=True)
    with rasterio.open(SEOUL / f"gangnam_maxdepth_{int(dx)}m.tif", "w", **prof) as dst:
        dst.write(dep_img.astype("float32"), 1)

    # --- 깊이 밴드 폴리곤 (산청 fim.py 와 같은 구간)
    edges = list(DEPTH_BANDS_M) + [np.inf]
    feats, band_stats = [], []
    for i, (lo, hi) in enumerate(zip(edges[:-1], edges[1:])):
        m = fin & (dep_img >= lo) & (dep_img < hi)
        n = int(m.sum())
        band_stats.append({"band": i, "min_m": lo, "max_m": None if np.isinf(hi) else hi,
                           "cells": n, "area_km2": round(n * dx * dx / 1e6, 4)})
        if n == 0:
            continue
        geoms = [shape(s) for s, v in rio_shapes(m.astype("uint8"), mask=m, transform=transform) if v == 1]
        if not geoms:
            continue
        merged = unary_union(geoms).simplify(SIMPLIFY_M, preserve_topology=True)
        parts = [p for p in (merged.geoms if merged.geom_type == "MultiPolygon" else [merged])
                 if p.area >= MIN_AREA_M2]
        if not parts:
            continue
        geom = unary_union(parts)
        vals = dep_img[m]
        feats.append({
            "type": "Feature",
            "properties": {"band": i, "depth_min_m": lo,
                           "depth_max_m": None if np.isinf(hi) else hi,
                           "depth_mean_m": round(float(vals.mean()), 3),
                           "depth_p90_m": round(float(np.percentile(vals, 90)), 3),
                           "area_m2": round(float(geom.area), 1)},
            "geometry": json.loads(json.dumps(mapping(geom))),
        })
        print(f"  밴드{i} {lo}~{'∞' if np.isinf(hi) else hi}m : {n:,}셀 "
              f"{n*dx*dx/1e4:7.2f}ha  평균 {vals.mean():.2f}m")

    fc = {"type": "FeatureCollection",
          "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::5179"}},
          "properties": {"지역": "서울 강남구", "유형": "내수침수(강우 강제)",
                         "강우": inp["강우"], "배수상수_mm_h": inp["배수상수_mm_h"],
                         "가정": inp["가정"], "검증": inp["검증"]},
          "features": feats}
    OUT.mkdir(exist_ok=True)
    (OUT / "gangnam_inundation_5179.geojson").write_text(
        json.dumps(fc, ensure_ascii=False), encoding="utf-8")

    summary = {"생성": __import__("datetime").datetime.now().isoformat(timespec="minutes"),
               "run": str(run_dir), "격자": g, "강우": inp["강우"],
               "배수상수_mm_h": inp["배수상수_mm_h"],
               "침수": {"cells": int(fin.sum()), "area_km2": round(float(fin.sum()*dx*dx/1e6), 4),
                      "median_m": round(float(np.median(dep_img[fin])), 3) if fin.any() else None,
                      "p90_m": round(float(np.percentile(dep_img[fin], 90)), 3) if fin.any() else None,
                      "max_m": round(float(dep_img[fin].max()), 3) if fin.any() else None},
               "밴드": band_stats, "feature수": len(feats),
               "한계": [inp["가정"], inp["검증"],
                      "0.3m 미만은 폴리곤에서 제외(산청과 동일 기준).",
                      "배수율 가정에 따라 0.3m↑ 침수면적이 235~1,955ha 로 8.3배 "
                      "달라진다 — outputs/gangnam_drain_sensitivity.json 참조.",
                      "강남역 사거리는 세 배수율 모두 0.1~0.2m 에 그친다. 그 지점 "
                      "침수는 관망 역류가 원인이라 상수 배수 모형으로는 재현되지 "
                      "않는다. 대치·삼성 같은 지형 저지대는 재현된다."]}
    (OUT / "gangnam_flood_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n저장: {SEOUL/f'gangnam_maxdepth_{int(dx)}m.tif'}")
    print(f"      {OUT/'gangnam_inundation_5179.geojson'}  feature {len(feats)}개")
    print(f"      {OUT/'gangnam_flood_summary.json'}")


if __name__ == "__main__":
    d = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
        r"C:/Users/user/AppData/Local/Temp/claude/aquaguard_work/sfincs_gangnam/drain75")
    main(d)
