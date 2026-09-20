"""
37_hand_fim.py  (Module B 검증참값 — HAND-FIM 실측수위 기반 침수도)

관측 피크 수위(HRFCO)를 지형에 투영해 관측 침수범위를 만든다(구름·초목 무관, 실측기반).
표준 HAND-FIM(NOAA/USGS): 침수 ⟺ HAND(cell) < stage(nearest drainage)
  stage(gauge) = WSE_obs − DEM_channel = (gdt+wl_peak) − DEM(게이지)
  → stage를 하천따라(y축, 본류 N→S) 보간 → flood = HAND < stage(y)
게이지: 고읍교(N,상류)·경호교(중,검증)·수산교(S,하류). 경호교는 SFINCS 입력 미사용→준독립.
출력: data/hydro/hand_fim_flood_2025-07-19.tif
"""
from __future__ import annotations
import warnings; warnings.filterwarnings("ignore")
import json
from pathlib import Path
import numpy as np, rasterio

ROOT=Path(r"G:/연구/공모전/аквагард") if False else Path(r"G:/연구/공모전/아쿠아가드")
HY=ROOT/"data"/"hydro"
# 게이지: (x,y 5179, WSE_obs = gdt+wl_peak)
GAUGES={"고읍교":(1029983,1721527,106.687+6.99),
        "경호교":(1033994,1713655,85.446+8.67),
        "수산교":(1039985,1704745,49.3+10.39)}

def sample_dem_min(dem,tr,x,y,win=60):
    inv=~tr; c,r=inv*(x,y); r,c=int(r),int(c); rad=int(win/abs(tr.a))
    sub=dem[max(0,r-rad):r+rad, max(0,c-rad):c+rad]
    sub=sub[np.isfinite(sub)&(sub>0)]
    return float(np.nanmin(sub)) if sub.size else np.nan

def main():
    with rasterio.open(HY/"reach_hand_5m.tif") as ds:
        hand=ds.read(1).astype("float32"); tr=ds.transform; crs=ds.crs; H,W=ds.shape; prof=ds.profile
    with rasterio.open(HY/"reach_dem_5m.tif") as ds:
        dem=ds.read(1).astype("float32"); nod=ds.nodata
    dem=np.where(dem==nod,np.nan,dem)

    # 게이지 stage = WSE - DEM_channel(min in window)
    ys=[]; stages=[]
    for nm,(x,y,wse) in GAUGES.items():
        bed=sample_dem_min(dem,tr,x,y); stage=wse-bed
        print(f"  {nm}: WSE {wse:.2f} - bed {bed:.2f} = stage {stage:.2f}m  (y={y})")
        ys.append(y); stages.append(stage)
    ys=np.array(ys); stages=np.array(stages)
    o=np.argsort(ys); ys=ys[o]; stages=stages[o]

    # 각 셀 y좌표 → stage 보간(본류 N-S)
    ny=np.arange(H); ycoord=tr.f+(ny+0.5)*tr.e     # 각 행의 y
    stage_row=np.interp(ycoord, ys, stages)         # (H,)
    stage_grid=np.repeat(stage_row[:,None], W, axis=1)

    flood=(np.isfinite(hand))&(hand<9000)&(hand<stage_grid)
    km2=flood.sum()*abs(tr.a*tr.e)/1e6
    print(f"\nHAND-FIM 침수: {int(flood.sum()):,}px = {km2:.2f}km² (stage {stages.min():.1f}~{stages.max():.1f}m)")

    p=prof.copy(); p.update(dtype="uint8",count=1,nodata=0,compress="deflate")
    outp=HY/"hand_fim_flood_2025-07-19.tif"
    with rasterio.open(outp,"w",**p) as o: o.write(flood.astype("uint8"),1)
    (ROOT/"outputs"/"hand_fim_meta.json").write_text(json.dumps(
        {"method":"HAND-FIM: flood=HAND<stage(y), stage=WSE_obs-DEM_channel",
         "gauges":{k:{"WSE":round(v[2],2)} for k,v in GAUGES.items()},
         "stages_m":[round(float(s),2) for s in stages],"flood_km2":round(km2,2)},
        ensure_ascii=False,indent=2),encoding="utf-8")
    print("saved ->", outp.name)

if __name__=="__main__": main()
