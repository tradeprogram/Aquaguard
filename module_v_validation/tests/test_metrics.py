"""metrics.py·leadtime.py 단위테스트."""
from __future__ import annotations

from module_v_validation import metrics, leadtime


def _sq(x0, y0, s):
    return {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {},
            "geometry": {"type": "Polygon", "coordinates": [[
                [x0, y0], [x0 + s, y0], [x0 + s, y0 + s], [x0, y0 + s], [x0, y0]]]}}]}


def test_identical():
    r = metrics.confusion(_sq(0, 0, 1000), _sq(0, 0, 1000), res=25)
    assert r["iou"] >= 0.98 and r["f1"] >= 0.98


def test_half_overlap_third():
    r = metrics.confusion(_sq(0, 0, 1000), _sq(500, 0, 1000), res=25)
    assert 0.30 <= r["iou"] <= 0.36        # 이론 1/3


def test_disjoint():
    r = metrics.confusion(_sq(0, 0, 300), _sq(9000, 9000, 300), res=25)
    assert r["iou"] == 0.0 and r["counts"]["TP"] == 0


def test_empty_geometry():
    r = metrics.confusion({"type": "FeatureCollection", "features": []},
                          {"type": "FeatureCollection", "features": []})
    assert r["iou"] == 0.0 and r.get("note") == "no geometry"


def test_confusion_geometry_present():
    r = metrics.confusion(_sq(0, 0, 1000), _sq(500, 0, 1000), res=50)
    cg = r["confusion_geometry"]
    assert len(cg["true_positive"]["features"]) >= 1
    assert len(cg["false_positive"]["features"]) >= 1
    assert len(cg["false_negative"]["features"]) >= 1


def test_lead_time_parse_alert_id():
    lt = leadtime.lead_time_min("AL-20250719-0915", "2025-07-19T12:37:00+09:00")
    assert lt == 202.0


def test_lead_time_none_when_obs_before():
    lt = leadtime.lead_time_min("AL-20250719-1300", "2025-07-19T09:00:00+09:00")
    assert lt is None


def test_lead_time_none_unparseable():
    assert leadtime.lead_time_min("bad", "also-bad") is None
