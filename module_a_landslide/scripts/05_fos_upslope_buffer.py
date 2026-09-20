"""
05_fos_upslope_buffer.py  (Module A 검증 개선 실험)

가설: 실태조사 우려지역 좌표는 발생부(급사면 상단)가 아니라 계곡/수용시설(하단)에
찍혀 있어, 지점 자체 경사가 완만해 FoS가 위험을 못 잡는다(04 결과 AUC 0.41).
검증: 각 지점 200m 버퍼 내 '최급경사·최약토성'(발생부 대용)으로 FoS 재계산 →
AUC가 오르면 위 가설 확인(물리 자체는 타당).  강우/가상값 없음.
"""
from __future__ import annotations
import warnings; warnings.filterwarnings("ignore")
import json, math
from pathlib import Path
import numpy as np, pandas as pd, geopandas as gpd, pyogrio
from sklearn.metrics import roc_auc_score

SOIL_ROOT = Path(r"G:/연구/산사태/데이터/토양도")
OUT = Path(r"G:/연구/공모전/아쿠아가드/outputs")
BUNDLE = json.loads((OUT / "fos_parameter_bundle.json").read_text(encoding="utf-8"))
SOIL_CRS = "EPSG:5174"; GAMMA_W = 9.81; BUF = 200.0
TEX = BUNDLE["texture_strength_ST"]; DEPTH = BUNDLE["soil_depth_AD"]
SL_PCT_MID = {"0-2%":1.0,"2-7%":4.5,"7-15%":11.0,"15-30%":22.5,"30-60%":45.0,"60-100%":80.0}
def sl_deg(c):
    p=SL_PCT_MID.get(str(c)); return None if p is None else math.degrees(math.atan(p/100))

def fos_sat(slope, c, phi, g, z, m=1.0):
    b=math.radians(max(0.1,min(slope,89))); d=g*z*math.sin(b)*math.cos(b)
    if d<=0: return float("inf")
    return (c+(g-m*GAMMA_W)*z*math.cos(b)**2*math.tan(math.radians(phi)))/d
def prob(f,k=6.0): f=max(0,min(f,5)); return 1/(1+math.exp(k*(f-1)))

def main():
    pts = gpd.read_file(OUT / "andong_points_soil.gpkg").to_crs(SOIL_CRS)
    bbox = tuple(pts.total_bounds + np.array([-BUF,-BUF,BUF,BUF]))
    # 버퍼 폴리곤
    buf = pts.copy(); buf["geometry"] = pts.geometry.buffer(BUF); buf["pid"] = range(len(buf))

    # SL 경사, ST 토성 소일 레이어 읽기(안동 bbox)
    def read(folder, shp):
        g = pyogrio.read_dataframe(SOIL_ROOT/folder/shp, bbox=bbox, encoding="cp949").set_crs(SOIL_CRS, allow_override=True)
        cc=[c for c in g.columns if c.upper().startswith("CODE")][0]
        lc=[c for c in g.columns if c not in ("AREA","PERIMETER") and not c.upper().startswith("CODE")][0]
        return g[[cc,lc,"geometry"]].rename(columns={cc:"code",lc:"cls"})
    sl = read("sl","SL_경사.shp"); sl["slope_deg"]=sl["cls"].map(sl_deg)
    st = read("st","ST_심토토성.shp")

    # 버퍼 ∩ SL → 지점별 최급경사
    j_sl = gpd.overlay(buf[["pid","geometry"]], sl[["slope_deg","geometry"]], how="intersection")
    max_slope = j_sl.groupby("pid")["slope_deg"].max()
    # 버퍼 ∩ ST → 지점별 최약토성(c'가 가장 낮은 것)
    st["c_kpa"]=st["cls"].map(lambda k: TEX[k]["c_kpa"] if k in TEX else np.nan)
    j_st = gpd.overlay(buf[["pid","geometry"]], st[["cls","c_kpa","geometry"]], how="intersection")
    weak = j_st.dropna(subset=["c_kpa"]).sort_values("c_kpa").groupby("pid").first()  # 최약

    df = buf[["pid","label","kind"]].copy()
    df["slope_src"] = df["pid"].map(max_slope)
    df["tex_weak"]  = df["pid"].map(weak["cls"])
    df = df.dropna(subset=["slope_src","tex_weak"])
    # 토심은 지점값(04와 동일 소스) — 여기선 대표 0.75m(50-100 중앙) 고정 비교(공정)
    z = 0.75
    def f(row):
        t=TEX[row["tex_weak"]]
        fo=fos_sat(row["slope_src"], t["c_kpa"], t["phi_deg"], t["gamma_kn_m3"], z)
        return prob(fo)
    df["prob_src"]=df.apply(f,axis=1)

    y=df.label.values; auc=roc_auc_score(y, df.prob_src.values)
    auc_sl=roc_auc_score(y, df.slope_src.values)
    pos=df[df.label==1]; bg=df[df.label==0]
    print(f"유효 {len(df)} (pos {len(pos)} / bg {len(bg)})")
    print(f"=== 상부 200m 버퍼(발생부 대용) ===")
    print(f"  AUC(FoS, 발생부경사) = {auc:.3f}   (지점경사 04: 0.41)")
    print(f"  AUC(최급경사만)      = {auc_sl:.3f}")
    print(f"  발생부 경사 중앙값: 우려 {pos.slope_src.median():.1f}° vs 배경 {bg.slope_src.median():.1f}°")
    print(f"  평균 prob: 우려 {pos.prob_src.mean():.3f} vs 배경 {bg.prob_src.mean():.3f}")
    (OUT/"andong_fos_upslope_summary.json").write_text(json.dumps({
        "auc_fos_upslope":round(float(auc),4),"auc_slope_upslope":round(float(auc_sl),4),
        "n_pos":int(len(pos)),"n_bg":int(len(bg)),"buffer_m":BUF,
        "note":"upslope 200m max-slope + weakest texture as source-area proxy"},
        ensure_ascii=False,indent=2),encoding="utf-8")
    print("saved -> outputs/andong_fos_upslope_summary.json")

if __name__=="__main__": main()
