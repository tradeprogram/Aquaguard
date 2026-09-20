"""
27_reach_hydrographs.py  (Module B — 경호강 구간모델 경계/검증 수문곡선)

경호강 산청읍 본류 구간(고읍교→경호교→수산교)을 흐름모델(ANUGA/SFINCS)로 풀기 위한
경계·검증 시계열을 HRFCO 실측에서 정리. 수면표고 WSE = 기준표고(gdt) + 관측수위(wl).

- 상류 유입경계(inflow): 고읍교(2018640) 유량 fw(t)  [gdt 106.687, x1029983 y1721527]
- 하류 수위경계(stage) : 수산교(2018650) WSE(t)      [gdt 49.3,   x1039985 y1704745]
- 내부 검증(interior)  : 경호교(2018645) WSE(t)      [gdt 85.446, x1033994 y1713655]

이벤트 2025-07-18 00 ~ 07-20 12 (피크 07-19 13~14시). 시각 t는 tstart로부터 초.
"""
from __future__ import annotations
import warnings; warnings.filterwarnings("ignore")
import json
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(r"G:/연구/공모전/아쿠아가드"); HR = ROOT/"data"/"hrfco"; OUT = ROOT/"data"/"hydro"
GDT = {2018640:106.687, 2018645:85.446, 2018650:49.3}
XY  = {2018640:(1029983,1721527), 2018645:(1033994,1713655), 2018650:(1039985,1704745)}
T0, T1 = pd.Timestamp("2025-07-18 00:00"), pd.Timestamp("2025-07-20 12:00")

def to_dt(v):
    s=str(int(v));  return pd.to_datetime(s, format="%Y%m%d%H" if len(s)==10 else "%Y%m%d%H%M")

def main():
    wl = pd.read_csv(HR/"waterlevel_series_sancheong_2025071x.csv")
    wl["dt"]=wl["ymdhm"].map(to_dt)
    wl["wl"]=pd.to_numeric(wl["wl"],errors="coerce"); wl["fw"]=pd.to_numeric(wl["fw"],errors="coerce")
    def series(cd):
        s=wl[(wl["obscd"]==cd)&(wl["dt"]>=T0)&(wl["dt"]<=T1)].sort_values("dt").copy()
        s["t_sec"]=(s["dt"]-T0).dt.total_seconds().astype(int)
        s["wse"]=GDT[cd]+s["wl"]
        return s
    up=series(2018640); dn=series(2018650); mid=series(2018645)

    up[["t_sec","dt","fw","wl","wse"]].to_csv(OUT/"reach_inflow_고읍교.csv",index=False,encoding="utf-8-sig")
    dn[["t_sec","dt","wl","wse"]].to_csv(OUT/"reach_stage_수산교.csv",index=False,encoding="utf-8-sig")
    mid[["t_sec","dt","wl","wse"]].to_csv(OUT/"reach_valid_경호교.csv",index=False,encoding="utf-8-sig")

    meta={"reach":"경호강 고읍교→경호교→수산교","tstart":str(T0),"tstop":str(T1),
          "inflow_up":{"stn":"고읍교(2018640)","xy_5179":XY[2018640],"gdt":GDT[2018640],
                       "Q_peak_m3s":round(float(up.fw.max()),1),"Q_base_m3s":round(float(up.fw.min()),1)},
          "stage_down":{"stn":"수산교(2018650)","xy_5179":XY[2018650],"gdt":GDT[2018650],
                        "WSE_peak_m":round(float(dn.wse.max()),2),"WSE_base_m":round(float(dn.wse.min()),2)},
          "valid_interior":{"stn":"경호교(2018645)","xy_5179":XY[2018645],"gdt":GDT[2018645],
                            "WSE_peak_m":round(float(mid.wse.max()),2),"WSE_base_m":round(float(mid.wse.min()),2),
                            "wl_peak_m":round(float(mid.wl.max()),2)}}
    (OUT/"reach_hydrograph_meta.json").write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(meta,ensure_ascii=False,indent=2))

if __name__=="__main__": main()
