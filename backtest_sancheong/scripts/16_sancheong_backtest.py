"""
16_sancheong_backtest.py  (산청 백테스트 3단계 — 골든타임)

산청 5m 격자 FoS 입력(경사·c'·φ'·γ·z·m0·dNBR) + ASOS 실측 시간강우로
시간별 FoS를 계산해 '위험임계 첫 초과 시각(T_agent)'을 구하고 공식경보(12:37)와 비교.

무한사면: FoS = [c'+Cr + (γ − m·γw)·z·cos²β·tanφ'] / [γ·z·sinβ·cosβ]
- Cr(뿌리점착력)=3.0kPa, 산불피해 f(dNBR)로 약화: Cr_eff = 3.0/f  (Key&Benson 등급)
- m(t) = clip(m0 + 강우기여(t), 0,1),  강우기여 = clip(24h누적/Rsat, 0, Wmax)
  ※ Rsat/Wmax·확률임계는 미보정 파라미터 → 민감도 함께 제시(설계 문서 §9.3)

정직: 이 결과는 물리 baseline + 미보정 강우-습윤 관계의 산출이며,
'N명 구했다'가 아니라 '공식경보보다 N시간 이른 actionable 신호'로만 해석.
"""
from __future__ import annotations
import warnings; warnings.filterwarnings("ignore")
import json, math
from pathlib import Path
import numpy as np, pandas as pd, rasterio

ROOT = Path(r"G:/연구/공모전/아쿠아가드")
FOS = ROOT/"data"/"sancheong_fos"
OUT = ROOT/"outputs"
GW = 9.81; CR_HEALTHY = 3.0
RSAT = 200.0; WMAX = 0.85     # 강우→습윤(미보정)
SLOPE_MIN = 15.0              # 산사태 가능 사면만(완만지 제외)
K_SIG = 6.0                   # FoS→확률 시그모이드(미보정)

def load(name):
    with rasterio.open(FOS/name) as ds: return ds.read(1).astype("float32")

def fire_f(dnbr):
    f = np.ones_like(dnbr)
    f[dnbr>=0.1] = 1.2; f[dnbr>=0.27]=2.0; f[dnbr>=0.44]=3.75   # low/mod/high
    f[~np.isfinite(dnbr)] = 1.0
    return f

def main():
    beta = np.deg2rad(np.clip(load_slope_deg(), 0.1, 89))
    c = load("c_kpa.tif"); phi = np.deg2rad(load("phi_deg.tif")); gam = load("gamma.tif")
    z = load("z_m.tif"); m0 = load("m0.tif"); dnbr = load("dnbr.tif")
    slope_deg = load_slope_deg()

    valid = np.isfinite(c)&np.isfinite(z)&np.isfinite(beta)&(slope_deg>=SLOPE_MIN)
    cr_eff = CR_HEALTHY/fire_f(dnbr)
    cosb=np.cos(beta); sinb=np.sin(beta)
    D = gam*z*sinb*cosb
    C = c + cr_eff
    A = (gam)*z*cosb**2*np.tan(phi)          # m=0항 계수
    B = GW*z*cosb**2*np.tan(phi)             # m 계수(뺄셈)
    # FoS(m) = (C + A - m*B)/D

    # 강우 시계열
    rain = pd.read_csv(ROOT/"data"/"kma"/"sancheong_asos_2025071819.csv", parse_dates=["time_kst"])
    rain = rain.sort_values("time_kst").reset_index(drop=True)
    rain["cum24"] = rain["rn_mm"].rolling(24, min_periods=1).sum()

    npix = valid.sum()
    t_official = pd.Timestamp("2025-07-19 12:37"); t_report=pd.Timestamp("2025-07-19 08:00")

    # === 민감도 2시나리오 (설계 문서 §9.3) ===
    # A: 토양도 토성(보수적)  B: 풍화화강토(P3 부산실측 c'2·φ36, 급사면 실제 파괴재료)
    scenarios = {
        "A_soilmap": dict(C=C, A=A, B=B, D=D),
        "B_weathered": None,  # 아래에서 c'=2, phi=36, gamma=19로 재계산
    }
    # B 시나리오 계수 (풍화토, Cr는 산불 f 반영 동일)
    cB=2.0; phiB=np.deg2rad(36.0); gamB=19.0
    DB=gamB*z*sinb*cosb; CB=cB+cr_eff; AB=gamB*z*cosb**2*np.tan(phiB); BB=GW*z*cosb**2*np.tan(phiB)
    scenarios["B_weathered"]=dict(C=CB, A=AB, B=BB, D=DB)

    results={}
    for name,co in scenarios.items():
        rows=[]
        for _,r in rain.iterrows():
            rain_term=min(WMAX, r["cum24"]/RSAT); m=np.clip(m0+rain_term,0,1)
            fos=(co["C"]+co["A"]-m*co["B"])/co["D"]
            crit=valid&(fos<1.0)
            rows.append({"time":r["time_kst"],"rn":r["rn_mm"],"cum24":round(r["cum24"],1),
                         "crit_frac_%":round(100*crit.sum()/npix,3)})
        results[name]=pd.DataFrame(rows)

    # 병합 저장
    out=results["A_soilmap"][["time","rn","cum24"]].copy()
    out["critA_%"]=results["A_soilmap"]["crit_frac_%"]
    out["critB_%"]=results["B_weathered"]["crit_frac_%"]
    out.to_csv(OUT/"sancheong_backtest_timeseries.csv", index=False, encoding="utf-8-sig")

    print(f"산사태 가능사면(≥{SLOPE_MIN}°) 픽셀: {npix:,}")
    print(out.to_string(index=False))
    print("\n=== T_agent (임계초과율이 그날 최대의 50%에 처음 도달한 시각) ===")
    for name,df in results.items():
        peak=df["crit_frac_%"].max()
        if peak<=0: print(f"  {name}: 임계 미도달(peak {peak}%)"); continue
        hit=df[df["crit_frac_%"]>=0.5*peak]
        ta=hit.iloc[0]["time"]; gt=(t_official-ta).total_seconds()/3600
        print(f"  {name}: peak {peak:.2f}% | T_agent {ta.strftime('%m-%d %H:%M')} | 골든타임(경보12:37−T_agent) {gt:.1f}h")
    print("\n(신고 08:00 · 공식경보 12:37. Rsat/Wmax/시그모이드 미보정 — 두 시나리오로 민감도 제시)")

# --- 슬로프 로더(별도 파일) ---
def load_slope_deg():
    with rasterio.open(ROOT/"data"/"dem"/"산청_slope_5m_5179.tif") as ds:
        return ds.read(1).astype("float32")
def load_slope():
    return load_slope_deg()

if __name__ == "__main__":
    main()
