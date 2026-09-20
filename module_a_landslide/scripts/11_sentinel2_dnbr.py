"""
11_sentinel2_dnbr.py  (AquaGuard 트랙① — 산청 산불 dNBR, Module A f(dNBR) 입력)

Element84 Earth Search STAC(무인증)에서 산청 Sentinel-2 산불 전/후 장면을 받아
산청 bbox를 덮는 모든 타일(52SCD·52SCE 등)을 windowed로 읽어 타일별 dNBR을
계산하고 모자이크한다. 전체 다운로드 X.  === 산청군 실제 bbox (안동 아님) ===

dNBR = NBR_prefire - NBR_postfire,  NBR = (B08_NIR - B12_SWIR)/(B08+B12)
산불=2025-03 산청·하동 산불. 장면: 산불전 2025-02, 산불후 2025-04-26(0%구름).
"""
from __future__ import annotations
import warnings; warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, requests, rasterio
from rasterio.warp import transform_bounds
from rasterio.windows import from_bounds
from rasterio.enums import Resampling
from rasterio.merge import merge

OUT = Path(r"G:/연구/공모전/아쿠아가드/data/sentinel"); OUT.mkdir(parents=True, exist_ok=True)
STAC = "https://earth-search.aws.element84.com/v1/search"
BBOX = [127.7284, 35.2197, 128.0668, 35.5619]  # 산청군 실제

def scenes(dt):
    body = {"collections": ["sentinel-2-l2a"], "bbox": BBOX, "datetime": dt, "limit": 40}
    return requests.post(STAC, json=body, timeout=60).json()["features"]

def best_per_tile(dt):
    """산청을 덮는 각 타일(52S..)별 최저구름 장면."""
    out = {}
    for f in scenes(dt):
        tile = f["id"].split("_")[1]  # e.g. 52SCD
        cc = f["properties"].get("eo:cloud_cover", 100)
        if tile not in out or cc < out[tile]["properties"].get("eo:cloud_cover", 100):
            out[tile] = f
    return out

def read_win(href, ref_shape=None, ref_transform=None, ref_crs=None):
    with rasterio.open(href) as ds:
        b = transform_bounds("EPSG:4326", ds.crs, *BBOX)
        win = from_bounds(*b, transform=ds.transform)
        if ref_shape is None:
            arr = ds.read(1, window=win).astype("float32")
            return arr, ds.window_transform(win), ds.crs
        arr = ds.read(1, window=win, out_shape=ref_shape, resampling=Resampling.bilinear).astype("float32")
        return arr, ref_transform, ref_crs

def nbr_tile(feat):
    nir, tr, crs = read_win(feat["assets"]["nir"]["href"])
    swir, _, _ = read_win(feat["assets"]["swir22"]["href"], nir.shape, tr, crs)
    nir[nir == 0] = np.nan; swir[swir == 0] = np.nan
    return (nir - swir) / (nir + swir), tr, crs

def main():
    pre = best_per_tile("2025-02-01T00:00:00Z/2025-03-05T00:00:00Z")
    post = best_per_tile("2025-04-15T00:00:00Z/2025-05-10T00:00:00Z")
    tiles = sorted(set(pre) & set(post))
    print(f"산청 커버 타일: {tiles}")
    dnbr_rasters = []
    for t in tiles:
        cc_pre = pre[t]["properties"]["eo:cloud_cover"]; cc_post = post[t]["properties"]["eo:cloud_cover"]
        print(f"  {t}: 전 {pre[t]['properties']['datetime'][:10]}({cc_pre:.0f}%) / 후 {post[t]['properties']['datetime'][:10]}({cc_post:.0f}%)")
        nbr_pre, tr, crs = nbr_tile(pre[t])
        nbr_post, _, _ = nbr_tile(post[t])
        h = min(nbr_pre.shape[0], nbr_post.shape[0]); w = min(nbr_pre.shape[1], nbr_post.shape[1])
        dnbr = (nbr_pre[:h, :w] - nbr_post[:h, :w]).astype("float32")
        prof = {"driver": "GTiff", "height": h, "width": w, "count": 1, "dtype": "float32",
                "crs": crs, "transform": tr, "nodata": np.nan}
        mp = OUT / f"_dnbr_{t}.tif"
        with rasterio.open(mp, "w", **prof) as ds: ds.write(dnbr, 1)
        dnbr_rasters.append(mp)

    # 모자이크
    srcs = [rasterio.open(p) for p in dnbr_rasters]
    mosaic, mtrans = merge(srcs)
    prof = srcs[0].profile.copy(); prof.update(height=mosaic.shape[1], width=mosaic.shape[2], transform=mtrans)
    for s in srcs: s.close()
    outp = OUT / "sancheong_dnbr_2025.tif"
    with rasterio.open(outp, "w", **prof) as ds: ds.write(mosaic[0], 1)
    for p in dnbr_rasters: p.unlink()

    v = mosaic[0][np.isfinite(mosaic[0])]
    print(f"\ndNBR 모자이크 저장: {outp}  ({mosaic.shape[1]}x{mosaic.shape[2]}, {prof['crs']})")
    print(f"  dNBR 범위 {np.nanmin(v):.2f}~{np.nanmax(v):.2f}, 평균 {np.nanmean(v):.3f}")
    for lab, lo in [("high(>0.66)", 0.66), ("mod-high(0.44~)", 0.44), ("low(0.1~)", 0.1)]:
        print(f"  dNBR {lab}: {(v > lo).mean()*100:.1f}%")

if __name__ == "__main__":
    main()
