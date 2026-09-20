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


def raster_to_featurecollection(depth_path: str, thr: float = 0.3) -> dict[str, Any]:
    """모형 최대침수심 래스터(EPSG:5179) → 침수(>thr) 폴리곤 FC."""
    import rasterio
    with rasterio.open(depth_path) as ds:
        dep = ds.read(1)
        transform = ds.transform
    mask = (dep > thr)
    return _shapes_to_fc(mask, transform, extra_props={"depth_thr_m": thr})


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
