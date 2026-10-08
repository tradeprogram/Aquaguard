"""
53_landslide_feature_boost.py — 산사태 예측력 개선 (AUPRC·ROC-AUC)

출발점 (42번, 흐름누적 D8 집계)
    AUPRC 0.0857 · ROC-AUC 0.4688 · lift 1.33 · 읍면LOO 중앙 0.0888
ROC-AUC 0.47 은 무작위 이하다. 두 갈래를 시도했고 **한쪽만 됐다**.

════════════════════════════════════════════════════════════════════════════
방법 ① Sentinel-1 RVI 변화  →  실패. 쓰지 않는다.

  RVI = 4·σ⁰_VH / (σ⁰_VV + σ⁰_VH)   (이중편파 근사, RTC 선형 power)

  처음에 07-12 → 07-18 차분이 ROC 0.609 로 좋아 보였다. 그런데 궤도 메타를 확인하니
  두 장면의 관측 기하가 아예 다르다.

      07-12  상대궤도 127  ascending   S1A
      07-18  상대궤도 134  descending  S1C      ← 상행/하행이 다르다
      07-19  상대궤도  54  ascending   S1A
      07-24  상대궤도 127  ascending   S1A      ← 07-12 과 같은 궤도
      07-25  상대궤도  54  ascending   S1C      ← 07-19 과 같은 궤도

  상행−하행 차분은 지표 변화가 아니라 **입사각·방위 차이**가 지배한다. 그 기하 차이는
  사면향과 상관되므로, 0.609 는 사면향을 RVI 로 포장해 잰 값이었다.
  실제로 RVI(07-18, 하행)와 북향도의 Spearman 상관이 **+0.464** 다.

  같은 궤도끼리 다시 재면 신호가 사라진다:
      ΔRVI 127asc 07-12 → 07-24 (사건 포함)  ROC 0.507   ← 누수를 허용해도 무작위
      ΔRVI  54asc 07-19 → 07-25 (사건 이후)  ROC 0.524
      RVI 07-12 단독 (상행)                  ROC 0.521
  그리고 북향도 위에 얹으면 모든 조합이 **나빠진다**(LOO 0.250 → 0.122).

  왜 안 되는가: 산청 2025 의 붕괴지는 20m·1km 집계에 묻힐 만큼 작고, 라벨도 발생부가
  아니라 마을 중심점이다. 식생 제거 신호가 격자 평균에 남지 않는다.
  → 사건 전 동일궤도 장면쌍이 없어 '정당한 사전 ΔRVI' 자체를 만들 수 없다.
    더 짧은 주기(상행 127 의 06-30 등)를 추가로 받으면 재시도할 수 있다.

════════════════════════════════════════════════════════════════════════════
방법 ② 국립산림과학원 위험지도 인자  →  성공. 이걸 쓴다.

  유송(국립산림과학원), 「산사태예측기술현황및발전방향」 p16
  2005~2011 산사태 약 2,000건으로 적합한 전국 로지스틱 회귀:

    LS = −2.596 + 0.069·Slope − 0.022·FlowLength + 0.011·Curvature + 0.734·TWI
         − 0.594·Diameter + 0.006·SoilDepth + (Aspect) + (Bedrock) + (ForestStand)

  우리가 안 보고 있던 것: **TWI · 곡률 · 사면길이 · 사면향**. 넷 다 5m DEM 에서
  계산된다. 새 자료가 필요 없다.

  ★ 단일 인자 성능 (같은 라벨·같은 격자)
      북향도 cos(사면향)   AUPRC 0.1435  ROC 0.6557  lift 2.23  LOO 0.2500
      −사면길이            0.1051        0.5453      1.63       0.1716
      토심                0.0824        0.5653      1.28       0.1184
      TWI                0.0782        0.5577      1.21       0.1292
      곡률                0.0725        0.5329      1.12       0.1403
      FoS(현 모형)        0.0605        0.4701      0.94       0.0918
      경사                0.0539        0.4145      0.84       0.0790   ← 무작위 이하

  경사가 무작위 이하라는 것이 핵심이다. 우리 FoS 는 경사가 주도하는데, 라벨은
  급사면이 아니라 **계곡의 마을**이다. 그래서 경사를 볼수록 라벨과 멀어진다.
  반대로 사면향은 거주지 분포와 무관하면서 붕괴와 연결된다.

  ★ 북향도의 견고성
      양성 평균 +0.141 vs 음성 −0.043 (Welch t 검정 p=0.0001)
      양성 있는 **9개 읍면 전부 lift > 1** (삼장면 15.3, 생비량면 9.3, 시천면 4.7)
      급사면 면적과 무상관(r=−0.021) — 격자 크기 교란이 아니다
  북향 사면은 일사가 적어 토양 수분이 오래 남고 풍화층이 두껍다. NIFoS 식도 사면향을
  인자로 쓴다(계수는 발표자료에 미공개라 범주 계수를 가져오지 못했다).

════════════════════════════════════════════════════════════════════════════
결과

    점수                          AUPRC    ROC-AUC   lift   읍면LOO
    42번 기존(FoS<1 흐름누적)        0.0857   0.4688   1.33   0.0888
    NIFoS 6항 등가중 순위            0.1004   0.6396   1.56   0.2020   ← 채택
    북향도 단독                     0.1435   0.6557   2.23   0.2500

  채택안을 북향도 단독이 아니라 6항 등가중으로 두는 이유: 북향도 단독이 수치는
  제일 좋지만 그건 **우리 라벨을 보고 고른 단일 변수**다. 6항은 변수 선택과 부호가
  전부 외부 공표식에서 오고 가중치를 적합하지 않으므로 선택 편의가 없다.
  북향도 단독 수치는 '가장 센 인자가 무엇인가'라는 발견으로 함께 적는다.

출력
  outputs/landslide_feature_boost.json
  outputs/landslide_feature_boost_grid.csv

정직
  - 라벨이 여전히 피해 집계 리(里) 중심점이다(42번 한계 그대로). 달성 가능한 AUPRC 에
    천장이 있고, 올라간 값도 그 천장 아래의 개선이다.
  - NIFoS 식의 범주형 항(사면향·모암·임상)과 경급은 계수 미공개·임상도 부재로 뺐다.
    따라서 **부분 재현**이며 원 논문 성능과 같지 않다.
  - 북향도의 부호(북향=위험)는 문헌 통념이지만 우리 자료에서 확인한 것이기도 하다.
    완전한 외부 사전정보라고 주장하지 않는다.
  - 양성 54개다. 작은 표본에서 여러 변수를 비교했으므로 읍면 LOO 를 주지표로 본다.
  - 뿌리 점착력은 42번의 상수 3.0 kPa 그대로다. 발표자료(p20~21, rTRIGRS)는 임상·밀도별
    1~5 kPa 를 제시하고 민감도 1위 인자로 꼽지만, 임상도가 없어 공간분포화하지 못했다.
"""
from __future__ import annotations

import importlib.util
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
from rasterio.warp import Resampling, reproject
from scipy.stats import rankdata, spearmanr, ttest_ind
from shapely.geometry import Point

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(r"G:/연구/공모전/아쿠아가드")
FOS = ROOT / "data" / "sancheong_fos"
SENT = ROOT / "data" / "sentinel"
OUT = ROOT / "outputs"

F = 4                      # 5m → 20m
GW, WMAX, SLOPE_MIN = 9.81, 0.85, 15.0
CR_HEALTHY = 3.0
MIN_STEEP_PX = 200
K_SIGMOID = 6.0

# NIFoS 공표 계수 (유송 발표자료 p16)
LS_B0, LS_SLOPE, LS_FLOWLEN, LS_CURV, LS_TWI, LS_SOIL = \
    -2.596, 0.069, -0.022, 0.011, 0.734, 0.006

# Sentinel-1 장면의 상대궤도·방향 (Planetary Computer STAC 조회 결과)
S1_ORBIT = {"07-12": (127, "ascending", "S1A"), "07-18": (134, "descending", "S1C"),
            "07-19": (54, "ascending", "S1A"), "07-24": (127, "ascending", "S1A"),
            "07-25": (54, "ascending", "S1C")}

NB8 = ((-1, -1, 2 ** .5), (-1, 0, 1.), (-1, 1, 2 ** .5), (0, -1, 1.),
       (0, 1, 1.), (1, -1, 2 ** .5), (1, 0, 1.), (1, 1, 2 ** .5))


def load42():
    spec = importlib.util.spec_from_file_location(
        "bt42", ROOT / "scripts" / "42_backtest_eval_split.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def block_mean(a, f=F):
    h, w = (a.shape[0] // f) * f, (a.shape[1] // f) * f
    return np.nanmean(a[:h, :w].reshape(h // f, f, w // f, f).astype("float64"), axis=(1, 3))


def block_any(a, f=F):
    h, w = (a.shape[0] // f) * f, (a.shape[1] // f) * f
    return a[:h, :w].reshape(h // f, f, w // f, f).any(axis=(1, 3))


def fos_fields(bt):
    """42번과 동일한 FoS. 이분값(crit)과 연속확률(p_fos)을 함께 낸다."""
    slope, tr, crs, shape = bt._read(ROOT / "data" / "dem" / "산청_slope_5m_5179.tif")
    z, *_ = bt._read(FOS / "z_m.tif")
    m0, *_ = bt._read(FOS / "m0.tif")
    dnbr, *_ = bt._read(FOS / "dnbr.tif")
    steep = np.isfinite(slope) & (slope >= SLOPE_MIN) & np.isfinite(z)
    f = np.ones_like(dnbr)
    f[dnbr >= 0.10] = 1.2
    f[dnbr >= 0.27] = 2.0
    f[dnbr >= 0.44] = 3.75
    f[~np.isfinite(dnbr)] = 1.0
    cr_eff = CR_HEALTHY / f
    del dnbr, f
    beta = np.deg2rad(np.clip(slope, 0.1, 89.0))
    cosb, sinb = np.cos(beta), np.sin(beta)
    c, phi, gam = 2.0, np.deg2rad(36.0), 19.0
    m = np.clip(m0 + WMAX, 0, 1)
    fos = (c + cr_eff + (gam - m * GW) * z * cosb ** 2 * np.tan(phi)) / (gam * z * sinb * cosb)
    p_fos = np.where(steep & np.isfinite(fos),
                     1.0 / (1.0 + np.exp(K_SIGMOID * (np.clip(fos, 0, 5) - 1.0))), 0.0)
    crit = steep & np.isfinite(fos) & (fos < 1.0)
    return slope, z, steep, crit, p_fos.astype("float32"), tr, crs, shape


def d8(dem, cell):
    """D8 수용셀·누적셀수·상류 사면길이."""
    H, W = dem.shape
    recv = np.full(H * W, -1, np.int64)
    best = np.zeros((H, W))
    step = np.zeros((H, W))
    for dr, dc, dist in NB8:
        drop = (dem - np.roll(np.roll(dem, -dr, 0), -dc, 1)) / dist
        upd = np.isfinite(drop) & (drop > best)
        best[upd] = drop[upd]
        step[upd] = dist
        idx = (np.arange(H)[:, None] + dr) * W + (np.arange(W)[None, :] + dc)
        recv.reshape(H, W)[upd] = idx[upd]
    acc = np.ones(H * W)
    flen = np.zeros(H * W)
    sf = step.ravel() * cell
    for i in np.argsort(dem.ravel())[::-1]:
        j = recv[i]
        if 0 <= j < H * W:
            acc[j] += acc[i]
            if flen[i] + sf[i] > flen[j]:
                flen[j] = flen[i] + sf[i]
    return acc.reshape(H, W), flen.reshape(H, W)


def curvature(dem, cell):
    """Zevenbergen & Thorne 총곡률, ArcGIS 와 같은 1/100m 단위."""
    zu, zd = np.roll(dem, 1, 0), np.roll(dem, -1, 0)
    zl, zr = np.roll(dem, 1, 1), np.roll(dem, -1, 1)
    return -2.0 * (((zl + zr) / 2 - dem) + ((zu + zd) / 2 - dem)) / cell ** 2 * 100.0


def rvi(date, shape, tr, crs):
    out = {}
    for pol in ("vv", "vh"):
        with rasterio.open(SENT / f"s1_sancheong_2025-{date}_{pol}.tif") as ds:
            src, stf, scrs = ds.read(1).astype("float32"), ds.transform, ds.crs
        src = np.where(src > 0, src, np.nan)
        dst = np.full(shape, np.nan, "float32")
        reproject(src, dst, src_transform=stf, src_crs=scrs, dst_transform=tr,
                  dst_crs=crs, src_nodata=np.nan, dst_nodata=np.nan,
                  resampling=Resampling.average)
        out[pol] = dst
    with np.errstate(invalid="ignore", divide="ignore"):
        r = 4.0 * out["vh"] / (out["vv"] + out["vh"])
    return np.where(np.isfinite(r), np.clip(r, 0, 4), np.nan)


def zonal_mean(field, mask, zones, n):
    out = np.zeros(n)
    sel = (zones > 0) & mask & np.isfinite(field)
    if not sel.any():
        return out
    idx = zones[sel] - 1
    s = np.bincount(idx, weights=field[sel], minlength=n)
    c = np.bincount(idx, minlength=n)
    np.divide(s, np.maximum(c, 1), out=out)
    return out


def main() -> None:
    bt = load42()
    print("FoS 적재...", flush=True)
    slope5, z5, steep5, crit5, p_fos5, tr, crs, shape = fos_fields(bt)
    print(f"  급사면 {int(steep5.sum()):,}px  FoS<1 {int(crit5.sum()):,}px")

    dem5, *_ = bt._read(ROOT / "data" / "dem" / "산청_dem_5m_5179.tif")
    cell = 5.0 * F
    dem20 = block_mean(dem5)
    H, W = dem20.shape
    tr20 = tr * rasterio.Affine.scale(F, F)
    steep20 = block_any(steep5)
    print(f"20m {H}×{W} — 지형인자...", flush=True)

    acc, flen = d8(dem20, cell)
    slope20 = block_mean(slope5)
    twi = np.log(np.maximum(acc * cell, 1.0) / np.tan(np.deg2rad(np.clip(slope20, .5, 89.))))
    curv = curvature(dem20, cell)
    gy, gx = np.gradient(dem20, cell)
    north = np.cos(np.arctan2(-gy, gx))
    soil = block_mean(z5) * 100.0
    p_fos20 = block_mean(p_fos5)

    # --- 격자·라벨 (42번과 동일)
    em = gpd.read_file(ROOT / "data/vector/adm_dong_5179.geojson")
    em = em[em["sggnm"].astype(str).str.contains("산청")].reset_index(drop=True).to_crs(crs)
    grid = bt.build_grid(crs, em)
    n = len(grid)
    z5r = rasterize(((g, i + 1) for i, g in enumerate(grid.geometry)),
                    out_shape=shape, transform=tr, fill=0, dtype="int32")
    z20 = rasterize(((g, i + 1) for i, g in enumerate(grid.geometry)),
                    out_shape=(H, W), transform=tr20, fill=0, dtype="int32")
    grid["급사면px"] = np.bincount(z5r[steep5], minlength=n + 1)[1:]
    print("42번 기준선(흐름누적 D8) 재현 중...", flush=True)
    grid["S0_기존_흐름누적"] = bt.flow_upslope_score(dem5, crit5, z5r, n)
    del dem5

    for k, v in (("slope", slope20), ("TWI", twi), ("curv", curv), ("flowlen", flen),
                 ("soil_cm", soil), ("north", north), ("p_fos", p_fos20)):
        grid[k] = zonal_mean(v, steep20, z20, n)

    print("RVI...", flush=True)
    R = {d: rvi(d, (H, W), tr20, crs) for d in S1_ORBIT}
    for d in S1_ORBIT:
        grid[f"RVI_{d}"] = zonal_mean(R[d], steep20, z20, n)
    grid["dRVI_127asc_12to24"] = zonal_mean(R["07-24"] - R["07-12"], steep20, z20, n)
    grid["dRVI_54asc_19to25"] = zonal_mean(R["07-25"] - R["07-19"], steep20, z20, n)
    grid["dRVI_혼합궤도_12to18"] = zonal_mean(R["07-18"] - R["07-12"], steep20, z20, n)
    del R

    ri = pd.read_csv(OUT / "sancheong_ri_validation.csv")
    pts = gpd.GeoDataFrame(ri, geometry=[Point(xy) for xy in zip(ri["lon"], ri["lat"])],
                           crs="EPSG:4326").to_crs(crs)
    j = gpd.sjoin(grid.reset_index().rename(columns={"index": "cell"}),
                  pts[["건수", "geometry"]], how="left", predicate="contains")
    grid["산사태건수"] = j.groupby("cell")["건수"].sum().fillna(0).reindex(
        range(n), fill_value=0).to_numpy()
    grid["y"] = (grid["산사태건수"] > 0).astype(int)

    ev = grid[grid["급사면px"] >= MIN_STEEP_PX].reset_index(drop=True)
    y = ev["y"].to_numpy(int)
    masks = [(ev["읍면"] == u).to_numpy() for u in sorted(ev["읍면"].unique())]
    print(f"\n평가격자 {len(ev)}개  양성 {int(y.sum())}개  기저 {100*y.mean():.1f}%\n")

    def ev_score(s, nm, tag):
        s = np.where(np.isfinite(s), s, 0.0)
        m = bt.metrics(y, s)
        loo = [v for v in (bt.metrics(y[k], s[k])["AUPRC"] for k in masks) if v is not None]
        med = round(float(np.median(loo)), 4) if loo else None
        print(f"{nm:34s} {m['AUPRC']:>7.4f} {m['ROC_AUC']:>8.4f} {str(m['lift']):>6} {str(med):>8}  {tag}")
        return {"점수": nm, "구분": tag, **m, "읍면LOO_AUPRC_중앙값": med}

    rk = lambda c: rankdata(np.nan_to_num(ev[c].to_numpy(float))) / len(ev)
    rows = []
    print(f"{'점수':34s} {'AUPRC':>7s} {'ROC-AUC':>8s} {'lift':>6s} {'읍면LOO':>8s}  구분")
    rows.append(ev_score(ev["S0_기존_흐름누적"], "42번 기존 (FoS<1 흐름누적)", "기준"))
    print("--- 방법② NIFoS 인자: 단일")
    for c, nm in (("north", "북향도 cos(사면향)"), ("flowlen", "사면길이(부호 반전)"),
                  ("soil_cm", "토심"), ("TWI", "TWI"), ("curv", "곡률"),
                  ("p_fos", "FoS 확률(현 모형)"), ("slope", "경사")):
        rows.append(ev_score(-ev[c] if c == "flowlen" else ev[c], nm, "②단일"))
    print("--- 방법② 결합 (가중치 적합 없음, 부호는 공표식)")
    nifos5 = rk("slope") - rk("flowlen") + rk("curv") + rk("TWI") + rk("soil_cm")
    rows.append(ev_score(nifos5, "NIFoS 5항 등가중", "②"))
    rows.append(ev_score(nifos5 + rk("north"), "NIFoS 6항 등가중 (+사면향) ★채택", "②"))
    ls = (LS_B0 + LS_SLOPE * ev["slope"] - abs(LS_FLOWLEN) * ev["flowlen"]
          + LS_CURV * ev["curv"] + LS_TWI * ev["TWI"] + LS_SOIL * ev["soil_cm"]).to_numpy()
    rows.append(ev_score(ls, "LS 공표계수 그대로", "②"))
    rows.append(ev_score(nifos5 + rk("north") + rk("p_fos"), "NIFoS 6항 + FoS", "②"))
    print("--- 방법① RVI")
    for c, nm in (("RVI_07-12", "RVI 07-12 단독 (127 asc)"),
                  ("RVI_07-18", "RVI 07-18 단독 (134 desc)"),
                  ("dRVI_127asc_12to24", "ΔRVI 127asc 12→24 (사건포함)"),
                  ("dRVI_54asc_19to25", "ΔRVI 54asc 19→25 (사후)"),
                  ("dRVI_혼합궤도_12to18", "ΔRVI 혼합궤도 12→18 ✗기하혼입")):
        rows.append(ev_score(ev[c], nm, "①"))
    rows.append(ev_score(rk("north") + rk("RVI_07-18"), "북향도 + RVI 07-18", "①+②"))

    # --- 북향도 견고성
    sp = {c: round(float(spearmanr(ev["north"], ev[c], nan_policy="omit").statistic), 3)
          for c in ("RVI_07-18", "RVI_07-12", "TWI", "curv", "flowlen", "급사면px")}
    tt = float(ttest_ind(ev.loc[y == 1, "north"], ev.loc[y == 0, "north"], equal_var=False).pvalue)
    per_em = []
    for u, k in zip(sorted(ev["읍면"].unique()), masks):
        m = bt.metrics(y[k], ev.loc[k, "north"].to_numpy())
        if m["AUPRC"] is not None:
            per_em.append({"읍면": u, **m})
    n_lift = sum(1 for r in per_em if r["lift"] > 1)
    print(f"\n북향도 견고성: 양성 평균 {ev.loc[y==1,'north'].mean():+.3f} vs 음성 "
          f"{ev.loc[y==0,'north'].mean():+.3f}  (Welch t p={tt:.1e})")
    print(f"  lift>1 인 읍면 {n_lift}/{len(per_em)}   north vs RVI_07-18 Spearman {sp['RVI_07-18']:+.3f}")

    base = rows[0]
    best = next(r for r in rows if "채택" in r["점수"])
    print(f"\n기준 → 채택:  AUPRC {base['AUPRC']} → {best['AUPRC']} "
          f"({100*(best['AUPRC']/base['AUPRC']-1):+.0f}%)   "
          f"ROC {base['ROC_AUC']} → {best['ROC_AUC']}   "
          f"읍면LOO {base['읍면LOO_AUPRC_중앙값']} → {best['읍면LOO_AUPRC_중앙값']}")

    OUT.mkdir(exist_ok=True)
    ev.drop(columns="geometry").to_csv(OUT / "landslide_feature_boost_grid.csv",
                                       index=False, encoding="utf-8-sig")
    (OUT / "landslide_feature_boost.json").write_text(json.dumps({
        "생성": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"),
        "출발점": {"출처": "42번 흐름누적 D8", "AUPRC": base["AUPRC"],
                "ROC_AUC": base["ROC_AUC"], "읍면LOO": base["읍면LOO_AUPRC_중앙값"]},
        "설계": {"평가격자": int(len(ev)), "양성": int(y.sum()),
               "지형인자_해상도_m": cell, "FoS→확률_k": K_SIGMOID},
        "방법①_RVI": {
            "결론": "실패 — 쓰지 않는다",
            "식": "RVI = 4·σ⁰_VH/(σ⁰_VV+σ⁰_VH), Sentinel-1 RTC 선형 power",
            "장면_궤도": {k: {"상대궤도": v[0], "방향": v[1], "위성": v[2]}
                      for k, v in S1_ORBIT.items()},
            "사유": ["사건 전 장면이 07-12(127 상행)과 07-18(134 하행)뿐이라 "
                   "**동일궤도 사전 쌍이 없다**. 둘을 차분하면 입사각·방위 차이가 지배한다.",
                   "그 혼합궤도 차분이 ROC 0.609 로 좋아 보였으나, RVI(07-18)와 북향도의 "
                   "Spearman 상관이 +0.464 로 사면향을 재포장한 값이었다.",
                   "동일궤도 차분은 사건을 포함해도 무작위다(127asc 12→24 ROC 0.507).",
                   "북향도 위에 얹으면 모든 조합이 나빠진다(읍면LOO 0.250 → 0.122)."],
            "재시도_조건": "사건 전 동일 상대궤도 장면 2장 이상(예: 상행 127 의 06-30·07-12)을 "
                       "확보하면 정당한 사전 ΔRVI 를 만들 수 있다."},
        "방법②_NIFoS": {
            "결론": "성공 — 채택",
            "출처": "유송(국립산림과학원), 「산사태예측기술현황및발전방향」 p16 — "
                  "2005~2011 산사태 약 2,000건 로지스틱 회귀",
            "공표식": "LS = -2.596 +0.069·Slope -0.022·FlowLength +0.011·Curvature "
                   "+0.734·TWI -0.594·Diameter +0.006·SoilDepth +(Aspect)+(Bedrock)+(ForestStand)",
            "추가한_인자": ["TWI", "곡률", "사면길이", "사면향(북향도)"],
            "뺀_항": ["Diameter(경급) — 임상도 없음",
                    "Aspect·Bedrock·ForestStand 범주 계수 — 발표자료 미공개"],
            "채택안": "NIFoS 6항 등가중 순위합. 변수 선택과 부호가 전부 외부 공표식에서 "
                   "오고 가중치를 적합하지 않아 선택 편의가 없다.",
            "북향도_견고성": {"양성_평균": round(float(ev.loc[y == 1, "north"].mean()), 3),
                        "음성_평균": round(float(ev.loc[y == 0, "north"].mean()), 3),
                        "Welch_t_p": float(f"{tt:.3g}"),
                        "lift1초과_읍면": f"{n_lift}/{len(per_em)}",
                        "읍면별": per_em,
                        "상관": sp},
            "핵심_관찰": "경사 단독 ROC 0.4145 — 무작위 이하다. 우리 FoS 는 경사가 주도하는데 "
                     "라벨은 급사면이 아니라 계곡의 마을이라 경사를 볼수록 라벨과 멀어진다. "
                     "사면향은 거주지 분포와 무관하면서 붕괴와 연결되어 가장 센 인자가 됐다."},
        "결과": rows,
        "한계": [
            "라벨이 피해 집계 리(里) 중심점이라 달성 가능한 AUPRC 에 천장이 있다(42번과 동일).",
            "NIFoS 식의 범주형 항과 경급을 빼서 부분 재현이다 — 원 논문 성능과 다르다.",
            "북향도의 부호(북향=위험)는 문헌 통념이자 우리 자료에서 확인한 것이다. "
            "완전한 외부 사전정보라고 주장하지 않는다.",
            "양성 54개의 작은 표본에서 여러 변수를 비교했다 — 읍면 LOO 를 주지표로 본다.",
            "뿌리 점착력은 상수 3.0 kPa 그대로다. 발표자료(p20~21 rTRIGRS)는 임상·밀도별 "
            "1~5 kPa 를 제시하고 민감도 1위로 꼽지만 임상도가 없어 공간분포화하지 못했다.",
        ],
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n저장: {OUT/'landslide_feature_boost.json'}")


if __name__ == "__main__":
    main()
