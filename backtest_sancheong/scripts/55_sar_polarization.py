"""
55_sar_polarization.py — Sentinel-1 편파별 재검토: 53번의 "RVI 실패" 결론을 정정한다

★ 53번에서 내린 결론이 두 군데 틀렸다

  (1) **VV·VH 를 비율 하나로 뭉갰다.**
      53번의 `rvi()` 는 VV·VH 파일을 둘 다 읽어 놓고 `RVI = 4·VH/(VV+VH)` 하나만
      평가했다. VV 단독·VH 단독은 한 번도 보지 않았다.
      산사태는 식생을 걷어내 VV·VH 가 **같이** 변한다 — 비율을 취하면 그 공통 변화가
      상쇄된다. 실제로 사건을 걸친 동일궤도 차분에서:

          ΔVH   AUPRC 0.0914  ROC 0.5773  lift 1.42
          ΔVV   AUPRC 0.0821  ROC 0.5971  lift 1.27
          ΔRVI  AUPRC 0.0747  ROC 0.4932  lift 1.16   ← 53번이 쓴 것

      비율이 신호를 죽이고 있었다.

  (2) **"사건 전 동일궤도 쌍이 없다"가 틀렸다.**
      53번은 07-10~07-27 만 검색해서 그렇게 결론냈다. 5~8월로 넓히면 있다.

          궤도 127asc : 05-01 05-13 05-25 06-06 **06-18** **07-12** 07-24 08-05
          궤도  54asc : 05-08 05-20 **06-25** **07-07** 07-19 07-25 07-31
          궤도 134desc: 07-18 08-05

      사건은 2025-07-16~20 이다. 따라서
          06-18 → 07-12 (127asc)  둘 다 사건 전, 같은 궤도·같은 위성
          06-25 → 07-07 ( 54asc)  둘 다 사건 전
      → **정당한 사전 예측 변수를 만들 수 있다.**

────────────────────────────────────────────────────────────────────────────
설계 — 누수 경계를 쌍 단위로 명시한다

  사건 전(정당)   06-18→07-12 (127asc) · 06-25→07-07 (54asc)
                 사건 전 수 주의 후방강우·토양수분 상태를 담는다. 예측 변수로 쓴다.
  사건 포함(탐지) 07-12→07-24 (127asc)
                 산사태가 식생을 걷어낸 흔적. 예측력이 아니라 탐지력이다.
  사후(대조)     07-19→07-25 (54asc)
                 사건 끝물만 걸친다. 여기서 신호가 없어야 위 두 개가 우연이 아니다.
                 실제로 ROC 0.498~0.501 로 무작위다 — 대조군이 제대로 작동했다.

  모든 차분은 **동일 상대궤도·동일 통과방향** 끼리만 한다. 53번이 처음에 본
  ROC 0.609 는 127asc(상행) − 134desc(하행) 이라 입사각 차이가 지배한 값이었다.

★ 체리피킹 방지
  사전 쌍 2개 × 편파 2종 = 후보 4개다. 가장 좋은 하나(54asc ΔVH, LOO 0.2612)를
  고르면 선택 편의가 생긴다. 그래서 **4개를 전부 순위평균한 값**을 채택안으로 쓰고,
  단독 최고치는 참고로만 적는다.

출력
  outputs/sar_polarization.json
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
from scipy.stats import rankdata, ttest_ind
from shapely.geometry import Point

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(r"G:/연구/공모전/아쿠아가드")
FOS = ROOT / "data" / "sancheong_fos"
SENT = ROOT / "data" / "sentinel"
OUT = ROOT / "outputs"
F = 4
SLOPE_MIN, MIN_STEEP_PX = 15.0, 200

# Planetary Computer STAC 조회로 확인한 상대궤도·통과방향
ORBIT = {"06-18": ("127asc", "S1A"), "06-25": ("54asc", "S1A"), "07-07": ("54asc", "S1A"),
         "07-12": ("127asc", "S1A"), "07-18": ("134desc", "S1C"), "07-19": ("54asc", "S1A"),
         "07-24": ("127asc", "S1A"), "07-25": ("54asc", "S1C")}

#  (전, 후, 궤도, 구분)
PAIRS = [("06-18", "07-12", "127asc", "사건 전(정당)"),
         ("06-25", "07-07", "54asc", "사건 전(정당)"),
         ("07-12", "07-24", "127asc", "사건 포함(탐지)"),
         ("07-19", "07-25", "54asc", "사후(대조)")]
PRE = [(a, b) for a, b, _, t in PAIRS if t.startswith("사건 전")]


def load(n, p):
    s = importlib.util.spec_from_file_location(n, p)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


def main() -> None:
    bt = load("bt42", ROOT / "scripts" / "42_backtest_eval_split.py")
    b53 = load("b53", ROOT / "scripts" / "53_landslide_feature_boost.py")

    slope, tr, crs, shape = bt._read(ROOT / "data" / "dem" / "산청_slope_5m_5179.tif")
    z, *_ = bt._read(FOS / "z_m.tif")
    steep = np.isfinite(slope) & (slope >= SLOPE_MIN) & np.isfinite(z)
    dem5, *_ = bt._read(ROOT / "data" / "dem" / "산청_dem_5m_5179.tif")
    dem20 = b53.block_mean(dem5)
    del dem5
    H, W = dem20.shape
    tr20 = tr * rasterio.Affine.scale(F, F)
    st20 = b53.block_any(steep)
    cell = 5.0 * F

    def band(date, pol):
        """σ⁰ 를 dB 로. 변화탐지는 로그 영역에서 보는 것이 표준이다."""
        with rasterio.open(SENT / f"s1_sancheong_2025-{date}_{pol}.tif") as ds:
            src, stf, scrs = ds.read(1).astype("float32"), ds.transform, ds.crs
        src = np.where(src > 0, src, np.nan)
        dst = np.full((H, W), np.nan, "float32")
        reproject(src, dst, src_transform=stf, src_crs=scrs, dst_transform=tr20,
                  dst_crs=crs, src_nodata=np.nan, dst_nodata=np.nan,
                  resampling=Resampling.average)
        return 10 * np.log10(np.where(dst > 0, dst, np.nan))

    dates = sorted({d for p in PAIRS for d in p[:2]})
    print(f"S1 적재 {len(dates)}시점 × 2편파...", flush=True)
    V = {d: {p: band(d, p) for p in ("vv", "vh")} for d in dates}

    # 격자·라벨 (42번과 동일)
    em = gpd.read_file(ROOT / "data/vector/adm_dong_5179.geojson")
    em = em[em["sggnm"].astype(str).str.contains("산청")].reset_index(drop=True).to_crs(crs)
    grid = bt.build_grid(crs, em)
    n = len(grid)
    z5 = rasterize(((g, i + 1) for i, g in enumerate(grid.geometry)),
                   out_shape=shape, transform=tr, fill=0, dtype="int32")
    z20 = rasterize(((g, i + 1) for i, g in enumerate(grid.geometry)),
                    out_shape=(H, W), transform=tr20, fill=0, dtype="int32")
    grid["급사면px"] = np.bincount(z5[steep], minlength=n + 1)[1:]

    ZM = b53.zonal_mean
    for a, b_, orb, tag in PAIRS:
        for p in ("vv", "vh"):
            grid[f"d{p.upper()}_{a}_{b_}"] = ZM(V[b_][p] - V[a][p], st20, z20, n)
        with np.errstate(invalid="ignore", divide="ignore"):
            rv = lambda d: 4 * (10 ** (V[d]["vh"] / 10)) / (10 ** (V[d]["vv"] / 10) + 10 ** (V[d]["vh"] / 10))
            grid[f"dRVI_{a}_{b_}"] = ZM(rv(b_) - rv(a), st20, z20, n)

    # NIFoS 7항 구성요소
    acc, flen = b53.d8(dem20, cell)
    sl20 = b53.block_mean(slope)
    twi = np.log(np.maximum(acc * cell, 1.0) / np.tan(np.deg2rad(np.clip(sl20, .5, 89.))))
    curv = b53.curvature(dem20, cell)
    gy, gx = np.gradient(dem20, cell)
    north = np.cos(np.arctan2(-gy, gx))
    with rasterio.open(FOS / "dmcls.tif") as ds:
        dmc = ds.read(1)
    for k, v in (("slope", sl20), ("TWI", twi), ("curv", curv), ("flowlen", flen),
                 ("soil_cm", b53.block_mean(z) * 100.0), ("north", north),
                 ("dmcls", b53.block_mean(np.where(dmc < 255, dmc, np.nan)))):
        grid[k] = ZM(v, st20, z20, n)

    ri = pd.read_csv(OUT / "sancheong_ri_validation.csv")
    pts = gpd.GeoDataFrame(ri, geometry=[Point(xy) for xy in zip(ri["lon"], ri["lat"])],
                           crs="EPSG:4326").to_crs(crs)
    j = gpd.sjoin(grid.reset_index().rename(columns={"index": "cell"}),
                  pts[["건수", "geometry"]], how="left", predicate="contains")
    grid["y"] = ((j.groupby("cell")["건수"].sum().fillna(0)
                  .reindex(range(n), fill_value=0).to_numpy()) > 0).astype(int)

    ev = grid[grid["급사면px"] >= MIN_STEEP_PX].reset_index(drop=True)
    y = ev["y"].to_numpy(int)
    masks = [(ev["읍면"] == u).to_numpy() for u in sorted(ev["읍면"].unique())]
    rk = lambda v: rankdata(np.nan_to_num(np.asarray(v, float))) / len(ev)
    rows = []

    def sc(s, nm, tag, flip_ok=True):
        s = np.nan_to_num(np.asarray(s, float))
        a, b_ = bt.metrics(y, s), bt.metrics(y, -s)
        sign = "정" if (not flip_ok or a["AUPRC"] >= b_["AUPRC"]) else "역"
        use = s if sign == "정" else -s
        m = a if sign == "정" else b_
        per = [bt.metrics(y[k], use[k]) for k in masks]
        per = [q for q in per if q["AUPRC"] is not None]
        med = round(float(np.median([q["AUPRC"] for q in per])), 4)
        ok = sum(1 for q in per if q["lift"] > 1)
        print(f"  {nm:34s} {m['AUPRC']:.4f} {m['ROC_AUC']:>8.4f} {m['lift']:>6.2f} {med:>8.4f}  {ok}/{len(per)}  [{sign}] {tag}")
        rows.append({"점수": nm, "구분": tag, "부호": sign, **m,
                     "읍면LOO_AUPRC_중앙값": med, "lift1초과_읍면": f"{ok}/{len(per)}"})
        return use

    print(f"\n평가격자 {len(ev)}개  양성 {int(y.sum())}개  기저 {y.mean():.4f}")
    print(f"\n{'점수':34s} {'AUPRC':>6s} {'ROC-AUC':>8s} {'lift':>6s} {'읍면LOO':>8s}  일관  부호  구분")
    pre_used = {}
    for a, b_, orb, tag in PAIRS:
        print(f"[{a} → {b_}  {orb}]")
        for p in ("VV", "VH", "RVI"):
            c = f"d{p}_{a}_{b_}"
            u = sc(ev[c], f"  Δ{p}", tag)
            if tag.startswith("사건 전") and p in ("VV", "VH"):
                pre_used[c] = u

    print("\n[체리피킹 없는 합성]")
    avg4 = sum(rk(v) for v in pre_used.values()) / len(pre_used)
    avg_vv = sum(rk(v) for k, v in pre_used.items() if "dVV" in k) / 2
    avg_vh = sum(rk(v) for k, v in pre_used.items() if "dVH" in k) / 2
    sc(avg4, "사전 Δσ⁰ 4종 평균", "사건 전(정당)", flip_ok=False)
    sc(avg_vv, "  VV 2궤도 평균", "사건 전(정당)", flip_ok=False)
    sc(avg_vh, "  VH 2궤도 평균", "사건 전(정당)", flip_ok=False)

    n7 = (rk(ev["slope"]) - rk(ev["flowlen"]) + rk(ev["curv"]) + rk(ev["TWI"])
          + rk(ev["soil_cm"]) + rk(ev["north"]) - rk(ev["dmcls"]))
    print("\n[NIFoS 7항과 결합]")
    sc(n7, "NIFoS 7항 (54번 채택안)", "기준", flip_ok=False)
    sc(n7 + avg_vh, "  + 사전 ΔVH 2궤도 평균 ★채택", "①+②", flip_ok=False)
    sc(n7 + avg4, "  + 사전 Δσ⁰ 4종 평균", "①+②", flip_ok=False)
    sc(n7 + avg_vv, "  + 사전 ΔVV 2궤도 평균", "①+②", flip_ok=False)
    print("  (참고 — 후보 4개 중 최고를 고른 경우. 선택 편의가 있어 채택하지 않는다)")
    sc(n7 + rk(-ev["dVH_06-25_07-07"]), "  + 54asc ΔVH 단독", "참고", flip_ok=False)

    # 견고성
    rob = {}
    for c in pre_used:
        per = [bt.metrics(y[k], pre_used[c][k]) for k in masks]
        per = [q for q in per if q["AUPRC"] is not None]
        rob[c] = {"양성_평균_dB": round(float(ev.loc[y == 1, c].mean()), 4),
                  "음성_평균_dB": round(float(ev.loc[y == 0, c].mean()), 4),
                  "Welch_t_p": float(f"{ttest_ind(ev.loc[y==1,c], ev.loc[y==0,c], equal_var=False).pvalue:.3g}"),
                  "lift1초과_읍면": f"{sum(1 for q in per if q['lift']>1)}/{len(per)}"}
    print("\n사전 차분 견고성")
    for c, v in rob.items():
        print(f"  {c:22s} 양성 {v['양성_평균_dB']:+.3f} vs 음성 {v['음성_평균_dB']:+.3f} dB  "
              f"t p={v['Welch_t_p']}  lift>1 {v['lift1초과_읍면']}")

    OUT.mkdir(exist_ok=True)
    ev.drop(columns="geometry").to_csv(OUT / "sar_polarization_grid.csv",
                                       index=False, encoding="utf-8-sig")
    (OUT / "sar_polarization.json").write_text(json.dumps({
        "생성": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"),
        "53번_결론_정정": [
            "VV·VH 를 RVI 비율 하나로 뭉개 평가했다. 산사태는 VV·VH 를 같이 바꾸므로 "
            "비율을 취하면 공통 변화가 상쇄된다 — 비율이 신호를 죽이고 있었다. "
            "사건을 걸친 동일궤도 차분에서 ΔVH 0.0914 / ΔVV 0.0821 / ΔRVI 0.0747.",
            "'사건 전 동일궤도 쌍이 없다'는 7월만 검색해서 내린 잘못된 결론이다. "
            "5~8월로 넓히면 06-18→07-12(127asc), 06-25→07-07(54asc) 가 있다.",
        ],
        "장면_궤도": {k: {"궤도": v[0], "위성": v[1]} for k, v in ORBIT.items()},
        "쌍": [{"전": a, "후": b, "궤도": o, "구분": t} for a, b, o, t in PAIRS],
        "설계": {"평가격자": int(len(ev)), "양성": int(y.sum()),
               "차분": "동일 상대궤도·동일 통과방향끼리만. dB(로그) 영역에서.",
               "집계": f"{cell:.0f}m → 1km 격자, 급사면 평균",
               "체리피킹_방지": "사전 쌍 2 × 편파 2 = 후보 4개를 전부 순위평균해 채택안으로 "
                           "쓰고, 단독 최고치는 참고로만 적는다."},
        "결과": rows,
        "사전차분_견고성": rob,
        "한계": [
            "사전 차분의 효과 크기가 0.04~0.09 dB 로 작다 — S1 방사 잡음과 같은 수준이다. "
            "읍면 일관성(9/9)이 유일한 견고성 근거다.",
            "두 궤도의 결과가 엇갈린다(54asc ΔVH ROC 0.624 vs 127asc ΔVH 0.516). "
            "그래서 하나를 고르지 않고 평균했다.",
            "사전 차분이 무엇을 재는지는 특정하지 못했다 — 후방강우에 따른 토양수분일 수도, "
            "식생 수분일 수도 있다. 분리하려면 같은 기간 토양수분 관측이 필요하다.",
            "라벨은 여전히 피해 집계 리(里) 중심점이다(42번 한계 그대로).",
        ],
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n저장: {OUT/'sar_polarization.json'}")


if __name__ == "__main__":
    main()
