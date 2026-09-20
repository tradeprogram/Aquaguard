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

침수심은 49번의 `depth_5m()` 을 그대로 쓴다 — 수역 제외 + 5m 다운스케일 + 강남구
클립. 두 산출물을 다른 방식으로 계산하면 표가 서로 어긋난다.

같이 하는 것: 지점 점검
  2022-08-08 실제로 잠긴 곳 몇 군데에서 모의 침수심을 뽑고, 그 지점의 **지형 성격**
  (와지 깊이 / 지표 집수면적)을 함께 적는다. 정량 검증은 아니다(침수흔적도 미확보).
  다만 "어떤 종류의 침수를 못 잡는가"가 이 표에서 드러난다.

  와지깊이 = 와지를 채운 DEM − 원 DEM. 0 이면 물이 갇히지 않고 지나가는 길목이다.
    대치역/은마 2.94m · 삼성역 0.35m · 강남역 사거리 0.00m
  지표 집수면적(D8, ±100m 최대)
    대치역 0.001km² · 삼성역 0.006km² · 강남역 0.051km²
  → 강남역은 셋 중 지표 집수면적이 가장 큰데도 가장 얕다. 물이 도착해도 고일 그릇이
    없기 때문이다. 실제 2022-08-08 강남역 침수는 지형 저류가 아니라 하수관망 통수능
    초과·역류로 생겼고, 그 물은 지표가 아니라 관을 타고 왔다. 지표 모형의 배수항은
    항상 물을 빼는 방향이라 부호부터 반대다.

선행: 48번으로 drain30/50/75 를 빌드하고 각각 sfincs.exe 를 돌려둘 것.

출력
  outputs/gangnam_drain_sensitivity.json

정직
  - 세 값 모두 **미검증**이다. 어느 값이 옳은지 고를 근거가 아직 없다. 서울시
    침수흔적도를 확보해야 비로소 고를 수 있다.
  - 따라서 이 표는 "정답 후보 3개"가 아니라 "가정 하나로 결과가 이만큼 움직인다"는
    불확실성 폭의 제시다.
"""
from __future__ import annotations

import importlib.util
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
PROBE_R_M = 100.0              # 지점 주변 이 반경의 최대 침수심을 본다

# 2022-08-08 집중호우 때 침수가 보도된 지점 (경위도). 참값 수위는 없다.
# 와지깊이·집수면적은 20m DEM priority-flood + D8 로 따로 계산한 값이다.
PROBES = {
    "강남역 사거리": (127.0276, 37.4979, 0.00, 0.051),
    "대치역/은마": (127.0632, 37.4945, 2.94, 0.001),
    "삼성역": (127.0630, 37.5088, 0.35, 0.006),
    "논현역": (127.0215, 37.5110, None, None),
    "개포동주민센터": (127.0664, 37.4786, None, None),
}


def load_pp():
    """49번을 모듈로 읽어 온다(파일명이 숫자로 시작해 import 가 안 된다)."""
    p = Path(__file__).resolve().parent / "49_gangnam_postprocess.py"
    spec = importlib.util.spec_from_file_location("pp49", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def main() -> None:
    pp = load_pp()
    from pyproj import Transformer

    f = Transformer.from_crs(4326, 5179, always_xy=True)
    rows = []
    for d in DRAINS:
        rd = BUILD / f"drain{d}"
        if not (rd / "sfincs_map.nc").exists():
            print(f"[건너뜀] drain{d}: sfincs_map.nc 없음")
            continue
        dep, dep_aoi, tr, res5, inp, n_water, aoi_ha = pp.depth_5m(rd)
        cell = res5 * res5
        edges = list(pp.DEPTH_BANDS_M) + [np.inf]
        bands = [{"min_m": lo, "max_m": None if np.isinf(hi) else hi,
                  "area_ha": round(float(np.nansum((dep_aoi >= lo) & (dep_aoi < hi)) * cell / 1e4), 2)}
                 for lo, hi in zip(edges[:-1], edges[1:])]
        over = dep_aoi[np.isfinite(dep_aoi) & (dep_aoi >= pp.DEPTH_BANDS_M[0])]

        R = int(PROBE_R_M / res5)
        probe = {}
        for nm, (lon, lat, sink, acc) in PROBES.items():
            x, y = f.transform(lon, lat)
            r, c = int((tr.f - y) // res5), int((x - tr.c) // res5)
            w = dep[max(0, r - R):r + R + 1, max(0, c - R):c + R + 1]
            probe[nm] = {"depth_m": round(float(np.nanmax(w)), 3) if np.isfinite(w).any() else 0.0,
                         "와지깊이_m": sink, "집수면적_km2": acc}

        rows.append({
            "배수상수_mm_h": inp["배수상수_mm_h"],
            "침수면적_0.3m이상_강남구_ha": round(float(over.size * cell / 1e4), 2),
            "침수면적_1.0m이상_강남구_ha": round(float(np.nansum(dep_aoi >= 1.0) * cell / 1e4), 2),
            "강남구_면적_대비_%": round(100 * over.size * cell / 1e4 / aoi_ha, 2),
            "최대침수심_강남구_m": round(float(np.nanmax(dep_aoi)), 3),
            "평균침수심_0.3m이상_m": round(float(over.mean()), 3) if over.size else None,
            "밴드": bands,
            f"지점_최대침수심_반경{int(PROBE_R_M)}m_m": probe,
        })
        print(f"qinf {d:>2} mm/h  0.3m↑ {rows[-1]['침수면적_0.3m이상_강남구_ha']:>7.1f} ha "
              f"({rows[-1]['강남구_면적_대비_%']:>4.1f}%)   "
              f"1.0m↑ {rows[-1]['침수면적_1.0m이상_강남구_ha']:>6.1f} ha   "
              f"최대 {rows[-1]['최대침수심_강남구_m']:.2f} m")

    if rows:
        key = f"지점_최대침수심_반경{int(PROBE_R_M)}m_m"
        print(f"\n지점 점검 (반경 {int(PROBE_R_M)}m 최대 침수심, m) — 참값 없음, 검증 아님")
        print("  " + "지점".ljust(16) + "와지  집수km2"
              + "".join(f"{'qinf ' + str(int(r['배수상수_mm_h'])):>10}" for r in rows))
        for nm in PROBES:
            s, a = PROBES[nm][2], PROBES[nm][3]
            print("  " + nm.ljust(16)
                  + (f"{s:4.2f}" if s is not None else "   -")
                  + (f"{a:8.3f}" if a is not None else "       -")
                  + "".join(f"{r[key][nm]['depth_m']:10.2f}" for r in rows))

    if len(rows) >= 2:
        a = [r["침수면적_0.3m이상_강남구_ha"] for r in rows]
        print(f"\n가정 폭: 0.3m↑ 침수면적 {min(a):.0f}~{max(a):.0f} ha "
              f"({max(a)/max(min(a), 1e-9):.1f}배). 배수율 가정 하나가 이만큼을 좌우한다.")

    OUT.mkdir(exist_ok=True)
    (OUT / "gangnam_drain_sensitivity.json").write_text(json.dumps({
        "생성": __import__("datetime").datetime.now().isoformat(timespec="minutes"),
        "대상": "서울 강남구 내수침수 (2022-08-08 AWS 400 실측 강우)",
        "강우": "합계 374.0mm, 최대 92.5mm/h",
        "집계범위": "강남구 법정경계 안 (LARD 11680). 침수심은 5m 다운스케일, 영구수역 제외",
        "케이스": rows,
        "근거": {"30": "서울시 하수도 일반 설계빈도(10년) 하단대, 노후 관거 가정",
               "50": "중간값",
               "75": "강남역 등 중점관리지역 30년빈도 상향 목표 수준의 상한 가정"},
        "지점_지형성격": {nm: {"와지깊이_m": v[2], "지표집수면적_km2": v[3]}
                    for nm, v in PROBES.items() if v[2] is not None},
        "한계": ["하수관망 미반영 — 배수를 공간·시간 상수로 대리했다. 국지 병목·역류는 "
                "재현하지 못한다.",
               "세 값 모두 미검증. 서울시 침수흔적도를 확보해야 값을 고를 수 있다.",
               "이 표는 정답 후보가 아니라 가정에 따른 불확실성 폭이다.",
               "강남역 사거리는 와지깊이가 0.00m 다 — 지형상 물이 고일 그릇이 없고 "
               "지나가는 길목이다. 반면 대치역/은마는 2.94m 깊이의 닫힌 와지라 물이 "
               "갇힌다. 그래서 대치는 지표 모형으로 잡히고 강남역은 어떤 배수율로도 "
               "얕게 나온다. 강남역을 맞추려면 관망(SWMM 결합 또는 배수분구 이송 "
               "대리모형)이 필요하지, 계수 조정으로 될 일이 아니다."],
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n저장: {OUT/'gangnam_drain_sensitivity.json'}")


if __name__ == "__main__":
    main()
