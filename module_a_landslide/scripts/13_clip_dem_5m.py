"""
13_clip_dem_5m.py  (AquaGuard 트랙① — 5m DEM 지역 clip, 30m 대체)

전국 5m DEM(EPSG:5179)에서 산청·안동을 windowed로 잘라 저장. 계산 없음(clip만).
- 경상남도 5m → 산청  (bbox 127.7284,35.2197,128.0668,35.5619)
- 경상북도 5m → 안동  (bbox 128.4354,36.2892,129.0045,36.8113)
출력 EPSG:5179(내부좌표 규칙), 격자 5m 유지.
"""
from __future__ import annotations
import warnings; warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, rasterio
from rasterio.warp import transform_bounds
from rasterio.windows import from_bounds

SRC = Path(r"G:/연구/데이터/DEM_5m_5179/DEM_5m_5179")
OUT = Path(r"G:/연구/공모전/아쿠아가드/data/dem"); OUT.mkdir(parents=True, exist_ok=True)

JOBS = [
    ("경상남도", "산청", (127.7284, 35.2197, 128.0668, 35.5619)),
    ("경상북도", "안동", (128.4354, 36.2892, 129.0045, 36.8113)),
]

def clip(prov, region, bbox_ll):
    src = SRC / f"dem_5m_{prov}.tif"
    with rasterio.open(src) as ds:
        b = transform_bounds("EPSG:4326", ds.crs, *bbox_ll)  # DEM은 5179
        win = from_bounds(*b, transform=ds.transform)
        arr = ds.read(1, window=win)
        tr = ds.window_transform(win)
        prof = ds.profile.copy()
        prof.update(height=arr.shape[0], width=arr.shape[1], transform=tr, compress="deflate")
    outp = OUT / f"{region}_dem_5m_5179.tif"
    with rasterio.open(outp, "w", **prof) as ds:
        ds.write(arr, 1)
    v = arr[arr != prof.get("nodata", -9999)]
    print(f"{region}: {outp.name}  {arr.shape} (5m)  표고 {float(np.nanmin(v)):.0f}~{float(np.nanmax(v)):.0f}m  {outp.stat().st_size/1e6:.0f}MB")
    return outp

if __name__ == "__main__":
    for prov, region, bbox in JOBS:
        clip(prov, region, bbox)
    print("완료 — 5m DEM 산청·안동 clip 저장 (30m 대체용).")
