"""
22_hrfco_acquire.py  (Module B 입력·검증 — HRFCO 하천수위/강우/유량)

한강홍수통제소(HRFCO) OpenAPI로 산청 유역의 수위(waterlevel)·강우(rainfall)·
유량(flowrate) 관측소를 좌표기반으로 추출하고, 2025-07 사건기간 시계열을 받는다.
- 수위: SFINCS 하류경계(수위) + 검증참값(관측수위 vs 모의수심 RMSE, SPEC §2)
- 강우: 유역 강제(rainfall forcing) 보조(ASOS 289와 교차)
- 유량: 상류 유입경계(discharge boundary) 후보

좌표계: HRFCO는 위경도 DMS('128-33-04') → 십진 변환. 산청 bbox+버퍼로 필터.
정직: 관측소가 사건기간 결측일 수 있음 — 받은 그대로 저장·보고.
"""
from __future__ import annotations
import warnings; warnings.filterwarnings("ignore")
import json, time
from pathlib import Path
import requests, pandas as pd

def _load_key(name: str) -> str:
    """.env 또는 환경변수에서 API 키를 읽는다. 없으면 즉시 멈춘다(빈 키로 조용히
    실패하면 원인 찾는 데 더 오래 걸린다)."""
    import os
    val = os.environ.get(name)
    if not val:
        for parent in [Path(__file__).resolve().parent, *Path(__file__).resolve().parents]:
            env = parent / ".env"
            if env.exists():
                for line in env.read_text(encoding="utf-8").splitlines():
                    if line.strip().startswith(f"{name}="):
                        val = line.split("=", 1)[1].strip().strip('"').strip("'")
                        break
            if val:
                break
    if not val:
        raise SystemExit(
            f"{name} 가 없습니다. 프로젝트 루트 .env 에 {name}=... 를 넣거나 "
            f"환경변수로 지정하세요. (.env 는 커밋 금지)")
    return val


ROOT = Path(r"G:/연구/공모전/아쿠아가드")
OUT = ROOT/"data"/"hrfco"; OUT.mkdir(parents=True, exist_ok=True)
# API 키는 소스에 박지 않는다 — 저장소가 공개되면 그대로 유출된다.
# 프로젝트 루트 .env 의 HRFCO_API_KEY 를 읽고, 없으면 환경변수에서 찾는다.
KEY = _load_key("HRFCO_API_KEY")
BASE = "http://api.hrfco.go.kr"

# 산청 관심영역 (Module A와 동일 bbox + 상·하류 버퍼 0.15deg)
BBOX = [127.7284-0.15, 35.2197-0.15, 128.0668+0.15, 35.5619+0.15]
EVENT_START = "202507150000"   # YYYYMMDDHHmm (1시간자료)
EVENT_END   = "202507220000"

def dms2dec(s):
    try:
        d, m, sec = [float(x) for x in str(s).strip().split("-")]
        return d + m/60 + sec/3600
    except Exception:
        return None

def get_info(hydro):  # hydro in {waterlevel, rainfall, flowrate}
    u = f"{BASE}/{KEY}/{hydro}/info.json"
    j = requests.get(u, timeout=60).json()
    df = pd.DataFrame(j.get("content", []))
    return df

def in_bbox(df, latcol="lat", loncol="lon"):
    df = df.copy()
    df["latd"] = df[latcol].map(dms2dec)
    df["lond"] = df[loncol].map(dms2dec)
    x0,y0,x1,y1 = BBOX
    m = (df["lond"].between(x0,x1)) & (df["latd"].between(y0,y1))
    return df[m].reset_index(drop=True)

def fetch_series(hydro, obscd, obscol):
    # 1시간 자료: /{key}/{hydro}/list/1H/{obscd}/{start}/{end}.json
    u = f"{BASE}/{KEY}/{hydro}/list/1H/{obscd}/{EVENT_START}/{EVENT_END}.json"
    try:
        j = requests.get(u, timeout=60).json()
        return pd.DataFrame(j.get("content", []))
    except Exception as e:
        print(f"   ! {hydro} {obscd} fetch fail: {e}")
        return pd.DataFrame()

def main():
    summary = {}
    for hydro, codecol in [("waterlevel","wlobscd"), ("rainfall","rfobscd"), ("flowrate","flobscd")]:
        try:
            info = get_info(hydro)
        except Exception as e:
            print(f"[{hydro}] info 실패: {e}"); continue
        if info.empty or "lat" not in info.columns:
            print(f"[{hydro}] info 컬럼: {list(info.columns)[:8]} (좌표없음 → 스킵)"); continue
        near = in_bbox(info)
        print(f"[{hydro}] 전국 {len(info)} → 산청유역 {len(near)}")
        near.to_csv(OUT/f"{hydro}_stations_sancheong.csv", index=False, encoding="utf-8-sig")
        rows = []
        for _, r in near.iterrows():
            obscd = r[codecol]
            ser = fetch_series(hydro, obscd, codecol)
            n = len(ser)
            nm = r.get("obsnm","")
            print(f"   - {obscd} {nm}: {n} rows")
            if n:
                ser["obscd"]=obscd; ser["obsnm"]=nm
                rows.append(ser)
            time.sleep(0.1)
        if rows:
            allser = pd.concat(rows, ignore_index=True)
            allser.to_csv(OUT/f"{hydro}_series_sancheong_2025071x.csv", index=False, encoding="utf-8-sig")
        summary[hydro] = {"stations": len(near), "with_data": len(rows)}
    (OUT/"_acquire_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\nSUMMARY", json.dumps(summary, ensure_ascii=False))

if __name__ == "__main__":
    main()
