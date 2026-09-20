"""
30_plot_module_b.py  (Module B 결과 시각화)
좌: ANUGA 모의 최대침수심 + Sentinel-1 관측 홍수 윤곽 + 관측소
우: 경호교 수면표고(WSE) 관측 vs 모의 수문곡선
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

def main():
    rpath=MD/"anuga_maxdepth_100m.tif"   # v1 = 공식(최선)
    tspath=OUTP/"anuga_reach_timeseries.csv"
    with rasterio.open(rpath) as ds:
        dep=ds.read(1).astype("float32"); tr=ds.transform; shape=ds.shape; ext=[ds.bounds.left,ds.bounds.right,ds.bounds.bottom,ds.bounds.top]
    with rasterio.open(HY/"sar_flood_extent_2025-07-19.tif") as ds:
        sar=ds.read(1).astype("float32"); str_=ds.transform; scrs=ds.crs
    sar_on=np.zeros(shape,dtype="float32")
    reproject(sar,sar_on,src_transform=str_,src_crs=scrs,dst_transform=tr,dst_crs="EPSG:5179",resampling=Resampling.max)

    fig,(ax1,ax2)=plt.subplots(1,2,figsize=(15,7))
    dshow=np.where(dep>0.05,dep,np.nan)
    im=ax1.imshow(dshow,extent=ext,origin="upper",cmap="Blues",vmin=0,vmax=6)
    ax1.contour(np.flipud(sar_on),levels=[0.5],extent=ext,origin="upper",colors="red",linewidths=0.7)
    for nm,(x,y) in GA.items():
        ax1.plot(x,y,"k^",ms=9); ax1.annotate(nm,(x,y),textcoords="offset points",xytext=(6,4),fontsize=9)
    ax1.set_title("ANUGA max flood depth (blue) vs Sentinel-1 flood (red outline)\nGyeongho R. reach, 2025-07-19 event")
    ax1.set_xlabel("EPSG:5179 X (m)"); ax1.set_ylabel("Y (m)")
    plt.colorbar(im,ax=ax1,label="depth (m)",shrink=0.8)
    meta=json.loads((OUTP/"module_b_validation.json").read_text(encoding="utf-8"))
    e=meta["extent_vs_S1"]
    ax1.text(0.02,0.02,f"IoU {e['IoU']}  F1 {e['F1']}  POD {e['POD']}  FAR {e['FAR']}",
             transform=ax1.transAxes,fontsize=10,bbox=dict(fc="white",alpha=0.8))

    sim=pd.read_csv(tspath); obs=pd.read_csv(HY/"reach_valid_경호교.csv")
    sim["h"]=(sim["t_sec"]-sim["t_sec"].min())/3600; obs2=obs.copy()
    ax2.plot(pd.to_numeric(obs["t_sec"]),pd.to_numeric(obs["wse"]),"o-",color="k",label="Observed (HRFCO Gyeongho)")
    ax2.plot(sim["t_sec"],sim["WSE_경호교"],"s--",color="tab:blue",label="ANUGA simulated")
    ax2.axvline(133200,color="r",ls=":",alpha=0.6,label="Obs peak 07-19 13:00")
    ax2.set_title(f"Gyeongho gauge WSE: obs vs sim\nRMSE {meta['gyeongho_WSE_rmse_m']} m, peak diff +{meta['gyeongho_WSE']['diff_m']} m")
    ax2.set_xlabel("time (s from 2025-07-18 00:00)"); ax2.set_ylabel("Water surface elevation (m)")
    ax2.legend(); ax2.grid(alpha=0.3)
    plt.tight_layout(); plt.savefig(OUTP/"module_b_result.png",dpi=130,bbox_inches="tight")
    print("saved -> outputs/module_b_result.png")

if __name__=="__main__": main()
