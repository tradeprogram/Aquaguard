"""module_b_flood.fim — 침수 범위 → GeoJSON FeatureCollection(EPSG:5179).

두 진입점:
1) raster_to_featurecollection: SFINCS/ANUGA 최대침수심 래스터 → 폴리곤(모형 실산출, b-out).
2) hand_fim_featurecollection: 예측 수위(WSE) + HAND/DEM → 침수 폴리곤(실시간 대리, HAND-FIM).

rasterio는 지연 import — 미설치/지형 미주입 시 run()이 빈 FC + warning으로 폴백(정직).
"""
from __future__ import annotations

from typing import Any


def _empty_fc() -> dict[str, Any]:
    return {"type": "FeatureCollection", "features": []}


# 침수심 구간 경계(m). UI가 3D 볼륨을 세울 때 높이로 쓰는 값이라 구간 수를 늘리면
# 폴리곤 수가 늘고 렌더링이 무거워진다 — 사람이 읽는 침수 단계(무릎/허리/성인 키/그 이상)
# 에 맞춰 4단으로 끊었다. 침수 여부만 필요한 호출부는 band를 무시하면 그대로 동작한다.
DEPTH_BANDS_M: tuple[float, ...] = (0.3, 1.0, 2.0, 5.0)


def _shapes_to_fc(mask, transform, extra_props: dict | None = None) -> dict[str, Any]:
    import numpy as np
    from rasterio.features import shapes
    feats = []
    m = mask.astype("uint8")
    for geom, val in shapes(m, mask=m > 0, transform=transform):
        if val != 1:
            continue
        feats.append({"type": "Feature", "geometry": geom,
                      "properties": {"flooded": 1, **(extra_props or {})}})
    return {"type": "FeatureCollection", "features": feats,
            "crs": {"type": "name", "properties": {"name": "EPSG:5179"}}}


def raster_to_featurecollection(depth_path: str, thr: float = 0.3,
                                bands: tuple[float, ...] | None = None) -> dict[str, Any]:
    """모형 최대침수심 래스터(EPSG:5179) → 침수(>thr) 폴리곤 FC.

    이진 마스크 하나로 폴리곤화하면 15m 침수와 0.4m 침수가 같은 도형이 되어
    깊이 정보가 여기서 버려진다. 그래서 구간(DEPTH_BANDS_M)별로 나눠 폴리곤화하고
    각 feature에 그 구간의 대푯값을 싣는다 — UI가 이 값을 3D 높이로 쓴다.

    properties:
      flooded      1 (기존 호출부 호환)
      depth_thr_m  침수 판정 임계 (기존 호출부 호환)
      depth_min_m  이 폴리곤이 속한 구간의 하한 — 3D 높이로 쓰는 보수적 값
      depth_max_m  구간 상한. 최상단 구간은 래스터 실제 최댓값
      depth_p90_m  구간 내 실제 침수심의 90분위 — 대표 깊이 표기용
      band         구간 인덱스(0부터)
    """
    import numpy as np
    import rasterio

    edges = tuple(bands) if bands else DEPTH_BANDS_M
    edges = tuple(e for e in edges if e >= thr) or (thr,)

    with rasterio.open(depth_path) as ds:
        dep = ds.read(1).astype("float32")
        transform = ds.transform

    finite = np.isfinite(dep)
    observed_max = float(dep[finite].max()) if finite.any() else thr

    feats: list[dict[str, Any]] = []
    for i, lo in enumerate(edges):
        hi = edges[i + 1] if i + 1 < len(edges) else float("inf")
        band_mask = finite & (dep >= lo) & (dep < hi)
        if not band_mask.any():
            continue
        values = dep[band_mask]
        props = {
            "flooded": 1,
            "depth_thr_m": thr,
            "depth_min_m": round(lo, 2),
            "depth_max_m": round(min(hi, observed_max), 2),
            "depth_p90_m": round(float(np.percentile(values, 90)), 2),
            "band": i,
        }
        feats.extend(_shapes_to_fc(band_mask, transform, extra_props=props)["features"])

    return {"type": "FeatureCollection", "features": feats,
            "crs": {"type": "name", "properties": {"name": "EPSG:5179"}}}


def hand_fim_featurecollection(wse_by_row=None, hand_path: str = None,
                               stage_m: float = None) -> dict[str, Any]:
    """HAND-FIM: 침수 ⟺ HAND < stage. 예측 수위 기반 실시간 침수 폴리곤.
    stage_m(스칼라) 또는 wse_by_row(행별 stage) 중 하나."""
    if hand_path is None:
        return _empty_fc()
    import numpy as np
    import rasterio
    with rasterio.open(hand_path) as ds:
        hand = ds.read(1).astype("float32")
        transform = ds.transform
    if wse_by_row is not None:
        stage = np.asarray(wse_by_row, dtype="float32")[:, None]
    else:
        stage = float(stage_m if stage_m is not None else 0.0)
    mask = np.isfinite(hand) & (hand < 9000) & (hand < stage)
    return _shapes_to_fc(mask, transform, extra_props={})
