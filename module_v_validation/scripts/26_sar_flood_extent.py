"""
26_sar_flood_extent.py  (Module B 검증참값 — Sentinel-1 홍수 침수범위)

산청 홍수(2025-07-19 피크)의 관측 침수범위를 Sentinel-1 SAR로 추출.
엔진(SFINCS/ANUGA) 무관 — 모의 침수 vs 관측 침수 IoU/F1/POD/FAR(SPEC §2) 참값.

원리: 잔잔한 수면=경면반사→후방산란 급감(어두움). 홍수=새로 생긴 수체.
전처리(SPEC §1): RTC(PC 완료) → 스펙클 median 7×7 → VV log-ratio dB=10log10(post/pre).
홍수 프록시: dB < thr(Otsu 자동, 음수측) & 평탄(slope<5°) & 상시수체 아님(pre도 어두우면 제외).

입력: data/sentinel/s1_sancheong_2025-07-{12,18,19}_vv.tif (PC RTC, EPSG:32652)
       data/dem/산청_slope_5m_5179.tif
출력: data/hydro/sar_flood_extent_2025-07-19.tif(1=홍수), outputs/sar_flood_meta.json
정직: S1 통과시각(~06/18시)과 피크(13시) 불일치 가능 — 07-18/19 둘 다 산출·비교, 결과 그대로.
"""
from __future__ import annotations
import warnings; warnings.filterwarnings("ignore")
import json
from pathlib import Path
import numpy as np, rasterio
from rasterio.warp import reproject, Resampling
from scipy.ndimage import median_filter

ROOT = Path(r"G:/연구/공모전/아쿠아가드")
SEN = ROOT/"data"/"sentinel"; OUT = ROOT/"data"/"hydro"; OUTP = ROOT/"outputs"
SPECKLE = 7; SLOPE_MAX = 5.0

def rd(p):
    with rasterio.open(p) as ds:
        return ds.read(1).astype("float32"), ds.profile, ds.transform, ds.crs, (ds.height,ds.width)

def otsu(x):
    x = x[np.isfinite(x)]
    if x.size < 100: return np.nan
    hist, edges = np.histogram(x, bins=256)
    p = hist/hist.sum(); w = np.cumsum(p); mu = np.cumsum(p*((edges[:-1]+edges[1:])/2))
    muT = mu[-1]
    with np.errstate(divide="ignore", invalid="ignore"):
        sb = (muT*w - mu)**2 / (w*(1-w))
    i = np.nanargmax(sb)
    return (edges[i]+edges[i+1])/2

def slope_to(grid_tr, grid_crs, shape):
    sl,_,str_,scr_,_ = rd(ROOT/"data"/"dem"/"산청_slope_5m_5179.tif")
    dst = np.full(shape, np.nan, dtype="float32")
    reproject(sl, dst, src_transform=str_, src_crs=scr_,
              dst_transform=grid_tr, dst_crs=grid_crs, resampling=Resampling.bilinear)
    return dst

def flood_for(post_date, pre_date="2025-07-12"):
    vv_pre,prof,tr,crs,shape = rd(SEN/f"s1_sancheong_{pre_date}_vv.tif")
    vv_post,*_ = rd(SEN/f"s1_sancheong_{post_date}_vv.tif")
    pre = median_filter(vv_pre, size=SPECKLE); post = median_filter(vv_post, size=SPECKLE)
    pre[pre<=0]=np.nan; post[post<=0]=np.nan
    dB = 10*np.log10(post/pre)                       # 변화(음수=어두워짐=새 수체)
    slope = slope_to(tr, crs, shape)
    flat = np.isfinite(slope)&(slope<SLOPE_MAX)
    # 상시수체(pre도 매우 어두움)는 제외 → 새 침수만
    pre_dB = 10*np.log10(pre/np.nanmedian(pre[np.isfinite(pre)]))
    perm_water = pre_dB < -6
    thr = otsu(dB[flat&np.isfinite(dB)])
    thr = float(np.clip(thr, -4.0, -2.0))            # 표준 홍수 change-detection 임계(2~4dB 감쇠)
    flood = flat & np.isfinite(dB) & (dB < thr) & (~perm_water)
    return flood, dB, slope, prof, thr, shape

def main():
    res = {}
    for pd_ in ["2025-07-18","2025-07-19"]:
        flood, dB, slope, prof, thr, shape = flood_for(pd_)
        n_flood = int(flood.sum())
        px_area = abs(prof["transform"][0]*prof["transform"][4])
        km2 = n_flood*px_area/1e6
        cp = prof.copy(); cp.update(dtype="uint8", count=1, nodata=0, compress="deflate")
        outp = OUT/f"sar_flood_extent_{pd_}.tif"
        with rasterio.open(outp,"w",**cp) as ds: ds.write(flood.astype("uint8"),1)
        res[pd_] = {"otsu_thr_dB":round(float(thr),2),"flood_px":n_flood,
                    "flood_km2":round(km2,2),"px_m":round(float(px_area**0.5),1)}
        print(f"{pd_}: Otsu {thr:.2f}dB | 홍수 {n_flood:,}px = {km2:.2f}km² -> {outp.name}")
    (OUTP/"sar_flood_meta.json").write_text(json.dumps(
        {"method":"S1 VV log-ratio + Otsu, flat(slope<5), speckle median7, exclude perm-water",
         "pre":"2025-07-12","results":res,
         "note":"홍수피크 07-19 13시. S1 통과시각 불일치 가능 → 07-18/19 병행."},
        ensure_ascii=False, indent=2), encoding="utf-8")
    print("saved -> outputs/sar_flood_meta.json")

if __name__ == "__main__":
    main()
