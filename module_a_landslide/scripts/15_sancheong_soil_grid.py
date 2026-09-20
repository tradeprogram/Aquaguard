"""
15_sancheong_soil_grid.py  (산청 백테스트 2단계)

정밀토양도(EPSG:5174) 심토토성(ST)·유효토심(AD)·배수(DC)를 산청 5m 격자
(EPSG:5179, 슬로프 래스터 기준)에 rasterize → FoS 지반정수 격자(c'·φ'·γ·z·m0) 생성.
파라미터는 fos_parameter_bundle.json(문헌 3중검증). dNBR도 격자에 리샘플.
"""
from __future__ import annotations
import warnings; warnings.filterwarnings("ignore")
import json
from pathlib import Path
import numpy as np, geopandas as gpd, pyogrio, rasterio
from rasterio.features import rasterize
from rasterio.warp import transform_bounds, reproject, Resampling

ROOT = Path(r"G:/연구/공모전/아쿠а가드".replace("а","아"))
SOIL = Path(r"G:/연구/산사태/데이터/토양도")
OUT = ROOT / "data" / "sancheong_fos"; OUT.mkdir(parents=True, exist_ok=True)
REF = ROOT / "data" / "dem" / "산청_slope_5m_5179.tif"
BUNDLE = json.loads((ROOT / "outputs" / "fos_parameter_bundle.json").read_text(encoding="utf-8"))
TEX = BUNDLE["texture_strength_ST"]; DEPTH = BUNDLE["soil_depth_AD"]; DRAIN = BUNDLE["drainage_wetness_DC"]

ST_KR = {1:"사질",2:"사양질",3:"미사사양질",4:"식양질",5:"미사식양질",6:"식질",7:"역질",8:"사력질"}
AD_KR = {1:"<20",2:"20-50",3:"50-100",4:">100"}
DC_KR = {1:"매우양호",2:"양호",3:"약간양호",4:"약간불량",5:"불량",6:"매우불량"}

def load_ref():
    with rasterio.open(REF) as ds:
        return ds.transform, ds.crs, (ds.height, ds.width), ds.read(1)

def clip_soil(folder, shp, bbox5179, dst_crs):
    # 산청 bbox를 5174로 변환해 읽고 → 5179 재투영
    b74 = transform_bounds(dst_crs, "EPSG:5174", *bbox5179)
    g = pyogrio.read_dataframe(SOIL/folder/shp, bbox=b74, encoding="cp949").set_crs("EPSG:5174", allow_override=True)
    return g.to_crs(dst_crs)

def rasterize_code(g, codecol, transform, shape):
    shapes = ((geom, int(code)) for geom, code in zip(g.geometry, g[codecol]) if code and 0<int(code)<900)
    return rasterize(shapes, out_shape=shape, transform=transform, fill=0, dtype="int16")

def code_to_param(code_arr, code_kr, kr_to_val):
    out = np.full(code_arr.shape, np.nan, dtype="float32")
    for code, kr in code_kr.items():
        val = kr_to_val(kr)
        if val is not None:
            out[code_arr == code] = val
    return out

def main():
    tr, crs, shape, slope = load_ref()
    with rasterio.open(REF) as ds: bbox5179 = tuple(ds.bounds)
    print(f"산청 격자 {shape} @5m, bbox5179 {[round(b) for b in bbox5179]}")

    layers = {"ST":("st","ST_심토토성.shp"),"AD":("ad","AD_유효토심.shp"),"DC":("dc","DC_배수등급.shp")}
    codes = {}
    for k,(folder,shp) in layers.items():
        g = clip_soil(folder, shp, bbox5179, crs)
        cc = [c for c in g.columns if c.upper().startswith("CODE")][0]
        codes[k] = rasterize_code(g, cc, tr, shape)
        print(f"  {k} rasterized: {len(g)} polygons, 유효픽셀 {(codes[k]>0).mean()*100:.0f}%")

    # 코드 → 파라미터 격자
    c   = code_to_param(codes["ST"], ST_KR, lambda kr: TEX.get(kr,{}).get("c_kpa"))
    phi = code_to_param(codes["ST"], ST_KR, lambda kr: TEX.get(kr,{}).get("phi_deg"))
    gam = code_to_param(codes["ST"], ST_KR, lambda kr: TEX.get(kr,{}).get("gamma_kn_m3"))
    z   = code_to_param(codes["AD"], AD_KR, lambda kr: DEPTH.get(kr))
    m0  = code_to_param(codes["DC"], DC_KR, lambda kr: DRAIN.get(kr))

    prof = {"driver":"GTiff","height":shape[0],"width":shape[1],"count":1,"dtype":"float32",
            "crs":crs,"transform":tr,"nodata":np.nan,"compress":"deflate"}
    for name,arr in [("c_kpa",c),("phi_deg",phi),("gamma",gam),("z_m",z),("m0",m0)]:
        with rasterio.open(OUT/f"{name}.tif","w",**prof) as ds: ds.write(arr,1)

    # dNBR 격자 리샘플(32652→5179 산청 격자)
    dnbr_src = ROOT/"data"/"sentinel"/"sancheong_dnbr_2025.tif"
    dnbr = np.full(shape, np.nan, dtype="float32")
    with rasterio.open(dnbr_src) as ds:
        reproject(ds.read(1), dnbr, src_transform=ds.transform, src_crs=ds.crs,
                  dst_transform=tr, dst_crs=crs, resampling=Resampling.bilinear)
    with rasterio.open(OUT/"dnbr.tif","w",**prof) as ds: ds.write(dnbr,1)

    valid = np.isfinite(c)
    print(f"\nFoS 지반정수 격자 저장 → {OUT}")
    print(f"  유효 토양픽셀 {valid.mean()*100:.0f}% | c' 중앙 {np.nanmedian(c):.1f}kPa, phi 중앙 {np.nanmedian(phi):.0f}°, z 중앙 {np.nanmedian(z):.2f}m")
    print(f"  dNBR>0.44(산불) 픽셀 {(dnbr>0.44).sum():,}개")

if __name__ == "__main__":
    main()
