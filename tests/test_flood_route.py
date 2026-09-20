"""대피 경로가 침수 구간을 지나면 통행 불가로 돌리는 로직(api_server._apply_flood_to_route)."""
import shapely.geometry as sg

import api_server

FLOOD = sg.box(127.0, 35.0, 127.01, 35.01)


def _result(coords):
    return {"shelter_id": "K1", "route_lonlat": coords, "time_feasible": True, "time_margin_min": 10.0}


def test_route_crossing_flood_is_blocked():
    r, warnings = _result([[126.99, 35.005], [127.02, 35.005]]), []
    api_server._apply_flood_to_route(r, FLOOD, (127.02, 35.005), warnings)
    assert r["route_flooded"] and r["flooded_route_m"] > 500
    assert r["time_feasible"] is False
    assert any("통행 불가" in w for w in warnings)


def test_dry_route_untouched():
    r, warnings = _result([[127.02, 35.02], [127.03, 35.02]]), []
    api_server._apply_flood_to_route(r, FLOOD, (127.03, 35.02), warnings)
    assert r["route_flooded"] is False and r["time_feasible"] is True and not warnings


def test_shelter_inside_flood_is_blocked_even_with_short_route():
    r, warnings = _result([[127.005, 35.005], [127.005, 35.0051]]), []
    api_server._apply_flood_to_route(r, FLOOD, (127.005, 35.0051), warnings)
    assert r["route_flooded"] and r["time_feasible"] is False


def test_no_flood_data_is_a_noop():
    r, warnings = _result([[126.99, 35.005], [127.02, 35.005]]), []
    api_server._apply_flood_to_route(r, None, (127.02, 35.005), warnings)
    assert r["route_flooded"] is False and r["time_feasible"] is True
