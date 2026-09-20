"""
40_fire_landslide_overlap.py  (bt-overlap: 산불흉터 × 산사태 사면 GIS 중첩검증)

질문: "실제로 불탄 사면에서 산사태가 더 많이 났는가?"
39번(bt-abl)은 *모형 안에서* 산불을 빼봤다. 여기서는 모형을 거치지 않고
**관측 대 관측**으로 본다 — dNBR 흉터와 실제 산사태 발생기록의 공간 중첩.

두 해상도로 본다(둘 다 좌표 한계가 있어 서로를 보완한다):
  읍면(10개)  경계가 정확. 단위가 커서 희석(dilution)이 심함.
  리(55개)    21번이 지오코딩한 중심점 + 반경 버퍼. 단위가 작지만 중심점 근사.

검정:
  Spearman ρ   산불비율 순위 vs 산사태밀도 순위
  Mann-Whitney 산불영향 구역 vs 비영향 구역의 밀도 분포 차이(비모수, n작음)
  중첩률       산사태 구역이 흉터와 겹치는 비율 vs 전체 급사면의 흉터 비율(기대값)

정직(치명적 한계 먼저):
  - 산사태 기록 362건은 **피해가 집계된 마을 위치**(리 단위)이지 발생부 좌표가
    아니다. 발생부는 급사면, 피해는 계곡·거주지 — 계통 편향이 있다.
  - 따라서 여기 상관은 '산불이 산사태를 일으켰다'의 인과 증거가 아니라
    '흉터와 피해가 같은 유역에 몰려 있다'는 공간 연관에 불과하다.
  - 교란변수(경사·강우·지질)를 통제하지 않았다. 급사면 비율은 함께 보고한다.
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
from scipy.stats import mannwhitneyu, spearmanr
from shapely.geometry import Point

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(r"G:/연구/공모전/아쿠아가드")
FOS = ROOT / "data" / "sancheong_fos"
OUT = ROOT / "outputs"

SLOPE_MIN = 15.0      # 산사태 가능사면
DNBR_BURN = 0.10      # Key&Benson low 이상 = '영향 있음'
DNBR_MOD = 0.27       # moderate 이상
BUF_M = 1500.0        # 리 중심점 버퍼(21번과 동일)


def _read(path: Path):
    with rasterio.open(path) as ds:
        return ds.read(1).astype("float32"), ds.transform, ds.crs, (ds.height, ds.width)


def zonal(zones: np.ndarray, zid: int, steep: np.ndarray,
          burn: np.ndarray, burn_mod: np.ndarray) -> dict:
    """구역 하나의 급사면·흉터 픽셀 수. 분모는 항상 '급사면'이다 —
    평지까지 넣으면 산사태와 무관한 면적이 비율을 희석한다."""
    z = zones == zid
    n_steep = int((z & steep).sum())
    if n_steep == 0:
        return {"급사면px": 0, "흉터급사면px": 0, "산불비율_%": 0.0, "중등이상_%": 0.0}
    n_burn = int((z & steep & burn).sum())
    n_mod = int((z & steep & burn_mod).sum())
    return {
        "급사면px": n_steep,
        "흉터급사면px": n_burn,
        "산불비율_%": round(100.0 * n_burn / n_steep, 3),
        "중등이상_%": round(100.0 * n_mod / n_steep, 3),
    }


def report(df: pd.DataFrame, label: str, dens_col: str) -> dict:
    """상관·군간차이 검정 한 세트."""
    x, y = df["산불비율_%"].to_numpy(float), df[dens_col].to_numpy(float)
    rho, p_rho = spearmanr(x, y)

    hit = df[df["산불비율_%"] > 0][dens_col].to_numpy(float)
    nohit = df[df["산불비율_%"] == 0][dens_col].to_numpy(float)
    if len(hit) >= 3 and len(nohit) >= 3:
        u, p_u = mannwhitneyu(hit, nohit, alternative="greater")
        mw = {"n_산불": int(len(hit)), "n_비산불": int(len(nohit)),
              "중앙값_산불": round(float(np.median(hit)), 4),
              "중앙값_비산불": round(float(np.median(nohit)), 4),
              "U": float(u), "p": round(float(p_u), 4)}
    else:
        mw = {"사유": f"표본부족(산불 {len(hit)} / 비산불 {len(nohit)}) → 검정 생략"}

    res = {
        "단위": label, "n": int(len(df)),
        "spearman_rho": round(float(rho), 3),
        "spearman_p": round(float(p_rho), 4),
        "유의": bool(p_rho < 0.05),
        "mannwhitney": mw,
    }
    print(f"\n[{label}] n={len(df)}  Spearman ρ={rho:.3f} (p={p_rho:.4f})"
          f"{'  ✱유의' if p_rho < 0.05 else '  (유의하지 않음)'}")
    if "p" in mw:
        print(f"    Mann-Whitney 산불>비산불: U={mw['U']:.0f} p={mw['p']:.4f} "
              f"(중앙값 {mw['중앙값_산불']} vs {mw['중앙값_비산불']})")
    else:
        print(f"    Mann-Whitney: {mw['사유']}")
    return res


def _verdict(res_em, res_ri_cnt, res_ri_den, enrich) -> dict:
    """검정 결과를 있는 그대로 한 줄 결론으로 굳힌다. 유리하게 각색하지 않는다."""
    results = [res_em, res_ri_cnt, res_ri_den]
    any_sig = bool(any(r["유의"] for r in results))
    # numpy 스칼라 비교는 np.bool_ 을 낸다 — json 직렬화 안 되므로 파이썬 bool 로.
    enriched = bool(enrich is not None and enrich > 1.0)
    if any_sig and enriched:
        판정 = "지지: 흉터와 산사태 피해가 유의하게 공간 연관됨"
    elif any_sig:
        판정 = "부분: 일부 척도에서만 유의 — 결론 유보"
    else:
        판정 = "불지지: 이 참값으로는 산불-산사태 공간 연관을 확인하지 못함"
    return {
        "판정": 판정,
        "유의한_검정_있음": any_sig,
        "농축배수_1초과": enriched,
        "해석": "이 결과는 산불 증폭 물리(Key&Benson 등급 × 뿌리점착력 감소)를 "
              "반증하지 않는다. 참값이 발생부가 아니라 '피해 집계 마을'이라 "
              "급사면 흉터와 계통적으로 어긋나 있기 때문이다. 즉 검정력이 없는 "
              "참값이지 물리가 틀렸다는 증거가 아니다. 발생부 좌표(산림청 요청 중)가 "
              "확보되면 같은 스크립트로 재검정하면 된다.",
        "반례_예시": "단성면은 산사태 99건(최다)인데 흉터 3.6%, 금서면은 흉터 4.8%인데 "
                 "산사태 0건 — 피해기록이 거주지 분포를 따라간다는 방증.",
    }

def main() -> None:
    print("래스터 적재 중...")
    slope, tr, crs, shape = _read(ROOT / "data" / "dem" / "산청_slope_5m_5179.tif")
    dnbr, _, _, _ = _read(FOS / "dnbr.tif")

    steep = np.isfinite(slope) & (slope >= SLOPE_MIN)
    burn = np.isfinite(dnbr) & (dnbr >= DNBR_BURN)
    burn_mod = np.isfinite(dnbr) & (dnbr >= DNBR_MOD)
    del slope, dnbr

    base_rate = 100.0 * (steep & burn).sum() / max(steep.sum(), 1)
    print(f"산청 전체 급사면 {int(steep.sum()):,}px 중 흉터 {int((steep&burn).sum()):,}px "
          f"= 기저 산불비율 {base_rate:.3f}%")

    inv = pd.read_excel(ROOT / "data" / "산청_산사태.xlsx")
    inv = inv[inv["연도"] == 2025]

    # ---------- 읍면 ----------
    em = gpd.read_file(ROOT / "data/vector/adm_dong_5179.geojson")
    em = em[em["sggnm"].astype(str).str.contains("산청")].reset_index(drop=True).to_crs(crs)
    em["area_km2"] = em.geometry.area / 1e6
    zones = rasterize(((g, i + 1) for i, g in enumerate(em.geometry)),
                      out_shape=shape, transform=tr, fill=0, dtype="int16")

    cnt = inv.groupby("상세주소_읍면도").size().rename("산사태건수")
    rows = []
    for i, nm in enumerate(em["name"]):
        r = {"읍면": nm, **zonal(zones, i + 1, steep, burn, burn_mod)}
        r["산사태건수"] = int(cnt.get(nm, 0))
        r["area_km2"] = round(float(em.loc[i, "area_km2"]), 2)
        r["발생밀도_건perkm2"] = round(r["산사태건수"] / max(r["area_km2"], 1e-9), 3)
        rows.append(r)
    em_df = pd.DataFrame(rows).sort_values("산불비율_%", ascending=False)
    em_df.to_csv(OUT / "overlap_eupmyeon.csv", index=False, encoding="utf-8-sig")
    print("\n=== 읍면 중첩 ===")
    print(em_df.to_string(index=False))
    res_em = report(em_df, "읍면(경계정확·희석큼)", "발생밀도_건perkm2")

    # ---------- 리 ----------
    ri = pd.read_csv(OUT / "sancheong_ri_validation.csv")
    pts = gpd.GeoDataFrame(
        ri, geometry=[Point(xy) for xy in zip(ri["lon"], ri["lat"])], crs="EPSG:4326"
    ).to_crs(crs)
    bufs = pts.geometry.buffer(BUF_M)
    zones_ri = rasterize(((g, i + 1) for i, g in enumerate(bufs)),
                         out_shape=shape, transform=tr, fill=0, dtype="int32")

    rows = []
    for i in range(len(ri)):
        r = {"읍면": ri.loc[i, "상세주소_읍면도"], "리": ri.loc[i, "상세주소_리"],
             **zonal(zones_ri, i + 1, steep, burn, burn_mod)}
        r["산사태건수"] = int(ri.loc[i, "건수"])
        # 버퍼 면적이 같으므로 건수 자체가 곧 밀도. 급사면수로 한 번 더 정규화해 본다.
        r["건수per급사면Mpx"] = round(r["산사태건수"] / max(r["급사면px"], 1) * 1e6, 3)
        rows.append(r)
    ri_df = pd.DataFrame(rows).sort_values("산불비율_%", ascending=False)
    ri_df.to_csv(OUT / "overlap_ri.csv", index=False, encoding="utf-8-sig")
    print(f"\n=== 리 중첩 (반경 {BUF_M:.0f}m 버퍼, 상위 12개) ===")
    print(ri_df.head(12).to_string(index=False))
    res_ri_cnt = report(ri_df, f"리(버퍼{BUF_M:.0f}m)·건수", "산사태건수")
    res_ri_den = report(ri_df, f"리(버퍼{BUF_M:.0f}m)·급사면정규화", "건수per급사면Mpx")

    # ---------- 중첩률 vs 기대값 ----------
    # 산사태 건수로 가중한 '평균 산불노출'을 전체 급사면 기저율과 비교한다.
    w = ri_df["산사태건수"].to_numpy(float)
    exposure = float(np.average(ri_df["산불비율_%"].to_numpy(float), weights=w))
    enrich = exposure / base_rate if base_rate > 0 else None
    print(f"\n=== 노출 대비 농축 ===")
    print(f"  산사태 가중 평균 산불노출 : {exposure:.3f}%")
    print(f"  전체 급사면 기저 산불비율 : {base_rate:.3f}%")
    print(f"  농축배수(enrichment)      : {enrich:.2f}×"
          if enrich else "  농축배수: 계산불가")

    summary = {
        "item": "bt-overlap",
        "생성": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"),
        "정의": {
            "급사면": f"slope ≥ {SLOPE_MIN}°",
            "흉터": f"dNBR ≥ {DNBR_BURN} (Key&Benson low 이상)",
            "분모": "구역 내 급사면 픽셀(평지 제외 — 희석 방지)",
            "리버퍼_m": BUF_M,
        },
        "기저_산불비율_%": round(base_rate, 3),
        "산사태가중_산불노출_%": round(exposure, 3),
        "농축배수": None if enrich is None else round(enrich, 2),
        "검정": {"읍면": res_em, "리_건수": res_ri_cnt, "리_정규화": res_ri_den},
        "결론": _verdict(res_em, res_ri_cnt, res_ri_den, enrich),
        "한계": [
            "362건은 발생부(source) 좌표가 아니라 피해 집계 마을(리) 위치 — 계통 편향.",
            "리 좌표는 지오코딩 중심점 + 반경버퍼 근사이며 실제 피해 범위가 아니다.",
            "경사·강우·지질 등 교란변수를 통제하지 않은 단변량 연관 분석이다.",
            "따라서 인과가 아니라 공간 연관으로만 해석할 것.",
        ],
    }
    (OUT / "overlap_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("")
    print("=== 결론 ===")
    print("  " + summary["결론"]["판정"])
    print(f"  {summary['결론']['반례_예시']}")
    print(f"\n저장: {OUT/'overlap_eupmyeon.csv'}, {OUT/'overlap_ri.csv'}, "
          f"{OUT/'overlap_summary.json'}")


if __name__ == "__main__":
    main()
