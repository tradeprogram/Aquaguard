"""
54_root_cohesion_imsangdo.py — 임상도로 뿌리 점착력 공간분포화 + 경급 항 추가

무엇이 바뀌는가
  42·53번까지 뿌리 점착력은 **전역 상수 3.0 kPa** 였다. 급사면이면 바위든 나지든
  빽빽한 숲이든 똑같이 3.0 kPa 를 더해 줬다는 뜻이다. 물리적으로 틀렸다.

  유송(국립산림과학원) 발표자료 p20~21 (rTRIGRS)은 뿌리 점착력을 **수관밀도별** 표로
  제시하고, 식생인자 민감도 분석에서 **뿌리 점착력이 1순위 변수**라고 명시한다.

      뿌리 점착력 (kPa)    소      중      밀
      약                 1.00   1.33   1.66
      중(표준)            2.00   2.67   3.33
      강                 3.00   4.00   5.00

  그동안 못 넣은 이유는 임상도가 없어서였다. 이제 있다.

자료
  임상도 1:5000 (2025년판, 경상남도) — G:/연구/보안붕 2세/data/임상도2025 1;5000/48/48.shp
  산청 범위 36,596 폴리곤 / 883.8 km², EPSG:5179 (우리 내부좌표 그대로)

  쓰는 속성
    DNST_CD   수관밀도  A=소 B=중 C=밀, NULL=무립목지      → 뿌리 점착력
    DMCLS_CD  경급      0=치수 1=소경목 2=중경목 3=대경목   → NIFoS 식의 Diameter 항
    FRTP_CD   임상      0=무립목지/비산림 1=침엽 2=활엽 3=혼효 4=죽림

  산청 분포: 밀 21,128 · 중 5,677 · 소 2,444 · 무립목지 7,347 폴리곤
            활엽수림 12,942 · 침엽수림 11,814 · 무립목지 5,324 · 혼효림 4,493 · 죽림 2,023

경급 항도 같이 켠다
  53번에서 NIFoS 공표식 중 `−0.594 × Diameter` 를 임상도가 없어 뺐었다. 계수가
  공표돼 있고(연속 항 중 두 번째로 크다) 이제 DMCLS_CD 가 있으므로 넣는다.

      LS = −2.596 + 0.069·Slope − 0.022·FlowLength + 0.011·Curvature + 0.734·TWI
           − 0.594·Diameter + 0.006·SoilDepth + (Aspect) + (Bedrock) + (ForestStand)

  남은 미사용 항은 모암(Bedrock)과 임상(ForestStand) 범주 계수뿐이다 — 발표자료에
  계수가 없다. 임상(FRTP)은 순위 인자로 참고 비교만 한다.

산불 보정은 그대로 둔다
  기존 dNBR 보정(f = 1.0/1.2/2.0/3.75 로 나눔)은 '뿌리가 타서 썩는다'는 시간 효과라
  수관밀도와 독립이다. 공간 c_r 을 먼저 정하고 그 위에 나눈다: c_r_eff = c_r(밀도) / f(dNBR).

출력
  data/sancheong_fos/cr_kpa.tif        뿌리 점착력 (kPa, 5m)
  data/sancheong_fos/dmcls.tif         경급 코드 (0~3, 무립목지 = nodata)
  data/sancheong_fos/frtp.tif          임상 코드 (0~4)
  outputs/root_cohesion_imsangdo.json

정직
  - 표의 '약/중/강'은 PDF 가 민감도 분석용으로 제시한 시나리오다. 표준(중)을 기본으로
    쓰고 세 가지를 모두 돌려 폭을 함께 보고한다 — 하나만 내면 가정이 결과처럼 보인다.
  - 죽림은 표에 없다. 수관밀도 코드가 있으므로 같은 표를 적용하되, 대나무 지하경의
    보강 특성은 교목과 달라 별도 근거가 필요하다는 점을 한계로 남긴다.
  - 무립목지/비산림은 c_r = 0 으로 둔다. 초본 뿌리는 깊이 0.3m 이내인데 우리 파괴면은
    0.35~1.2m 라 기여가 작다. 0 은 보수적(불안정 쪽) 가정이다.
  - 임상도는 항공사진 판독 기반이라 일부 속성이 현장과 다를 수 있다(산림청 고지).
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
from shapely.geometry import Point
from scipy.stats import rankdata

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(r"G:/연구/공모전/아쿠아가드")
FOS = ROOT / "data" / "sancheong_fos"
OUT = ROOT / "outputs"
IMSANG_SRC = Path(r"G:/연구/보안붕 2세/data/임상도2025 1;5000/48/48.shp")
IMSANG_CLIP = FOS / "imsangdo_sancheong.gpkg"

GW, WMAX, SLOPE_MIN = 9.81, 0.85, 15.0
MIN_STEEP_PX = 200
K_SIGMOID = 6.0
F = 4

# 유송 발표자료 p21 — 수관밀도별 뿌리 점착력 (kPa)
CR_TABLE = {"약": {"A": 1.00, "B": 1.33, "C": 1.66},
            "표준": {"A": 2.00, "B": 2.67, "C": 3.33},
            "강": {"A": 3.00, "B": 4.00, "C": 5.00}}
CR_NONE = 0.0           # 무립목지/비산림
CR_LEGACY = 3.0         # 42·53번이 쓰던 전역 상수

LS_B0, LS_SLOPE, LS_FLOWLEN, LS_CURV, LS_TWI, LS_DIAM, LS_SOIL = \
    -2.596, 0.069, -0.022, 0.011, 0.734, -0.594, 0.006

FRTP_NM = {0: "무립목지/비산림", 1: "침엽수림", 2: "활엽수림", 3: "혼효림", 4: "죽림"}
DNST_NM = {"A": "소", "B": "중", "C": "밀"}


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def clip_imsangdo(bounds):
    if IMSANG_CLIP.exists():
        return gpd.read_file(IMSANG_CLIP)
    import pyogrio
    g = pyogrio.read_dataframe(IMSANG_SRC, bbox=bounds)
    IMSANG_CLIP.parent.mkdir(parents=True, exist_ok=True)
    g.to_file(IMSANG_CLIP, driver="GPKG")
    return g


def main() -> None:
    bt = load("bt42", ROOT / "scripts" / "42_backtest_eval_split.py")
    b53 = load("b53", ROOT / "scripts" / "53_landslide_feature_boost.py")

    slope, tr, crs, shape = bt._read(ROOT / "data" / "dem" / "산청_slope_5m_5179.tif")
    z, *_ = bt._read(FOS / "z_m.tif")
    m0, *_ = bt._read(FOS / "m0.tif")
    dnbr, *_ = bt._read(FOS / "dnbr.tif")
    with rasterio.open(ROOT / "data" / "dem" / "산청_slope_5m_5179.tif") as ds:
        bnd = ds.bounds

    print("임상도 적재...", flush=True)
    g = clip_imsangdo((bnd.left, bnd.bottom, bnd.right, bnd.top)).to_crs(crs)
    print(f"  폴리곤 {len(g):,}개  {g.geometry.area.sum()/1e6:.1f} km²")

    dn = g["DNST_CD"].fillna("")
    dm = pd.to_numeric(g["DMCLS_CD"], errors="coerce")
    ft = pd.to_numeric(g["FRTP_CD"], errors="coerce")

    print("래스터화 (5m)...", flush=True)
    # 경급·임상은 코드 그대로 (무립목지는 255 = nodata)
    dmcls = rasterize(((geom, int(v) if np.isfinite(v) else 255)
                       for geom, v in zip(g.geometry, dm)),
                      out_shape=shape, transform=tr, fill=255, dtype="uint8")
    frtp = rasterize(((geom, int(v) if np.isfinite(v) else 255)
                      for geom, v in zip(g.geometry, ft)),
                     out_shape=shape, transform=tr, fill=255, dtype="uint8")
    # 밀도는 A/B/C → 1/2/3, 무립목지 0
    dcode = rasterize(((geom, {"A": 1, "B": 2, "C": 3}.get(v, 0))
                       for geom, v in zip(g.geometry, dn)),
                      out_shape=shape, transform=tr, fill=0, dtype="uint8")
    del g

    steep = np.isfinite(slope) & (slope >= SLOPE_MIN) & np.isfinite(z)
    tot = int(steep.sum())
    print(f"  급사면 {tot:,}px 중 밀도 분포: " + "  ".join(
        f"{DNST_NM.get(k,'무립목지')} {100*((dcode==v)&steep).sum()/tot:.1f}%"
        for k, v in (("", 0), ("A", 1), ("B", 2), ("C", 3))))
    print("  급사면 임상: " + "  ".join(
        f"{FRTP_NM.get(k,'?')} {100*((frtp==k)&steep).sum()/tot:.1f}%" for k in range(5)))

    fburn = np.ones_like(dnbr)
    fburn[dnbr >= 0.10] = 1.2
    fburn[dnbr >= 0.27] = 2.0
    fburn[dnbr >= 0.44] = 3.75
    fburn[~np.isfinite(dnbr)] = 1.0
    del dnbr

    beta = np.deg2rad(np.clip(slope, 0.1, 89.0))
    cosb, sinb = np.cos(beta), np.sin(beta)
    c, phi, gam = 2.0, np.deg2rad(36.0), 19.0
    m = np.clip(m0 + WMAX, 0, 1)
    denom = gam * z * sinb * cosb
    base_num = c + (gam - m * GW) * z * cosb ** 2 * np.tan(phi)
    del m0, m, beta, sinb

    def fos_with(cr_map):
        fos = (base_num + cr_map / fburn) / denom
        p = np.where(steep & np.isfinite(fos),
                     1.0 / (1.0 + np.exp(K_SIGMOID * (np.clip(fos, 0, 5) - 1.0))), 0.0)
        return fos, p.astype("float32")

    scen = {}
    for name, tbl in CR_TABLE.items():
        cr = np.zeros(shape, "float32")
        for k, v in (("A", 1), ("B", 2), ("C", 3)):
            cr[dcode == v] = tbl[k]
        cr[dcode == 0] = CR_NONE
        scen[name] = cr
    cr_legacy = np.full(shape, CR_LEGACY, "float32")

    prof = dict(driver="GTiff", height=shape[0], width=shape[1], count=1,
                crs=crs, transform=tr, compress="deflate", tiled=True,
                blockxsize=256, blockysize=256)
    with rasterio.open(FOS / "cr_kpa.tif", "w", dtype="float32", nodata=np.nan, **prof) as ds:
        ds.write(scen["표준"], 1)
    with rasterio.open(FOS / "dmcls.tif", "w", dtype="uint8", nodata=255, **prof) as ds:
        ds.write(dmcls, 1)
    with rasterio.open(FOS / "frtp.tif", "w", dtype="uint8", nodata=255, **prof) as ds:
        ds.write(frtp, 1)

    print("\nFoS 변화 (급사면 기준)")
    rows_fos = []
    fos_l, p_l = fos_with(cr_legacy)
    crit_legacy = steep & (fos_l < 1.0)      # 뒤에서 42번 기준선 재현에 쓴다
    n_crit_l = int(crit_legacy.sum())
    print(f"  기존 전역 {CR_LEGACY} kPa      평균 FoS {np.nanmean(fos_l[steep]):.3f}  "
          f"FoS<1 {n_crit_l:,}px ({100*n_crit_l/tot:.3f}%)")
    rows_fos.append({"시나리오": f"기존 전역 {CR_LEGACY} kPa",
                     "평균_FoS": round(float(np.nanmean(fos_l[steep])), 4),
                     "FoS<1_px": n_crit_l, "FoS<1_비율_%": round(100 * n_crit_l / tot, 4)})
    p_scen = {}
    for name in ("약", "표준", "강"):
        fos_s, p_s = fos_with(scen[name])
        p_scen[name] = p_s
        nc = int((steep & (fos_s < 1.0)).sum())
        print(f"  임상도 {name:2s}           평균 FoS {np.nanmean(fos_s[steep]):.3f}  "
              f"FoS<1 {nc:,}px ({100*nc/tot:.3f}%)   "
              f"기존 대비 {100*(nc/max(n_crit_l,1)-1):+.1f}%")
        rows_fos.append({"시나리오": f"임상도 {name}",
                         "평균_FoS": round(float(np.nanmean(fos_s[steep])), 4),
                         "FoS<1_px": nc, "FoS<1_비율_%": round(100 * nc / tot, 4),
                         "기존대비_%": round(100 * (nc / max(n_crit_l, 1) - 1), 1)})
    del fos_l, base_num, denom, fburn, cosb

    # ─── 평가 (53번과 같은 격자·라벨·지표)
    print("\n지형인자...", flush=True)
    dem5, *_ = bt._read(ROOT / "data" / "dem" / "산청_dem_5m_5179.tif")
    cell = 5.0 * F
    dem20 = b53.block_mean(dem5)
    H, W = dem20.shape
    tr20 = tr * rasterio.Affine.scale(F, F)
    steep20 = b53.block_any(steep)
    acc, flen = b53.d8(dem20, cell)
    slope20 = b53.block_mean(slope)
    twi = np.log(np.maximum(acc * cell, 1.0) / np.tan(np.deg2rad(np.clip(slope20, .5, 89.))))
    curv = b53.curvature(dem20, cell)
    gy, gx = np.gradient(dem20, cell)
    north = np.cos(np.arctan2(-gy, gx))
    soil = b53.block_mean(z) * 100.0
    dmcls20 = b53.block_mean(np.where(dmcls < 255, dmcls, np.nan))
    frtp20 = np.where(np.isfinite(b53.block_mean(np.where(frtp < 255, frtp, np.nan))),
                      b53.block_mean(np.where(frtp < 255, frtp, np.nan)), 0.0)

    em = gpd.read_file(ROOT / "data/vector/adm_dong_5179.geojson")
    em = em[em["sggnm"].astype(str).str.contains("산청")].reset_index(drop=True).to_crs(crs)
    grid = bt.build_grid(crs, em)
    n = len(grid)
    z5r = rasterize(((gm, i + 1) for i, gm in enumerate(grid.geometry)),
                    out_shape=shape, transform=tr, fill=0, dtype="int32")
    z20 = rasterize(((gm, i + 1) for i, gm in enumerate(grid.geometry)),
                    out_shape=(H, W), transform=tr20, fill=0, dtype="int32")
    grid["급사면px"] = np.bincount(z5r[steep], minlength=n + 1)[1:]
    print("42번 기준선 재현...", flush=True)
    grid["S0_기존"] = bt.flow_upslope_score(dem5, crit_legacy, z5r, n)
    del dem5

    ZM = b53.zonal_mean
    for k, v in (("slope", slope20), ("TWI", twi), ("curv", curv), ("flowlen", flen),
                 ("soil_cm", soil), ("north", north), ("dmcls", dmcls20), ("frtp", frtp20)):
        grid[k] = ZM(v, steep20, z20, n)
    grid["p_fos_기존"] = ZM(b53.block_mean(p_l), steep20, z20, n)
    for name in ("약", "표준", "강"):
        grid[f"p_fos_{name}"] = ZM(b53.block_mean(p_scen[name]), steep20, z20, n)

    ri = pd.read_csv(OUT / "sancheong_ri_validation.csv")
    pts = gpd.GeoDataFrame(ri, geometry=[Point(xy) for xy in zip(ri["lon"], ri["lat"])],
                           crs="EPSG:4326").to_crs(crs)
    jj = gpd.sjoin(grid.reset_index().rename(columns={"index": "cell"}),
                   pts[["건수", "geometry"]], how="left", predicate="contains")
    grid["산사태건수"] = jj.groupby("cell")["건수"].sum().fillna(0).reindex(
        range(n), fill_value=0).to_numpy()
    grid["y"] = (grid["산사태건수"] > 0).astype(int)

    ev = grid[grid["급사면px"] >= MIN_STEEP_PX].reset_index(drop=True)
    y = ev["y"].to_numpy(int)
    masks = [(ev["읍면"] == u).to_numpy() for u in sorted(ev["읍면"].unique())]
    rk = lambda c: rankdata(np.nan_to_num(ev[c].to_numpy(float))) / len(ev)
    print(f"\n평가격자 {len(ev)}개  양성 {int(y.sum())}개\n")

    rows = []

    def sc(s, nm, tag):
        s = np.where(np.isfinite(s), s, 0.0)
        m_ = bt.metrics(y, s)
        loo = [v for v in (bt.metrics(y[k], s[k])["AUPRC"] for k in masks) if v is not None]
        med = round(float(np.median(loo)), 4) if loo else None
        print(f"{nm:36s} {m_['AUPRC']:>7.4f} {m_['ROC_AUC']:>8.4f} {str(m_['lift']):>6} {str(med):>8}  {tag}")
        rows.append({"점수": nm, "구분": tag, **m_, "읍면LOO_AUPRC_중앙값": med})

    print(f"{'점수':36s} {'AUPRC':>7s} {'ROC-AUC':>8s} {'lift':>6s} {'읍면LOO':>8s}  구분")
    sc(ev["S0_기존"], "42번 기존 (상수 3.0kPa, 흐름누적)", "기준")
    sc(ev["p_fos_기존"], "FoS 확률 — 상수 3.0kPa", "FoS")
    for name in ("약", "표준", "강"):
        sc(ev[f"p_fos_{name}"], f"FoS 확률 — 임상도 {name}", "FoS")
    sc(ev["dmcls"], "경급 DMCLS (부호 반전)", "NIFoS") if False else sc(-ev["dmcls"], "경급 DMCLS (부호 반전)", "NIFoS")
    nifos6 = rk("slope") - rk("flowlen") + rk("curv") + rk("TWI") + rk("soil_cm") + rk("north")
    sc(nifos6, "53번 NIFoS 6항", "기준2")
    sc(nifos6 - rk("dmcls"), "NIFoS 7항 (+경급) ★", "NIFoS")
    sc(nifos6 - rk("dmcls") + rk("p_fos_표준"), "NIFoS 7항 + FoS(임상도)", "NIFoS")
    ls = (LS_B0 + LS_SLOPE * ev["slope"] + LS_FLOWLEN * ev["flowlen"] + LS_CURV * ev["curv"]
          + LS_TWI * ev["TWI"] + LS_DIAM * ev["dmcls"].fillna(0) + LS_SOIL * ev["soil_cm"])
    sc(ls.to_numpy(), "LS 공표계수 (경급 포함)", "NIFoS")
    sc((ls + 2.0 * ev["north"]).to_numpy(), "LS 공표계수 + 2.0·북향도", "NIFoS")
    sc(ev["frtp"], "임상 FRTP (참고)", "참고")

    # 경급 견고성 — 53번에서 북향도에 했던 것과 같은 점검
    from scipy.stats import ttest_ind
    dm_ev = ev["dmcls"]
    per_em = []
    for u, k in zip(sorted(ev["읍면"].unique()), masks):
        mm = bt.metrics(y[k], -dm_ev[k].to_numpy())
        if mm["AUPRC"] is not None:
            per_em.append({"읍면": u, **mm})
    dm_robust = {
        "결측허수_격자수": int((dm_ev == 0).sum()),
        "범위": [round(float(dm_ev.min()), 2), round(float(dm_ev.max()), 2)],
        "양성_평균": round(float(dm_ev[y == 1].mean()), 3),
        "음성_평균": round(float(dm_ev[y == 0].mean()), 3),
        "Welch_t_p": float(f"{ttest_ind(dm_ev[y==1], dm_ev[y==0], equal_var=False).pvalue:.3g}"),
        "lift1초과_읍면": f"{sum(1 for r in per_em if r['lift'] > 1)}/{len(per_em)}",
        "읍면별": per_em,
    }
    print(f"\n경급 견고성: 양성 평균 {dm_robust['양성_평균']} vs 음성 {dm_robust['음성_평균']} "
          f"(Welch t p={dm_robust['Welch_t_p']})  lift>1 {dm_robust['lift1초과_읍면']}  "
          f"결측허수 격자 {dm_robust['결측허수_격자수']}개")

    base = rows[0]
    best = max((r for r in rows if r["구분"] in ("NIFoS", "FoS")),
               key=lambda r: r["읍면LOO_AUPRC_중앙값"] or 0)
    print(f"\n기준 → 최고(읍면LOO): {base['읍면LOO_AUPRC_중앙값']} → "
          f"{best['읍면LOO_AUPRC_중앙값']}  ({best['점수']})")

    OUT.mkdir(exist_ok=True)
    ev.drop(columns="geometry").to_csv(OUT / "root_cohesion_grid.csv", index=False,
                                       encoding="utf-8-sig")
    (OUT / "root_cohesion_imsangdo.json").write_text(json.dumps({
        "생성": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"),
        "자료": {"임상도": "임상도 1:5000 2025년판 경상남도(48). 산청 범위 "
                      f"{36596}폴리곤 / 883.8 km², EPSG:5179",
               "쓴_속성": {"DNST_CD": "수관밀도 A=소 B=중 C=밀, NULL=무립목지 → 뿌리 점착력",
                        "DMCLS_CD": "경급 0=치수 1=소경목 2=중경목 3=대경목 → NIFoS Diameter",
                        "FRTP_CD": "임상 0=무립목지 1=침엽 2=활엽 3=혼효 4=죽림"}},
        "뿌리점착력표_kPa": CR_TABLE,
        "무립목지_kPa": CR_NONE,
        "기존_전역상수_kPa": CR_LEGACY,
        "출처": "유송(국립산림과학원), 「산사태예측기술현황및발전방향」 p20~21 (rTRIGRS). "
              "식생인자 민감도 1순위가 뿌리 점착력이라고 명시.",
        "FoS_변화": rows_fos,
        "평가": rows,
        "경급_견고성": dm_robust,
        "채택": "NIFoS 7항 등가중(+경급). 변수 선택·부호가 전부 외부 공표식에서 오고 가중치를 적합하지 않는다. LS 공표계수+2.0·북향도 가 읍면LOO 는 더 높지만 그 2.0 은 우리가 고른 가중치라 선택 편의가 있다.",
        "한계": [
            "약/중/강은 PDF 가 민감도용으로 제시한 시나리오다. 표준을 기본으로 쓰되 "
            "세 가지를 모두 돌려 폭을 함께 보고한다.",
            "죽림은 표에 없다. 수관밀도 코드로 같은 표를 적용했으나 대나무 지하경의 "
            "보강 특성은 교목과 달라 별도 근거가 필요하다.",
            "무립목지/비산림은 c_r=0 이다. 초본 뿌리는 0.3m 이내인데 파괴면이 0.35~1.2m "
            "라 기여가 작다 — 보수적(불안정 쪽) 가정이다.",
            "임상도는 항공사진 판독 기반이라 일부 속성이 현장과 다를 수 있다(산림청 고지).",
            "모암(Bedrock)과 임상(ForestStand) 범주 계수는 여전히 미공개라 LS 식에 "
            "넣지 못했다. 임상은 순위 인자로 참고 비교만 했다.",
            "라벨은 여전히 피해 집계 리(里) 중심점이다 — 42번 한계 그대로.",
        ],
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n저장: {OUT/'root_cohesion_imsangdo.json'}")
    print(f"      {FOS/'cr_kpa.tif'} · dmcls.tif · frtp.tif")


if __name__ == "__main__":
    main()
