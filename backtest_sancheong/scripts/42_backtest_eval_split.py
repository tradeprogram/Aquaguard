"""
42_backtest_eval_split.py  (bt-eval: 공간분할 검증 — AUPRC / spatial CV)

무엇을 분할하는가에 대한 주의부터:
  이 모형은 **학습하지 않는다**. FoS는 문헌 지반정수로 계산하는 물리식이고
  적합할 계수가 없다. 따라서 여기서 분할은 '훈련/시험'이 아니라
  **"이 예측력이 특정 읍면 하나가 만든 착시인가, 지역을 바꿔도 남는가"**를 보는
  일반화 점검이다. 학습 누수는 원천적으로 없다.

설계:
  단위   1km 격자(산청 경계 내). 리 중심점보다 균질하고 음성(negative)이 정의된다.
  점수   격자 내 급사면 중 FoS<1 비율 (시나리오 B_weathered, observed 산불, 피크습윤)
  라벨   그 격자 안에 2025년 산사태 기록 리(里) 중심점이 있으면 1, 없으면 0
  지표   AUPRC(주지표, 불균형 대응) + ROC-AUC + 무작위기저(=양성비율)

  분할 3종
    (a) 전체      분할 없음 — 낙관적 상한
    (b) 무작위 5-fold   공간자기상관 때문에 여전히 낙관적(참고용)
    (c) 읍면 leave-one-out   ← 정직한 지표. 한 읍면을 통째로 빼고 평가

  이벤트 분할(2023 vs 2025)은 2023 기록이 2건뿐이라 통계적으로 성립하지 않는다.
  시도하고 그 사실을 수치로 남긴다(숨기지 않는다).

정직: 양성 라벨은 '발생부'가 아니라 '피해 집계 마을(리) 중심점'이다. 40번에서
확인했듯 이 참값은 거주지 분포를 따라가므로 급사면 물리와 계통적으로 어긋난다.
따라서 낮은 AUPRC는 모형 실패와 참값 부적합이 섞인 값이며 분리할 수 없다.
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
from sklearn.metrics import average_precision_score, roc_auc_score

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(r"G:/연구/공모전/아쿠아가드")
FOS = ROOT / "data" / "sancheong_fos"
OUT = ROOT / "outputs"

GW = 9.81
CR_HEALTHY = 3.0
WMAX = 0.85
SLOPE_MIN = 15.0
CELL_M = 1000.0
MIN_STEEP_PX = 200   # 급사면이 거의 없는 격자는 산사태 가능성이 없어 평가에서 뺀다


def _read(path: Path):
    with rasterio.open(path) as ds:
        return ds.read(1).astype("float32"), ds.transform, ds.crs, (ds.height, ds.width)


def crit_mask() -> tuple[np.ndarray, np.ndarray, object, object, tuple]:
    """피크 습윤에서의 FoS<1 마스크 (시나리오 B_weathered, observed 산불)."""
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
    del dnbr, f

    beta = np.deg2rad(np.clip(slope, 0.1, 89.0))
    cosb, sinb = np.cos(beta), np.sin(beta)
    c, phi, gam = 2.0, np.deg2rad(36.0), 19.0
    m = np.clip(m0 + WMAX, 0, 1)
    fos = (c + cr_eff + (gam - m * GW) * z * cosb ** 2 * np.tan(phi)) / (gam * z * sinb * cosb)
    crit = steep & np.isfinite(fos) & (fos < 1.0)
    del slope, z, m0, cr_eff, beta, cosb, sinb, m, fos
    return steep, crit, tr, crs, shape


def build_grid(crs, em: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    minx, miny, maxx, maxy = em.total_bounds
    xs = np.arange(minx, maxx, CELL_M)
    ys = np.arange(miny, maxy, CELL_M)
    cells = [box(x, y, x + CELL_M, y + CELL_M) for x in xs for y in ys]
    g = gpd.GeoDataFrame(geometry=cells, crs=crs)
    # 산청 경계에 실제로 걸치는 격자만
    g = gpd.sjoin(g, em[["name", "geometry"]], how="inner", predicate="intersects")
    # sjoin이 남기는 index_right 는 뒤의 두 번째 sjoin에서 이름 충돌을 일으킨다
    g = g.drop(columns=[c for c in ("index_right", "index_left") if c in g.columns])
    g = g.drop_duplicates(subset="geometry").reset_index(drop=True)
    return g.rename(columns={"name": "읍면"})


def metrics(y: np.ndarray, s: np.ndarray) -> dict:
    """양성/음성이 모두 있어야 지표가 정의된다. 아니면 정직하게 None."""
    if y.sum() == 0 or y.sum() == len(y):
        return {"n": int(len(y)), "양성": int(y.sum()), "AUPRC": None,
                "ROC_AUC": None, "기저": None, "lift": None}
    base = float(y.mean())
    ap = float(average_precision_score(y, s))
    return {
        "n": int(len(y)), "양성": int(y.sum()),
        "AUPRC": round(ap, 4),
        "ROC_AUC": round(float(roc_auc_score(y, s)), 4),
        "기저": round(base, 4),
        "lift": round(ap / base, 2) if base > 0 else None,
    }


def main() -> None:
    print("래스터 적재 중...")
    steep, crit, tr, crs, shape = crit_mask()
    print(f"급사면 {int(steep.sum()):,}px, 피크습윤 임계초과 {int(crit.sum()):,}px "
          f"({100*crit.sum()/max(steep.sum(),1):.3f}%)")

    em = gpd.read_file(ROOT / "data/vector/adm_dong_5179.geojson")
    em = em[em["sggnm"].astype(str).str.contains("산청")].reset_index(drop=True).to_crs(crs)

    grid = build_grid(crs, em)
    print(f"1km 격자: {len(grid)}개")

    zones = rasterize(((g, i + 1) for i, g in enumerate(grid.geometry)),
                      out_shape=shape, transform=tr, fill=0, dtype="int32")

    # 격자별 점수
    n_steep = np.bincount(zones[steep], minlength=len(grid) + 1)[1:]
    n_crit = np.bincount(zones[steep & crit], minlength=len(grid) + 1)[1:]
    grid["급사면px"] = n_steep
    grid["임계px"] = n_crit
    grid["점수"] = np.where(n_steep > 0, n_crit / np.maximum(n_steep, 1), 0.0)

    # 라벨: 2025 산사태 리 중심점 포함 여부
    ri = pd.read_csv(OUT / "sancheong_ri_validation.csv")
    pts = gpd.GeoDataFrame(ri, geometry=[Point(xy) for xy in zip(ri["lon"], ri["lat"])],
                           crs="EPSG:4326").to_crs(crs)
    joined = gpd.sjoin(grid.reset_index().rename(columns={"index": "cell"}),
                       pts[["건수", "geometry"]], how="left", predicate="contains")
    hits = joined.groupby("cell")["건수"].sum().fillna(0)
    grid["산사태건수"] = hits.reindex(range(len(grid)), fill_value=0).to_numpy()
    grid["y"] = (grid["산사태건수"] > 0).astype(int)

    # 급사면이 거의 없는 격자는 평가대상 아님
    ev = grid[grid["급사면px"] >= MIN_STEEP_PX].reset_index(drop=True)
    print(f"평가격자(급사면≥{MIN_STEEP_PX}px): {len(ev)}개, 양성 {int(ev['y'].sum())}개 "
          f"(양성비율 {100*ev['y'].mean():.1f}%)")

    y = ev["y"].to_numpy(int)
    s = ev["점수"].to_numpy(float)

    results = {"a_전체": metrics(y, s)}
    print(f"\n(a) 전체(낙관적 상한): {results['a_전체']}")

    # (b) 무작위 5-fold
    rng = np.random.default_rng(42)
    fold = rng.permutation(len(ev)) % 5
    rnd = [metrics(y[fold == k], s[fold == k]) for k in range(5)]
    aps = [r["AUPRC"] for r in rnd if r["AUPRC"] is not None]
    results["b_무작위5fold"] = {
        "fold별": rnd,
        "AUPRC_평균": round(float(np.mean(aps)), 4) if aps else None,
        "AUPRC_표준편차": round(float(np.std(aps)), 4) if aps else None,
        "주의": "공간자기상관으로 낙관 편향. 참고용.",
    }
    print(f"(b) 무작위 5-fold AUPRC 평균: {results['b_무작위5fold']['AUPRC_평균']} "
          f"± {results['b_무작위5fold']['AUPRC_표준편차']}")

    # (c) 읍면 leave-one-out  ← 정직한 지표
    print("\n(c) 읍면 leave-one-out (한 읍면 통째로 hold-out):")
    loo = []
    for nm in sorted(ev["읍면"].unique()):
        mask = (ev["읍면"] == nm).to_numpy()
        m = metrics(y[mask], s[mask])
        m["읍면"] = nm
        loo.append(m)
        print(f"   {nm:6s} n={m['n']:4d} 양성={m['양성']:3d} "
              f"AUPRC={m['AUPRC']}  lift={m['lift']}")
    aps_loo = [m["AUPRC"] for m in loo if m["AUPRC"] is not None]
    lifts = [m["lift"] for m in loo if m["lift"] is not None]
    results["c_읍면LOO"] = {
        "읍면별": loo,
        "평가가능_읍면수": len(aps_loo),
        "AUPRC_중앙값": round(float(np.median(aps_loo)), 4) if aps_loo else None,
        "AUPRC_범위": [round(float(min(aps_loo)), 4), round(float(max(aps_loo)), 4)] if aps_loo else None,
        "lift_중앙값": round(float(np.median(lifts)), 2) if lifts else None,
        "lift_1초과_읍면수": int(sum(1 for l in lifts if l > 1.0)),
    }
    print(f"   → AUPRC 중앙값 {results['c_읍면LOO']['AUPRC_중앙값']}, "
          f"lift>1 인 읍면 {results['c_읍면LOO']['lift_1초과_읍면수']}/{len(lifts)}")

    # (d) 이벤트 분할 시도 — 2023 표본이 몇 건인지 수치로 남긴다
    inv = pd.read_excel(ROOT / "data" / "산청_산사태.xlsx")
    n23, n25 = int((inv["연도"] == 2023).sum()), int((inv["연도"] == 2025).sum())
    results["d_이벤트분할"] = {
        "2023_건수": n23, "2025_건수": n25,
        "성립여부": False,
        "사유": f"2023년 기록이 {n23}건뿐이라 AUPRC 추정이 불가능하다(양성 격자 "
              f"1~2개). 이벤트 간 일반화는 다른 시군 이벤트를 확보해야 평가 가능.",
    }
    print(f"\n(d) 이벤트 분할: 2023 {n23}건 / 2025 {n25}건 → 통계적으로 성립하지 않음")

    ev[["읍면", "급사면px", "임계px", "점수", "산사태건수", "y"]].to_csv(
        OUT / "backtest_eval_grid.csv", index=False, encoding="utf-8-sig")

    summary = {
        "item": "bt-eval",
        "생성": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"),
        "설계": {
            "단위": f"{CELL_M:.0f}m 격자", "평가격자수": int(len(ev)),
            "점수": "격자 내 급사면 중 FoS<1 비율(B_weathered·observed·피크습윤)",
            "라벨": "격자 내 2025 산사태 기록 리(里) 중심점 존재 여부",
            "제외": f"급사면 < {MIN_STEEP_PX}px 격자",
            "학습없음": "물리모형이라 적합 계수가 없다 — 분할은 일반화 점검용이지 "
                    "훈련/시험 분리가 아니다.",
        },
        "결과": results,
        "한계": [
            "양성 라벨이 발생부가 아니라 피해 집계 마을 중심점 — 계통 편향(40번 참조).",
            "따라서 낮은 AUPRC에는 모형 오차와 참값 부적합이 섞여 있고 분리 불가.",
            "단일 이벤트(2025-07)라 이벤트 간 일반화는 미검증.",
            "1km 격자 크기는 임의 선택 — 리 중심점 근사와 맞춘 값.",
        ],
    }
    (OUT / "backtest_eval_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n저장: {OUT/'backtest_eval_grid.csv'}")
    print(f"      {OUT/'backtest_eval_summary.json'}")


if __name__ == "__main__":
    main()
