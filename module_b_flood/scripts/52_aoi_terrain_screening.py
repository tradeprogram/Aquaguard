"""
52_aoi_terrain_screening.py — 지표 기반 침수모형이 통할 AOI 인가를 **미리** 판별

왜 필요한가
  51번에서 강남구 모형이 침수흔적도 대비 IoU 0.037, 필지 적중률 33% 로 실패했다.
  원인은 강남역에서 이미 드러났다 — 관측 침수지점이 **닫힌 와지**가 아니라 물이
  지나가는 **길목**이면, 중력만 아는 지표 모형은 거기에 물을 세울 수 없다.

  그렇다면 AOI 를 옮기기 전에 그 판별을 먼저 하면 된다. SFINCS 를 다시 짓지 않고
  DEM 과 침수흔적도만으로 "이 구는 지형 모형으로 잡히는 종류의 침수인가"를 잰다.
  모형을 만든 뒤에 실패를 확인하는 것보다 싸다.

판별 지표
  와지깊이  priority-flood 로 채운 DEM − 원 DEM. 0 이면 물이 갇히지 않고 지나간다.
            관측 침수지점에서 이 값이 크면 지형이 물을 가둔 침수 → 지표 모형이 잡는다.
  집수면적  D8 누적. 물이 얼마나 모이는가. 크면서 와지깊이가 0 이면 전형적 길목이다.

  강남역 사거리는 와지깊이 0.00m 인데 집수면적은 대치역의 50배였다 — 물은 오는데
  담을 그릇이 없는 자리다. 실제 침수는 관망 역류로 생겼다.

출력
  outputs/aoi_terrain_screening.json

정직
  - 이건 **모형 성능 예측**이지 성능 측정이 아니다. 와지깊이가 커도 강우·배수 조건에
    따라 틀릴 수 있다. 다만 와지깊이가 0 에 몰려 있으면 지표 모형은 확실히 못 잡는다.
  - 침수흔적도는 피해 신고 인벤토리라 도로·공원이 빠져 있다(51번 주의 참조).
"""
from __future__ import annotations

import heapq
import json
import sys
import warnings

warnings.filterwarnings("ignore")
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.features import rasterize
from rasterio.windows import from_bounds

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(r"G:/연구/공모전/아쿠아가드")
OUT = ROOT / "outputs"
DEM_SRC = Path(r"G:/연구/데이터/DEM_5m_5179/DEM_5m_5179")
DEM_TILES = ("서울특별시", "경기도")
ADM_LARD = Path(r"G:/연구/지역shp/LARD_ADM_SECT_SGG_서울/LARD_ADM_SECT_SGG_11_202405.shp")
TRACE = Path(r"C:/Users/user/AppData/Local/Temp/claude/aquaguard_work/trace2022/trace2022.shp")
MOJIBAKE = {"諛곗닔?⑸웾珥덇낵": "배수용량초과"}

GU = {"강남구": "11680", "서초구": "11650"}
BUFFER_M = 500.0
DX = 20.0                 # 판별용 격자. 5m 로 할 필요 없다
NODATA_BELOW = -10.0
NB = [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1)]


def dem_20m(bounds):
    """도별 5m 타일을 모자이크해 20m 평균 DEM 을 만든다(47번과 같은 출처)."""
    x0, y0, x1, y1 = bounds
    dem5 = tr5 = None
    for name in DEM_TILES:
        src = DEM_SRC / f"dem_5m_{name}.tif"
        if not src.exists():
            continue
        with rasterio.open(src) as ds:
            win = from_bounds(x0, y0, x1, y1, transform=ds.transform)
            a = ds.read(1, window=win, boundless=True, fill_value=-9999).astype("float32")
            t = ds.window_transform(win)
        if dem5 is None:
            dem5, tr5 = a, t
        else:
            dem5 = np.where(dem5 <= NODATA_BELOW, a, dem5)
    if dem5 is None:
        raise SystemExit("DEM 타일을 열지 못했습니다")
    bad = int((dem5 <= NODATA_BELOW).sum())
    H, W = dem5.shape
    ny, nx = H // 4, W // 4
    dem = dem5[:ny * 4, :nx * 4].reshape(ny, 4, nx, 4).mean(axis=(1, 3)).astype("float64")
    tr = rasterio.transform.from_origin(tr5.c, tr5.f, DX, DX)
    return dem, tr, bad


def priority_flood(dem):
    ny, nx = dem.shape
    filled = np.full_like(dem, np.inf)
    seen = np.zeros(dem.shape, bool)
    h = []
    for j in range(ny):
        for i in (0, nx - 1):
            filled[j, i] = dem[j, i]
            heapq.heappush(h, (dem[j, i], j, i))
    for i in range(nx):
        for j in (0, ny - 1):
            filled[j, i] = dem[j, i]
            heapq.heappush(h, (dem[j, i], j, i))
    while h:
        z, j, i = heapq.heappop(h)
        if seen[j, i]:
            continue
        seen[j, i] = True
        for dj, di in NB:
            a, b = j + dj, i + di
            if 0 <= a < ny and 0 <= b < nx and not seen[a, b]:
                nz = max(dem[a, b], z)
                filled[a, b] = nz
                heapq.heappush(h, (nz, a, b))
    return filled - dem


def d8_accum(filled):
    ny, nx = filled.shape
    dist = [DX, DX, DX, DX, DX * 2 ** .5, DX * 2 ** .5, DX * 2 ** .5, DX * 2 ** .5]
    drop = np.full((8, ny, nx), -np.inf)
    for k, (dj, di) in enumerate(NB):
        s = np.full_like(filled, np.inf)
        s[max(0, -dj):ny - max(0, dj), max(0, -di):nx - max(0, di)] = \
            filled[max(0, dj):ny + min(0, dj), max(0, di):nx + min(0, di)]
        drop[k] = (filled - s) / dist[k]
    best = np.argmax(drop, axis=0)
    slope = np.max(drop, axis=0)
    acc = np.ones((ny, nx))
    for idx in np.argsort(filled.ravel())[::-1]:
        j, i = divmod(int(idx), nx)
        if slope[j, i] <= 0:
            continue
        dj, di = NB[best[j, i]]
        a, b = j + dj, i + di
        if 0 <= a < ny and 0 <= b < nx:
            acc[a, b] += acc[j, i]
    return acc * DX * DX / 1e6      # km²


def main() -> None:
    adm = gpd.read_file(ADM_LARD, encoding="cp949").to_crs(5179)
    obs_all = gpd.read_file(TRACE).to_crs(5179)
    obs_all["R"] = obs_all["F_RSN_DTL"].map(lambda s: MOJIBAKE.get(s, s))
    obs_all["F_SHIM"] = pd.to_numeric(obs_all["F_SHIM"], errors="coerce")

    rows = []
    for name, code in GU.items():
        geom = adm[adm["ADM_SECT_C"].astype(str) == code].geometry.union_all()
        minx, miny, maxx, maxy = geom.bounds
        b = (np.floor((minx - BUFFER_M) / DX) * DX, np.floor((miny - BUFFER_M) / DX) * DX,
             np.ceil((maxx + BUFFER_M) / DX) * DX, np.ceil((maxy + BUFFER_M) / DX) * DX)
        dem, tr, nbad = dem_20m(b)
        print(f"[{name}] 면적 {geom.area/1e6:.1f}km²  DEM {dem.shape} @{DX:.0f}m  "
              f"결측 {nbad:,}  표고 {dem.min():.1f}~{dem.max():.1f}m", flush=True)
        sink = priority_flood(dem)
        acc = d8_accum(dem + sink)
        ny, nx = dem.shape

        o = obs_all[obs_all["GU_NAM"].astype(str).str.strip() == name]
        lab = rasterize([(g, i + 1) for i, g in enumerate(o.geometry)],
                        out_shape=(ny, nx), transform=tr, dtype="int32")
        s_at, a_at = [], []
        for i in range(1, len(o) + 1):
            m = lab == i
            if not m.any():
                continue
            s_at.append(float(sink[m].max()))
            a_at.append(float(acc[m].max()))
        s_at, a_at = np.array(s_at), np.array(a_at)

        inside = rasterize([(geom, 1)], out_shape=(ny, nx), transform=tr, dtype="uint8") == 1
        r = {
            "자치구": name, "코드": code,
            "면적_km2": round(float(geom.area / 1e6), 1),
            "관측건수": int(len(o)),
            "관측_기하면적_ha": round(float(o.geometry.area.sum() / 1e4), 1),
            "실측침수심": {"중앙_m": round(float(o["F_SHIM"].median()), 2),
                      "p90_m": round(float(o["F_SHIM"].quantile(.9)), 2),
                      "최대_m": round(float(o["F_SHIM"].max()), 2)},
            "구_전체_와지깊이": {"0.1m초과_비율": round(float((sink[inside] > 0.1).mean()), 3),
                         "중앙_m": round(float(np.median(sink[inside])), 3)},
            "관측지점_와지깊이": {
                "표본수": int(s_at.size),
                "0_인_비율": round(float((s_at <= 0.01).mean()), 3),
                "0.3m초과_비율": round(float((s_at > 0.3).mean()), 3),
                "1.0m초과_비율": round(float((s_at > 1.0).mean()), 3),
                "중앙_m": round(float(np.median(s_at)), 3),
                "p90_m": round(float(np.percentile(s_at, 90)), 3)},
            "관측지점_집수면적_km2": {"중앙": round(float(np.median(a_at)), 4),
                            "p90": round(float(np.percentile(a_at, 90)), 4)},
            "침수원인_상위": o["R"].value_counts().head(6).to_dict(),
            "대상유형": o["TYPE"].value_counts().head(6).to_dict(),
        }
        rows.append(r)
        q = r["관측지점_와지깊이"]
        print(f"   관측 {r['관측건수']:,}건 중 격자에 걸린 {q['표본수']:,}개")
        print(f"   와지깊이  0인 곳 {100*q['0_인_비율']:.0f}%  |  0.3m↑ {100*q['0.3m초과_비율']:.0f}%"
              f"  |  1.0m↑ {100*q['1.0m초과_비율']:.0f}%  |  중앙 {q['중앙_m']:.2f}m  p90 {q['p90_m']:.2f}m")
        print(f"   집수면적  중앙 {r['관측지점_집수면적_km2']['중앙']:.4f}km²  "
              f"p90 {r['관측지점_집수면적_km2']['p90']:.4f}km²\n", flush=True)

    if len(rows) == 2:
        a, b = rows
        print("판별")
        for r in rows:
            q = r["관측지점_와지깊이"]
            print(f"  {r['자치구']}: 관측지점의 {100*q['0.3m초과_비율']:.0f}% 가 0.3m 이상 와지 "
                  f"→ 지표 모형이 물을 세울 수 있는 자리")
        w = max(rows, key=lambda r: r["관측지점_와지깊이"]["0.3m초과_비율"])
        print(f"  → {w['자치구']} 가 지형 모형에 유리하다")

    OUT.mkdir(exist_ok=True)
    (OUT / "aoi_terrain_screening.json").write_text(json.dumps({
        "생성": __import__("datetime").datetime.now().isoformat(timespec="minutes"),
        "목적": "지표 기반 침수모형이 통할 AOI 인가를 SFINCS 재구축 없이 미리 판별",
        "방법": {"격자_m": DX, "DEM": "국토정보플랫폼 5m 도별 타일 모자이크 → 20m 평균",
               "와지깊이": "priority-flood 채움 − 원 DEM",
               "집수면적": "채운 DEM 에서 D8 누적",
               "표본": "침수흔적도 2022 관측 폴리곤 안 최대값"},
        "결과": rows,
        "해석기준": "관측지점 와지깊이가 0 에 몰리면 지표 모형은 그 침수를 재현할 수 "
                "없다(강남역형). 0.3m 이상 와지 비율이 높을수록 지형 모형이 유리하다.",
        "한계": ["모형 성능 예측이지 측정이 아니다. 실제 성능은 모형을 돌려 51번으로 재야 한다.",
               "침수흔적도는 피해 신고 인벤토리라 도로·공원이 빠져 있다.",
               "와지깊이는 DEM 인공 와지(교량 하부·터널 입구)도 같이 센다."],
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"저장: {OUT/'aoi_terrain_screening.json'}")


if __name__ == "__main__":
    main()
