"""
33d_sfincs_build_deokcheon.py  (Module B — SFINCS 덕천강 상류 모델 빌드)  [env: sfincs]

지리산 쪽 계곡(시천면·삼장면)의 침수를 계산한다. 경호강 구간 모델(33)은 이쪽을 덮지 않아,
산불 흉터가 가장 넓게 남은 곳이 지금 시스템에서는 "침수 계산 범위 밖"이다(현장조사 반영 ④).

구성 — 25(군 전체 강우 강제)와 33(명시 격자·한글경로 우회)을 합쳤다:
- 영역: 시천면 ∪ 삼장면 경계 박스 + 1km 여유, 50m 격자, EPSG:5179
- 지형 5m DEM, 조도 Manning 5m (subgrid 10)
- 강제: 유역평균 시간강우(HRFCO, 공간 균일) — 이 영역에는 수위·유량 관측소 자료가 없다
- 경계: 낮은 고도의 격자 가장자리 outflow (덕천강이 영역을 빠져나가는 쪽)
- 이벤트: 2025-07-18 00:00 ~ 07-21 00:00 KST

한계: 수위 관측소가 없어 검증할 참값이 없고, 시간별 수위 곡선도 없어 화면에는 최대 범위만
표시된다(module_b_flood/domains.json의 stage_series: null). 단성면 쪽 덕천강 하류는 이
영역 밖이다.

실행 순서 (G: 드라이브 PC):
  1. python module_b_flood/scripts/33d_sfincs_build_deokcheon.py --dry-run      # 격자·입력 확인
  2. set AQUAGUARD_SFINCS_ROOT=C:\\sfincs_deokcheon                               # ASCII 경로
     conda run -n sfincs python module_b_flood/scripts/33d_sfincs_build_deokcheon.py
  3. 그 폴더에서 sfincs.exe 실행 → sfincs_map.nc
  4. python module_b_flood/scripts/33d_sfincs_build_deokcheon.py --postprocess %AQUAGUARD_SFINCS_ROOT%\\sfincs_map.nc
     → module_b_flood/data/sfincs_deokcheon_maxdepth_50m.tif
  5. module_b_flood/domains.json 의 deokcheon_upper status 를 "computed"로 고치고
     python scripts/build_demo_snapshot.py 로 저장본을 다시 만든다.

★ netCDF 한글경로 버그 때문에 빌드 폴더는 ASCII 경로여야 한다(33과 같은 이유).
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PROOT = Path(os.environ.get("AQUAGUARD_DATA_ROOT", r"G:/연구/공모전/아쿠아가드"))
DEM = PROOT / "data" / "dem" / "산청_dem_5m_5179.tif"
MANNING = PROOT / "data" / "hydro" / "sancheong_manning_5m_5179.tif"
PRECIP = PROOT / "data" / "hydro" / "sfincs_precip_basinmean.csv"
BUILD_ROOT = Path(os.environ.get("AQUAGUARD_SFINCS_ROOT", r"C:/sfincs_deokcheon"))
OUT_TIF = REPO / "module_b_flood" / "data" / "sfincs_deokcheon_maxdepth_50m.tif"

TOWNSHIPS = ("시천면", "삼장면")
BUFFER_M = 1000.0
DX = 50
EPSG = 5179
TREF = "20250718 000000"
TSTART = "20250718 000000"
TSTOP = "20250721 000000"


def domain_grid() -> dict:
    """시천면 ∪ 삼장면 경계 박스 + 여유를 50m 격자에 맞춘다. 저장소 안의 행정경계만 쓴다."""
    from shapely.geometry import shape
    from shapely.ops import unary_union

    fc = json.loads((REPO / "data" / "vector" / "adm_dong_5179.geojson").read_text(encoding="utf-8"))
    parts = [shape(f["geometry"]) for f in fc["features"]
             if f["properties"].get("sggnm") == "산청군" and f["properties"].get("name") in TOWNSHIPS]
    if len(parts) != len(TOWNSHIPS):
        raise SystemExit(f"행정경계에서 {TOWNSHIPS}를 다 찾지 못함({len(parts)}개)")
    minx, miny, maxx, maxy = unary_union(parts).bounds
    x0 = math.floor((minx - BUFFER_M) / DX) * DX
    y0 = math.floor((miny - BUFFER_M) / DX) * DX
    x1 = math.ceil((maxx + BUFFER_M) / DX) * DX
    y1 = math.ceil((maxy + BUFFER_M) / DX) * DX
    return {"x0": x0, "y0": y0, "mmax": int((x1 - x0) / DX), "nmax": int((y1 - y0) / DX),
            "footprint_5179": [x0, y0, x1, y1]}


def dry_run() -> int:
    g = domain_grid()
    print(f"격자 x0={g['x0']} y0={g['y0']} mmax={g['mmax']} nmax={g['nmax']} (dx={DX}m, EPSG:{EPSG})")
    print(f"footprint_5179 = {g['footprint_5179']}")
    for name, path in (("DEM", DEM), ("Manning", MANNING), ("강우", PRECIP)):
        print(f"  {name:8s} {'있음' if path.exists() else '없음'}  {path}")
    print(f"  빌드 폴더 {BUILD_ROOT} ({'ASCII' if str(BUILD_ROOT).isascii() else '한글 포함 — netCDF 오류 위험'})")
    return 0


def build() -> int:
    import pandas as pd
    from hydromt_sfincs import SfincsModel

    # hydromt-sfincs 1.2.2 x pandas 3.0 호환: 제거된 Index.is_integer 복원 (33과 같음)
    if not hasattr(pd.Index, "is_integer"):
        pd.Index.is_integer = lambda self: bool(pd.api.types.is_integer_dtype(self.dtype))
    missing = [p for p in (DEM, MANNING, PRECIP) if not p.exists()]
    if missing:
        raise SystemExit(f"입력 없음: {missing}")
    if not str(BUILD_ROOT).isascii():
        raise SystemExit(f"빌드 폴더는 ASCII 경로여야 한다: {BUILD_ROOT}")

    g = domain_grid()
    import shutil
    if BUILD_ROOT.exists():
        shutil.rmtree(BUILD_ROOT)
    BUILD_ROOT.mkdir(parents=True)
    mod = SfincsModel(root=str(BUILD_ROOT), mode="w+")
    mod.setup_grid(x0=g["x0"], y0=g["y0"], dx=DX, dy=DX, nmax=g["nmax"], mmax=g["mmax"], rotation=0, epsg=EPSG)
    mod.setup_dep(datasets_dep=[{"elevtn": str(DEM)}])
    mod.setup_mask_active(zmin=-5, fill_area=10, drop_area=0, reset_mask=True)
    mod.setup_mask_bounds(btype="outflow", zmax=120, reset_bounds=True)
    mod.setup_subgrid(datasets_dep=[{"elevtn": str(DEM)}], datasets_rgh=[{"manning": str(MANNING)}],
                      nr_subgrid_pixels=10, nlevels=10, write_dep_tif=True, write_man_tif=True)
    mod.setup_config(tref=TREF, tstart=TSTART, tstop=TSTOP,
                     dtout=3600.0, dthisout=600.0, dtmaxout=999999.0, alpha=0.5, advection=0)
    prc = pd.read_csv(PRECIP, parse_dates=["dt"]).set_index("dt")["precip_mm"]
    prc = prc.loc[pd.Timestamp("2025-07-18"):pd.Timestamp("2025-07-21")].to_frame(name="precip")
    mod.setup_precip_forcing(timeseries=prc)
    mod.write()
    print(f"=== 덕천강 상류 SFINCS 빌드 완료 -> {BUILD_ROOT}  (격자 {g['mmax']}x{g['nmax']})")
    print("다음: 이 폴더에서 sfincs.exe 실행 → --postprocess <sfincs_map.nc>")
    return 0


def postprocess(map_nc: Path) -> int:
    """sfincs_map.nc → 최대침수심 GeoTIFF. 34b와 같은 규칙(n=0이 남쪽이라 flipud, nodata=0)."""
    import numpy as np
    import rasterio
    import xarray as xr

    g = domain_grid()
    ds = xr.open_dataset(map_nc)
    zb = ds["zb"].values
    zsmax = ds["zsmax"].values
    if zsmax.ndim == 3:
        zsmax = zsmax[0]
    dep = np.where(np.isfinite(zsmax) & (zsmax > zb), zsmax - zb, 0.0).astype("float32")
    if dep.shape != (g["nmax"], g["mmax"]):
        raise SystemExit(f"격자 크기 불일치: map {dep.shape} vs 빌드 {(g['nmax'], g['mmax'])}")
    transform = rasterio.transform.from_origin(g["x0"], g["y0"] + g["nmax"] * DX, DX, DX)
    profile = dict(driver="GTiff", height=g["nmax"], width=g["mmax"], count=1, dtype="float32",
                   crs=f"EPSG:{EPSG}", transform=transform, nodata=0, compress="deflate")
    with rasterio.open(OUT_TIF, "w", **profile) as out:
        out.write(np.flipud(dep), 1)
    print(f"침수도 저장: 최대수심 {dep.max():.2f}m, 0.3m 초과 {(dep > 0.3).sum() * DX * DX / 1e6:.2f}km² -> {OUT_TIF}")
    return 0


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="덕천강 상류(시천·삼장) SFINCS 모델")
    ap.add_argument("--dry-run", action="store_true", help="격자와 입력 파일만 확인")
    ap.add_argument("--postprocess", type=Path, help="sfincs_map.nc → 최대침수심 GeoTIFF")
    args = ap.parse_args()
    if args.dry_run:
        return dry_run()
    if args.postprocess:
        return postprocess(args.postprocess)
    return build()


if __name__ == "__main__":
    sys.exit(main())
