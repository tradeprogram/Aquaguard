"""
31_hand_reach.py  (Module B — HAND(하천고도기준높이) 계산)  [env: sfincs, pyflwdir]

경호강 구간 5m DEM에서 흐름방향→하천망→HAND(Height Above Nearest Drainage, Nobre 2011)를 산출.
용도: ①SAR 홍수맵 노이즈 제거(HAND 큰 곳=사면=홍수 아님) ②공정 평가역(HAND 낮은 범람가능 저지대).
출력: data/hydro/reach_hand_5m.tif, reach_streams_5m.tif
"""
from __future__ import annotations
import warnings; warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, rasterio, pyflwdir

ROOT=Path(r"G:/연구/공모전/아쿠아가드"); HY=ROOT/"data"/"hydro"
UPA_MIN=1.0   # 하천 정의 최소 유역면적(km²)

def main():
    with rasterio.open(HY/"reach_dem_5m.tif") as ds:
        dem=ds.read(1).astype("float32"); tr=ds.transform; crs=ds.crs; prof=ds.profile; nod=ds.nodata
    dem_valid=np.where(dem==nod, np.nan, dem)
    flw=pyflwdir.from_dem(data=dem_valid, nodata=np.nan, transform=tr, latlon=False)
    upa=flw.upstream_area(unit="km2")
    streams=upa>UPA_MIN
    hand=flw.hand(drain=streams, elevtn=dem_valid)
    hand=np.where(np.isfinite(hand), hand, 9999).astype("float32")

    p=prof.copy(); p.update(dtype="float32", nodata=9999, compress="deflate")
    with rasterio.open(HY/"reach_hand_5m.tif","w",**p) as ds: ds.write(hand,1)
    p2=prof.copy(); p2.update(dtype="uint8", nodata=0, compress="deflate")
    with rasterio.open(HY/"reach_streams_5m.tif","w",**p2) as ds: ds.write(streams.astype("uint8"),1)
    print(f"HAND: valid {np.isfinite(dem_valid).sum():,}px | 하천 {int(streams.sum()):,}px(UPA>{UPA_MIN}km²)")
    for thr in [2,5,10]:
        print(f"  HAND<{thr}m 저지대: {int((hand<thr).sum()):,}px = {(hand<thr).sum()*25/1e6:.1f}km²")
    print("saved -> data/hydro/reach_hand_5m.tif, reach_streams_5m.tif")

if __name__=="__main__": main()
