"""대피 경로가 통제 구간을 지나면 표시하고 도달 불가로 돌리는 로직(api_server._apply_closures_to_route).

네이버 경로는 도로 중심선을 따르지만, 통제 구간도 같은 선을 손으로 옮겨 적은 것이라 몇 m
어긋난다. 그래서 통제 구간 둘레 8m 안을 20m 넘게 따라가야 '통과'로 본다 — 교차로에서
직각으로 스치기만 한 경로는 통과가 아니다.
"""
from fastapi.testclient import TestClient

import api_server

LAT = 35.4
# 경도 0.0001° ≈ 9.1m (35.4°N)
CLOSED_ROAD = {"type": "LineString", "coordinates": [[128.000, LAT], [128.002, LAT]]}  # 동서로 약 180m
CLOSURE = {
    "type": "Feature",
    "geometry": CLOSED_ROAD,
    "properties": {"id": "c1", "reason": "송경천 복구 공사", "start": "2026-09-01", "end": None,
                   "source": "현장조사", "link_ids": ["L1"]},
}


def _result(coords):
    return {"shelter_id": "K1", "route_lonlat": coords, "time_feasible": True, "time_margin_min": 10.0}


def test_route_along_closure_is_flagged():
    r, warnings = _result([[127.999, LAT], [128.0005, LAT]]), []  # 통제 구간 위를 약 45m
    api_server._apply_closures_to_route(r, [CLOSURE], warnings)
    assert r["route_closed"] is True and r["closed_route_m"] > 20
    assert r["time_feasible"] is False and r["time_margin_min"] is None
    assert any("송경천 복구 공사" in w for w in warnings)


def test_route_crossing_at_intersection_is_not_flagged():
    r, warnings = _result([[128.001, LAT - 0.001], [128.001, LAT + 0.001]]), []  # 남북으로 직각 교차
    api_server._apply_closures_to_route(r, [CLOSURE], warnings)
    assert r["route_closed"] is False and r["time_feasible"] is True and not warnings


def test_no_closures_is_a_noop():
    r, warnings = _result([[127.999, LAT], [128.0005, LAT]]), []
    api_server._apply_closures_to_route(r, [], warnings)
    assert r["route_closed"] is False and r["time_feasible"] is True


def test_road_closures_endpoint_returns_feature_collection():
    body = TestClient(api_server.app).get("/road-closures").json()
    assert body["type"] == "FeatureCollection"
    assert isinstance(body["features"], list)
