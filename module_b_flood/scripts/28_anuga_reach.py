"""
28_anuga_reach.py  (Module B — ANUGA 경호강 구간 홍수 시뮬레이션)  [env: anuga]

SFINCS 바이너리(Deltares)는 로그인 배포라 확보불가 → SPEC 승인 대체엔진 ANUGA
(호주 ANU/Geoscience Australia, 완전 2D 천수방정식 유한체적)로 산청 홍수 재현.
자체 solver 금지 준수(기성 오픈모델 재사용).

구간: 경호강 고읍교(상류)→경호교(검증)→수산교(하류), 실측 수문곡선 강제.
- 상류 유입: 고읍교 유량 Q(t) (peak 3019㎥/s)  [Inlet_operator]
- 하류 수위: 수산교 WSE(t) (peak 59.69m)        [stage boundary]
- 검증: 경호교 WSE(t) (obs peak 94.12m) RMSE + SAR 침수범위 IoU
지형/조도: 5m DEM·ESA WorldCover Manning (구간 클립).

실행:  conda run -n anuga python scripts/28_anuga_reach.py
정직: 대체엔진(ANUGA)임을 명시. 급경사 구간이라 격자·시간창 제약. 결과 그대로 보고.
"""
from __future__ import annotations
import warnings; warnings.filterwarnings("ignore")
import json, time as _time
from pathlib import Path
import numpy as np, pandas as pd, rasterio
from scipy.interpolate import RegularGridInterpolator

ROOT = Path(r"G:/연구/공모전/아쿠아가드"); HY = ROOT/"data"/"hydro"; OUTP = ROOT/"outputs"
MODELDIR = ROOT/"models"/"anuga_reach"; MODELDIR.mkdir(parents=True, exist_ok=True)
# netCDF4가 한글경로 .sww를 못 만듦 → ASCII 경로에 sww 기록
SWWDIR = Path(r"C:/Users/user/AppData/Local/Temp/claude/G----------------/4ca28ed5-e0c3-4be0-987f-f1bd326760dd/scratchpad/anuga_sww")
SWWDIR.mkdir(parents=True, exist_ok=True)

# 구간 bbox(5179) — 클립 DEM과 동일
X0,Y0,X1,Y1 = 1028000,1703000,1042000,1723000
RES = 100.0                       # 격자(m) — 150→100 세분(채널 표현↑)
# 시간창: t_sec 기준(tstart=2025-07-18 00:00). 피크 07-19 13시(t=133200)
# full spin-up: 07-18 06:00부터 시작 → 채널을 미리 채워 dry-start 아티팩트 제거
T_SIM_START = 21600              # 07-18 06:00
T_SIM_STOP  = 165600             # 07-19 22:00 (40h, 31h spin-up + 피크 + 감쇠)
YIELD = 600.0
GHEO = {"고읍교":(1029983,1721527),"경호교":(1033994,1713655),"수산교":(1039985,1704745)}

def interp_from_raster(path, fill):
    with rasterio.open(path) as ds:
        a = ds.read(1).astype("float64"); tr = ds.transform; H,W = a.shape
    a = np.where(np.isfinite(a), a, fill)
    xs = tr.c + (np.arange(W)+0.5)*tr.a
    ys = tr.f + (np.arange(H)+0.5)*tr.e     # tr.e<0
    order = np.argsort(ys)
    f = RegularGridInterpolator((ys[order], xs), a[order,:], bounds_error=False, fill_value=fill)
    def g(x,y):
        pts = np.column_stack([np.clip(y, ys.min(), ys.max()), np.clip(x, xs.min(), xs.max())])
        return f(pts)
    return g

def hydro_interp(csv, tcol, vcol):
    df = pd.read_csv(HY/csv)
    t = df[tcol].values.astype(float); v = pd.to_numeric(df[vcol], errors="coerce").values
    ok = np.isfinite(v); t,v = t[ok], v[ok]
    return lambda tt: float(np.interp(tt, t, v))

def main():
    import anuga
    t_wall = _time.time()

    elev_f = interp_from_raster(HY/"reach_dem_5m.tif", fill=1200.0)
    man_f  = interp_from_raster(HY/"reach_manning_5m.tif", fill=0.04)
    Qup    = hydro_interp("reach_inflow_고읍교.csv", "t_sec", "fw")     # 유량
    Sdn    = hydro_interp("reach_stage_수산교.csv", "t_sec", "wse")     # 하류 WSE

    # 격자
    m = int((X1-X0)/RES); n = int((Y1-Y0)/RES)
    print(f"mesh {m}x{n} rect (~{m*n*4:,} tri) @ {RES}m")
    points, vertices, boundary = anuga.rectangular_cross(m, n, len1=(X1-X0), len2=(Y1-Y0), origin=(X0,Y0))
    domain = anuga.Domain(points, vertices, boundary)
    domain.set_name("anuga_reach"); domain.set_datadir(str(SWWDIR))
    domain.set_store(False)   # .sww 저장 끔(한글경로 netCDF 회피·속도↑) — maxdepth/WSE는 파이썬에서 직접 집계
    domain.set_flow_algorithm("DE0")
    domain.set_quantity("elevation", function=lambda x,y: elev_f(x,y), location="centroids")
    domain.set_quantity("friction",  function=lambda x,y: np.clip(man_f(x,y),0.02,0.2), location="centroids")
    domain.set_quantity("stage", expression="elevation")   # dry start

    # 하류(bottom, y=Y0) 수위경계, 나머지 반사
    def stage_bc(t):  # t는 sim시작 기준 → 절대 t_sec로 변환
        return Sdn(T_SIM_START + t)
    Bstage = anuga.Transmissive_momentum_set_stage_boundary(domain, function=stage_bc)
    Bref = anuga.Reflective_boundary(domain)
    domain.set_boundary({"bottom":Bstage, "top":Bref, "left":Bref, "right":Bref})

    # 상류 유입(고읍교) — 계곡 횡단선
    gx,gy = GHEO["고읍교"]
    inlet_line = [[gx-700, gy],[gx+700, gy]]
    inlet = anuga.Inlet_operator(domain, inlet_line, Q=Qup(T_SIM_START))

    # 검증점 최근접 센트로이드 인덱스
    cc = domain.get_centroid_coordinates(absolute=True)
    def nearest(xy):
        return int(np.argmin((cc[:,0]-xy[0])**2+(cc[:,1]-xy[1])**2))
    idx = {k:nearest(v) for k,v in GHEO.items()}

    stage_q = domain.quantities["stage"]; elev_q = domain.quantities["elevation"]
    elev_c = elev_q.centroid_values.copy()
    maxdepth = np.zeros(domain.number_of_triangles)
    rec = []
    print("evolve 시작...")
    for t in domain.evolve(yieldstep=YIELD, finaltime=(T_SIM_STOP-T_SIM_START)):
        inlet.set_Q(Qup(T_SIM_START + t))
        sc = stage_q.centroid_values
        depth = np.maximum(sc - elev_c, 0.0)
        maxdepth = np.maximum(maxdepth, depth)
        row = {"t_sec": int(T_SIM_START+t)}
        for k,i in idx.items(): row[f"WSE_{k}"] = float(sc[i]); row[f"h_{k}"]=float(max(sc[i]-elev_c[i],0))
        rec.append(row)
        if int(t) % 3600 == 0:
            print(f"  t={int(t)//3600}h  경호교WSE={row['WSE_경호교']:.2f} h={row['h_경호교']:.2f}  wet={int((depth>0.1).sum())}  {(_time.time()-t_wall):.0f}s")

    df = pd.DataFrame(rec); df.to_csv(OUTP/"anuga_reach_timeseries.csv", index=False, encoding="utf-8-sig")
    # 크래시 안전: maxdepth+좌표 즉시 저장(ASCII 경로)
    np.savez(str(SWWDIR/"maxdepth.npz"), cc=cc, maxdepth=maxdepth, elev=elev_c)
    print("maxdepth npz 저장, 래스터화...")

    # 최대침수 래스터화(100m) — nearest(cKDTree, QHull 회피)
    grid_res=100
    gx_ = np.arange(X0+grid_res/2, X1, grid_res); gy_ = np.arange(Y0+grid_res/2, Y1, grid_res)
    from scipy.spatial import cKDTree
    GX,GY = np.meshgrid(gx_, gy_)
    tree = cKDTree(cc)
    dist, ii = tree.query(np.column_stack([GX.ravel(), GY.ravel()]), k=1)
    mdf = maxdepth[ii]; mdf[dist > grid_res*1.5] = 0.0   # 셀 밖 채움(1D)
    md = np.flipud(mdf.reshape(GX.shape))
    tr = rasterio.transform.from_origin(X0, Y1, grid_res, grid_res)
    prof = dict(driver="GTiff",height=md.shape[0],width=md.shape[1],count=1,dtype="float32",
                crs="EPSG:5179",transform=tr,nodata=0,compress="deflate")
    with rasterio.open(MODELDIR/"anuga_maxdepth_100m.tif","w",**prof) as ds: ds.write(md.astype("float32"),1)

    # 검증: 경호교 WSE peak
    obs = pd.read_csv(HY/"reach_valid_경호교.csv"); obs_peak=float(pd.to_numeric(obs["wse"],errors="coerce").max())
    sim_peak=float(df["WSE_경호교"].max())
    meta={"engine":"ANUGA (SPEC 승인 대체, SFINCS 바이너리 로그인배포로 미확보)",
          "mesh":f"{m}x{n} rect @ {RES}m","sim_window_tsec":[T_SIM_START,T_SIM_STOP],
          "runtime_s":round(_time.time()-t_wall,0),
          "valid_경호교_WSE":{"obs_peak_m":round(obs_peak,2),"sim_peak_m":round(sim_peak,2),
                              "diff_m":round(sim_peak-obs_peak,2)},
          "maxdepth_raster":"models/anuga_reach/anuga_maxdepth_100m.tif",
          "wet_cells_max":int((maxdepth>0.1).sum())}
    (OUTP/"anuga_reach_meta.json").write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding="utf-8")
    print("\n=== 결과 ==="); print(json.dumps(meta,ensure_ascii=False,indent=2))

if __name__=="__main__": main()
