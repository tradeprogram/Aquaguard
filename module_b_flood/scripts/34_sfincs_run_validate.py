"""
34_sfincs_run_validate.py  (Module B — SFINCS 실행 + 검증)  [env: sfincs]

사용법: python scripts/34_sfincs_run_validate.py "<sfincs.exe 경로>"
  예: python scripts/34_sfincs_run_validate.py "C:/Users/user/Downloads/SFINCS_2026_01_release/sfincs.exe"

1) ASCII root(scratchpad/sfincs_reach)에서 sfincs.exe 실행 → sfincs_map.nc
2) zsmax→최대침수심 래스터(5179), zs(t)@경호교→WSE 시계열
3) 검증: IoU/F1/POD/FAR vs Sentinel-1(HAND<5m 공정평가), 경호교 WSE RMSE — ANUGA와 동일 참값
결과: outputs/sfincs_reach_*.{json,csv}, models/anuga_reach/sfincs_maxdepth_50m.tif
"""
from __future__ import annotations
import warnings; warnings.filterwarnings("ignore")
import sys, subprocess, json, time
from pathlib import Path
import numpy as np, pandas as pd, xarray as xr, rasterio
from rasterio.warp import reproject, Resampling

PROOT=Path(r"G:/연구/공모전/아쿠아가드")
HY=PROOT/"data"/"hydro"; OUTP=PROOT/"outputs"; MD=PROOT/"models"/"anuga_reach"
ROOT=Path(r"C:/Users/user/AppData/Local/Temp/claude/G----------------/4ca28ed5-e0c3-4be0-987f-f1bd326760dd/scratchpad/sfincs_reach")
GYEONGHO=(1033994,1713655); GHDT=85.446
DEPTH_THR=0.3

def run_sfincs(exe):
    print("SFINCS 실행:", exe)
    t0=time.time()
    with open(ROOT/"sfincs_log.txt","w") as log:
        r=subprocess.run([exe], cwd=str(ROOT), stdout=log, stderr=subprocess.STDOUT, timeout=3600)
    print(f"  종료코드 {r.returncode}, {time.time()-t0:.0f}s")
    return r.returncode

def main():
    if len(sys.argv)<2:
        print("사용법: python scripts/34_sfincs_run_validate.py <sfincs.exe 경로>"); return
    exe=sys.argv[1]
    if not Path(exe).exists():
        print("exe 없음:", exe); return
    rc=run_sfincs(exe)
    mapf=ROOT/"sfincs_map.nc"
    if not mapf.exists():
        print("sfincs_map.nc 생성 안됨. sfincs_log.txt 확인 필요.");
        print((ROOT/"sfincs_log.txt").read_text(errors="ignore")[-1500:]); return

    ds=xr.open_dataset(mapf)
    print("map vars:", list(ds.data_vars))
    # 격자 좌표
    xc=ds["x"].values if "x" in ds else ds["xc"].values
    yc=ds["y"].values if "y" in ds else ds["yc"].values
    zb=ds["zb"].values if "zb" in ds else None
    zsmax=ds["zsmax"].values if "zsmax" in ds else ds["zs"].max("time").values
    if zsmax.ndim==3: zsmax=np.nanmax(zsmax,axis=0)
    dep=np.where(zb is not None, zsmax-zb, np.nan)
    dep=np.where(np.isfinite(dep)&(dep>0), dep, 0.0)

    # 래스터 저장(5179 grid)
    if xc.ndim==1:
        # 1D coords → transform
        dx=abs(xc[1]-xc[0]); dy=abs(yc[1]-yc[0])
        x0=xc.min()-dx/2; y1=yc.max()+dy/2
        arr=dep if yc[0]<yc[-1] else dep  # 방향 확인
        # y 오름차순이면 flip
        if yc[0]<yc[-1]: arr=np.flipud(dep)
        tr=rasterio.transform.from_origin(x0,y1,dx,dy)
        H,W=arr.shape
    else:
        arr=dep; tr=None
    prof=dict(driver="GTiff",height=arr.shape[0],width=arr.shape[1],count=1,dtype="float32",
              crs="EPSG:5179",transform=tr,nodata=0,compress="deflate")
    outtif=MD/"sfincs_maxdepth_50m.tif"
    with rasterio.open(outtif,"w",**prof) as o: o.write(arr.astype("float32"),1)
    print("saved ->", outtif.name)

    # 경호교 WSE 시계열
    zs=ds["zs"].values  # (time, n, m) or (time, npoints)
    tt=pd.to_datetime(ds["time"].values)
    # 경호교 최근접 셀
    if xc.ndim==1:
        ci=np.argmin(np.abs(xc-GYEONGHO[0])); ri=np.argmin(np.abs(yc-GYEONGHO[1]))
        wse=zs[:,ri,ci] if zs.ndim==3 else None
    if wse is not None:
        sim=pd.DataFrame({"dt":tt,"WSE_sim":wse})
        obs=pd.read_csv(HY/"reach_valid_경호교.csv", parse_dates=["dt"])
        m=pd.merge(sim,obs[["dt","wse"]],on="dt",how="inner")
        rmse=float(np.sqrt(((m["WSE_sim"]-m["wse"])**2).mean())) if len(m) else None
        sim.to_csv(OUTP/"sfincs_reach_wse.csv",index=False,encoding="utf-8-sig")
        print(f"경호교 WSE: sim피크 {np.nanmax(wse):.2f} obs 94.12 | RMSE {rmse} 겹침{len(m)}")

    # 검증(IoU vs SAR, HAND<5m) — 29 로직 재사용
    from rasterio.warp import reproject as rpj
    with rasterio.open(outtif) as d: depr=d.read(1).astype("float32"); dtr=d.transform; dcrs=d.crs; shp=d.shape
    model_flood=depr>DEPTH_THR
    def to_grid(path,resamp,fill):
        with rasterio.open(path) as s: a=s.read(1).astype("float32"); st=s.transform; sc=s.crs
        dst=np.full(shp,fill,dtype="float32"); rpj(a,dst,src_transform=st,src_crs=sc,dst_transform=dtr,dst_crs=dcrs,resampling=resamp); return dst
    sar=to_grid(HY/"sar_flood_extent_2025-07-19.tif",Resampling.max,0)>0.5
    hand=to_grid(HY/"reach_hand_5m.tif",Resampling.min,9999)
    fp=hand<5.0
    obs_f=sar&fp; mod_f=model_flood&fp; valid=np.isfinite(depr)&fp
    TP=int((mod_f&obs_f).sum());FP=int((mod_f&~obs_f&valid).sum());FN=int((~mod_f&obs_f&valid).sum())
    iou=TP/max(TP+FP+FN,1);prec=TP/max(TP+FP,1);pod=TP/max(TP+FN,1);f1=2*prec*pod/max(prec+pod,1e-9);far=FP/max(FP+TP,1)
    res={"engine":"SFINCS (50m+subgrid, reduced-physics)","returncode":rc,
         "extent_vs_S1":{"IoU":round(iou,3),"F1":round(f1,3),"POD":round(pod,3),"FAR":round(far,3),"precision":round(prec,3)},
         "gyeongho_WSE_rmse_m":round(rmse,2) if 'rmse' in dir() and rmse else None,
         "gyeongho_sim_peak_m":round(float(np.nanmax(wse)),2) if wse is not None else None}
    (OUTP/"sfincs_reach_validation.json").write_text(json.dumps(res,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(res,ensure_ascii=False,indent=2))

if __name__=="__main__": main()
