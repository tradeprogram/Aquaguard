"""
46_ldaps_forecast.py — LDAPS 예보 시간강우 → Module A `_forecast` 시계열

`hours_to_critical` 은 예보 시계열이 있어야 산출된다(module_a_landslide/forecast.py).
그동안 그 시계열이 없어 항상 null 이었다. 이 스크립트가 기상청 API허브에서 **실제
LDAPS 예보**를 받아 계약이 정한 형식으로 떨어뜨린다.

    input["_forecast"] = {"source": "LDAPS 2025-07-19T09:00 발표", "rain_1h_mm": [...]}

leakage 없음 — 발표시각(tmfc) 이후 예측만 쓰므로 사후 실측이 섞이지 않는다.

────────────────────────────────────────────────────────────────────────────
호출 규격 (여기까지 오는 데 시행착오가 있어 전부 적어 둔다)

  nwp_vars_down.php?nwp=l015&sub=unis&vars=ncpc&tmfc=YYYYMMDDHH&ef=N&dataType=TEXT

  nwp=l015   UM 국지예보모델(LDAPS) 1.5km. ※ UM 은 2026-03-31 생산종료(→ KIM)
  sub=unis   **필수**. 빠뜨리면 서버가 없는 경로를 만들어 "file not exist" 가 뜬다
  vars=ncpc  4글자 코드다. `ncpcp`(5글자)는 거부된다.
             nwp_grib_guidance.pdf p21~22 의 ${VAR} 열이 이 값이다.
             강수 계열 중 실제로 값이 오는 것: ncpc(대규모강수) · lspr(강수율).
             apcp(총강수)·tpra·acpc·cpra 는 인식은 되나 빈 응답이다.
             LDAPS 1.5km 는 대류를 명시적으로 푸는 해상도라 대규모강수 ≈ 총강수다.
  tmfc       발표시각 **UTC**. 09 KST = 00 UTC
  ef         예측시간(시). 국지는 1시간 간격, 0~36h

응답: 1행 파일명, 2행 격자정보, 3행부터 값(10개/행, -9999=결측).
      602(동서) × 781(남북), 저장순서 남→북·서→동.

격자 지리참조: Lambert Conformal Conic, lat_1=30 lat_2=60 lat_0=38 lon_0=126,
구면 반경 6371229m. SW 모서리 121.834429E / 32.256875N, 간격 1500m.
(검증: 역변환 오차 ~700m 로 1.5km 격자 이내)

정직: ncpc 는 대규모강수만이라 대류성 강수를 따로 세지 않는다. 그리고 아래 실행
결과에서 보듯 **LDAPS 는 이 사건의 강도를 과소예측**했다 — 산청 격자 예보 최대
18.5mm/h 대 ASOS 실측 66.8mm/h. 예보를 쓰면 hours_to_critical 이 실측 기반보다
늦게 나온다. 그것이 실제 운영 조건이므로 보정하지 않고 그대로 쓴다.
"""
from __future__ import annotations

import json
import sys
import warnings

warnings.filterwarnings("ignore")
from pathlib import Path

import numpy as np
import requests
from pyproj import CRS, Transformer

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(r"G:/연구/공모전/아쿠아가드")
OUT = ROOT / "outputs"
API = "https://apihub.kma.go.kr/api/typ06/url/nwp_vars_down.php"

NX, NY, DX = 602, 781, 1500.0
SW_LON, SW_LAT = 121.834429, 32.256875
LDAPS_CRS = CRS.from_proj4(
    "+proj=lcc +lat_1=30 +lat_2=60 +lat_0=38 +lon_0=126 "
    "+a=6371229 +b=6371229 +units=m +no_defs")
MISSING = -9000.0


def load_key() -> str:
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith("KMA_APIHUB_KEY="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("KMA_APIHUB_KEY not in .env")


def grid_index(x_5179: float, y_5179: float) -> tuple[int, int]:
    to_lcc = Transformer.from_crs(LDAPS_CRS.geodetic_crs, LDAPS_CRS, always_xy=True)
    lon, lat = Transformer.from_crs("EPSG:5179", "EPSG:4326", always_xy=True).transform(x_5179, y_5179)
    x0, y0 = to_lcc.transform(SW_LON, SW_LAT)
    xs, ys = to_lcc.transform(lon, lat)
    return int(round((xs - x0) / DX)), int(round((ys - y0) / DX))


def fetch(key: str, tmfc: str, ef: int, var: str = "ncpc") -> np.ndarray | None:
    """LDAPS 단일면 격자 1장. 값이 안 오면 None(빈 응답은 40B 파일명뿐이다)."""
    r = requests.get(API, params=dict(nwp="l015", sub="unis", vars=var, tmfc=tmfc,
                                      ef=ef, dataType="TEXT", authKey=key), timeout=180)
    if len(r.content) < 5000:
        return None
    vals: list[float] = []
    for line in r.content.decode("utf-8", "replace").splitlines()[2:]:
        for tok in line.split():
            try:
                vals.append(float(tok))
            except ValueError:
                pass
    if len(vals) < NX * NY:
        return None
    return np.array(vals[:NX * NY]).reshape(NY, NX)


def series(key: str, tmfc: str, ix: int, iy: int, hours: int = 12,
           radius: int = 2) -> list[dict]:
    """예보 시간강우 시계열. 지점값과 주변 반경 최대를 함께 낸다.

    1.5km 격자에서 대류셀은 한 칸 차이로 크게 갈린다. 지점값만 쓰면 바로 옆 칸의
    폭우를 놓치므로, 보수적 운용을 위해 주변 최대도 같이 기록한다(선택은 호출부 몫).
    """
    rows = []
    for ef in range(1, hours + 1):
        a = fetch(key, tmfc, ef)
        if a is None:
            rows.append({"ef": ef, "point_mm": None, "nbr_max_mm": None})
            continue
        v = float(a[iy, ix])
        sub = a[max(0, iy - radius):iy + radius + 1, max(0, ix - radius):ix + radius + 1]
        sub = sub[sub > MISSING]
        rows.append({
            "ef": ef,
            "point_mm": round(v, 3) if v > MISSING else None,
            "nbr_max_mm": round(float(sub.max()), 3) if sub.size else None,
        })
        print(f"    ef={ef:02d}  지점 {rows[-1]['point_mm']}  주변최대 {rows[-1]['nbr_max_mm']}", flush=True)
    return rows


def main() -> None:
    key = load_key()
    # 데모 트리거 좌표(시천면 산불피해 급사면) — contracts/module_a.example.json 과 동일
    X, Y = 1028621.7, 1696861.2
    ix, iy = grid_index(X, Y)
    print(f"산청 데모 좌표 → LDAPS 격자 ({ix}, {iy})")

    out = {"생성": __import__("datetime").datetime.now().isoformat(timespec="minutes"),
           "격자": {"ix": ix, "iy": iy, "nx": NX, "ny": NY, "dx_m": DX},
           "변수": "ncpc (Large-scale Precipitation, mm)",
           "발표별": {}}

    for tmfc, label in (("2025071812", "07-18 12UTC = 18일 21시 KST"),
                        ("2025071818", "07-18 18UTC = 19일 03시 KST"),
                        ("2025071900", "07-19 00UTC = 19일 09시 KST")):
        print(f"\n[발표 {tmfc}] {label}")
        rows = series(key, tmfc, ix, iy)
        out["발표별"][tmfc] = {
            "label": label,
            "rows": rows,
            "_forecast": {
                "source": f"LDAPS {tmfc} 발표 (nwp=l015 sub=unis vars=ncpc)",
                "rain_1h_mm": [r["point_mm"] or 0.0 for r in rows],
            },
            "_forecast_nbr_max": {
                "source": f"LDAPS {tmfc} 발표 · 주변 ±2격자 최대(보수적)",
                "rain_1h_mm": [r["nbr_max_mm"] or 0.0 for r in rows],
            },
        }

    OUT.mkdir(exist_ok=True)
    (OUT / "ldaps_forecast_sancheong.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n저장: {OUT/'ldaps_forecast_sancheong.json'}")


if __name__ == "__main__":
    main()
