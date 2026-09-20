"""
36_plot_sfincs.py  (SFINCS 결과 + ANUGA 비교 시각화)
좌: SFINCS 최대침수심 + Sentinel-1 홍수윤곽 + 관측소
우: 경호교 WSE — 관측 vs SFINCS vs ANUGA (SFINCS의 정확도·속도 우위)
"""
from __future__ import annotations
import warnings; warnings.filterwarnings("ignore")
import json
from pathlib import Path
import numpy as np, pandas as pd, rasterio
from rasterio.warp import reproject, Resampling
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT=Path(r"G:/연구/공모전/아쿠아가드"); HY=ROOT/"data"/"hydro"; MD=ROOT/"models"/"anuga_reach"; OUTP=ROOT/"outputs"
GA={"Goeup(up)":(1029983,1721527),"Gyeongho(valid)":(1033994,1713655),"Susan(down)":(1039985,1704745)}
T0=pd.Timestamp("2025-07-18")

def main():
    with rasterio.open(MD/"sfincs_maxdepth_50m.tif") as ds:
        dep=ds.read(1).astype("float32"); tr=ds.transform; shp=ds.shape
        ext=[ds.bounds.left,ds.bounds.right,ds.bounds.bottom,ds.bounds.top]
    with rasterio.open(HY/"sar_flood_extent_2025-07-19.tif") as ds:
        sar=ds.read(1).astype("float32"); st=ds.transform; sc=ds.crs
    sar_on=np.zeros(shp,dtype="float32")
    reproject(sar,sar_on,src_transform=st,src_crs=sc,dst_transform=tr,dst_crs="EPSG:5179",resampling=Resampling.max)

    cmp=json.loads((OUTP/"module_b_engine_comparison.json").read_text(encoding="utf-8"))
    sf=cmp["SFINCS"]; an=cmp["ANUGA_v1"]

    fig,(ax1,ax2)=plt.subplots(1,2,figsize=(15,7))
    dshow=np.where(dep>0.05,dep,np.nan)
    im=ax1.imshow(dshow,extent=ext,origin="upper",cmap="Blues",vmin=0,vmax=6)
    ax1.contour(np.flipud(sar_on),levels=[0.5],extent=ext,origin="upper",colors="red",linewidths=0.7)
    for nm,(x,y) in GA.items():
        ax1.plot(x,y,"k^",ms=9); ax1.annotate(nm,(x,y),textcoords="offset points",xytext=(6,4),fontsize=9)
    ax1.set_title("SFINCS max flood depth (blue) vs Sentinel-1 (red)\nGyeongho R. reach, 2025-07-19  |  2.5-day sim in 43 s")
    ax1.set_xlabel("EPSG:5179 X (m)"); ax1.set_ylabel("Y (m)")
    plt.colorbar(im,ax=ax1,label="depth (m)",shrink=0.8)
    ax1.text(0.02,0.02,f"IoU {sf['IoU']}  F1 {sf['F1']}  POD {sf['POD']}  FAR {sf['FAR']}",
             transform=ax1.transAxes,fontsize=10,bbox=dict(fc="white",alpha=0.85))

    obs=pd.read_csv(HY/"reach_valid_경호교.csv"); obs["dt"]=T0+pd.to_timedelta(obs["t_sec"],unit="s")
    sfw=pd.read_csv(OUTP/"sfincs_reach_wse.csv"); sfw["dt"]=pd.to_datetime(sfw["dt"])
    anw=pd.read_csv(OUTP/"anuga_reach_timeseries.csv"); anw["dt"]=T0+pd.to_timedelta(anw["t_sec"],unit="s")
    ax2.plot(obs["dt"],obs["wse"],"o-",color="k",lw=2,label="Observed (HRFCO)")
    ax2.plot(sfw["dt"],sfw["WSE_sim"],"s-",color="tab:blue",label=f"SFINCS (RMSE {sf['WSE_rmse_m']} m)")
    ax2.plot(anw["dt"],anw["WSE_경호교"],"^--",color="tab:orange",alpha=0.8,label=f"ANUGA (RMSE {an['WSE_rmse_m']} m)")
    ax2.axvline(pd.Timestamp("2025-07-19 13:00"),color="r",ls=":",alpha=0.5)
    ax2.set_title("Gyeongho gauge water level: obs vs SFINCS vs ANUGA")
    ax2.set_xlabel("date"); ax2.set_ylabel("Water surface elevation (m)")
    ax2.legend(); ax2.grid(alpha=0.3)
    for lb in ax2.get_xticklabels(): lb.set_rotation(30); lb.set_ha("right")
    plt.tight_layout(); plt.savefig(OUTP/"module_b_sfincs_result.png",dpi=130,bbox_inches="tight")
    print("saved -> outputs/module_b_sfincs_result.png")

if __name__=="__main__": main()
