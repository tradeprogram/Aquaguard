"""
43_ml_residual_correction.py  (a-ml: 물리 baseline 위 ML 보정 — 학습·공간검증)

목적: FoS 물리점수를 대체하는 게 아니라, 물리가 못 잡는 잔차를 지형·피복 변수로
보정할 수 있는지 **검증**한다. 채택 여부는 결과가 정한다.

설계상 못 박아 둘 것:
  1) ML은 물리 위에 얹는다. 물리점수(FoS<1 비율)를 feature로 넣고, 물리를
     빼버린 모형과 비교한다. 물리 없이 이기면 그건 지형암기지 보정이 아니다.
  2) 평가는 반드시 **읍면 leave-one-out(공간분할)**. 무작위 CV는 공간자기상관
     때문에 반드시 과대평가된다(42번에서 확인).
  3) 채택 기준을 미리 정한다 — 사전 등록(pre-registration):
        공간CV AUPRC 중앙값이 물리단독보다 **유의하게** 높아야 채택.
        아니면 기각하고 물리단독을 유지한다. 사후에 기준을 바꾸지 않는다.

치명적 위험(반드시 읽을 것):
  참값이 '피해 집계 마을 중심점'이라 거주지 분포를 따라간다(40·42번). 여기에
  ML을 맞추면 모형은 산사태가 아니라 **"사람이 사는 곳"을 학습**한다. 표면적
  점수는 오르는데 산사태 예측력은 오히려 떨어질 수 있다. 그래서 채택 기준을
  공간CV로 걸고, 채택되더라도 기본 비활성으로 배포한다.
"""
from __future__ import annotations

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
from shapely.geometry import Point, box
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(r"G:/연구/공모전/아쿠아가드")
FOS = ROOT / "data" / "sancheong_fos"
OUT = ROOT / "outputs"
MODELS = ROOT / "models"

GW = 9.81
CR_HEALTHY = 3.0
WMAX = 0.85
SLOPE_MIN = 15.0
CELL_M = 1000.0
MIN_STEEP_PX = 200
SEED = 42

PHYS = "물리_임계비율"
FEATURES_GEO = ["평균경사", "급사면비율", "평균dNBR", "흉터비율", "평균토심", "평균m0"]


def _read(path: Path):
    with rasterio.open(path) as ds:
        return ds.read(1).astype("float32"), ds.transform, ds.crs, (ds.height, ds.width)


def build_table() -> pd.DataFrame:
    """1km 격자 × (물리점수 + 지형/피복 feature + 라벨). 42번과 같은 격자·라벨."""
    slope, tr, crs, shape = _read(ROOT / "data" / "dem" / "산청_slope_5m_5179.tif")
    z, _, _, _ = _read(FOS / "z_m.tif")
    m0, _, _, _ = _read(FOS / "m0.tif")
    dnbr, _, _, _ = _read(FOS / "dnbr.tif")

    steep = np.isfinite(slope) & (slope >= SLOPE_MIN) & np.isfinite(z)

    f = np.ones_like(dnbr)
    f[dnbr >= 0.10] = 1.2
    f[dnbr >= 0.27] = 2.0
    f[dnbr >= 0.44] = 3.75
    f[~np.isfinite(dnbr)] = 1.0
    cr_eff = CR_HEALTHY / f

    beta = np.deg2rad(np.clip(slope, 0.1, 89.0))
    cosb, sinb = np.cos(beta), np.sin(beta)
    c, phi, gam = 2.0, np.deg2rad(36.0), 19.0
    m = np.clip(m0 + WMAX, 0, 1)
    fos = (c + cr_eff + (gam - m * GW) * z * cosb ** 2 * np.tan(phi)) / (gam * z * sinb * cosb)
    crit = steep & np.isfinite(fos) & (fos < 1.0)
    burn = np.isfinite(dnbr) & (dnbr >= 0.10)
    del cr_eff, f, beta, cosb, sinb, m, fos

    em = gpd.read_file(ROOT / "data/vector/adm_dong_5179.geojson")
    em = em[em["sggnm"].astype(str).str.contains("산청")].reset_index(drop=True).to_crs(crs)

    minx, miny, maxx, maxy = em.total_bounds
    cells = [box(x, y, x + CELL_M, y + CELL_M)
             for x in np.arange(minx, maxx, CELL_M) for y in np.arange(miny, maxy, CELL_M)]
    g = gpd.GeoDataFrame(geometry=cells, crs=crs)
    g = gpd.sjoin(g, em[["name", "geometry"]], how="inner", predicate="intersects")
    g = g.drop(columns=[c for c in ("index_right", "index_left") if c in g.columns])
    g = g.drop_duplicates(subset="geometry").reset_index(drop=True).rename(columns={"name": "읍면"})

    zones = rasterize(((geom, i + 1) for i, geom in enumerate(g.geometry)),
                      out_shape=shape, transform=tr, fill=0, dtype="int32")
    n = len(g)

    def _cnt(mask):
        return np.bincount(zones[mask], minlength=n + 1)[1:].astype(float)

    def _sum(mask, arr):
        return np.bincount(zones[mask], weights=arr[mask], minlength=n + 1)[1:]

    npx = _cnt(zones > 0)
    nst = _cnt(steep)
    safe = np.maximum(nst, 1)

    g["급사면px"] = nst.astype(int)
    g[PHYS] = _cnt(steep & crit) / safe
    g["평균경사"] = _sum(steep, slope) / safe
    g["급사면비율"] = nst / np.maximum(npx, 1)
    finite_d = steep & np.isfinite(dnbr)
    g["평균dNBR"] = _sum(finite_d, dnbr) / np.maximum(_cnt(finite_d), 1)
    g["흉터비율"] = _cnt(steep & burn) / safe
    g["평균토심"] = _sum(steep, z) / safe
    g["평균m0"] = _sum(steep, m0) / safe

    ri = pd.read_csv(OUT / "sancheong_ri_validation.csv")
    pts = gpd.GeoDataFrame(ri, geometry=[Point(xy) for xy in zip(ri["lon"], ri["lat"])],
                           crs="EPSG:4326").to_crs(crs)
    j = gpd.sjoin(g.reset_index().rename(columns={"index": "cell"}),
                  pts[["건수", "geometry"]], how="left", predicate="contains")
    hits = j.groupby("cell")["건수"].sum().fillna(0)
    g["y"] = (hits.reindex(range(n), fill_value=0).to_numpy() > 0).astype(int)

    return pd.DataFrame(g.drop(columns="geometry"))


def spatial_cv(df: pd.DataFrame, cols: list[str], model_fn) -> tuple[list[float], list[dict]]:
    """읍면 leave-one-out. 한 읍면을 통째로 빼고 학습 → 그 읍면에서만 평가."""
    aps, per = [], []
    for nm in sorted(df["읍면"].unique()):
        te = df["읍면"] == nm
        tr_df, te_df = df[~te], df[te]
        if te_df["y"].sum() == 0 or te_df["y"].nunique() < 2:
            per.append({"읍면": nm, "AUPRC": None, "사유": "hold-out에 양성 없음"})
            continue
        if tr_df["y"].sum() < 5:
            per.append({"읍면": nm, "AUPRC": None, "사유": "학습 양성 부족"})
            continue
        mdl = model_fn()
        mdl.fit(tr_df[cols].to_numpy(float), tr_df["y"].to_numpy(int))
        s = mdl.predict_proba(te_df[cols].to_numpy(float))[:, 1]
        ap = float(average_precision_score(te_df["y"].to_numpy(int), s))
        aps.append(ap)
        per.append({"읍면": nm, "AUPRC": round(ap, 4), "n": int(len(te_df)),
                    "양성": int(te_df["y"].sum())})
    return aps, per


def phys_only_cv(df: pd.DataFrame) -> tuple[list[float], list[dict]]:
    """물리점수를 그대로 순위점수로 쓴 경우(학습 없음)의 같은 분할 성적."""
    aps, per = [], []
    for nm in sorted(df["읍면"].unique()):
        te_df = df[df["읍면"] == nm]
        if te_df["y"].sum() == 0 or te_df["y"].nunique() < 2:
            per.append({"읍면": nm, "AUPRC": None, "사유": "hold-out에 양성 없음"})
            continue
        ap = float(average_precision_score(te_df["y"].to_numpy(int),
                                           te_df[PHYS].to_numpy(float)))
        aps.append(ap)
        per.append({"읍면": nm, "AUPRC": round(ap, 4), "n": int(len(te_df)),
                    "양성": int(te_df["y"].sum())})
    return aps, per


def main() -> None:
    print("특징표 생성 중...")
    df = build_table()
    df = df[df["급사면px"] >= MIN_STEEP_PX].reset_index(drop=True)
    print(f"평가격자 {len(df)}개, 양성 {int(df['y'].sum())}개 "
          f"(양성비율 {100*df['y'].mean():.1f}%)")
    df.to_csv(OUT / "ml_feature_table.csv", index=False, encoding="utf-8-sig")

    cols_full = [PHYS] + FEATURES_GEO
    cols_nophys = FEATURES_GEO

    def lr():
        return make_pipeline(StandardScaler(),
                             LogisticRegression(max_iter=2000, class_weight="balanced",
                                                random_state=SEED))

    def gb():
        return HistGradientBoostingClassifier(max_depth=3, max_iter=200,
                                              learning_rate=0.05, random_state=SEED)

    print("\n=== 읍면 leave-one-out 공간검증 ===")
    runs = {}
    ap_phys, per_phys = phys_only_cv(df)
    runs["물리단독"] = {"AUPRC": ap_phys, "읍면별": per_phys}
    print(f"  물리단독            중앙값 {np.median(ap_phys):.4f}  (n={len(ap_phys)})")

    for name, fn, cols in [("로지스틱+물리", lr, cols_full),
                           ("GBDT+물리", gb, cols_full),
                           ("GBDT_물리제외", gb, cols_nophys)]:
        aps, per = spatial_cv(df, cols, fn)
        runs[name] = {"AUPRC": aps, "읍면별": per, "features": cols}
        print(f"  {name:18s} 중앙값 {np.median(aps):.4f}  (n={len(aps)})")

    # 짝지어 비교 — 같은 읍면끼리 비교해야 공정하다
    def paired_gain(name: str) -> dict:
        a = {p["읍면"]: p["AUPRC"] for p in runs[name]["읍면별"] if p.get("AUPRC") is not None}
        b = {p["읍면"]: p["AUPRC"] for p in per_phys if p.get("AUPRC") is not None}
        common = sorted(set(a) & set(b))
        d = [a[k] - b[k] for k in common]
        if not d:
            return {"비교가능_읍면": 0}
        wins = sum(1 for v in d if v > 0)
        try:
            from scipy.stats import wilcoxon
            p = float(wilcoxon(d).pvalue) if len(d) >= 5 else None
        except Exception:
            p = None
        return {"비교가능_읍면": len(common), "평균차": round(float(np.mean(d)), 4),
                "중앙값차": round(float(np.median(d)), 4),
                "이긴_읍면": wins, "진_읍면": len(d) - wins,
                "wilcoxon_p": None if p is None else round(p, 4)}

    print("\n=== 물리단독 대비 짝지은 이득 ===")
    gains = {}
    for name in ("로지스틱+물리", "GBDT+물리", "GBDT_물리제외"):
        gains[name] = paired_gain(name)
        g = gains[name]
        print(f"  {name:18s} 평균차 {g.get('평균차')}  "
              f"승/패 {g.get('이긴_읍면')}/{g.get('진_읍면')}  p={g.get('wilcoxon_p')}")

    # 사전 등록한 채택 기준
    best = max(("로지스틱+물리", "GBDT+물리"),
               key=lambda k: gains[k].get("중앙값차", -9))
    gb_ = gains[best]
    adopt = bool(gb_.get("중앙값차", 0) > 0
                 and gb_.get("wilcoxon_p") is not None
                 and gb_["wilcoxon_p"] < 0.05)

    verdict = {
        "채택": adopt,
        "최선모형": best,
        "기준": "공간CV(읍면 LOO) AUPRC 중앙값이 물리단독보다 높고 Wilcoxon p<0.05",
        "판정": ("채택 — 물리 위 ML 보정이 공간분할에서도 유의하게 개선"
               if adopt else
               "기각 — 공간분할에서 물리단독 대비 유의한 개선 없음. 물리단독 유지."),
    }
    print(f"\n=== 사전 등록 기준에 따른 판정 ===\n  {verdict['판정']}")

    MODELS.mkdir(exist_ok=True)
    summary = {
        "item": "a-ml",
        "생성": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"),
        "설계": {
            "단위": f"{CELL_M:.0f}m 격자", "격자수": int(len(df)),
            "양성": int(df["y"].sum()),
            "features_물리": PHYS, "features_지형": FEATURES_GEO,
            "검증": "읍면 leave-one-out (공간분할)",
            "사전등록_채택기준": verdict["기준"],
        },
        "공간CV_AUPRC_중앙값": {
            k: (round(float(np.median(v["AUPRC"])), 4) if v["AUPRC"] else None)
            for k, v in runs.items()
        },
        "짝지은_이득": gains,
        "판정": verdict,
        "읍면별_상세": {k: v["읍면별"] for k, v in runs.items()},
        "한계": [
            "참값이 피해 집계 마을 중심점이라 ML이 '거주지 분포'를 학습할 위험이 크다.",
            "격자 838개·양성 54개로 표본이 작다 — 추정 분산이 크다.",
            "단일 이벤트라 이벤트 간 일반화는 검증하지 못했다.",
            "채택되더라도 module_a에는 기본 비활성으로 배포한다(명시적 opt-in).",
        ],
    }
    (OUT / "ml_residual_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n저장: {OUT/'ml_feature_table.csv'}")
    print(f"      {OUT/'ml_residual_summary.json'}")


if __name__ == "__main__":
    main()
