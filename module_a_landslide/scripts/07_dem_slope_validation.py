"""
07_dem_slope_validation.py  (Module A — A-2 DEM 경사로 재검증)

Copernicus GLO-30 DEM(무료·무로그인)로 경사를 계산해, 04의 토양도 경사등급(거친
범주)을 대체하고 안동 우려지역 검증 AUC를 다시 측정한다. 5m DEM(국토정보플랫폼)
확보 시 동일 파이프라인에 해상도만 올리면 됨.

경사: DEM 모자이크 → EPSG:5186(m) 30m 재투영 → np.gradient → slope(°).
지점경사 + 상부 발생부 경사(200m 최대, maximum_filter)를 각각 산출.
토성·토심은 03 소일샘플(andong_points_soil.csv) 재사용. 가상값 없음.
"""
from __future__ import annotations
import warnings; warnings.filterwarnings("ignore")
import json, math
from pathlib import Path
import numpy as np, pandas as pd
import rasterio
from rasterio.merge import merge
from rasterio.warp import calculate_default_transform, reproject, Resampling
from scipy.ndimage import maximum_filter
from sklearn.metrics import roc_auc_score

DEM_DIR = Path(r"G:/연구/공모전/아쿠아가드/data/dem")
OUT = Path(r"G:/연구/공모전/아쿠아가드/outputs")
BUNDLE = json.loads((OUT / "fos_parameter_bundle.json").read_text(encoding="utf-8"))
TEX = BUNDLE["texture_strength_ST"]; DEPTH = BUNDLE["soil_depth_AD"]
DST_CRS = "EPSG:5186"; RES = 30.0; GAMMA_W = 9.81; BUF_PX = 7  # 7px*30m≈200m 반경

def build_slope():
    tiles = list(DEM_DIR.glob("Copernicus_DSM_*_DEM.tif"))
    srcs = [rasterio.open(t) for t in tiles]
    mosaic, mtrans = merge(srcs)
    src0 = srcs[0]
    # 4326 mosaic → 5186(m) 재투영
    dst_trans, w, h = calculate_default_transform(
        src0.crs, DST_CRS, mosaic.shape[2], mosaic.shape[1],
        *rasterio.transform.array_bounds(mosaic.shape[1], mosaic.shape[2], mtrans), resolution=RES)
    dem_m = np.empty((h, w), dtype="float32")
    reproject(mosaic[0], dem_m, src_transform=mtrans, src_crs=src0.crs,
              dst_transform=dst_trans, dst_crs=DST_CRS, resampling=Resampling.bilinear)
    for s in srcs: s.close()
    dem_m[dem_m < -1000] = np.nan
    # 경사(도): np.gradient (cellsize=RES m)
    gy, gx = np.gradient(dem_m, RES, RES)
    slope = np.degrees(np.arctan(np.sqrt(gx**2 + gy**2)))
    slope_up = maximum_filter(np.nan_to_num(slope, nan=0.0), size=BUF_PX*2+1)  # 상부 발생부 대용
    return slope, slope_up, dst_trans

def sample(arr, trans, xs, ys):
    inv = ~trans
    out = []
    H, W = arr.shape
    for x, y in zip(xs, ys):
        c, r = inv * (x, y)
        c, r = int(round(c)), int(round(r))
        out.append(arr[r, c] if (0 <= r < H and 0 <= c < W) else np.nan)
    return np.array(out)

def fos_sat(slope, c, phi, g, z, m=1.0):
    b = math.radians(max(0.1, min(slope, 89))); d = g*z*math.sin(b)*math.cos(b)
    return float("inf") if d <= 0 else (c+(g-m*GAMMA_W)*z*math.cos(b)**2*math.tan(math.radians(phi)))/d
def prob(f, k=6.0): f = max(0, min(f, 5)); return 1/(1+math.exp(k*(f-1)))

def main():
    slope, slope_up, trans = build_slope()
    print(f"DEM 경사 래스터: {slope.shape}, 중앙 경사 {np.nanmedian(slope):.1f}°")

    df = pd.read_csv(OUT / "andong_points_soil.csv")
    df = df[df["ST_class"].isin(TEX.keys()) & df["AD_class"].isin(DEPTH.keys())].copy()
    # 좌표 5174 → 5186
    import pyproj
    tf = pyproj.Transformer.from_crs("EPSG:5174", DST_CRS, always_xy=True)
    xs, ys = tf.transform(df["x_5174"].values, df["y_5174"].values)
    df["slope_pt"] = sample(slope, trans, xs, ys)
    df["slope_up"] = sample(slope_up, trans, xs, ys)
    df = df.dropna(subset=["slope_pt", "slope_up"])

    def calc(col):
        def f(row):
            t = TEX[row["ST_class"]]; z = DEPTH[row["AD_class"]]
            return prob(fos_sat(row[col], t["c_kpa"], t["phi_deg"], t["gamma_kn_m3"], z))
        return df.apply(f, axis=1)
    df["prob_pt"] = calc("slope_pt"); df["prob_up"] = calc("slope_up")

    y = df.label.values
    res = {
        "auc_dem_point":  round(float(roc_auc_score(y, df.prob_pt)), 4),
        "auc_dem_upslope":round(float(roc_auc_score(y, df.prob_up)), 4),
        "auc_slope_point_only":  round(float(roc_auc_score(y, df.slope_pt)), 4),
        "auc_slope_upslope_only":round(float(roc_auc_score(y, df.slope_up)), 4),
        "n_pos": int((y==1).sum()), "n_bg": int((y==0).sum()),
        "dem": "Copernicus GLO-30 (free, no-login)", "note": "vs 04 soil-map-class: point 0.41 / upslope 0.60",
    }
    pos = df[df.label==1]; bg = df[df.label==0]
    print("\n=== DEM 경사 기반 재검증 (04 토양도등급과 비교) ===")
    print(f"  지점경사   AUC = {res['auc_dem_point']:.3f}   (04 토양도등급: 0.41)")
    print(f"  발생부경사 AUC = {res['auc_dem_upslope']:.3f}   (04 토양도등급: 0.60)")
    print(f"  경사중앙값 발생부: 우려 {pos.slope_up.median():.1f}° vs 배경 {bg.slope_up.median():.1f}°")
    df.to_csv(OUT / "andong_dem_validation.csv", index=False, encoding="utf-8-sig")
    (OUT / "andong_dem_validation_summary.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    print("saved -> outputs/andong_dem_validation.csv, andong_dem_validation_summary.json")

if __name__ == "__main__":
    main()
