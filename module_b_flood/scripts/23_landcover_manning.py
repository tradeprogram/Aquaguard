"""
23_landcover_manning.py  (Module B 입력 — 조도계수 Manning n 그리드)

ESA WorldCover 2021 v200(10m, 개방·STAC 무료)을 산청 bbox로 받아 DEM 5m 격자(EPSG:5179)에
정합하고, 토지피복 클래스 → Manning 조도계수 n 룩업으로 n 래스터를 만든다(SPEC §5: B만 조도 사용).

Manning n 출처(하천수리학 표준):
- Chow (1959) "Open-Channel Hydraulics" Table 5-6
- Arcement & Schneider (1989) USGS WSP 2339 (하도·홍수터 n 산정)
- SFINCS 매뉴얼 landuse 예시(Deltares) 범위와 정합.
값은 문헌 중앙값 채택, 임의변경 금지(SPEC 원칙).

WorldCover 클래스코드(ESA):
 10 Tree, 20 Shrubland, 30 Grassland, 40 Cropland, 50 Built-up,
 60 Bare/sparse, 70 Snow/ice, 80 Water, 90 Wetland, 95 Mangrove, 100 Moss/lichen
"""
from __future__ import annotations
import warnings; warnings.filterwarnings("ignore")
import json
from pathlib import Path
import numpy as np, rasterio, requests
from rasterio.warp import reproject, Resampling, transform_bounds
from rasterio.windows import from_bounds

ROOT = Path(r"G:/연구/공모전/아쿠아가드")
DEM = ROOT/"data"/"dem"/"산청_dem_5m_5179.tif"
OUT = ROOT/"data"/"sancheong_fos".replace("sancheong_fos","hydro") if False else ROOT/"data"/"hydro"
OUT.mkdir(parents=True, exist_ok=True)
BBOX = [127.7284, 35.2197, 128.0668, 35.5619]  # 산청 (Module A와 동일)
STAC = "https://planetarycomputer.microsoft.com/api/stac/v1/search"
SIGN = "https://planetarycomputer.microsoft.com/api/sas/v1/sign?href="

# 토지피복 → Manning n (문헌 중앙값; Chow1959 / Arcement&Schneider1989)
LC2N = {10:0.120, 20:0.060, 30:0.035, 40:0.040, 50:0.050,
        60:0.025, 70:0.025, 80:0.030, 90:0.050, 95:0.080, 100:0.030}
N_DEFAULT = 0.040

def sign(href):
    return requests.get(SIGN+requests.utils.quote(href,safe=""),timeout=30).json()["href"]

def main():
    # 기준격자 = 산청 DEM 5m 5179
    with rasterio.open(DEM) as ds:
        REF_TR, REF_CRS, REF_SHAPE = ds.transform, ds.crs, (ds.height, ds.width)
        dem = ds.read(1)
    print(f"기준격자 DEM {REF_SHAPE} {REF_CRS}")

    body = {"collections":["esa-worldcover"], "bbox":BBOX, "limit":10}
    feats = requests.post(STAC, json=body, timeout=60).json()["features"]
    # 최신(2021, v200) 우선
    feats = sorted(feats, key=lambda f: f["properties"].get("start_datetime",""), reverse=True)
    print(f"WorldCover tiles: {len(feats)} → {[f['id'] for f in feats[:6]]}")

    acc = np.zeros(REF_SHAPE, dtype="uint8")
    for f in feats:
        asset = f["assets"].get("map") or list(f["assets"].values())[0]
        href = sign(asset["href"])
        with rasterio.open(href) as ds:
            b = transform_bounds("EPSG:4326", ds.crs, *BBOX)
            try:
                win = from_bounds(*b, transform=ds.transform)
                arr = ds.read(1, window=win); st = ds.window_transform(win); sc = ds.crs
            except Exception:
                continue
        if arr.size == 0: continue
        dst = np.zeros(REF_SHAPE, dtype="uint8")
        reproject(arr, dst, src_transform=st, src_crs=sc,
                  dst_transform=REF_TR, dst_crs=REF_CRS, resampling=Resampling.nearest)
        acc = np.where(acc==0, dst, acc)  # 첫 유효값(모자이크)

    vals, cnts = np.unique(acc[acc>0], return_counts=True)
    dist = {int(v):int(c) for v,c in zip(vals,cnts)}
    print("LC 분포(px):", dist)

    # Manning n 그리드
    n = np.full(REF_SHAPE, N_DEFAULT, dtype="float32")
    for code, nv in LC2N.items():
        n[acc==code] = nv
    n[acc==0] = N_DEFAULT

    # 저장: 토지피복 + Manning n
    prof = dict(driver="GTiff", height=REF_SHAPE[0], width=REF_SHAPE[1], count=1,
                crs=REF_CRS, transform=REF_TR, compress="deflate")
    with rasterio.open(OUT/"sancheong_worldcover_5m_5179.tif","w",dtype="uint8",nodata=0,**prof) as ds:
        ds.write(acc,1)
    with rasterio.open(OUT/"sancheong_manning_5m_5179.tif","w",dtype="float32",nodata=0,**prof) as ds:
        ds.write(n,1)

    meta = {"source":"ESA WorldCover 2021 v200 (10m, open) via MS Planetary Computer",
            "manning_ref":"Chow 1959 Table5-6; Arcement&Schneider 1989 USGS WSP2339",
            "lc2n":LC2N, "n_default":N_DEFAULT,
            "lc_distribution_px":dist,
            "n_stats":{"min":float(np.nanmin(n)),"max":float(np.nanmax(n)),
                       "mean":round(float(np.nanmean(n)),4),"median":float(np.nanmedian(n))}}
    (OUT/"manning_meta.json").write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding="utf-8")
    print("Manning n: mean %.4f median %.4f" % (meta["n_stats"]["mean"], meta["n_stats"]["median"]))
    print("saved -> data/hydro/sancheong_worldcover_5m_5179.tif, sancheong_manning_5m_5179.tif")

if __name__ == "__main__":
    main()
