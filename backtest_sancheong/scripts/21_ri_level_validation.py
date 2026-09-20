"""
21_ri_level_validation.py  (리(里)-level zonal 검증 — 좌표 대체)

362 산사태기록의 리(里) 이름을 VWorld 지오코더로 좌표화 → 리 주변 급사면 FoS
위험도 집계 → 실제 발생(건수/밀도)과 대조. 좌표없음의 차선책(읍면 10→리 ~100).
정직: 여전히 '피해기록' 편향 잔존, 리센트로이드+버퍼 근사. 결과 그대로 보고.
"""
from __future__ import annotations
import warnings; warnings.filterwarnings("ignore")
import time, math, json, urllib.parse
from pathlib import Path
import numpy as np, pandas as pd, requests, rasterio
from pyproj import Transformer
from scipy.stats import spearmanr
from sklearn.metrics import average_precision_score

def _load_key(name: str) -> str:
    """.env 또는 환경변수에서 API 키를 읽는다. 없으면 즉시 멈춘다."""
    import os
    val = os.environ.get(name)
    if not val:
        for parent in [Path(__file__).resolve().parent, *Path(__file__).resolve().parents]:
            env = parent / ".env"
            if env.exists():
                for line in env.read_text(encoding="utf-8").splitlines():
                    if line.strip().startswith(f"{name}="):
                        val = line.split("=", 1)[1].strip().strip('"').strip("'")
                        break
            if val:
                break
    if not val:
        raise SystemExit(f"{name} 가 없습니다. .env 에 {name}=... 를 넣으세요. (.env 는 커밋 금지)")
    return val


ROOT=Path(r"G:/연구/공모전/아쿠아가드"); FOS=ROOT/"data"/"sancheong_fos"; OUT=ROOT/"outputs"
KEY = _load_key("VWORLD_API_KEY")
GW=9.81; CR=3.0; WMAX=0.85; SLOPE_MIN=15.0; KSIG=6.0; BUF_M=1500.0
tf=Transformer.from_crs("EPSG:4326","EPSG:5179",always_xy=True)

def geocode(addr):
    try:
        u=f"http://api.vworld.kr/req/address?service=address&request=getcoord&version=2.0&crs=epsg:4326&type=parcel&address={urllib.parse.quote(addr)}&key={KEY}&domain=localhost"
        r=requests.get(u,timeout=10).json()["response"]
        if r["status"]=="OK":
            pt=r["result"]["point"]; return float(pt["x"]),float(pt["y"])
    except Exception: pass
    return None,None

def main():
    df=pd.read_excel(ROOT/"data/산청_산사태.xlsx"); df=df[df["연도"]==2025]
    grp=df.groupby(["상세주소_읍면도","상세주소_리"]).size().reset_index(name="건수")
    print(f"고유 리(里): {len(grp)}개, 총 {grp['건수'].sum()}건")

    # 리 지오코딩
    lons,lats=[],[]
    for _,r in grp.iterrows():
        addr=f"경상남도 산청군 {r['상세주소_읍면도']} {r['상세주소_리']}"
        x,y=geocode(addr)
        if x is None:  # 리 실패시 읍면으로 폴백
            x,y=geocode(f"경상남도 산청군 {r['상세주소_읍면도']}")
        lons.append(x); lats.append(y); time.sleep(0.05)
    grp["lon"]=lons; grp["lat"]=lats
    ok=grp.dropna(subset=["lon","lat"]).copy()
    print(f"지오코딩 성공: {len(ok)}/{len(grp)} 리")

    # FoS 위험도(시나리오B 피크)
    def ld(p):
        with rasterio.open(p) as ds: return ds.read(1).astype("float32"), ds.transform
    slope,tr=ld(ROOT/"data"/"dem"/"산청_slope_5m_5179.tif")
    z,_=ld(FOS/"z_m.tif"); m0,_=ld(FOS/"m0.tif"); dn,_=ld(FOS/"dnbr.tif")
    with rasterio.open(ROOT/"data"/"dem"/"산청_slope_5m_5179.tif") as ds: crs=ds.crs; H,W=ds.shape
    beta=np.deg2rad(np.clip(slope,0.1,89))
    f=np.ones_like(dn); f[dn>=0.1]=1.2; f[dn>=0.27]=2.0; f[dn>=0.44]=3.75; f[~np.isfinite(dn)]=1.0
    m=np.clip(m0+WMAX,0,1); cb=np.cos(beta); sb=np.sin(beta)
    fos=(2.0+CR/f+(19.0-m*GW)*z*cb**2*np.tan(np.deg2rad(36.0)))/(19.0*z*sb*cb)
    prob=1/(1+np.exp(KSIG*(fos-1)))
    steep=np.isfinite(slope)&(slope>=SLOPE_MIN)
    inv=~tr
    def zonal(x5179,y5179):
        col,row=inv*(x5179,y5179); r0,c0=int(row),int(col); rad=int(BUF_M/5)
        rr=slice(max(0,r0-rad),min(H,r0+rad)); cc=slice(max(0,c0-rad),min(W,c0+rad))
        ps=prob[rr,cc]; st=steep[rr,cc]
        vals=ps[st&np.isfinite(ps)]
        if vals.size==0: return np.nan,np.nan
        return float(np.nanmean(vals)), float((vals>0.5).mean())
    means,highs=[],[]
    for _,r in ok.iterrows():
        X,Y=tf.transform(r["lon"],r["lat"]); mn,hi=zonal(X,Y); means.append(mn); highs.append(hi)
    ok["FoS_mean_prob"]=means; ok["FoS_high_frac"]=highs
    ok=ok.dropna(subset=["FoS_mean_prob"])

    rho1=spearmanr(ok["FoS_high_frac"],ok["건수"]).correlation
    rho2=spearmanr(ok["FoS_mean_prob"],ok["건수"]).correlation
    ok.to_csv(OUT/"sancheong_ri_validation.csv",index=False,encoding="utf-8-sig")
    print(ok.sort_values("건수",ascending=False)[["상세주소_읍면도","상세주소_리","건수","FoS_high_frac","FoS_mean_prob"]].head(15).to_string(index=False))
    print(f"\n리-level Spearman: 고위험비율 vs 건수 ρ={rho1:.3f} | 평균확률 vs 건수 ρ={rho2:.3f}  (n={len(ok)} 리)")

if __name__=="__main__": main()
