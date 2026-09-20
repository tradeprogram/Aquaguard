"""
09_kma_rainfall_client.py  (AquaGuard 트랙① — 기상청 실측강우 연동)

기상청 API허브 ASOS(kma_sfctm3) 시간강수를 받아 파싱·저장한다. 키는 .env에서 로드.
산청 2025-07-19 산사태 사건 실데이터 재현. 가상값 없음(전부 실측).

검증(2026-09-10): 산청(289) 2025-07-18~19 누적 416.9mm, 09시 피크 66.8mm/h.
LDAPS/UM 예보(nwp_vars_down.php)는 이 계정으로 **받을 수 없다** — 권한 문제다.
nwp_file_list.php 가 403 "허용되지 않은 API", nwp_vars_down.php 는 모든 날짜에서
file not exist(vars 파라미터도 무시됨). 같은 키로 ASOS 는 정상이므로 키가 아니라
데이터셋 이용 신청 문제로 보인다. API허브에서 수치예보모델 이용 신청 필요.
주석 이력: '2025-07 보존 확인'(근거 없음) → '보존 안 해 확보 불가'(오독) → 현재.
상세 docs/handoff/TRACK1_REPLY.md §3 (2026-09-20).
"""
from __future__ import annotations
import os, re, io
from pathlib import Path
import requests
import pandas as pd

ROOT = Path(r"G:/연구/공모전/아쿠아가드")
DATA = ROOT / "data" / "kma"; DATA.mkdir(parents=True, exist_ok=True)

def load_key() -> str:
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith("KMA_APIHUB_KEY="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("KMA_APIHUB_KEY not in .env")

KEY = load_key()
BASE = "https://apihub.kma.go.kr/api/typ01/url"

# ASOS 지점번호
STN = {"산청": 289, "안동": 136, "서울": 108}

def fetch_asos_hourly(stn: int, tm1: str, tm2: str) -> pd.DataFrame:
    """ASOS 시간자료 기간조회(kma_sfctm3). 고정폭 텍스트 → DataFrame(time, rn_mm 등)."""
    url = f"{BASE}/kma_sfctm3.php"
    params = {"tm1": tm1, "tm2": tm2, "stn": stn, "help": 0, "authKey": KEY}
    r = requests.get(url, params=params, timeout=30); r.raise_for_status()
    rows = []
    for line in r.text.splitlines():
        if not line or line.startswith("#"):
            continue
        f = line.split()
        if len(f) < 16:
            continue
        # 컬럼순서: [0]YYMMDDHHMI [1]STN ... [11]TA [13]HM [15]RN ...
        def num(x):
            try:
                v = float(x); return None if v <= -9.0 else v
            except ValueError:
                return None
        rows.append({
            "time_kst": pd.to_datetime(f[0], format="%Y%m%d%H%M"),
            "stn": int(f[1]),
            "ta_c": num(f[11]),      # 기온
            "hm_pct": num(f[13]),    # 습도
            "rn_mm": num(f[15]) or 0.0,  # 시간강수량(mm), 결측/무강수→0
        })
    return pd.DataFrame(rows)

def main():
    # 산청 산사태 사건 (2025-07-18 ~ 07-20)
    df = fetch_asos_hourly(STN["산청"], "202507180000", "202507200000")
    out = DATA / "sancheong_asos_2025071819.csv"
    df.to_csv(out, index=False, encoding="utf-8-sig")
    tot = df["rn_mm"].sum(); peak = df.loc[df["rn_mm"].idxmax()]
    print(f"산청 ASOS 시간강우 저장: {out}  ({len(df)}시간)")
    print(f"  누적강수 {tot:.1f} mm | 피크 {peak['rn_mm']:.1f} mm/h @ {peak['time_kst']}")
    # 사건일 08~14시 요약(골든타임 구간)
    win = df[(df.time_kst >= "2025-07-19 06:00") & (df.time_kst <= "2025-07-19 14:00")]
    print("  [07-19 06~14시] " + ", ".join(f"{t.strftime('%H')}시:{v:.0f}" for t,v in zip(win.time_kst, win.rn_mm)))

if __name__ == "__main__":
    main()
