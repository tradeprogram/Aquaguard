"""
34b_sfincs_postprocess.py  (SFINCS map.nc → 침수도 + 경호교 WSE + 검증)  [env: sfincs]
34가 만든 sfincs_map.nc(이미 실행됨)를 올바른 격자구조(2D x/y, zs(time,n,m))로 후처리.
"""
from __future__ import annotations
import warnings; warnings.filterwarnings("ignore")
import json
from pathlib import Path
import numpy as np, pandas as pd, xarray as xr, rasterio
from rasterio.warp import reproject, Resampling

PROOT=Path(r"G:/연구/공모전/아쿠아가드"); HY=PROOT/"data"/"hydro"; OUTP=PROOT/"outputs"; MD=PROOT/"models"/"anuga_reach"
SF=Path(r"C:/Users/user/AppData/Local/Temp/claude/G----------------/4ca28ed5-e0c3-4be0-987f-f1bd326760dd/scratchpad/sfincs_reach")
X0,Y0,DX,NMAX,MMAX=1028000,1703000,50,400,280
GYEONGHO=(1033994,1713655); DEPTH_THR=0.3

def main():
    ds=xr.open_dataset(SF/"sfincs_map.nc")
    x=ds["x"].values; y=ds["y"].values           # (n,m) 셀중심
    zb=ds["zb"].values
    zsmax=ds["zsmax"].values
    if zsmax.ndim==3: zsmax=zsmax[0]
    dep=np.where(np.isfinite(zsmax)&(zsmax>zb), zsmax-zb, 0.0).astype("float32")

    # 래스터(5179): n=0이 남(y0), 위로 북 → GeoTIFF는 flipud
    arr=np.flipud(dep)
    tr=rasterio.transform.from_origin(X0, Y0+NMAX*DX, DX, DX)
    prof=dict(driver="GTiff",height=NMAX,width=MMAX,count=1,dtype="float32",crs="EPSG:5179",transform=tr,nodata=0,compress="deflate")
    outtif=MD/"sfincs_maxdepth_50m.tif"
    with rasterio.open(outtif,"w",**prof) as o: o.write(arr,1)
    print(f"침수도 저장: 최대수심 {dep.max():.2f}m, 침수(>0.3m) {(dep>0.3).sum()*DX*DX/1e6:.2f}km² -> {outtif.name}")

    # 경호교 WSE 시계열(최근접 셀)
    d2=(x-GYEONGHO[0])**2+(y-GYEONGHO[1])**2
    ri,ci=np.unravel_index(np.argmin(d2), d2.shape)
    zs=ds["zs"].values  # (time,n,m)
    wse=zs[:,ri,ci]; tt=pd.to_datetime(ds["time"].values)
    sim=pd.DataFrame({"dt":tt,"WSE_sim":wse})
    sim.to_csv(OUTP/"sfincs_reach_wse.csv",index=False,encoding="utf-8-sig")
    obs=pd.read_csv(HY/"reach_valid_경호교.csv", parse_dates=["dt"])
    m=pd.merge(sim,obs[["dt","wse"]],on="dt",how="inner")
    rmse=float(np.sqrt(((m["WSE_sim"]-m["wse"])**2).mean())) if len(m) else None
    simpeak=float(np.nanmax(wse)); obspeak=float(obs["wse"].max())
    print(f"경호교 WSE: sim피크 {simpeak:.2f} obs {obspeak:.2f} | 차 {simpeak-obspeak:+.2f}m | RMSE {rmse:.2f}m (겹침 {len(m)})")

    # 검증: IoU vs SAR (HAND<5m)
    with rasterio.open(outtif) as d: depr=d.read(1).astype("float32"); dtr=d.transform; dcrs=d.crs; shp=d.shape
    model_flood=depr>DEPTH_THR
    def to_grid(path,resamp,fill):
        with rasterio.open(path) as s: a=s.read(1).astype("float32"); st=s.transform; sc=s.crs
        dst=np.full(shp,fill,dtype="float32"); reproject(a,dst,src_transform=st,src_crs=sc,dst_transform=dtr,dst_crs=dcrs,resampling=resamp); return dst
    sar=to_grid(HY/"sar_flood_extent_2025-07-19.tif",Resampling.max,0)>0.5
    hand=to_grid(HY/"reach_hand_5m.tif",Resampling.min,9999); fp=hand<5.0
    obs_f=sar&fp; mod_f=model_flood&fp; valid=np.isfinite(depr)&fp
    TP=int((mod_f&obs_f).sum());FP=int((mod_f&~obs_f&valid).sum());FN=int((~mod_f&obs_f&valid).sum())
    iou=TP/max(TP+FP+FN,1);prec=TP/max(TP+FP,1);pod=TP/max(TP+FN,1);f1=2*prec*pod/max(prec+pod,1e-9);far=FP/max(FP+TP,1)
    res={"engine":"SFINCS v2.4.0 (50m + subgrid, 국지관성)","runtime_note":"2.5일 시뮬 43초",
         "extent_vs_S1_HAND":{"IoU":round(iou,3),"F1":round(f1,3),"POD":round(pod,3),"FAR":round(far,3),"precision":round(prec,3),"TP":TP,"FP":FP,"FN":FN},
         "model_flood_km2":round(mod_f.sum()*DX*DX/1e6,2),"obs_flood_km2":round(obs_f.sum()*DX*DX/1e6,2),
         "gyeongho_WSE":{"obs_peak":round(obspeak,2),"sim_peak":round(simpeak,2),"diff_m":round(simpeak-obspeak,2),"rmse_m":round(rmse,2) if rmse else None}}
    (OUTP/"sfincs_reach_validation.json").write_text(json.dumps(res,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(res,ensure_ascii=False,indent=2))

if __name__=="__main__": main()
