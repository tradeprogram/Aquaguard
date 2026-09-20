"""
25_sfincs_build.py  (Module B — HydroMT-SFINCS 모델 빌드)  [env: sfincs]

산청 경호강 유역 SFINCS(국지관성 축소천수, Bates2010 / Leijnse2021 subgrid) 모델 빌드.
자체 solver 금지(SPEC §5) → Deltares SFINCS 재사용, HydroMT-SFINCS로 입력 생성.

1차 구성: 강우 강제(HRFCO 유역평균 546.9mm, 공간균일) + 하류 outflow 경계 + subgrid(5m).
입력 전부 실데이터·개방. 좌표 EPSG:5179. 이벤트 2025-07-18 00 ~ 07-21 00 KST.
실행:  conda run -n sfincs python scripts/25_sfincs_build.py
"""
from __future__ import annotations
import warnings; warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd, rasterio

ROOT = Path(r"G:/연구/공모전/아쿠아가드")
DEM = ROOT/"data"/"dem"/"산청_dem_5m_5179.tif"
MANNING = ROOT/"data"/"hydro"/"sancheong_manning_5m_5179.tif"
MODEL = ROOT/"models"/"sancheong_sfincs"
CRS = 5179
RES = 50           # 계산격자(m)
NSUB = 10          # subgrid 서브픽셀 (50/10=5m ≈ DEM)
TREF = "20250718 000000"; TSTART = "20250718 000000"; TSTOP = "20250721 000000"
BBOX = [127.7284, 35.2197, 128.0668, 35.5619]   # 산청 (WGS84, region용)

def load_precip():
    df = pd.read_csv(ROOT/"data"/"hydro"/"sfincs_precip_basinmean.csv", parse_dates=["dt"])
    df = df.set_index("dt")["precip_mm"]
    df = df.loc[pd.Timestamp("2025-07-18"):pd.Timestamp("2025-07-21")]
    return df.to_frame(name="precip")

def main():
    from hydromt_sfincs import SfincsModel

    if MODEL.exists():
        import shutil; shutil.rmtree(MODEL)
    MODEL.mkdir(parents=True, exist_ok=True)

    mod = SfincsModel(root=str(MODEL), mode="w+")

    # 1) 계산격자 (WGS84 bbox → EPSG:5179, res 50m)
    mod.setup_grid_from_region(region={"bbox": BBOX}, res=RES, crs=CRS, rotated=False)
    try:
        print("grid config:", {k:mod.config.get(k) for k in ("mmax","nmax","dx","dy","x0","y0","epsg")})
    except Exception as e:
        print("grid built (config read skip):", e)

    # 2) 지형 dep (5m DEM)
    mod.setup_dep(datasets_dep=[{"elevtn": str(DEM)}])

    # 3) 활성역: 유효 고도 셀 (해수면 이상)
    mod.setup_mask_active(zmin=-5, fill_area=10, drop_area=0, reset_mask=True)

    # 4) 하류 outflow 경계: 낮은 고도의 격자경계 셀 (물 유출) — 남강 하류측
    mod.setup_mask_bounds(btype="outflow", zmax=120, reset_bounds=True)

    # 5) subgrid (5m DEM + Manning 서브픽셀) → 하도 표현
    mod.setup_subgrid(datasets_dep=[{"elevtn": str(DEM)}],
                      datasets_rgh=[{"manning": str(MANNING)}],
                      nr_subgrid_pixels=NSUB, nlevels=10,
                      write_dep_tif=True, write_man_tif=True)

    # 6) config 시간·출력 (강우 forcing 시간슬라이싱 전에 반드시 먼저)
    mod.setup_config(tref=TREF, tstart=TSTART, tstop=TSTOP,
                     dtout=3600.0, dthisout=600.0, dtmaxout=999999.0,
                     alpha=0.5, advection=0)

    # 7) 강우 강제 (공간균일 유역평균)
    prc = load_precip()
    print("precip rows:", len(prc), "range", prc.index.min(), prc.index.max(), "sum", round(float(prc['precip'].sum()),1))
    mod.setup_precip_forcing(timeseries=prc)

    mod.write()
    print("=== SFINCS 빌드 완료 ->", MODEL)
    for f in sorted(MODEL.glob("*")):
        print("  ", f.name)

if __name__ == "__main__":
    main()
