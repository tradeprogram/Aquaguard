"""§4.2 계약 준수·폴백 계층 테스트 (Module V)."""
from __future__ import annotations

import module_v_validation as mv

KEYS = {"status", "fallback_tier", "data", "warnings"}
DATA_KEYS = {"iou", "f1", "precision", "recall", "confusion_geometry_5179", "lead_time_min"}


def _fc(features=None):
    return {"type": "FeatureCollection", "features": features or []}


def _sq(x0, y0, s):
    return _fc([{"type": "Feature", "properties": {},
                 "geometry": {"type": "Polygon", "coordinates": [[
                     [x0, y0], [x0 + s, y0], [x0 + s, y0 + s], [x0, y0 + s], [x0, y0]]]}}])


def _pred(fc, mod="A"):
    return {"source_module": mod, "geometry_5179": fc}


def _obs(fc, typ="sentinel1_sar_change", ts="2025-07-19T12:37:00+09:00"):
    return {"type": typ, "geometry_5179": fc, "acquisition_timestamp": ts,
            "source": "Copernicus Sentinel-1"}


def _assert_env(out):
    assert set(out.keys()) == KEYS
    assert out["status"] in ("ok", "degraded", "error")
    assert out["fallback_tier"] in (1, 2, 3)
    d = out["data"]
    assert DATA_KEYS <= set(d.keys())
    for k in ("iou", "f1", "precision", "recall"):
        assert 0.0 <= d[k] <= 1.0
    cg = d["confusion_geometry_5179"]
    for k in ("true_positive", "false_positive", "false_negative"):
        assert cg[k]["type"] == "FeatureCollection"
    assert d["lead_time_min"] is None or d["lead_time_min"] >= 0


def test_example_empty():
    out = mv.run({"alert_id": "AL-20250719-0915",
                  "predicted": _pred(_fc()), "observed": _obs(_fc())})
    _assert_env(out)
    assert out["fallback_tier"] == 1


def test_identical_iou_one():
    sq = _sq(0, 0, 1000)
    out = mv.run({"alert_id": "AL-20250719-0915",
                  "predicted": _pred(sq), "observed": _obs(sq)})
    _assert_env(out)
    assert out["data"]["iou"] >= 0.98        # 동일 폴리곤 → IoU≈1


def test_half_overlap():
    out = mv.run({"alert_id": "AL-20250719-0915",
                  "predicted": _pred(_sq(0, 0, 1000)),
                  "observed": _obs(_sq(500, 0, 1000))})
    _assert_env(out)
    assert 0.28 <= out["data"]["iou"] <= 0.38   # 이론 1/3


def test_disjoint_iou_zero():
    out = mv.run({"alert_id": "AL-20250719-0915",
                  "predicted": _pred(_sq(0, 0, 500)),
                  "observed": _obs(_sq(5000, 5000, 500))})
    _assert_env(out)
    assert out["data"]["iou"] == 0.0


def test_tier2_inventory():
    out = mv.run({"alert_id": "A-1", "predicted": _pred(_sq(0, 0, 100)),
                  "observed": _obs(_sq(0, 0, 100), typ="landslide_inventory")})
    _assert_env(out)
    assert out["fallback_tier"] == 2 and out["status"] == "degraded"


def test_tier3_gauge():
    out = mv.run({"alert_id": "A-1", "predicted": _pred(_sq(0, 0, 100)),
                  "observed": _obs(_sq(0, 0, 100), typ="river_gauge")})
    _assert_env(out)
    assert out["fallback_tier"] == 3


def test_error_missing_geometry():
    out = mv.run({"alert_id": "A-1", "predicted": {"source_module": "A"},
                  "observed": _obs(_fc())})
    _assert_env(out)
    assert out["status"] == "error"


def test_never_raises():
    for bad in [{}, {"alert_id": "x"}, {"alert_id": "x", "predicted": {}, "observed": {}},
                {"alert_id": "x", "predicted": {"geometry_5179": "oops"}, "observed": {}}]:
        out = mv.run(bad)
        _assert_env(out)


def test_lead_time_positive():
    """예측경보(09:15) < 관측(12:37) → lead 202분."""
    out = mv.run({"alert_id": "AL-20250719-0915",
                  "predicted": _pred(_sq(0, 0, 100)),
                  "observed": _obs(_sq(0, 0, 100), ts="2025-07-19T12:37:00+09:00")})
    assert out["data"]["lead_time_min"] == 202.0
