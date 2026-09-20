"""
14_sancheong_slope.py  (AquaGuard 트랙① / 산청 백테스트 1단계)

산청 5m DEM(EPSG:5179)에서 경사(도)를 계산해 저장. FoS의 beta 입력.
slope = atan(sqrt((dz/dx)^2+(dz/dy)^2)), cellsize=5m. Horn 유사(np.gradient).
"""
from __future__ import annotations
import warnings; warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, rasterio

DEM = Path(r"G:/연구/공모전/아쿠아가드/data/dem/산청_dem_5m_5179.tif")
OUT = Path(r"G:/연구/공모전/아쿠아가드/data/dem")

with rasterio.open(DEM) as ds:
    dem = ds.read(1).astype("float32")
    prof = ds.profile.copy()
    res = ds.res[0]
    nodata = ds.nodata

dem[dem == nodata] = np.nan
gy, gx = np.gradient(dem, res, res)
slope = np.degrees(np.arctan(np.sqrt(gx**2 + gy**2))).astype("float32")

prof.update(dtype="float32", nodata=np.nan, compress="deflate")
outp = OUT / "산청_slope_5m_5179.tif"
with rasterio.open(outp, "w", **prof) as ds:
    ds.write(slope, 1)

v = slope[np.isfinite(slope)]
print(f"산청 경사 저장: {outp.name}  {slope.shape} @5m")
print(f"  경사 중앙 {np.nanmedian(v):.1f}°, 평균 {np.nanmean(v):.1f}°, 90퍼센타일 {np.nanpercentile(v,90):.1f}°")
print(f"  급경사(>30°) {(v>30).mean()*100:.1f}%,  >20° {(v>20).mean()*100:.1f}%")
