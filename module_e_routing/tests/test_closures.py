"""복구·통제 구간 — 고립 판정에서 그 구간을 끊고, 침수로 끊긴 길과 따로 보고한다."""
from datetime import date

import pytest

from module_e_routing import closures
from module_e_routing import isolation as iso
from module_e_routing.tests.conftest import LAT, A, B, box

LINE_E2 = {"type": "LineString", "coordinates": [list(A), list(B)]}


def closure(**props):
    base = {"id": "c1", "reason": "송경천 복구 공사", "start": "2026-09-01", "end": None, "source": "현장조사"}
    return {"type": "Feature", "geometry": LINE_E2, "properties": {**base, "link_ids": ["e2"], **props}}


def test_active_on_date():
    fc = [closure(start="2026-09-01", end="2026-12-31")]
    assert closures.active(fc, date(2026, 10, 8)) == fc
    assert closures.active(fc, date(2025, 7, 19)) == []
    assert closures.active([closure(end=None)], date(2030, 1, 1))  # 종료일 없음 = 계속 유효


def test_line_closure_without_link_ids_is_rejected():
    bad = closure()
    bad["properties"].pop("link_ids")
    with pytest.raises(closures.ClosureError):
        closures.validate([bad])


def test_missing_required_property_is_rejected():
    bad = closure()
    bad["properties"]["reason"] = ""
    with pytest.raises(closures.ClosureError):
        closures.validate([bad])


def test_shipped_closure_file_is_valid():
    assert isinstance(closures.load(), list)


def test_closure_isolates_village_and_is_reported(toy):
    r = iso.check_isolation(toy["bbox"], toy["shelters"], None, closures=[closure()])
    assert r["isolated_building_count"] == 1
    props = r["closed_roads"]["features"][0]["properties"]
    assert props["kind"] == "closed_road"
    assert props["reason"] == "송경천 복구 공사"
    assert props["link_id"] == "e2"
    assert r["blocked_roads"]["features"] == []  # 침수로 끊긴 길과 섞지 않는다


def test_polygon_closure_cuts_intersecting_edges(toy):
    poly = {
        "type": "Feature",
        "geometry": box(128.0013, LAT - 0.0001, 128.0017, LAT + 0.0001),
        "properties": {"id": "c2", "reason": "구역 통제", "start": "2026-09-01", "end": None, "source": "군청"},
    }
    r = iso.check_isolation(toy["bbox"], toy["shelters"], None, closures=[poly])
    assert r["isolated_building_count"] == 1
    assert r["closed_roads"]["features"][0]["properties"]["closure_id"] == "c2"
