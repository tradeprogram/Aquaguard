"""
20_module_v_ndvi.py  (Module V 개선 — 광학 NDVI 붕괴흔적 탐지)

Sentinel-2 NDVI 변화로 산사태 스카프(식생소실) 탐지 → FoS 예측 검증.
SAR 진폭보다 토양수분 혼입이 적어 붕괴 탐지에 깨끗함.
pre=2025-04-26(식생, 산불후·홍수전), post=2025-09-23(사건후) → dNDVI=NDVI_pre-NDVI_post.
스카프 프록시: dNDVI>0.30 & 경사≥15° (급사면 한정 → 농경지 수확 혼입↓).
★ data-leakage: 관측(사건후 광학)은 FoS 예측에 안 씀.
정직: pre~post 5개월(계절·일부 재식생)이라 완벽친 않음 — 결과 그대로 보고.
"""
from __future__ import annotations
import warnings; warnings.filterwarnings("ignore")
import json
from pathlib import Path
import numpy as np, requests, rasterio
from rasterio.warp import transform_bounds, reproject, Resampling
from rasterio.windows import from_bounds
from sklearn.metrics import average_precision_score

ROOT=Path(r"G:/연구/공모전/아쿠아가드"); FOS=ROOT/"data"/"sancheong_fos"; OUT=ROOT/"outputs"
STAC="https://earth-search.aws.element84.com/v1/search"
BBOX=[127.7284,35.2197,128.0668,35.5619]
GW=9.81; CR=3.0; WMAX=0.85; SLOPE_MIN=15.0; KSIG=6.0; DNDVI_THR=0.30

def best_per_tile(dt):
    feats=requests.post(STAC,json={"collections":["sentinel-2-l2a"],"bbox":BBOX,"datetime":dt,"limit":40},timeout=60).json()["features"]
    out={}
    for f in feats:
        t=f["id"].split("_")[1]; cc=f["properties"].get("eo:cloud_cover",100)
        if t not in out or cc<out[t]["properties"]["eo:cloud_cover"]: out[t]=f
    return out

# 기준격자 = FoS 5179 (예측 native)
with rasterio.open(ROOT/"data"/"dem"/"산청_slope_5m_5179.tif") as ds:
    REF_TR=ds.transform; REF_CRS=ds.crs; REF_SHAPE=(ds.height,ds.width); SLOPE=ds.read(1).astype("float32")

def read_band_to_ref(href):
    with rasterio.open(href) as ds:
        b=transform_bounds("EPSG:4326",ds.crs,*BBOX); win=from_bounds(*b,transform=ds.transform)
        arr=ds.read(1,window=win).astype("float32"); st=ds.window_transform(win); sc=ds.crs
    dst=np.full(REF_SHAPE,np.nan,dtype="float32")
    reproject(arr,dst,src_transform=st,src_crs=sc,dst_transform=REF_TR,dst_crs=REF_CRS,resampling=Resampling.bilinear)
    return dst

def ndvi_mosaic(scenes):
    acc=np.full(REF_SHAPE,np.nan,dtype="float32")
    for t,f in scenes.items():
        nir=read_band_to_ref(f["assets"]["nir"]["href"]); red=read_band_to_ref(f["assets"]["red"]["href"])
        nd=(nir-red)/(nir+red+1e-6)
        acc=np.where(np.isfinite(acc),acc,nd)  # 첫 유효값 채움(모자이크)
    return acc

def main():
    pre=best_per_tile("2025-04-15T00:00:00Z/2025-05-05T00:00:00Z")
    post=best_per_tile("2025-09-15T00:00:00Z/2025-09-30T00:00:00Z")
    print("pre 타일:", {t:f["properties"]["datetime"][:10] for t,f in pre.items()})
    print("post 타일:", {t:(f["properties"]["datetime"][:10],round(f["properties"]["eo:cloud_cover"])) for t,f in post.items()})
    ndvi_pre=ndvi_mosaic(pre); ndvi_post=ndvi_mosaic(post)
    dndvi=ndvi_pre-ndvi_post

    # FoS 예측(시나리오B 피크)
    z=rasterio.open(FOS/"z_m.tif").read(1).astype("float32")
    m0=rasterio.open(FOS/"m0.tif").read(1).astype("float32")
    dn=rasterio.open(FOS/"dnbr.tif").read(1).astype("float32")
    beta=np.deg2rad(np.clip(SLOPE,0.1,89))
    f=np.ones_like(dn); f[dn>=0.1]=1.2; f[dn>=0.27]=2.0; f[dn>=0.44]=3.75; f[~np.isfinite(dn)]=1.0
    m=np.clip(m0+WMAX,0,1); cb=np.cos(beta); sb=np.sin(beta)
    fos=(2.0+CR/f+(19.0-m*GW)*z*cb**2*np.tan(np.deg2rad(36.0)))/(19.0*z*sb*cb)
    prob=1/(1+np.exp(KSIG*(fos-1)))

    steep=np.isfinite(SLOPE)&(SLOPE>=SLOPE_MIN)&np.isfinite(dndvi)&np.isfinite(prob)
    observed=steep&(dndvi>DNDVI_THR)
    predicted=steep&(prob>0.5)
    n=steep.sum()
    TP=(observed&predicted).sum();FP=(~observed&predicted).sum();FN=(observed&~predicted).sum();TN=(~observed&~predicted).sum()
    iou=TP/max(TP+FP+FN,1);prec=TP/max(TP+FP,1);pod=TP/max(TP+FN,1)
    f1=2*prec*pod/max(prec+pod,1e-9);far=FP/max(FP+TP,1)
    auprc=average_precision_score(observed[steep].astype(int),prob[steep])
    print(f"\n급사면 {n:,} | NDVI스카프 {observed.sum():,}({100*observed.sum()/n:.1f}%) | 예측고위험 {predicted.sum():,}({100*predicted.sum()/n:.1f}%)")
    print(f"혼동 TP {TP:,} FP {FP:,} FN {FN:,} TN {TN:,}")
    print(f"=== Module V(광학 NDVI) 지표 ===")
    for k,v in [("IoU",iou),("F1",f1),("POD",pod),("FAR",far),("Precision",prec),("AUPRC",auprc)]:
        print(f"  {k:10s} {v:.3f}")
    print(f"  (기저율 {observed.sum()/n:.3f})")
    res=dict(iou=round(float(iou),4),f1=round(float(f1),4),pod=round(float(pod),4),far=round(float(far),4),
             precision=round(float(prec),4),auprc=round(float(auprc),4),base_rate=round(float(observed.sum()/n),4),
             method="optical NDVI change", dndvi_thr=DNDVI_THR)
    (OUT/"module_v_ndvi_metrics.json").write_text(json.dumps(res,ensure_ascii=False,indent=2),encoding="utf-8")
    print("saved -> outputs/module_v_ndvi_metrics.json")

if __name__=="__main__": main()
