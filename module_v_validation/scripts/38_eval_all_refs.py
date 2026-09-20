"""
38_eval_all_refs.py  (Module B — SFINCS/ANUGA를 SAR·HAND-FIM 두 참값으로 평가)  [env: sfincs]
공통 50m격자·HAND<15m 계곡 평가역. SAR(과소탐지)·HAND-FIM(과대) 두 참값으로 IoU/POD/FAR 보고.
"""
from __future__ import annotations
import warnings; warnings.filterwarnings("ignore")
import json
from pathlib import Path
import numpy as np, rasterio
from rasterio.warp import reproject, Resampling

ROOT=Path(r"G:/연구/공모전/аквагард") if False else Path(r"G:/연구/공모전/아쿠아가드")
HY=ROOT/"data"/"hydro"; OUTP=ROOT/"outputs"; MD=ROOT/"models"/"anuga_reach"
X0,Y0,X1,Y1=1028000,1703000,1042000,1723000; GR=50; THR=0.3
W=int((X1-X0)/GR); H=int((Y1-Y0)/GR); TR=rasterio.transform.from_origin(X0,Y1,GR,GR); SHP=(H,W); CRS="EPSG:5179"

def cg(path,resamp,fill):
    with rasterio.open(path) as s: a=s.read(1).astype("float32"); st=s.transform; sc=s.crs
    d=np.full(SHP,fill,dtype="float32"); reproject(a,d,src_transform=st,src_crs=sc,dst_transform=TR,dst_crs=CRS,resampling=resamp); return d

def met(mod,obs,valid):
    m=mod&valid; o=obs&valid
    TP=int((m&o).sum());FP=int((m&~o).sum());FN=int((~m&o).sum())
    iou=TP/max(TP+FP+FN,1);prec=TP/max(TP+FP,1);pod=TP/max(TP+FN,1);f1=2*prec*pod/max(prec+pod,1e-9);far=FP/max(FP+TP,1)
    return dict(IoU=round(iou,3),F1=round(f1,3),POD=round(pod,3),FAR=round(far,3),precision=round(prec,3))

def main():
    hand=cg(HY/"reach_hand_5m.tif",Resampling.min,9999)
    valley=hand<15.0
    sar=cg(HY/"sar_flood_extent_2025-07-19.tif",Resampling.max,0)>0.5
    fim=cg(HY/"hand_fim_flood_2025-07-19.tif",Resampling.max,0)>0.5
    sfincs=cg(MD/"sfincs_maxdepth_50m.tif",Resampling.bilinear,0)>THR
    anuga=cg(MD/"anuga_maxdepth_100m.tif",Resampling.bilinear,0)>THR

    a=GR*GR/1e6
    res={"eval_domain":"HAND<15m 계곡, 공통50m",
         "areas_km2":{"SAR":round(int((sar&valley).sum())*a,2),"HAND_FIM":round(int((fim&valley).sum())*a,2),
                      "SFINCS":round(int((sfincs&valley).sum())*a,2),"ANUGA":round(int((anuga&valley).sum())*a,2)},
         "vs_SAR":{"SFINCS":met(sfincs,sar,valley),"ANUGA":met(anuga,sar,valley)},
         "vs_HAND_FIM":{"SFINCS":met(sfincs,fim,valley),"ANUGA":met(anuga,fim,valley)},
         "SFINCS_vs_ANUGA(모델간 일치)":met(sfincs,anuga,valley)}
    (OUTP/"module_b_allrefs.json").write_text(json.dumps(res,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(res,ensure_ascii=False,indent=2))
    print("\n=== IoU 요약 ===")
    print(f"{'':10s}{'vs SAR':>10s}{'vs HAND-FIM':>13s}")
    for e in ["SFINCS","ANUGA"]:
        print(f"{e:10s}{res['vs_SAR'][e]['IoU']:>10}{res['vs_HAND_FIM'][e]['IoU']:>13}")
    print(f"모델간 일치 IoU(SFINCS vs ANUGA): {res['SFINCS_vs_ANUGA(모델간 일치)']['IoU']}")

if __name__=="__main__": main()
