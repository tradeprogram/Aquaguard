"""
18_backtest_validation_eupmyeon.py  (산청 백테스트 검증 — bt-eval)

산청 읍면별 FoS 위험도(피크 습윤 시나리오B) vs 실제 산사태 발생건수(362, 리→읍면 집계)
를 대조해 순위상관(Spearman)·hit로 검증. 362 발생지가 리 단위(좌표없음)라 읍면 집계.

위험도 지표: 위험사면(≥15°) 중 landslide_prob>0.5 픽셀 비율(읍면 zonal).
발생 지표: 읍면별 산사태 건수 및 면적정규화 밀도(건/km²).
"""
from __future__ import annotations
import warnings; warnings.filterwarnings("ignore")
import json, math
from pathlib import Path
import numpy as np, pandas as pd, geopandas as gpd, rasterio
from rasterio.features import rasterize
from scipy.stats import spearmanr

ROOT=Path(r"G:/연구/공모전/아쿠아가드"); FOS=ROOT/"data"/"sancheong_fos"; OUT=ROOT/"outputs"
GW=9.81; CR=3.0; WMAX=0.85; SLOPE_MIN=15.0; KSIG=6.0
def load(p):
    with rasterio.open(p) as ds: return ds.read(1).astype("float32"), ds.transform, ds.crs, (ds.height,ds.width)

def main():
    slope,tr,crs,shape = load(ROOT/"data"/"dem"/"산청_slope_5m_5179.tif")
    beta=np.deg2rad(np.clip(slope,0.1,89))
    z,_,_,_=load(FOS/"z_m.tif"); m0,_,_,_=load(FOS/"m0.tif"); dnbr,_,_,_=load(FOS/"dnbr.tif")
    # 시나리오B 풍화화강토
    c=2.0; phi=np.deg2rad(36.0); gam=19.0
    f=np.ones_like(dnbr); f[dnbr>=0.1]=1.2; f[dnbr>=0.27]=2.0; f[dnbr>=0.44]=3.75; f[~np.isfinite(dnbr)]=1.0
    cr_eff=CR/f
    m=np.clip(m0+WMAX,0,1)
    cosb=np.cos(beta); sinb=np.sin(beta)
    fos=(c+cr_eff+(gam-m*GW)*z*cosb**2*np.tan(phi))/(gam*z*sinb*cosb)
    prob=1/(1+np.exp(KSIG*(fos-1)))
    valid=np.isfinite(z)&(slope>=SLOPE_MIN)
    highrisk=valid&(prob>0.5)

    # 읍면 경계 → 격자 라벨
    em=gpd.read_file(ROOT/"data/vector/adm_dong_5179.geojson")
    em=em[em["sggnm"].astype(str).str.contains("산청")].reset_index(drop=True).to_crs(crs)
    em["area_km2"]=em.geometry.area/1e6
    idmap={i+1:em.loc[i,"name"] for i in range(len(em))}
    zones=rasterize(((g,i+1) for i,g in enumerate(em.geometry)), out_shape=shape, transform=tr, fill=0, dtype="int16")

    # 읍면별 위험도(위험사면 중 고위험 비율)
    rows=[]
    for zid,nm in idmap.items():
        zmask=zones==zid; vsteep=(zmask&valid).sum()
        hr=(zmask&highrisk).sum()
        rows.append({"읍면":nm,"위험사면px":int(vsteep),"고위험비율_%":round(100*hr/max(vsteep,1),2)})
    risk=pd.DataFrame(rows)

    # 실제 산사태 건수(읍면)
    ls=pd.read_excel(ROOT/"data/산청_산사태.xlsx")
    ls=ls[ls["연도"]==2025]
    cnt=ls.groupby("상세주소_읍면도").size().rename("산사태건수").reset_index().rename(columns={"상세주소_읍면도":"읍면"})
    m2=risk.merge(cnt,on="읍면",how="left").merge(em[["name","area_km2"]].rename(columns={"name":"읍면"}),on="읍면",how="left")
    m2["산사태건수"]=m2["산사태건수"].fillna(0)
    m2["발생밀도_건perkm2"]=(m2["산사태건수"]/m2["area_km2"]).round(3)
    m2=m2.sort_values("고위험비율_%",ascending=False)

    rho_cnt=spearmanr(m2["고위험비율_%"],m2["산사태건수"]).correlation
    rho_den=spearmanr(m2["고위험비율_%"],m2["발생밀도_건perkm2"]).correlation
    m2.to_csv(OUT/"sancheong_backtest_eupmyeon_validation.csv",index=False,encoding="utf-8-sig")
    print(m2.to_string(index=False))
    print(f"\nSpearman 순위상관 (FoS 고위험비율 vs 산사태):")
    print(f"  vs 건수  ρ = {rho_cnt:.3f}")
    print(f"  vs 밀도  ρ = {rho_den:.3f}   (면적정규화, 더 공정)")

if __name__=="__main__": main()
