"""
35_compare_engines.py  (ANUGA v1 vs SFINCS 공정 비교)  [env: sfincs]
두 모델 침수도를 동일 50m 격자·동일 SAR참값·동일 HAND<5m 평가역에서 재평가 → 공정 IoU/F1/POD/FAR.
WSE RMSE는 각 모델 시계열에서.
"""
from __future__ import annotations
import warnings; warnings.filterwarnings("ignore")
import json
from pathlib import Path
import numpy as np, pandas as pd, rasterio
from rasterio.warp import reproject, Resampling

PROOT=Path(r"G:/연구/공모전/아쿠아가드"); HY=PROOT/"data"/"hydro"; OUTP=PROOT/"outputs"; MD=PROOT/"models"/"anuga_reach"
X0,Y0,X1,Y1=1028000,1703000,1042000,1723000; GR=50; THR=0.3
# 공통 격자
W=int((X1-X0)/GR); H=int((Y1-Y0)/GR)
TR=rasterio.transform.from_origin(X0,Y1,GR,GR); SHP=(H,W); CRS="EPSG:5179"

def to_common(path,resamp,fill):
    with rasterio.open(path) as s: a=s.read(1).astype("float32"); st=s.transform; sc=s.crs
    dst=np.full(SHP,fill,dtype="float32"); reproject(a,dst,src_transform=st,src_crs=sc,dst_transform=TR,dst_crs=CRS,resampling=resamp); return dst

def metrics(dep, sar, fp):
    mod=(dep>THR)&fp; obs=sar&fp; valid=np.isfinite(dep)&fp
    TP=int((mod&obs).sum());FP=int((mod&~obs&valid).sum());FN=int((~mod&obs&valid).sum())
    iou=TP/max(TP+FP+FN,1);prec=TP/max(TP+FP,1);pod=TP/max(TP+FN,1);f1=2*prec*pod/max(prec+pod,1e-9);far=FP/max(FP+TP,1)
    return dict(IoU=round(iou,3),F1=round(f1,3),POD=round(pod,3),FAR=round(far,3),precision=round(prec,3),
                flood_km2=round(mod.sum()*GR*GR/1e6,2))

def wse_rmse(ts_csv, col, is_dt):
    obs=pd.read_csv(HY/"reach_valid_경호교.csv", parse_dates=["dt"])
    sim=pd.read_csv(OUTP/ts_csv)
    if is_dt:
        sim["dt"]=pd.to_datetime(sim["dt"]); key="dt"; m=pd.merge(sim[[key,col]],obs[["dt","wse"]],on="dt",how="inner")
    else:
        m=pd.merge(sim[["t_sec",col]],obs[["t_sec","wse"]],on="t_sec",how="inner")
    if not len(m): return None,None
    return round(float(np.sqrt(((m[col]-m["wse"])**2).mean())),2), round(float(sim[col].max()),2)

def main():
    sar=to_common(HY/"sar_flood_extent_2025-07-19.tif",Resampling.max,0)>0.5
    hand=to_common(HY/"reach_hand_5m.tif",Resampling.min,9999); fp=hand<5.0
    anuga=to_common(MD/"anuga_maxdepth_100m.tif",Resampling.bilinear,0)
    sfincs=to_common(MD/"sfincs_maxdepth_50m.tif",Resampling.bilinear,0)

    res={"eval":"공통 50m격자·동일 SAR·HAND<5m 평가역","obs_flood_km2":round((sar&fp).sum()*GR*GR/1e6,2),
         "ANUGA_v1":{**metrics(anuga,sar,fp)}, "SFINCS":{**metrics(sfincs,sar,fp)}}
    r1,p1=wse_rmse("anuga_reach_timeseries.csv","WSE_경호교",False)
    r2,p2=wse_rmse("sfincs_reach_wse.csv","WSE_sim",True)
    res["ANUGA_v1"]["WSE_rmse_m"]=r1; res["ANUGA_v1"]["WSE_peak_m"]=p1
    res["SFINCS"]["WSE_rmse_m"]=r2; res["SFINCS"]["WSE_peak_m"]=p2
    (OUTP/"module_b_engine_comparison.json").write_text(json.dumps(res,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(res,ensure_ascii=False,indent=2))
    print(f"\n{'':10s}{'IoU':>7s}{'F1':>7s}{'POD':>7s}{'FAR':>7s}{'WSE RMSE':>10s}{'WSE peak':>10s}  (obs peak 94.12)")
    for e in ["ANUGA_v1","SFINCS"]:
        d=res[e]; print(f"{e:10s}{d['IoU']:>7}{d['F1']:>7}{d['POD']:>7}{d['FAR']:>7}{str(d['WSE_rmse_m'])+'m':>10s}{str(d['WSE_peak_m'])+'m':>10s}")

if __name__=="__main__": main()
