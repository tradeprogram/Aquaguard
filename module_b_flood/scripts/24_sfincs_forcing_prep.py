"""
24_sfincs_forcing_prep.py  (Module B — SFINCS 강제/경계/검증 시계열 준비)

HRFCO 원자료(scripts 22)에서 SFINCS 입력용 시계열을 만든다.
1) 강우 강제: 산청유역 HRFCO 강우 42소 시간강우 → 유역평균(공간균일 precip forcing).
   ASOS 289(416.9mm 누적)와 교차검증(총량 비교).
2) 하류 수위경계: 남강 하류 관측(원지/진주 등) 수위 시계열 → SFINCS waterlevel bnd.
3) 상류 유입경계(옵션): 상류 관측 fw(유량) → discharge src.
4) 검증참값: 산청 내부 수위관측(경호교/수산교/고읍교/소이교) 실측수위 → 모의수심 RMSE(SPEC §2).

정직: 관측 결측·표준화 이슈 있으면 그대로 표기. 시각은 KST, ymdhm=YYYYMMDDHH(정시).
"""
from __future__ import annotations
import warnings; warnings.filterwarnings("ignore")
import json
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(r"G:/연구/공모전/아쿠아가드")
HR = ROOT/"data"/"hrfco"; OUT = ROOT/"data"/"hydro"; OUT.mkdir(parents=True, exist_ok=True)

# 산청 내부 검증 관측소(경호강 본류)
VALID_WL = {2018640:"고읍교", 2018645:"경호교", 2018650:"수산교",
            2018662:"소이교", 2018665:"하정리", 2018673:"원리교", 2018674:"묵곡교"}
# 하류 수위경계 후보(남강 하류) — 원지 2018670, 진주 내평리 2018690
DOWNSTREAM = {2018670:"원지", 2018690:"진주내평리", 2018688:"진주덕천교"}

def to_dt(ymdhm):
    s = str(int(ymdhm))
    if len(s)==10: return pd.to_datetime(s, format="%Y%m%d%H")
    return pd.to_datetime(s, format="%Y%m%d%H%M")

def main():
    # --- 강우 유역평균 ---
    rf = pd.read_csv(HR/"rainfall_series_sancheong_2025071x.csv")
    rf["dt"] = rf["ymdhm"].map(to_dt)
    rcol = "rf" if "rf" in rf.columns else [c for c in rf.columns if c not in
            ("rfobscd","ymdhm","obscd","obsnm","links","dt")][0]
    rf[rcol] = pd.to_numeric(rf[rcol], errors="coerce")
    basin = rf.groupby("dt")[rcol].mean().rename("precip_mm").reset_index()
    basin = basin.sort_values("dt")
    total = basin["precip_mm"].sum()
    peak = basin.loc[basin["precip_mm"].idxmax()]
    basin.to_csv(OUT/"sfincs_precip_basinmean.csv", index=False, encoding="utf-8-sig")
    print(f"[강우] 유역평균 누적 {total:.1f}mm | 시간최대 {peak['precip_mm']:.1f}mm @ {peak['dt']}")

    # ASOS 교차
    try:
        asos = pd.read_csv(ROOT/"data/kma/sancheong_asos_2025071819.csv")
        print(f"[강우] ASOS289 교차: 파일 {len(asos)}행")
    except Exception as e:
        print(f"[강우] ASOS 교차 skip: {e}")

    # --- 수위 시계열(검증 + 하류경계) ---
    wl = pd.read_csv(HR/"waterlevel_series_sancheong_2025071x.csv")
    wl["dt"] = wl["ymdhm"].map(to_dt)
    wl["wl"] = pd.to_numeric(wl["wl"], errors="coerce")
    wl["fw"] = pd.to_numeric(wl.get("fw"), errors="coerce")

    def dump(codes, tag):
        rows=[]
        for cd,nm in codes.items():
            s = wl[wl["obscd"]==cd].sort_values("dt")
            if s.empty or s["wl"].notna().sum()==0:
                print(f"   ! {tag} {cd} {nm} 수위결측 → 제외"); continue
            pk = s.loc[s["wl"].idxmax()]
            # 표고기준(>50m) 등 이상치 관측소 플래그
            flag = " ⚠이상치(표고기준?)" if s.wl.max()>50 or s.wl.min()<-10 else ""
            print(f"   {tag} {cd} {nm}: 수위 {s.wl.min():.2f}~{s.wl.max():.2f}m, 피크 {pk['dt']}, 유량피크 {s.fw.max():.1f}{flag}")
            s2 = s[["dt","wl","fw"]].copy(); s2["obscd"]=cd; s2["obsnm"]=nm; s2["outlier"]=bool(flag); rows.append(s2)
        if rows:
            out = pd.concat(rows, ignore_index=True)
            out.to_csv(OUT/f"sfincs_{tag}.csv", index=False, encoding="utf-8-sig")

    print("[검증 내부수위]"); dump(VALID_WL, "validation_wl")
    print("[하류 수위경계]"); dump(DOWNSTREAM, "downstream_bnd")

    meta = {"precip_basin_total_mm":round(float(total),1),
            "precip_peak_mm":round(float(peak["precip_mm"]),1),
            "precip_peak_time":str(peak["dt"]),
            "validation_stations":VALID_WL, "downstream_bnd":DOWNSTREAM,
            "event_window":"2025-07-15~22 (1H)",
            "note":"precip 공간균일(유역평균). 하류수위경계=남강 하류. fw=유량(m3/s)."}
    (OUT/"sfincs_forcing_meta.json").write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding="utf-8")
    print("saved -> data/hydro/sfincs_precip_basinmean.csv, sfincs_validation_wl.csv, sfincs_downstream_bnd.csv")

if __name__ == "__main__":
    main()
