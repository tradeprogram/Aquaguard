"""
50_gangnam_drain_sensitivity.py — 강남 내수침수 배수율 민감도 (30 / 50 / 75 mm/h)

왜 필요한가
  48번은 하수관망을 넣지 않고 배수를 **상수 qinf** 로 대리한다. 그 상수는 관측된
  값이 아니라 가정이다. 값 하나만 내놓으면 그 가정이 결과처럼 보이므로, 세 값으로
  돌려 결과가 가정에 얼마나 끌려다니는지 같이 보고한다.

값 선정 근거
  30 mm/h  서울시 하수도 일반 설계빈도(10년) 하단대. 노후 관거 구간 가정
  50 mm/h  중간값
  75 mm/h  강남역 등 중점관리지역 30년빈도 상향 목표 수준의 상한 가정
  (실제 관망 용량 자료를 확보하면 이 세 값을 통째로 대체해야 한다.)

선행: 48번으로 drain30/drain50/drain75 를 빌드하고 각각 sfincs.exe 를 돌려둘 것.

같이 하는 것: 지점 점검
  2022-08-08 실제로 잠긴 곳 몇 군데에서 모의 침수심을 뽑는다. 정량 검증은 아니다
  (침수흔적도가 없다). 다만 "어떤 종류의 침수를 못 잡는가"는 이걸로 드러난다.

출력
  outputs/gangnam_drain_sensitivity.json

정직
  - 세 값 모두 **미검증**이다. 어느 값이 옳은지 고를 근거가 아직 없다. 서울시
    침수흔적도를 확보해야 비로소 고를 수 있다.
  - 따라서 이 표는 "정답 후보 3개"가 아니라 "가정 하나로 결과가 이만큼 움직인다"는
    불확실성 폭의 제시다.
"""
from __future__ import annotations

import json
import sys
import warnings

warnings.filterwarnings("ignore")
from pathlib import Path

import numpy as np

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(r"G:/연구/공모전/아쿠아가드")
OUT = ROOT / "outputs"
BUILD = Path(r"C:/Users/user/AppData/Local/Temp/claude/aquaguard_work/sfincs_gangnam")
DRAINS = (30, 50, 75)
DEPTH_BANDS_M = (0.3, 1.0, 2.0, 5.0)
ZB_MIN_M, ZB_MAX_M = -20.0, 700.0
PROBE_R = 2                    # ±2셀 = ±40m 반경 최대치를 본다

# 2022-08-08 집중호우 때 침수가 보도된 지점 (경위도). 참값 수위는 없다.
PROBES = {
    "강남역 사거리": (127.0276, 37.4979),
    "대치역/은마": (127.0632, 37.4945),
    "삼성역": (127.0630, 37.5088),
    "논현역": (127.0215, 37.5110),
    "개포동주민센터": (127.0664, 37.4786),
    "구룡마을": (127.0577, 37.4715),
}


def depth_field(run_dir: Path):
    import xarray as xr

    ds = xr.open_dataset(run_dir / "sfincs_map.nc")
    zsmax = np.asarray(ds["zsmax"].values)
    if zsmax.ndim == 3:
        zsmax = np.nanmax(zsmax, axis=0)
    zb = np.asarray(ds["zb"].values)
    if zb.ndim == 3:
        zb = zb[0]
    msk = np.asarray(ds["msk"].values) if "msk" in ds else np.ones_like(zb)
    act = msk > 0
    bad = act & (~np.isfinite(zb) | (zb < ZB_MIN_M) | (zb > ZB_MAX_M))
    if bad.any():
        raise SystemExit(f"{run_dir.name}: zb 이상값 {int(bad.sum()):,}셀 — 49번 안내 참조")
    dep = np.where(np.isfinite(zsmax - zb) & act, zsmax - zb, np.nan)
    return np.where(dep > 0, dep, np.nan)


def probe(dep: np.ndarray, x0: float, y0: float, dx: float) -> dict:
    """보도된 침수지점의 모의 침수심. 참값이 없으므로 검증이 아니라 점검이다."""
    from pyproj import Transformer

    f = Transformer.from_crs(4326, 5179, always_xy=True)
    out = {}
    for nm, (lon, lat) in PROBES.items():
        x, y = f.transform(lon, lat)
        i, j = int((x - x0) // dx), int((y - y0) // dx)
        w = dep[max(0, j - PROBE_R):j + PROBE_R + 1,
                max(0, i - PROBE_R):i + PROBE_R + 1]
        out[nm] = round(float(np.nanmax(w)), 3) if np.isfinite(w).any() else None
    return out


def stats(run_dir: Path) -> dict:
    import xarray as xr

    dep = depth_field(run_dir)
    meta = json.loads((run_dir / "_build_meta.json").read_text(encoding="utf-8"))
    dx = float(meta["격자"]["dx_m"])
    cell_ha = dx * dx / 1e4
    dom = json.loads((ROOT / "data" / "seoul" / "gangnam_domain_meta.json")
                     .read_text(encoding="utf-8"))["도메인_5179"]

    edges = list(DEPTH_BANDS_M) + [np.inf]
    bands = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        n = int(np.nansum((dep >= lo) & (dep < hi)))
        bands.append({"min_m": lo, "max_m": None if np.isinf(hi) else hi,
                      "cells": n, "area_ha": round(n * cell_ha, 2)})
    over = dep[dep >= DEPTH_BANDS_M[0]]
    return {
        "배수상수_mm_h": meta["배수상수_mm_h"],
        "최대침수심_m": round(float(np.nanmax(dep)), 3),
        "침수면적_0.3m이상_ha": round(float(over.size * cell_ha), 2),
        "침수면적_1.0m이상_ha": round(float((dep >= 1.0).sum() * cell_ha), 2),
        "평균침수심_0.3m이상_m": round(float(over.mean()), 3) if over.size else None,
        "밴드": bands,
        "지점_모의침수심_m": probe(dep, dom["x0"], dom["y0"], dx),
    }


def main() -> None:
    rows = []
    for d in DRAINS:
        rd = BUILD / f"drain{d}"
        if not (rd / "sfincs_map.nc").exists():
            print(f"[건너뜀] drain{d}: sfincs_map.nc 없음")
            continue
        r = stats(rd)
        rows.append(r)
        print(f"qinf {d:>2} mm/h  0.3m↑ {r['침수면적_0.3m이상_ha']:>8.2f} ha   "
              f"1.0m↑ {r['침수면적_1.0m이상_ha']:>7.2f} ha   "
              f"최대 {r['최대침수심_m']:.2f} m   평균 {r['평균침수심_0.3m이상_m']:.2f} m")

    if rows:
        names = list(rows[0]["지점_모의침수심_m"])
        print()
        print("지점 점검 (±40m 반경 최대 침수심, m) — 참값 없음, 검증 아님")
        print("  " + "지점".ljust(16)
              + "".join(f"{'qinf ' + str(int(r['배수상수_mm_h'])):>12}" for r in rows))
        for nm in names:
            print("  " + nm.ljust(16)
                  + "".join(f"{(r['지점_모의침수심_m'][nm] or 0):12.2f}" for r in rows))

    if len(rows) >= 2:
        a = [r["침수면적_0.3m이상_ha"] for r in rows]
        print(f"\n가정 폭: 0.3m↑ 침수면적 {min(a):.0f}~{max(a):.0f} ha "
              f"({max(a)/min(a):.1f}배). 배수율 가정 하나가 이만큼을 좌우한다.")

    OUT.mkdir(exist_ok=True)
    (OUT / "gangnam_drain_sensitivity.json").write_text(json.dumps({
        "생성": __import__("datetime").datetime.now().isoformat(timespec="minutes"),
        "대상": "서울 강남구 내수침수 (2022-08-08 AWS 400 실측 강우)",
        "강우": "합계 374.0mm, 최대 92.5mm/h",
        "케이스": rows,
        "근거": {"30": "서울시 하수도 일반 설계빈도(10년) 하단대, 노후 관거 가정",
               "50": "중간값",
               "75": "강남역 등 중점관리지역 30년빈도 상향 목표 수준의 상한 가정"},
        "한계": ["하수관망 미반영 — 배수를 공간·시간 상수로 대리했다. 국지 병목·역류는 "
                "재현하지 못한다.",
               "세 값 모두 미검증. 서울시 침수흔적도를 확보해야 값을 고를 수 있다.",
               "이 표는 정답 후보가 아니라 가정에 따른 불확실성 폭이다.",
               "지점 점검에서 대치·삼성 같은 지형 저지대는 배수율을 낮추면 깊어지지만, "
               "강남역 사거리는 세 케이스 모두 0.1~0.2m 에 머문다. 2022-08-08 강남역 "
               "침수는 지형 저류가 아니라 하수관망 통수능 초과·역류로 생긴 것이라 "
               "상수 배수 모형이 구조적으로 재현할 수 없는 유형이다. 배수율을 더 "
               "낮춰 억지로 맞추면 다른 지역이 과대침수된다 — 관망 모형이 있어야 한다."],
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n저장: {OUT/'gangnam_drain_sensitivity.json'}")


if __name__ == "__main__":
    main()
