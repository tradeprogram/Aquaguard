"""
48_gangnam_sfincs_build.py — 강남구 내수침수 SFINCS 모델 빌드  [env: sfincs]

산청(33번)과 무엇이 다른가
  산청  하천범람 — 상류 유량(discharge) + 하류 수위(waterlevel) 경계로 푼다
  강남  내수침수 — **격자 전체에 비를 뿌리고**(precip) 하수도 배수를 빼서 푼다
2022-08-08 강남역 침수는 하천이 넘친 게 아니라 하수도 용량을 초과한 빗물이
저지대에 고인 것이므로 강제 방식 자체가 다르다.

구성
  도메인   47번이 만든 강남구+500m 버퍼 (11.20 × 9.87 km)
  계산격자 20m (560×494) + 5m DEM/Manning subgrid — SFINCS subgrid 의 설계 의도대로
           거친 계산격자 + 세밀 지형으로 도시 소규모 지형을 살린다
  강제     공간균일 시간강우 (AWS 실측)
  배수     setup_constant_infiltration 으로 하수도 용량을 상수 배수로 대리
  유출     저지대 경계(한강 방향)를 outflow 로 열어 물이 빠져나가게 한다

★ 하수관망을 넣지 않는 것의 의미 (반드시 읽을 것)
  실제 배수는 관망 용량·지선 병목·역류로 시공간에 따라 다른데, 여기서는 **상수**로
  둔다. 그래서 이 모형은 "관망이 설계용량만큼 균일하게 빼줬다면" 이라는 가정 아래의
  결과이고, 국지 병목으로 생기는 실제 침수 깊이를 재현하지 못한다.
  배수율을 여러 값으로 돌려 민감도를 함께 내는 이유다 — 하나만 내면 그 가정이
  결과처럼 보인다.

  서울시 하수도 설계빈도: 일반 10년빈도, 강남역 등 중점관리지역은 30년빈도로 상향
  추진. 여기서는 30·50·75 mm/h 세 값으로 돌려 비교한다(75는 10년빈도 설계강우
  수준의 상한 가정). 실제 관망 자료를 확보하면 이 가정을 대체해야 한다.

★ netCDF 가 한글 경로에서 깨지므로 33번과 같이 ASCII 경로(scratchpad)에 빌드한다.

실행
  conda run -n sfincs python scripts/48_gangnam_sfincs_build.py --rain <강우json> --drain 75
  그다음 빌드 폴더에서 sfincs.exe 실행 → sfincs_map.nc
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# hydromt-sfincs 1.2.2 x pandas 3.0 호환 (33번과 동일 패치)
if not hasattr(pd.Index, "is_integer"):
    pd.Index.is_integer = lambda self: bool(pd.api.types.is_integer_dtype(self.dtype))

PROOT = Path(r"G:/연구/공모전/아쿠아가드")
SEOUL = PROOT / "data" / "seoul"
DEM = SEOUL / "gangnam_dem_5m_5179.tif"
MANNING = SEOUL / "gangnam_manning_5m_5179.tif"
META = SEOUL / "gangnam_domain_meta.json"
BUILD = Path(r"C:/Users/user/AppData/Local/Temp/claude/aquaguard_work/sfincs_gangnam")

EPSG = 5179
DX = 20.0                      # 계산격자
SUBGRID_PIXELS = 4             # 20m / 5m = 4
EVENT_DAY = "20220808"
NL = chr(10)          # heredoc 이스케이프 문제를 피하려고 상수로 둔다


def default_rain() -> pd.DataFrame:
    """강우 미지정 시 쓰는 자리표시자 — 실측이 아니다.

    AWS 지점 확정 전까지 모델 구조를 검증하려고 둔 값이다. 실제 실행에는
    --rain 으로 46번 형식의 실측 시계열을 넣어야 한다.
    """
    idx = pd.date_range("2022-08-08 14:00", "2022-08-09 02:00", freq="h")
    mm = [5, 10, 20, 40, 90, 60, 30, 20, 10, 5, 2, 1, 0]
    return pd.DataFrame({"precip": mm[:len(idx)]}, index=idx)


def load_rain(path: Path | None) -> tuple[pd.DataFrame, str]:
    if path is None:
        return default_rain(), "PLACEHOLDER(실측 아님) — AWS 지점 확정 후 교체 필요"
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    idx = pd.to_datetime(d["times"])
    return pd.DataFrame({"precip": d["rain_1h_mm"]}, index=idx), d.get("source", str(path))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rain", type=Path, default=None,
                    help='{"times":[...],"rain_1h_mm":[...],"source":"..."} JSON')
    ap.add_argument("--drain", type=float, default=75.0,
                    help="하수도 배수 대리 상수 (mm/h). 기본 75")
    ap.add_argument("--tag", default=None)
    args = ap.parse_args()

    from hydromt_sfincs import SfincsModel   # env: sfincs

    meta = json.loads(META.read_text(encoding="utf-8"))
    d = meta["도메인_5179"]
    x0, y0 = d["x0"], d["y0"]
    mmax = int(round((d["x1"] - x0) / DX))     # 동서 셀수
    nmax = int(round((d["y1"] - y0) / DX))     # 남북 셀수

    rain, rain_src = load_rain(args.rain)
    tag = args.tag or f"drain{int(args.drain)}"
    root = BUILD / tag
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)

    tref = rain.index[0].strftime("%Y%m%d %H%M%S")
    tstop = (rain.index[-1] + pd.Timedelta(hours=6)).strftime("%Y%m%d %H%M%S")
    print(f"도메인 {mmax}×{nmax} @{DX:.0f}m  원점({x0:.0f},{y0:.0f})")
    print(f"강우 {len(rain)}시간, 합계 {rain['precip'].sum():.1f}mm, 최대 {rain['precip'].max():.1f}mm/h")
    print(f"  출처: {rain_src}")
    print(f"배수 상수 {args.drain:.0f} mm/h  → 순강우 최대 {max(0, rain['precip'].max()-args.drain):.1f}mm/h")

    mod = SfincsModel(root=str(root), mode="w+")
    mod.setup_grid(x0=x0, y0=y0, dx=DX, dy=DX, mmax=mmax, nmax=nmax, rotation=0, epsg=EPSG)
    mod.setup_dep(datasets_dep=[{"elevtn": str(DEM)}])
    # 활성역: 육상 전체. 내수침수라 하천 유무와 무관하게 격자 전체가 대상이다.
    mod.setup_mask_active(zmin=-5, fill_area=10, drop_area=0, reset_mask=True)
    # 유출 경계: 저지대(한강 방향) 가장자리를 열어 물이 빠지게 한다. 닫아두면
    # 도메인 안에 물이 갇혀 침수가 과대해진다.
    mod.setup_mask_bounds(btype="outflow", zmax=12.0, reset_bounds=True)
    mod.setup_subgrid(datasets_dep=[{"elevtn": str(DEM)}],
                      datasets_rgh=[{"manning": str(MANNING)}],
                      nr_subgrid_pixels=SUBGRID_PIXELS, nlevels=10,
                      write_dep_tif=True, write_man_tif=True)
    # 하수도 배수 대리는 sfincs.inp 의 qinf(mm/hr) 스칼라로 넣는다.
    # setup_constant_infiltration() 은 래스터를 요구해서(공간분포 침투용) 상수에는
    # 맞지 않는다 — 관망 자료가 생기면 그때 공간분포 래스터로 바꾸면 된다.
    mod.setup_config(tref=tref, tstart=tref, tstop=tstop,
                     dtout=1800.0, dthisout=600.0, dtmaxout=999999.0, alpha=0.5,
                     qinf=float(args.drain))
    mod.setup_precip_forcing(timeseries=rain)
    mod.write()
    # write() 가 config 를 덮어쓰는 구현이 있어 qinf 를 다시 확인·보정한다
    inp = root / "sfincs.inp"
    txt = inp.read_text(encoding="utf-8")
    if "qinf" not in txt:
        inp.write_text(txt.rstrip() + NL + f"qinf = {args.drain}" + NL, encoding="utf-8")
        print(f"  qinf={args.drain} 를 sfincs.inp 에 추가")

    (root / "_build_meta.json").write_text(json.dumps({
        "대상": "서울 강남구 내수침수",
        "격자": {"dx_m": DX, "mmax": mmax, "nmax": nmax, "subgrid_px": SUBGRID_PIXELS},
        "강우": {"source": rain_src, "합계_mm": float(rain["precip"].sum()),
               "최대_mm_h": float(rain["precip"].max()),
               "시작": tref, "종료": tstop},
        "배수상수_mm_h": args.drain,
        "가정": "하수관망 미반영. 배수를 공간·시간 상수로 대리했다. 국지 병목·역류로 "
              "생기는 실제 침수는 재현하지 못하며, 배수율 가정에 결과가 민감하다.",
        "검증": "미검증. 서울시 침수흔적도를 확보하면 대조해야 한다.",
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n빌드 완료 → {root}")
    for f in sorted(root.iterdir()):
        print(f"   {f.name}")
    print("\n다음: 이 폴더에서 sfincs.exe 실행 → sfincs_map.nc")


if __name__ == "__main__":
    main()
