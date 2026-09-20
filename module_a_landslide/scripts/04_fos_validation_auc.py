"""
04_fos_validation_auc.py  (AquaGuard 트랙① / Module A 검증)

안동 우려지역(양성) vs 배경(무작위)에 Module A의 Infinite Slope FoS를 적용해
presence-vs-background AUC(=R)를 측정한다. FoS 계산은 module_a_landslide/fos.py와
동일 물리(가상값 없음, 파라미터=fos_parameter_bundle.json 문헌값).

취약성 지표: 포화상태(m=1, SHALSTAB류 최악조건) FoS → 확률. 지형(경사)·토성·토심으로
정적 취약성을 판별(강우 임계는 별도 시나리오로 부가 산출). 경사는 정밀토양도 SL
경사등급 중앙값에서 도(°)로 변환(DEM 확보 시 5m로 정밀화 예정 — A-2).

검증 성격(정직): 양성은 '전문가 조사 우려지역'이지 확인된 발생지가 아니다.
따라서 AUC는 '물리 FoS가 우려지역을 배경보다 높게 평가하는 정도'이며,
'실붕괴 예측 정확도'로 과대주장하지 않는다.
"""
from __future__ import annotations
import warnings; warnings.filterwarnings("ignore")
import json, math
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

OUT = Path(r"G:/연구/공모전/아쿠아가드/outputs")
BUNDLE = json.loads((OUT / "fos_parameter_bundle.json").read_text(encoding="utf-8"))
GAMMA_W = 9.81

# SL 경사등급(%) → 대표 경사(도). 등급 중앙값의 %기울기를 atan으로 환산.
SL_PCT_MID = {"0-2%": 1.0, "2-7%": 4.5, "7-15%": 11.0, "15-30%": 22.5,
              "30-60%": 45.0, "60-100%": 80.0}
def slope_deg_from_class(sl_class):
    pct = SL_PCT_MID.get(str(sl_class))
    return None if pct is None else math.degrees(math.atan(pct / 100.0))

TEX = BUNDLE["texture_strength_ST"]      # 한글 토성 → c/phi/gamma/ksat
DEPTH = BUNDLE["soil_depth_AD"]          # "<20".. → z
DRAIN = BUNDLE["drainage_wetness_DC"]    # 배수 → m0

def fos_saturated(slope_deg, c_kpa, phi_deg, gamma, z, cr=0.0, m=1.0):
    beta = math.radians(max(0.1, min(slope_deg, 89.0)))
    driving = gamma * z * math.sin(beta) * math.cos(beta)
    if driving <= 0: return float("inf")
    resisting = (c_kpa + cr + (gamma - m * GAMMA_W) * z * math.cos(beta)**2 * math.tan(math.radians(phi_deg)))
    return resisting / driving

def prob(fos, k=6.0):
    fos = max(0.0, min(fos, 5.0))
    return 1.0 / (1.0 + math.exp(k * (fos - 1.0)))

def main():
    df = pd.read_csv(OUT / "andong_points_soil.csv")
    n0 = len(df)
    # 유효 분류만: ST 토성이 파라미터표에 있고, SL/AD 유효
    df = df[df["ST_class"].isin(TEX.keys())]
    df = df[df["SL_class"].map(slope_deg_from_class).notna()]
    df = df[df["AD_class"].isin(DEPTH.keys())].copy()
    print(f"유효 지점: {len(df)}/{n0} (기타·결측 제외)")

    def compute(row):
        t = TEX[row["ST_class"]]
        z = DEPTH[row["AD_class"]]
        beta = slope_deg_from_class(row["SL_class"])
        fos = fos_saturated(beta, t["c_kpa"], t["phi_deg"], t["gamma_kn_m3"], z, cr=0.0, m=1.0)
        return pd.Series({"slope_deg": beta, "z_m": z, "c_kpa": t["c_kpa"],
                          "phi_deg": t["phi_deg"], "fos_sat": fos, "prob_sat": prob(fos)})
    res = df.join(df.apply(compute, axis=1))

    y = res["label"].values
    p = res["prob_sat"].values
    auc = roc_auc_score(y, p)
    # 부가: 경사만으로의 AUC(물리가 경사 이상을 하는지 비교 기준)
    slope_only = res["slope_deg"].values
    auc_slope = roc_auc_score(y, slope_only)

    pos = res[res.label == 1]; bg = res[res.label == 0]
    print(f"\n=== presence-vs-background AUC (R) ===")
    print(f"  Module A FoS(포화) 확률  AUC = {auc:.3f}   (n_pos={len(pos)}, n_bg={len(bg)})")
    print(f"  (참고) 경사만 AUC       = {auc_slope:.3f}")
    print(f"\n  평균 landslide_prob : 우려지역 {pos.prob_sat.mean():.3f}  vs 배경 {bg.prob_sat.mean():.3f}")
    print(f"  평균 FoS(포화)      : 우려지역 {pos.fos_sat.median():.2f}  vs 배경 {bg.fos_sat.median():.2f} (중앙값)")
    print(f"  FoS<1(불안정) 비율  : 우려지역 {(pos.fos_sat<1).mean():.1%}  vs 배경 {(bg.fos_sat<1).mean():.1%}")

    res.to_csv(OUT / "andong_fos_validation.csv", index=False, encoding="utf-8-sig")
    summary = {
        "n_positive": int(len(pos)), "n_background": int(len(bg)),
        "auc_fos_prob": round(float(auc), 4), "auc_slope_only": round(float(auc_slope), 4),
        "mean_prob_positive": round(float(pos.prob_sat.mean()), 4),
        "mean_prob_background": round(float(bg.prob_sat.mean()), 4),
        "frac_unstable_positive": round(float((pos.fos_sat < 1).mean()), 4),
        "frac_unstable_background": round(float((bg.fos_sat < 1).mean()), 4),
        "method": "Infinite Slope FoS (saturated m=1), slope from soil-map SL class (no DEM yet)",
        "honesty": "positives = surveyed concern areas (not confirmed failures); presence-vs-background AUC",
    }
    (OUT / "andong_fos_validation_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\nsaved -> outputs/andong_fos_validation.csv, andong_fos_validation_summary.json")

if __name__ == "__main__":
    main()
