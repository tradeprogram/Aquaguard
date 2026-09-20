"""
45_risk_polygons_timeseries.py  — 산사태 위험 폴리곤 시계열 (risk_polygons 생성)

Module O 는 landslide_prob >= 0.7 일 때만 하류 모듈(D/E/G)을 돌리고, 그때
`risk_polygons[].geometry_5179` 를 넘긴다. 그런데 그 지오메트리가 지금까지
비어 있었다 — UI 주석(MapExplorer.tsx)에도 "risk_polygons 지오메트리가 없다"고
적혀 있고, 3D 시뮬레이터가 손으로 배치한 흐름 경로를 쓰고 있었다.

이 스크립트가 그 공백을 메운다. 산청 전역 5m 격자에 무한사면 FoS 를 실측 강우로
구동해서, **위험등급별 폴리곤 + 각 폴리곤이 임계에 도달한 시각**을 GeoJSON 으로 낸다.

핵심 계산 트릭 — 프레임마다 벡터화하지 않는다:
  FoS(m) = (C + A − m·B)/D  는 m 에 대해 선형이므로, 확률 임계 P 에 대응하는
  FoS 임계 F(P) = 1 + ln((1−P)/P)/k 를 넘는 조건은
        m ≥ (C + A − F·D)/B ≡ m_crit
  이고, m(t) = clip(m0 + rain_term(t), 0, 1) 이므로
        임계 도달 ⟺ rain_term(t) ≥ m_crit − m0 ≡ margin
  rain_term 의 누적최대(rt_max)는 단조증가라서, 픽셀별 **첫 도달 시각**은
  searchsorted(rt_max, margin) 한 번으로 전부 구해진다.
  → 47M 셀 × T 프레임 벡터화(느림)가 아니라, "도달시각 래스터" 1장을
     등급당 1회만 벡터화하면 끝난다. UI 는 arrival_hour 로 필터링해 애니메이션한다.

지반 시나리오 2종을 모두 낸다(백테스트와 동일한 정의):
  A_soilmap     토양도 토성 — Module A(soil_sampler)가 실제로 쓰는 값. **정합용 기본**
  B_weathered   풍화화강토(c'2·φ36·γ19, P3 부산실측) — 급사면 실제 파괴재료 가정

정직: Rsat·Wmax·시그모이드 k 는 미보정이다. 이 폴리곤은 "그날 그 사면이 이만큼
위험해졌다"는 물리 계산이지 검증된 예측이 아니다. 발생부 참값이 없어 공간정확도는
검증하지 못했다(backtest_sancheong/README.md §3·§4).
"""
from __future__ import annotations

import json
import math
import sys
import warnings

warnings.filterwarnings("ignore")
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from rasterio.features import shapes as rio_shapes
from shapely.geometry import mapping, shape
from shapely.ops import unary_union

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(r"G:/연구/공모전/아쿠아가드")
FOS = ROOT / "data" / "sancheong_fos"
OUT = ROOT / "outputs"

GW = 9.81
CR_HEALTHY = 3.0
RSAT = 200.0
WMAX = 0.85
SLOPE_MIN = 15.0
K_SIG = 6.0

# 확률 임계 → FoS 임계. P = 1/(1+exp(k(FoS−1))) 를 FoS 에 대해 푼 값.
LEVELS = {"warning": 0.5, "critical": 0.7}
SIMPLIFY_M = 5.0          # 5m 격자라 5m 단순화는 계단만 깎고 형상은 보존
MIN_AREA_M2 = 250.0       # 10셀 미만 파편 제거 — 3D 에서 점처럼 보이고 파일만 키운다


def fos_threshold(p: float) -> float:
    return 1.0 + math.log((1.0 - p) / p) / K_SIG


def _read(path: Path):
    with rasterio.open(path) as ds:
        return ds.read(1).astype("float32"), ds.transform, ds.crs


def rain_series() -> pd.DataFrame:
    r = pd.read_csv(ROOT / "data" / "kma" / "sancheong_asos_2025071819.csv",
                    parse_dates=["time_kst"]).sort_values("time_kst").reset_index(drop=True)
    r["cum24"] = r["rn_mm"].rolling(24, min_periods=1).sum()
    r["rain_term"] = np.minimum(WMAX, r["cum24"] / RSAT)
    return r


def margins(slope, z, m0, c, phi, gam, cr_eff, f_thr):
    """rain_term 이 이 값 이상이면 그 픽셀은 FoS ≤ f_thr (= prob ≥ P)."""
    beta = np.deg2rad(np.clip(slope, 0.1, 89.0))
    cosb, sinb = np.cos(beta), np.sin(beta)
    tanphi = np.tan(np.deg2rad(phi))
    C = c + cr_eff
    A = gam * z * cosb ** 2 * tanphi
    B = GW * z * cosb ** 2 * tanphi
    D = gam * z * sinb * cosb
    with np.errstate(divide="ignore", invalid="ignore"):
        m_crit = (C + A - f_thr * D) / B
    m_crit = np.where(B > 0, m_crit, np.inf)
    # m(t) = clip(m0 + rain_term, 0, 1) 이라 m 은 1 을 못 넘는다. m_crit > 1 인
    # 픽셀은 완전포화로도 그 FoS 에 도달하지 못하므로 '영영 미도달'로 밀어낸다.
    # (이 clip 을 빠뜨리면 m0 가 큰 배수불량 픽셀이 거짓 도달로 잡힌다 —
    #  A_soilmap critical 이 411 → 1,131 로 부풀었던 원인.)
    m_crit = np.where(m_crit > 1.0, np.inf, m_crit)
    return (m_crit - m0).astype("float32")


def arrival_raster(margin, valid, rt_max):
    """픽셀별 첫 도달 프레임 index(+1). 0 = 끝까지 미도달(= nodata)."""
    idx = np.searchsorted(rt_max, margin.ravel(), side="right").reshape(margin.shape)
    arr = np.where(valid & (idx < len(rt_max)), idx + 1, 0)
    return arr.astype("int16")


def vectorize(arr, transform, times):
    """도달시각 래스터 → 폴리곤. 같은 도달시각끼리 병합해 feature 수를 줄인다."""
    feats = []
    for hour_idx in np.unique(arr):
        if hour_idx == 0:
            continue
        mask = arr == hour_idx
        geoms = [shape(g) for g, v in rio_shapes(arr, mask=mask, transform=transform) if v == hour_idx]
        if not geoms:
            continue
        merged = unary_union(geoms)
        merged = merged.simplify(SIMPLIFY_M, preserve_topology=True)
        parts = [g for g in (merged.geoms if merged.geom_type == "MultiPolygon" else [merged])
                 if g.area >= MIN_AREA_M2]
        if not parts:
            continue
        geom = unary_union(parts)
        t = times[int(hour_idx) - 1]
        feats.append({
            "type": "Feature",
            "properties": {
                "arrival_hour": int(hour_idx) - 1,
                "arrival_time": t.strftime("%Y-%m-%dT%H:%M:%S+09:00"),
                "area_m2": round(float(geom.area), 1),
            },
            "geometry": json.loads(json.dumps(mapping(geom))),
        })
    return feats


def main() -> None:
    print("래스터 적재 중...")
    slope, tr, crs = _read(ROOT / "data" / "dem" / "산청_slope_5m_5179.tif")
    z, _, _ = _read(FOS / "z_m.tif")
    m0, _, _ = _read(FOS / "m0.tif")
    c, _, _ = _read(FOS / "c_kpa.tif")
    phi, _, _ = _read(FOS / "phi_deg.tif")
    gam, _, _ = _read(FOS / "gamma.tif")
    dnbr, _, _ = _read(FOS / "dnbr.tif")

    f = np.ones_like(dnbr)
    f[dnbr >= 0.10] = 1.2
    f[dnbr >= 0.27] = 2.0
    f[dnbr >= 0.44] = 3.75
    f[~np.isfinite(dnbr)] = 1.0
    cr_eff = CR_HEALTHY / f
    del dnbr, f

    valid = np.isfinite(slope) & (slope >= SLOPE_MIN) & np.isfinite(z) & np.isfinite(c)
    print(f"급사면(≥{SLOPE_MIN}°) 유효 픽셀: {int(valid.sum()):,}")

    rain = rain_series()
    rt = rain["rain_term"].to_numpy(float)
    rt_max = np.maximum.accumulate(rt)          # 단조증가 → searchsorted 가능
    times = list(rain["time_kst"])
    print(f"강우 프레임: {len(times)}개  {times[0]:%m-%d %H:%M} ~ {times[-1]:%m-%d %H:%M}")

    scenarios = {
        "A_soilmap": (c, phi, gam),
        "B_weathered": (np.float32(2.0), np.float32(36.0), np.float32(19.0)),
    }

    index = {"생성": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"), "layers": {}}
    for sname, (cc, pp, gg) in scenarios.items():
        for lname, p_thr in LEVELS.items():
            f_thr = fos_threshold(p_thr)
            mg = margins(slope, z, m0, cc, pp, gg, cr_eff, f_thr)
            arr = arrival_raster(mg, valid, rt_max)
            n_px = int((arr > 0).sum())
            print(f"  {sname:12s} {lname:8s} (P≥{p_thr}, FoS≤{f_thr:.3f}) "
                  f"도달 픽셀 {n_px:,} ({n_px*25/1e6:.3f} km²)", flush=True)
            if n_px == 0:
                continue
            feats = vectorize(arr, tr, times)
            fc = {
                "type": "FeatureCollection",
                "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::5179"}},
                "properties": {
                    "scenario": sname, "level": lname, "prob_threshold": p_thr,
                    "fos_threshold": round(f_thr, 4),
                    "note": "arrival_hour 로 필터링해 시계열 애니메이션. 미보정 파라미터 "
                            f"(Rsat={RSAT}, Wmax={WMAX}, k={K_SIG}).",
                },
                "features": feats,
            }
            fn = OUT / f"risk_landslide_{sname}_{lname}_5179.geojson"
            fn.write_text(json.dumps(fc, ensure_ascii=False), encoding="utf-8")
            size_kb = fn.stat().st_size / 1024
            print(f"       → {fn.name}  feature {len(feats)}개  {size_kb:.0f} KB")
            index["layers"][f"{sname}_{lname}"] = {
                "file": fn.name, "features": len(feats), "pixels": n_px,
                "area_km2": round(n_px * 25 / 1e6, 4), "size_kb": round(size_kb, 1),
                "prob_threshold": p_thr,
            }

    index["frames"] = [{"hour": i, "time": t.strftime("%Y-%m-%dT%H:%M:%S+09:00"),
                        "rn_mm": float(rain["rn_mm"][i]), "cum24_mm": round(float(rain["cum24"][i]), 1)}
                       for i, t in enumerate(times)]
    index["한계"] = [
        "Rsat=200mm · Wmax=0.85 · sigmoid k=6.0 은 미보정이다.",
        "발생부 참값이 없어 이 폴리곤의 공간정확도는 검증되지 않았다.",
        "A_soilmap 이 Module A(soil_sampler)와 정합하는 기본값이고, "
        "B_weathered 는 급사면 파괴재료 가정 시나리오다 — 섞어 쓰지 말 것.",
        "arrival_hour 는 '그 시각에 임계를 처음 넘었다'이지 '그 시각에 붕괴했다'가 아니다.",
    ]
    (OUT / "risk_landslide_index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n저장: {OUT/'risk_landslide_index.json'}")


if __name__ == "__main__":
    main()
