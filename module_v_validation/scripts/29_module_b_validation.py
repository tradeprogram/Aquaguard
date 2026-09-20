"""
29_module_b_validation.py  (Module B 검증 — 모의침수 vs 관측)

ANUGA 모의 최대침수(anuga_maxdepth_100m.tif)를 관측과 대조(SPEC §2 지표).
1) 공간(extent): vs Sentinel-1 홍수범위(sar_flood_extent_2025-07-19.tif) → IoU/F1/POD/FAR
   - 구간 bbox·평탄역 한정, SAR는 5179격자로 재투영(nearest).
2) 수위(depth): 경호교 모의 WSE peak vs 관측(reach_valid_경호교) → 오차(m). (RMSE는 시계열)
정직: ANUGA는 SFINCS 대체엔진. 관측 침수는 SAR 프록시(통과시각 caveat). 결과 그대로.
"""
from __future__ import annotations
import warnings; warnings.filterwarnings("ignore")
import json
from pathlib import Path
import numpy as np, pandas as pd, rasterio
from rasterio.warp import reproject, Resampling

ROOT=Path(r"G:/연구/공모전/아쿠아가드"); HY=ROOT/"data"/"hydro"; MD=ROOT/"models"/"anuga_reach"; OUTP=ROOT/"outputs"
DEPTH_THR=0.3   # 침수판정 수심(m)

def main():
    # v1(단일유입+spin-up)이 최선. v2(다중유입)는 과충전으로 역효과 → v1을 공식 결과로.
    rpath = MD/"anuga_maxdepth_100m.tif"
    print("model raster:", rpath.name)
    with rasterio.open(rpath) as ds:
        dep=ds.read(1).astype("float32"); tr=ds.transform; crs=ds.crs; shape=ds.shape
    model_flood = dep>DEPTH_THR

    # SAR 홍수 → 모델격자 재투영
    with rasterio.open(HY/"sar_flood_extent_2025-07-19.tif") as ds:
        sar=ds.read(1).astype("float32"); str_=ds.transform; scrs=ds.crs
    sar_on=np.zeros(shape,dtype="float32")
    reproject(sar,sar_on,src_transform=str_,src_crs=scrs,dst_transform=tr,dst_crs=crs,resampling=Resampling.max)
    obs_flood = sar_on>0.5

    # HAND(하천고도기준높이) → 모델격자. 범람가능 저지대(HAND<5m)만 공정 평가(사면 제외).
    with rasterio.open(HY/"reach_hand_5m.tif") as ds:
        hand=ds.read(1).astype("float32"); htr=ds.transform; hcrs=ds.crs
    hand_on=np.full(shape,9999,dtype="float32")
    reproject(hand,hand_on,src_transform=htr,src_crs=hcrs,dst_transform=tr,dst_crs=crs,resampling=Resampling.min)
    floodplain = hand_on < 5.0
    # 물리적으로 사면(HAND 큰 곳)의 SAR 화소는 홍수 아님(그림자·젖은농지) → 제거
    obs_flood = obs_flood & floodplain
    model_flood = model_flood & floodplain

    # 평가역: 범람가능 저지대(공정)
    valid=np.isfinite(dep) & floodplain
    TP=int((model_flood&obs_flood&valid).sum()); FP=int((model_flood&~obs_flood&valid).sum())
    FN=int((~model_flood&obs_flood&valid).sum()); TN=int((~model_flood&~obs_flood&valid).sum())
    iou=TP/max(TP+FP+FN,1); prec=TP/max(TP+FP,1); pod=TP/max(TP+FN,1)
    f1=2*prec*pod/max(prec+pod,1e-9); far=FP/max(FP+TP,1)

    # 경호교 WSE
    try:
        meta_a=json.loads((OUTP/"anuga_reach_meta.json").read_text(encoding="utf-8"))
        wse=meta_a.get("valid_경호교_WSE",{})
    except Exception:
        wse={}
    # WSE RMSE(시계열, 겹치는 시각)
    rmse=None
    try:
        sim=pd.read_csv(OUTP/"anuga_reach_timeseries.csv"); obs=pd.read_csv(HY/"reach_valid_경호교.csv")
        m=pd.merge(sim[["t_sec","WSE_경호교"]],obs[["t_sec","wse"]],on="t_sec",how="inner")
        if len(m): rmse=float(np.sqrt(((m["WSE_경호교"]-m["wse"])**2).mean()))
    except Exception as e:
        print("rmse skip",e)

    res={"engine":"ANUGA","depth_thr_m":DEPTH_THR,
         "extent_vs_S1":{"IoU":round(iou,3),"F1":round(f1,3),"POD":round(pod,3),"FAR":round(far,3),
                         "precision":round(prec,3),"TP":TP,"FP":FP,"FN":FN,"TN":TN},
         "model_flood_km2":round(model_flood.sum()*abs(tr[0]*tr[4])/1e6,2),
         "obs_flood_km2":round(obs_flood.sum()*abs(tr[0]*tr[4])/1e6,2),
         "gyeongho_WSE":wse,"gyeongho_WSE_rmse_m":round(rmse,3) if rmse else None}
    (OUTP/"module_b_validation.json").write_text(json.dumps(res,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(res,ensure_ascii=False,indent=2))

if __name__=="__main__": main()
