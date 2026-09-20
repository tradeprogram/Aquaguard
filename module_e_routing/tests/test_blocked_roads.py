"""위험영역과 겹쳐 끊기는 도로 구간 산출 — §7 고립 판정의 부산물.

remove_hazard_edges 는 원래 제거 개수만 돌려줬다. 지도에 "어느 길이 끊기는가"를
칠하려면 지오메트리가 필요해서 제거된 엣지 자체를 돌려주도록 바꿨고, 그 계약을
여기서 고정한다. VWorld 호출 없이 합성 격자 그래프로만 검증한다.
"""
from __future__ import annotations

import networkx as nx
import pytest

from module_e_routing import isolation


def _grid_graph(n: int = 5, step: float = 0.01, lon0: float = 127.0, lat0: float = 35.0) -> nx.Graph:
    """n×n 격자 도로망. 노드는 (lon, lat)."""
    graph = nx.Graph()
    for i in range(n):
        for j in range(n):
            if i < n - 1:
                graph.add_edge((lon0 + i * step, lat0 + j * step),
                               (lon0 + (i + 1) * step, lat0 + j * step))
            if j < n - 1:
                graph.add_edge((lon0 + i * step, lat0 + j * step),
                               (lon0 + i * step, lat0 + (j + 1) * step))
    return graph


def _square(lon_min: float, lat_min: float, lon_max: float, lat_max: float) -> dict:
    return {
        "type": "Polygon",
        "coordinates": [[
            [lon_min, lat_min], [lon_max, lat_min],
            [lon_max, lat_max], [lon_min, lat_max], [lon_min, lat_min],
        ]],
    }


HAZARD = _square(127.005, 35.005, 127.025, 35.025)


def test_removed_edges_are_returned_not_just_counted():
    graph = _grid_graph()
    before = graph.number_of_edges()

    removed = isolation.remove_hazard_edges(graph, HAZARD)

    assert removed, "위험영역이 격자를 가로지르므로 끊기는 구간이 있어야 한다"
    assert graph.number_of_edges() == before - len(removed)
    for u, v in removed:
        assert not graph.has_edge(u, v)


def test_blocked_road_features_are_drawable_geojson():
    graph = _grid_graph()
    removed = isolation.remove_hazard_edges(graph, HAZARD)

    fc = isolation.blocked_road_features(removed)

    assert fc["type"] == "FeatureCollection"
    assert len(fc["features"]) == len(removed)
    for feature in fc["features"]:
        assert feature["geometry"]["type"] == "LineString"
        coords = feature["geometry"]["coordinates"]
        assert len(coords) == 2 and all(len(p) == 2 for p in coords)
        assert feature["properties"]["kind"] == "blocked_road"


def test_featurecollection_hazard_matches_plain_polygon():
    """Module B의 침수범위는 깊이 구간별 폴리곤 수백 개인 FeatureCollection으로 온다."""
    as_polygon = isolation.remove_hazard_edges(_grid_graph(), HAZARD)
    as_fc = isolation.remove_hazard_edges(
        _grid_graph(),
        {"type": "FeatureCollection",
         "features": [{"type": "Feature", "properties": {"depth_p90_m": 1.2},
                       "geometry": HAZARD}]},
    )
    assert sorted(as_polygon) == sorted(as_fc)


def test_multipart_hazard_removes_union_of_both():
    """떨어져 있는 두 침수 구역이 각각 도로를 끊는다 — 합집합으로 처리돼야 한다."""
    left = _square(127.005, 35.005, 127.015, 35.015)
    right = _square(127.025, 35.025, 127.035, 35.035)

    only_left = set(isolation.remove_hazard_edges(_grid_graph(), left))
    only_right = set(isolation.remove_hazard_edges(_grid_graph(), right))
    both = set(isolation.remove_hazard_edges(
        _grid_graph(),
        {"type": "MultiPolygon",
         "coordinates": [left["coordinates"], right["coordinates"]]},
    ))

    assert only_left and only_right
    assert both == only_left | only_right


@pytest.mark.parametrize(
    "hazard",
    [
        None,
        {},
        {"type": "FeatureCollection", "features": []},
        {"type": "Polygon", "coordinates": "깨진 입력"},
        {"type": "듣도보도 못한 타입", "coordinates": []},
    ],
    ids=["none", "empty-dict", "empty-fc", "malformed", "unknown-type"],
)
def test_unusable_hazard_removes_nothing_and_does_not_raise(hazard):
    """§4.2 — 위험영역을 못 읽어도 예외로 죽지 않는다. 도로를 임의로 끊지도 않는다."""
    graph = _grid_graph()
    before = graph.number_of_edges()

    removed = isolation.remove_hazard_edges(graph, hazard)

    assert removed == []
    assert graph.number_of_edges() == before
