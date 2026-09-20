"""module_v_validation.metrics — 예측 vs 실측 공간 혼동행렬 (계약 무관).

두 GeoJSON FeatureCollection(EPSG:5179)을 공통격자에 rasterize → TP/FP/FN →
IoU/F1/precision/recall + confusion_geometry(TP/FP/FN 분리 폴리곤).
공간자기상관 과대평가 방지: 픽셀단위가 아니라 폴리곤 겹침 기반(SPEC §2, ARCHITECTURE §15.6).

rasterio/shapely 지연 import — 미설치 시 run()이 error 봉투로 폴백.
"""
from __future__ import annotations

from typing import Any

RES_DEFAULT = 30.0   # m
MAX_CELLS = 4_000_000  # 격자 상한(초과 시 해상도 자동 하향)


def _empty_fc():
    return {"type": "FeatureCollection", "features": []}


def _iter_geoms(fc):
    from shapely.geometry import shape
    for f in fc.get("features", []):
        g = f.get("geometry")
        if g:
            try:
                yield shape(g)
            except Exception:  # noqa: BLE001
                continue


def _bounds(*fcs):
    xs0 = ys0 = float("inf"); xs1 = ys1 = float("-inf")
    any_geom = False
    for fc in fcs:
        for g in _iter_geoms(fc):
            any_geom = True
            a, b, c, d = g.bounds
            xs0, ys0, xs1, ys1 = min(xs0, a), min(ys0, b), max(xs1, c), max(ys1, d)
    return (xs0, ys0, xs1, ys1) if any_geom else None


def _rasterize(fc, transform, shape_hw):
    from rasterio.features import rasterize
    geoms = [(g, 1) for g in _iter_geoms(fc)]
    if not geoms:
        import numpy as np
        return np.zeros(shape_hw, dtype="uint8")
    return rasterize(geoms, out_shape=shape_hw, transform=transform, fill=0,
                     all_touched=True, dtype="uint8")


def _mask_to_fc(mask, transform):
    import numpy as np
    from rasterio.features import shapes
    m = mask.astype("uint8")
    feats = [{"type": "Feature", "geometry": geom, "properties": {}}
             for geom, val in shapes(m, mask=m > 0, transform=transform) if val == 1]
    return {"type": "FeatureCollection", "features": feats,
            "crs": {"type": "name", "properties": {"name": "EPSG:5179"}}}


def confusion(predicted_fc: dict, observed_fc: dict, res: float = RES_DEFAULT) -> dict[str, Any]:
    """IoU/F1/precision/recall + confusion_geometry. 지오메트리 없으면 0."""
    import numpy as np
    import rasterio

    b = _bounds(predicted_fc, observed_fc)
    if b is None:
        return {"iou": 0.0, "f1": 0.0, "precision": 0.0, "recall": 0.0,
                "confusion_geometry": {"true_positive": _empty_fc(),
                                       "false_positive": _empty_fc(),
                                       "false_negative": _empty_fc()},
                "note": "no geometry"}
    x0, y0, x1, y1 = b
    pad = res * 2
    x0, y0, x1, y1 = x0 - pad, y0 - pad, x1 + pad, y1 + pad
    W = max(1, int(np.ceil((x1 - x0) / res)))
    H = max(1, int(np.ceil((y1 - y0) / res)))
    while W * H > MAX_CELLS:                 # 너무 크면 해상도 하향
        res *= 2; W = max(1, int(np.ceil((x1 - x0) / res))); H = max(1, int(np.ceil((y1 - y0) / res)))
    transform = rasterio.transform.from_origin(x0, y1, res, res)

    P = _rasterize(predicted_fc, transform, (H, W)).astype(bool)
    O = _rasterize(observed_fc, transform, (H, W)).astype(bool)
    tp = P & O; fp = P & ~O; fn = ~P & O
    TP, FP, FN = int(tp.sum()), int(fp.sum()), int(fn.sum())
    iou = TP / max(TP + FP + FN, 1)
    prec = TP / max(TP + FP, 1)
    rec = TP / max(TP + FN, 1)
    f1 = 2 * prec * rec / max(prec + rec, 1e-9)
    return {"iou": round(iou, 3), "f1": round(f1, 3), "precision": round(prec, 3), "recall": round(rec, 3),
            "confusion_geometry": {"true_positive": _mask_to_fc(tp, transform),
                                   "false_positive": _mask_to_fc(fp, transform),
                                   "false_negative": _mask_to_fc(fn, transform)},
            "counts": {"TP": TP, "FP": FP, "FN": FN}, "res_m": res}
