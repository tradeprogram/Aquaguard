"""
12_sentinel1_acquire.py  (AquaGuard 트랙① — 산청 Sentinel-1 SAR 다운로드만)

Microsoft Planetary Computer의 sentinel-1-rtc(방사·지형보정 완료, γ0, 지오코딩)를
무료 익명접근으로 받아 산청 bbox만 저장. 계산 없음 — 원본 VV·VH 저장만.
산청 사건 장면: 07-18(사전) / 07-19 09:23(사건당일) / 07-25(사후).
"""
from __future__ import annotations
import warnings; warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, requests, rasterio
from rasterio.warp import transform_bounds
from rasterio.windows import from_bounds

OUT = Path(r"G:/연구/공모전/아쿠아가드/data/sentinel"); OUT.mkdir(parents=True, exist_ok=True)
PC = "https://planetarycomputer.microsoft.com/api/stac/v1/search"
SIGN = "https://planetarycomputer.microsoft.com/api/sas/v1/sign"
BBOX = [127.7284, 35.2197, 128.0668, 35.5619]  # 산청군 실제 (안동 아님!)

def sign(href): return requests.get(SIGN, params={"href": href}, timeout=30).json()["href"]

def read_win(href):
    with rasterio.open(sign(href)) as ds:
        b = transform_bounds("EPSG:4326", ds.crs, *BBOX)
        win = from_bounds(*b, transform=ds.transform)
        arr = ds.read(1, window=win).astype("float32")
        tr = ds.window_transform(win)
        prof = {"driver":"GTiff","height":arr.shape[0],"width":arr.shape[1],"count":1,
                "dtype":"float32","crs":ds.crs,"transform":tr,"compress":"deflate","nodata":0}
    return arr, prof

def main():
    body = {"collections":["sentinel-1-rtc"],"bbox":BBOX,
            "datetime":"2025-07-10T00:00:00Z/2025-07-28T00:00:00Z","limit":15}
    feats = requests.post(PC, json=body, timeout=60).json()["features"]
    feats = sorted(feats, key=lambda f: f["properties"]["datetime"])
    print(f"산청 Sentinel-1 RTC 장면 {len(feats)}건 → VV·VH 다운로드")
    for f in feats:
        d = f["properties"]["datetime"][:10]
        for pol in ("vv","vh"):
            if pol not in f["assets"]: continue
            arr, prof = read_win(f["assets"][pol]["href"])
            p = OUT / f"s1_sancheong_{d}_{pol}.tif"
            with rasterio.open(p, "w", **prof) as ds: ds.write(arr, 1)
            print(f"  저장 {p.name}  {arr.shape}  ({p.stat().st_size/1e6:.0f}MB)")
    print("완료 — 계산 없이 원본만 저장.")

if __name__ == "__main__":
    main()
