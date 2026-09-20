"""
33_sfincs_build_reach.py  (Module B — SFINCS 경호강 구간 모델 빌드)  [env: sfincs]

ANUGA v1과 동일 구성으로 SFINCS(Deltares) 모델을 빌드 → 동일 참값으로 직접 비교.
SFINCS는 국지관성(축소물리)+subgrid라 세밀격자·배수를 빠르고 정확히 처리(ANUGA 한계 해소).

구성:
- 격자 50m, EPSG:5179, 구간 bbox(1028000,1703000~1042000,1723000) = 280×400
- dep: 5m DEM(reach_dem_5m.tif), subgrid: dep+Manning(reach_manning_5m.tif)
- 유입: 고읍교 유량 src(reach_inflow_고읍교 fw, peak 3019㎥/s)
- 하류: 수산교 수위경계(reach_stage_수산교 wse)
- 이벤트: 2025-07-18 00:00 ~ 07-20 12:00, 자연 spin-up

★ netCDF 한글경로 버그 회피 위해 ROOT를 ASCII 경로(scratchpad)에 빌드.
실행:  env python scripts/33_sfincs_build_reach.py
그다음 sfincs.exe를 이 폴더에서 실행 → sfincs_map.nc 검증.
"""
from __future__ import annotations
import warnings; warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd, geopandas as gpd
from shapely.geometry import Point
# hydromt-sfincs 1.2.2 x pandas 3.0 호환: 제거된 Index.is_integer 복원
if not hasattr(pd.Index, "is_integer"):
    pd.Index.is_integer = lambda self: bool(pd.api.types.is_integer_dtype(self.dtype))

PROOT=Path(r"G:/연구/공모전/아쿠아가드")
HY=PROOT/"data"/"hydro"
ROOT=Path(r"C:/Users/user/AppData/Local/Temp/claude/G----------------/4ca28ed5-e0c3-4be0-987f-f1bd326760dd/scratchpad/sfincs_reach")
DEM=HY/"reach_dem_5m.tif"; MANNING=HY/"reach_manning_5m.tif"
X0,Y0=1028000,1703000; DX=50; NMAX=400; MMAX=280; EPSG=5179
GOEUP=(1029983,1721527); SUSAN=(1039985,1704745)
TREF="20250718 000000"; TSTART="20250718 000000"; TSTOP="20250720 120000"

def ts_discharge():
    df=pd.read_csv(HY/"reach_inflow_고읍교.csv", parse_dates=["dt"])
    s=df.set_index("dt")["fw"].astype(float)
    s=s.loc[pd.Timestamp("2025-07-18"):pd.Timestamp("2025-07-20 12:00")]
    return pd.DataFrame({1:s.values}, index=s.index)

def ts_waterlevel():
    df=pd.read_csv(HY/"reach_stage_수산교.csv", parse_dates=["dt"])
    s=df.set_index("dt")["wse"].astype(float)
    s=s.loc[pd.Timestamp("2025-07-18"):pd.Timestamp("2025-07-20 12:00")]
    return pd.DataFrame({1:s.values}, index=s.index)

def main():
    from hydromt_sfincs import SfincsModel
    import shutil
    if ROOT.exists(): shutil.rmtree(ROOT)
    ROOT.mkdir(parents=True, exist_ok=True)
    mod=SfincsModel(root=str(ROOT), mode="w+")

    mod.setup_grid(x0=X0, y0=Y0, dx=DX, dy=DX, nmax=NMAX, mmax=MMAX, rotation=0, epsg=EPSG)
    mod.setup_dep(datasets_dep=[{"elevtn": str(DEM)}])
    mod.setup_mask_active(zmin=-5, fill_area=10, drop_area=0, reset_mask=True)
    # 하류(저지대 남측) 수위경계
    mod.setup_mask_bounds(btype="waterlevel", zmax=60, reset_bounds=True)
    mod.setup_subgrid(datasets_dep=[{"elevtn": str(DEM)}],
                      datasets_rgh=[{"manning": str(MANNING)}],
                      nr_subgrid_pixels=10, nlevels=10,
                      write_dep_tif=True, write_man_tif=True)
    # config 시간 먼저
    mod.setup_config(tref=TREF, tstart=TSTART, tstop=TSTOP,
                     dtout=3600.0, dthisout=600.0, dtmaxout=999999.0, alpha=0.5)
    # 유입(고읍교 discharge src)
    locq=gpd.GeoDataFrame({"index":[1]}, geometry=[Point(*GOEUP)], crs=f"EPSG:{EPSG}").set_index("index")
    mod.setup_discharge_forcing(timeseries=ts_discharge(), locations=locq)
    # 하류(수산교 waterlevel bnd)
    locw=gpd.GeoDataFrame({"index":[1]}, geometry=[Point(*SUSAN)], crs=f"EPSG:{EPSG}").set_index("index")
    mod.setup_waterlevel_forcing(timeseries=ts_waterlevel(), locations=locw, buffer=20000)

    mod.write()
    print("=== SFINCS 구간모델 빌드 완료 ->", ROOT)
    import os
    for f in sorted(os.listdir(ROOT)): print("  ", f)

if __name__=="__main__":
    main()
