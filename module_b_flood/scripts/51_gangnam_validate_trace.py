"""
51_gangnam_validate_trace.py — 강남 침수모형을 **서울시 침수흔적도**로 검증

여기까지 강남 모형은 "미검증"이었다. 산청은 경호교 수위계로 RMSE 1.42m 를 냈는데
강남에는 대응하는 참값이 없었다. 그 칸을 채운다.

참값
  서울시 침수흔적도 (서울 열린데이터광장 OA-15636, 공공누리 1유형)
  파일: "2022년 침수흔적도_260105 수정.zip" (3.65MB, EPSG:5179)
  https://data.seoul.go.kr/dataList/OA-15636/F/1/datasetView.do

  주요 컬럼
    GU_NAM     자치구
    F_SHIM     침수심(m)  ← 실측
    F_AREA     침수면적(m²)
    F_DISA_NM  재해명 ("2022년 8.8.~17. 호우" 등)
    F_RSN_DTL  침수 원인 ("배수용량초과", "침수(도로범람유입)", "공공하수도역류" …)
    TYPE       대상 (주택/상가/농경지/도로)

★ 이 자료의 성격 — 결과를 읽기 전에 반드시 알아야 한다
  침수흔적도는 **피해 신고·재난지원금 대상 인벤토리**다. 강남구 682건 중 주택이
  459건이다. 즉 "물이 30cm 이상 찼던 모든 땅"이 아니라 "피해가 접수된 필지"다.
  따라서
    · 관측 면적(58.3ha)은 실제 침수면적의 **하한**이다. 도로·공원·무피해 구역은
      빠져 있다. 그래서 모형 면적이 관측보다 크다고 곧바로 과대추정은 아니다.
    · 반대로 **적중률(관측 지점을 모형이 잡았는가)** 은 유효하다. 그 필지들은
      분명히 잠겼기 때문이다. 놓쳤다면 그건 진짜 놓친 것이다.
    · 오경보(FP)는 이 자료로 셀 수 없다. "마른 것이 확인된 땅" 목록이 아니다.
  그래서 IoU 는 참고값으로만 적고, 판단은 적중률과 침수심 분포로 한다.

출력
  outputs/gangnam_validation.json
  outputs/gangnam_trace2022_gangnam.geojson   강남구 부분만 잘라낸 참값(재배포 가능)

사용
  python scripts/51_gangnam_validate_trace.py [침수흔적도.shp 경로]
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
from rasterio.features import rasterize

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(r"G:/연구/공모전/아쿠아가드")
OUT = ROOT / "outputs"
BUILD = Path(r"C:/Users/user/AppData/Local/Temp/claude/aquaguard_work/sfincs_gangnam")
TRACE = Path(r"C:/Users/user/AppData/Local/Temp/claude/aquaguard_work/trace2022/trace2022.shp")
GU = "강남구"
DRAINS = (30, 50, 75)
THR_M = 0.3            # 모형 침수 판정 기준. 49번 폴리곤과 같은 값
SOURCE = ("서울시 침수흔적도 2022 (서울 열린데이터광장 OA-15636, 공공누리 1유형), "
          "파일 '2022년 침수흔적도_260105 수정.zip'")


# 원본 dbf 는 .cpg 가 949 인데 일부 행만 UTF-8 바이트로 기록돼 있다. GDAL 이 그
# 행을 cp949 로 디코드하면서 매핑 안 되는 바이트를 '?' 로 바꿔 버려, 읽은 뒤에는
# 재인코딩으로 되돌릴 수 없다(.cpg 를 바꿔 다시 읽어도 같다).
# 라벨 자체는 확실하다 — 서울 전체 집계에서 다른 자치구는 '배수용량초과' 로 정상
# 출력되고, 깨진 문자열의 바이트열도 그것과 일치한다. 그래서 확인된 것만 치환한다.
MOJIBAKE = {
    "諛곗닔?⑸웾珥덇낵": "배수용량초과",
}


def fix_mojibake(s):
    return MOJIBAKE.get(s, s) if isinstance(s, str) else s


def load_pp():
    import importlib.util

    p = Path(__file__).resolve().parent / "49_gangnam_postprocess.py"
    spec = importlib.util.spec_from_file_location("pp49", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def main(shp: Path) -> None:
    pp = load_pp()
    obs = gpd.read_file(shp)
    gn = obs[obs["GU_NAM"].astype(str).str.strip() == GU].copy().to_crs(5179)
    for c in ("F_RSN_DTL", "F_DISA_NM", "TYPE", "F_ZONE_NM"):
        if c in gn.columns:
            gn[c] = gn[c].map(fix_mojibake)
    gn["F_SHIM"] = pd.to_numeric(gn["F_SHIM"], errors="coerce")
    obs_area_ha = float(gn.geometry.area.sum() / 1e4)
    shim = gn["F_SHIM"].dropna()
    print(f"참값 {GU} {len(gn):,}건  기하면적 {obs_area_ha:.1f}ha")
    print(f"  실측 침수심  중앙 {shim.median():.2f}m  p90 {shim.quantile(.9):.2f}m  "
          f"최대 {shim.max():.2f}m")
    reason = gn["F_RSN_DTL"].value_counts().head(6).to_dict()
    print("  침수 원인 상위: " + ", ".join(f"{k} {v}" for k, v in list(reason.items())[:4]))

    OUT.mkdir(exist_ok=True)
    keep = ["GU_NAM", "F_SHIM", "F_AREA", "F_DISA_NM", "F_RSN_DTL", "TYPE",
            "F_SAT_YMD", "geometry"]
    gn[[c for c in keep if c in gn.columns]].to_file(
        OUT / "gangnam_trace2022_gangnam.geojson", driver="GeoJSON")

    cases = []
    for d in DRAINS:
        rd = BUILD / f"drain{d}"
        if not (rd / "sfincs_map.nc").exists():
            print(f"[건너뜀] drain{d}")
            continue
        dep, dep_aoi, tr, res5, inp, n_water, aoi_ha = pp.depth_5m(rd)
        H, W = dep.shape
        cell = res5 * res5

        om = rasterize([(g, 1) for g in gn.geometry], out_shape=(H, W),
                       transform=tr, dtype="uint8") == 1
        mm = np.isfinite(dep_aoi) & (dep_aoi >= THR_M)
        tp, fn, fp = int((om & mm).sum()), int((om & ~mm).sum()), int((~om & mm).sum())
        iou = tp / max(tp + fn + fp, 1)

        # 관측 필지별 적중 — 필지 안 최대 모의 침수심이 기준 이상인가
        lab = rasterize([(g, i + 1) for i, g in enumerate(gn.geometry)],
                        out_shape=(H, W), transform=tr, dtype="int32")
        dmod, obsd = [], []
        for i, (_, row) in enumerate(gn.iterrows(), start=1):
            s = lab == i
            if not s.any():
                continue                      # 5m 격자보다 작아 래스터에 안 걸린 필지
            v = dep_aoi[s]
            dmod.append(float(np.nanmax(v)) if np.isfinite(v).any() else 0.0)
            obsd.append(row["F_SHIM"])
        dmod, obsd = np.array(dmod), np.array(obsd, dtype="float64")
        hit = int((dmod >= THR_M).sum())
        ok = np.isfinite(obsd) & (dmod > 0)
        bias = float(np.median(dmod[ok] - obsd[ok])) if ok.any() else None

        cases.append({
            "배수상수_mm_h": inp["배수상수_mm_h"],
            "모의_0.3m이상_면적_ha": round(float(mm.sum() * cell / 1e4), 2),
            "관측_래스터화_면적_ha": round(float(om.sum() * cell / 1e4), 2),
            "면적비_모의대관측": round(float(mm.sum() / max(om.sum(), 1)), 2),
            "화소_IoU": round(iou, 4),
            "TP_ha": round(tp * cell / 1e4, 2), "FN_ha": round(fn * cell / 1e4, 2),
            "관측필지수": int(len(dmod)), "적중필지수": hit,
            "적중률": round(hit / max(len(dmod), 1), 3),
            "모의침수심_중앙_m": round(float(np.median(dmod)), 3),
            "모의침수심_최대_m": round(float(dmod.max()), 3),
            "실측침수심_중앙_m": round(float(np.nanmedian(obsd)), 3),
            "실측침수심_최대_m": round(float(np.nanmax(obsd)), 3),
            "편의_모의빼기실측_중앙_m": None if bias is None else round(bias, 3),
        })
        c = cases[-1]
        print(f"\nqinf {d:>2} mm/h")
        print(f"  면적   모의 {c['모의_0.3m이상_면적_ha']:>7.1f}ha / 관측 "
              f"{c['관측_래스터화_면적_ha']:.1f}ha = {c['면적비_모의대관측']:.1f}배   IoU {c['화소_IoU']:.3f}")
        print(f"  적중   {hit}/{len(dmod)} = {100*hit/max(len(dmod),1):.0f}%   "
              f"(관측 필지 중 모형이 {THR_M}m 이상으로 잡은 비율)")
        print(f"  침수심 모의 중앙 {c['모의침수심_중앙_m']:.2f}m / 실측 중앙 "
              f"{c['실측침수심_중앙_m']:.2f}m,  모의 최대 {c['모의침수심_최대_m']:.2f}m / "
              f"실측 최대 {c['실측침수심_최대_m']:.2f}m")

    best = max(cases, key=lambda r: r["적중률"]) if cases else None
    verdict = [
        "IoU 0.04 수준이다. **지표 기반 모형이 2022-08-08 강남구 침수를 공간적으로 "
        "재현하지 못한다.** 강남역 한 지점의 문제가 아니라 전반적이다.",
        "적중률이 가장 좋은 경우도 3곳 중 1곳이다. 실제로 잠긴 필지의 2/3 를 놓친다.",
        "관측 침수 원인 1·2위가 '배수용량초과'와 '도로범람유입'이다 — 지형 저류가 "
        "아니라 관망 용량이 결정한 침수라는 뜻이고, 우리 모형에 없는 바로 그 과정이다.",
        "배수율을 높이면(qinf 75) 총면적은 관측과 맞아 보이지만(1.0배) 적중률은 12% 로 "
        "떨어진다. **면적이 우연히 맞는 것이지 맞는 곳에 물이 있는 게 아니다.** "
        "면적 일치를 근거로 배수율을 고르면 안 된다.",
        "실측 침수심은 중앙 0.20m·최대 0.60m 로 얕고 넓게 퍼져 있다. 우리 모형은 "
        "좁고 깊게(폐합 저지) 고인다. 분포 모양 자체가 다르다.",
        "결론: 현재 강남 모형은 '지형상 물이 고이기 쉬운 곳' 정도로만 읽어야 하고, "
        "필지 단위 침수 예측에 쓸 수 없다. 쓰려면 관망(집중형 관망 또는 SWMM 결합)을 "
        "넣어야 한다.",
    ]
    print("\n".join(["", "판정"] + [f"  - {v}" for v in verdict]))

    (OUT / "gangnam_validation.json").write_text(json.dumps({
        "생성": __import__("datetime").datetime.now().isoformat(timespec="minutes"),
        "대상": f"서울 {GU} 2022-08-08 집중호우",
        "참값": {"출처": SOURCE, "건수": int(len(gn)), "기하면적_ha": round(obs_area_ha, 2),
               "실측침수심_중앙_m": round(float(shim.median()), 3),
               "실측침수심_최대_m": round(float(shim.max()), 3),
               "침수원인_상위": reason,
               "대상유형": gn["TYPE"].value_counts().head(6).to_dict()},
        "판정기준_m": THR_M,
        "케이스": cases,
        "최고적중_배수율": None if best is None else best["배수상수_mm_h"],
        "자료성격_주의": [
            "침수흔적도는 피해 신고·재난지원금 대상 인벤토리다(강남구 682건 중 주택 459건).",
            "관측 면적은 실제 침수면적의 하한이다 — 도로·공원·무피해 구역은 빠져 있다.",
            "따라서 오경보(FP)는 이 자료로 셀 수 없고, IoU 는 참고값이다.",
            "적중률과 침수심 분포가 유효한 지표다.",
        ],
        "판정": verdict,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n저장: {OUT/'gangnam_validation.json'}")
    print(f"      {OUT/'gangnam_trace2022_gangnam.geojson'}  ({len(gn)}건)")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else TRACE)
