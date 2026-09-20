"""
19_module_v.py  (Module V — Sentinel-1 예측 vs 실측 검증)

산청 Sentinel-1 RTC(07-12 사건전 → 07-25 사건후) 변화탐지로 붕괴부 추출,
Module A FoS 예측과 겹쳐 IoU·F1·POD·FAR·precision·AUPRC 산출.

SAR 전처리(SPEC §1): RTC(정밀궤도·열잡음·방사·지형보정 = Planetary Computer에서 완료)
 → 스펙클필터 median 7×7 → VH 로그비 변화 dB=10log10(post/pre)
관측 붕괴 프록시: VH_dB < -3 (식생/표면 소실) & 경사≥15°  (급사면 한정, 노이즈↓)
예측: FoS(B 풍화화강토, 피크습윤) landslide_prob>0.5 & 경사≥15°
★ data-leakage 금지: 관측(사건후 SAR)은 예측 계산에 안 씀. FoS는 사건전 지형·토양·강우만.
정직: SAR 산사태탐지는 강우 후 토양수분·식생위상 변화가 섞여 노이즈 큼 → 결과 그대로 보고.
"""
from __future__ import annotations
import warnings; warnings.filterwarnings("ignore")
import json
from pathlib import Path
import numpy as np, rasterio
from rasterio.warp import reproject, Resampling
from scipy.ndimage import median_filter
from sklearn.metrics import average_precision_score

ROOT=Path(r"G:/연구/공모전/아쿠아가드"); SEN=ROOT/"data"/"sentinel"; FOS=ROOT/"data"/"sancheong_fos"; OUT=ROOT/"outputs"
GW=9.81; CR=3.0; WMAX=0.85; SLOPE_MIN=15.0; KSIG=6.0; CHG_DB=-3.0; SPECKLE=7

def rd(p):
    with rasterio.open(p) as ds: return ds.read(1).astype("float32"), ds.profile, ds.transform, ds.crs, (ds.height,ds.width)

def main():
    # SAR 그리드(관측 기준)
    vh_pre,prof,tr,crs,shape = rd(SEN/"s1_sancheong_2025-07-12_vh.tif")
    vh_post,*_ = rd(SEN/"s1_sancheong_2025-07-25_vh.tif")
    # 스펙클 필터
    vh_pre_f=median_filter(vh_pre,size=SPECKLE); vh_post_f=median_filter(vh_post,size=SPECKLE)
    eps=1e-6
    vh_pre_f[vh_pre_f<=0]=np.nan; vh_post_f[vh_post_f<=0]=np.nan
    dB=10*np.log10((vh_post_f+eps)/(vh_pre_f+eps))   # 변화(dB)

    # FoS 예측(5179,5m) 계산 후 SAR격자로 재투영
    def load5179(p):
        with rasterio.open(p) as ds: return ds.read(1).astype("float32"), ds.transform, ds.crs
    slope5,tr5,crs5=load5179(ROOT/"data"/"dem"/"산청_slope_5m_5179.tif")
    z5,_,_=load5179(FOS/"z_m.tif"); m05,_,_=load5179(FOS/"m0.tif"); dn5,_,_=load5179(FOS/"dnbr.tif")
    beta=np.deg2rad(np.clip(slope5,0.1,89))
    f=np.ones_like(dn5); f[dn5>=0.1]=1.2; f[dn5>=0.27]=2.0; f[dn5>=0.44]=3.75; f[~np.isfinite(dn5)]=1.0
    m=np.clip(m05+WMAX,0,1); cb=np.cos(beta); sb=np.sin(beta)
    fos=(2.0+CR/f+(19.0-m*GW)*z5*cb**2*np.tan(np.deg2rad(36.0)))/(19.0*z5*sb*cb)
    prob5=1/(1+np.exp(KSIG*(fos-1)))

    def to_sar(src,src_tr,resamp=Resampling.bilinear):
        dst=np.full(shape,np.nan,dtype="float32")
        reproject(src,dst,src_transform=src_tr,src_crs=crs5,dst_transform=tr,dst_crs=crs,resampling=resamp)
        return dst
    prob=to_sar(prob5,tr5); slope=to_sar(slope5,tr5)

    steep=np.isfinite(slope)&(slope>=SLOPE_MIN)&np.isfinite(dB)&np.isfinite(prob)
    observed=steep&(dB<CHG_DB)          # 관측 붕괴 프록시
    predicted=steep&(prob>0.5)          # 예측 고위험
    n=steep.sum()
    TP=(observed&predicted).sum(); FP=(~observed&predicted).sum()
    FN=(observed&~predicted).sum(); TN=(~observed&~predicted).sum()
    iou=TP/max(TP+FP+FN,1); prec=TP/max(TP+FP,1); pod=TP/max(TP+FN,1)
    f1=2*prec*pod/max(prec+pod,1e-9); far=FP/max(FP+TP,1)
    auprc=average_precision_score(observed[steep].astype(int), prob[steep])

    print(f"급사면(≥{SLOPE_MIN}°) 유효픽셀 {n:,} | 관측붕괴 {observed.sum():,}({100*observed.sum()/n:.1f}%) | 예측고위험 {predicted.sum():,}({100*predicted.sum()/n:.1f}%)")
    print(f"혼동: TP {TP:,} FP {FP:,} FN {FN:,} TN {TN:,}")
    print(f"\n=== Module V 6지표 (산사태=공간, RMSE는 홍수수심용이라 N/A) ===")
    print(f"  IoU       {iou:.3f}")
    print(f"  F1        {f1:.3f}")
    print(f"  POD(재현) {pod:.3f}")
    print(f"  FAR(오경보){far:.3f}")
    print(f"  Precision {prec:.3f}")
    print(f"  AUPRC     {auprc:.3f}  (기저율 {observed.sum()/n:.3f})")

    res={"iou":round(float(iou),4),"f1":round(float(f1),4),"pod":round(float(pod),4),
         "far":round(float(far),4),"precision":round(float(prec),4),"auprc":round(float(auprc),4),
         "base_rate":round(float(observed.sum()/n),4),
         "params":{"speckle":SPECKLE,"change_dB":CHG_DB,"slope_min":SLOPE_MIN,"pol":"VH",
                   "pre":"2025-07-12","post":"2025-07-25","prob_scenario":"B_weathered"},
         "note":"SAR 변화는 강우후 토양수분·식생위상 혼입으로 노이즈 큼. observed=proxy."}
    (OUT/"module_v_metrics.json").write_text(json.dumps(res,ensure_ascii=False,indent=2),encoding="utf-8")
    # 혼동 래스터 저장(UI 오버레이용)
    conf=np.zeros(shape,dtype="uint8"); conf[observed&predicted]=1; conf[~observed&predicted]=2; conf[observed&~predicted]=3
    cp=prof.copy(); cp.update(dtype="uint8",count=1,nodata=0,compress="deflate")
    with rasterio.open(OUT/"module_v_confusion.tif","w",**cp) as ds: ds.write(conf,1)
    print("\nsaved -> outputs/module_v_metrics.json, module_v_confusion.tif")

if __name__=="__main__": main()
