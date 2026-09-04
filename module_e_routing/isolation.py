"""
고립마을 자동탐지 (§7, 독창성 축 4 — 트랙④ 소유).

VWorld 도로망(LT_L_MOCTLINK)으로 networkx 그래프를 만들고, 위험폴리곤과 겹치는
도로를 제거한 뒤, 대피소들로부터 역방향 도달가능성을 계산한다. 그 도달 가능
집합에 들지 못한 건물(VWorld LT_C_SPBD)이 "고립"이다.

착수 순서(HANDOFF.md §7 그대로): 노드 스냅 → 위험 엣지 제거 → 역방향 도달가능성
→ 건물 매핑 → 클러스터링.

좌표계: VWorld Data API가 그대로 EPSG:4326(lon, lat)으로 응답하므로(api_server.py의
/vworld/roads·/vworld/buildings와 동일 관례), 이 파일도 끝까지 4326으로만 다룬다 —
module_e_routing/__init__.py(대피경로)가 5179를 쓰는 것과 달라 보이지만, 그쪽은
Module O 계약(§4.1)을 따르는 반면 이 파일은 그 계약 밖의 신규 기능(§7)이라 VWorld
원본 좌표계를 그대로 쓰는 쪽이 재투영 오차·코드 복잡도를 줄인다.
"""
from __future__ import annotations

import math
import os
from typing import Any

import networkx as nx
import requests
import shapely.geometry
from pyproj import Transformer
from shapely.ops import unary_union

VWORLD_URL = "http://api.vworld.kr/req/data"
VWORLD_ROAD_LAYER = "LT_L_MOCTLINK"
VWORLD_BUILDING_LAYER = "LT_C_SPBD"
VWORLD_PAGE_SIZE = 1000
VWORLD_MAX_QUERY_AREA_KM2 = 9.0  # api_server.py와 동일한 VWorld 쿼리 면적 한도

NODE_SNAP_DECIMALS = 5  # 위도 35~38°N에서 소수 5자리 ≈ 1.1m — 부동소수점 오차로 끊긴 도로 병합용
ISOLATION_CLUSTER_RADIUS_M = 200.0  # 이 거리 안의 고립 건물끼리 같은 구역으로 묶음

_TO_5179 = Transformer.from_crs("EPSG:4326", "EPSG:5179", always_xy=True)


def _haversine_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    r = 6371000.0
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lon / 2) ** 2
    )
    return 2 * r * math.asin(math.sqrt(a))


def _split_bbox(bbox: tuple[float, float, float, float], max_km2: float = VWORLD_MAX_QUERY_AREA_KM2) -> list[tuple[float, float, float, float]]:
    """VWorld 9km² 쿼리 한도를 넘는 bbox를 타일로 쪼갠다(api_server.py의 클램프와 달리
    범위를 줄이지 않고 전체를 빠짐없이 커버해야 하므로 격자로 나눈다)."""
    minx, miny, maxx, maxy = bbox
    center_lat = (miny + maxy) / 2
    width_km = (maxx - minx) * 111.32 * math.cos(math.radians(center_lat))
    height_km = (maxy - miny) * 110.54
    if width_km * height_km <= max_km2:
        return [bbox]

    side_km = math.sqrt(max_km2) * 0.9  # 여유를 좀 더 두어 경계 근처 결측 방지
    n_cols = max(1, math.ceil(width_km / side_km))
    n_rows = max(1, math.ceil(height_km / side_km))
    dx = (maxx - minx) / n_cols
    dy = (maxy - miny) / n_rows
    tiles = []
    for i in range(n_cols):
        for j in range(n_rows):
            tiles.append((minx + i * dx, miny + j * dy, minx + (i + 1) * dx, miny + (j + 1) * dy))
    return tiles


def _vworld_get_feature(data_layer: str, bbox: tuple[float, float, float, float]) -> list[dict[str, Any]]:
    api_key = os.environ.get("VWORLD_API_KEY")
    if not api_key:
        raise RuntimeError("VWORLD_API_KEY not configured (.env)")
    minx, miny, maxx, maxy = bbox
    features: list[dict[str, Any]] = []
    page = 1
    while True:
        resp = requests.get(
            VWORLD_URL,
            params={
                "service": "data",
                "request": "GetFeature",
                "data": data_layer,
                "key": api_key,
                "domain": "localhost",
                "format": "json",
                "size": VWORLD_PAGE_SIZE,
                "page": page,
                "geomFilter": f"BOX({minx},{miny},{maxx},{maxy})",
            },
            timeout=10,
        )
        resp.raise_for_status()
        body = resp.json().get("response", {})
        status = body.get("status")
        if status == "NOT_FOUND":
            break
        if status != "OK":
            raise RuntimeError(f"VWorld error: {body.get('error')}")
        result = body["result"]["featureCollection"]
        page_features = result.get("features", [])
        features.extend(page_features)
        total_count = int(body.get("record", {}).get("total", len(page_features)))
        if len(features) >= total_count or len(page_features) < VWORLD_PAGE_SIZE:
            break
        page += 1
    return features


def fetch_roads(bbox: tuple[float, float, float, float]) -> list[dict[str, Any]]:
    features: list[dict[str, Any]] = []
    for tile in _split_bbox(bbox):
        features.extend(_vworld_get_feature(VWORLD_ROAD_LAYER, tile))
    return features


def fetch_buildings(bbox: tuple[float, float, float, float]) -> list[dict[str, Any]]:
    features: list[dict[str, Any]] = []
    for tile in _split_bbox(bbox):
        features.extend(_vworld_get_feature(VWORLD_BUILDING_LAYER, tile))
    return features


def _snap(lon: float, lat: float) -> tuple[float, float]:
    return (round(lon, NODE_SNAP_DECIMALS), round(lat, NODE_SNAP_DECIMALS))


def _iter_line_segments(geometry: dict[str, Any]):
    """LineString/MultiLineString geometry에서 (연속 좌표 두 점) 세그먼트를 순회한다."""
    gtype = geometry.get("type")
    if gtype == "LineString":
        lines = [geometry["coordinates"]]
    elif gtype == "MultiLineString":
        lines = geometry["coordinates"]
    else:
        return
    for line in lines:
        for a, b in zip(line, line[1:]):
            yield a, b


def build_road_graph(road_features: list[dict[str, Any]]) -> nx.Graph:
    """도로 링크들을 노드 스냅 후 그래프로 만든다. rd_type_h(교량/터널/일반도로) 등
    속성은 엣지에 그대로 실어 나중에 위험 제거·시각화에 쓸 수 있게 한다."""
    graph = nx.Graph()
    for feature in road_features:
        geometry = feature.get("geometry") or {}
        props = feature.get("properties", {})
        for a, b in _iter_line_segments(geometry):
            na, nb = _snap(*a), _snap(*b)
            if na == nb:
                continue
            weight = _haversine_m(*na, *nb)
            graph.add_edge(na, nb, weight=weight, link_id=props.get("link_id"), rd_type_h=props.get("rd_type_h"))
    return graph


def remove_hazard_edges(graph: nx.Graph, hazard_polygon: dict[str, Any] | None) -> int:
    """위험폴리곤(GeoJSON Polygon, lon/lat)과 교차하는 도로 엣지를 그래프에서 제거한다.
    반환값은 제거된 엣지 수(호출측 warnings/디버깅용)."""
    if not hazard_polygon or not hazard_polygon.get("type"):
        return 0
    try:
        hazard_shape = shapely.geometry.shape(hazard_polygon)
    except Exception:
        return 0
    to_remove = []
    for u, v in graph.edges():
        segment = shapely.geometry.LineString([u, v])
        if segment.intersects(hazard_shape):
            to_remove.append((u, v))
    graph.remove_edges_from(to_remove)
    return len(to_remove)


def _nearest_node(graph: nx.Graph, lon: float, lat: float) -> tuple[float, float] | None:
    """그래프 안에서 (lon, lat)에 가장 가까운 노드를 찾는다 — 마을 규모 그래프(수백~수천
    노드) 기준으로는 브루트포스로 충분히 빠르다."""
    best_node, best_dist = None, float("inf")
    for node in graph.nodes():
        d = _haversine_m(lon, lat, node[0], node[1])
        if d < best_dist:
            best_node, best_dist = node, d
    return best_node


def reachable_from_shelters(graph: nx.Graph, shelter_lonlat: list[tuple[float, float]]) -> set[tuple[float, float]]:
    """대피소 각각에서 역방향(무방향 그래프라 정방향과 동일) BFS로 도달 가능한 노드를
    모두 합친다 — "최소 1곳 대피소라도 갈 수 있는 노드 집합"."""
    reachable: set[tuple[float, float]] = set()
    for lon, lat in shelter_lonlat:
        node = _nearest_node(graph, lon, lat)
        if node is None:
            continue
        reachable |= nx.node_connected_component(graph, node)
    return reachable


def find_isolated_buildings(
    building_features: list[dict[str, Any]], graph: nx.Graph, reachable: set[tuple[float, float]]
) -> list[tuple[float, float]]:
    """건물 무게중심 → 최근접 도로 노드 매핑, 그 노드가 도달가능집합 밖이면 고립."""
    isolated: list[tuple[float, float]] = []
    for feature in building_features:
        geometry = feature.get("geometry")
        if not geometry:
            continue
        try:
            centroid = shapely.geometry.shape(geometry).centroid
        except Exception:
            continue
        node = _nearest_node(graph, centroid.x, centroid.y)
        if node is None or node not in reachable:
            isolated.append((centroid.x, centroid.y))
    return isolated


def cluster_isolated_buildings(points: list[tuple[float, float]]) -> list[dict[str, Any]]:
    """고립 건물들을 ISOLATION_CLUSTER_RADIUS_M 이내끼리 묶어 구역(convex hull)으로 만든다.
    구현: 두 건물이 반경 이내면 그래프 엣지로 잇고, 연결요소(connected component)를 클러스터로 삼는다.
    """
    if not points:
        return []
    points_5179 = [_TO_5179.transform(lon, lat) for lon, lat in points]

    cluster_graph = nx.Graph()
    cluster_graph.add_nodes_from(range(len(points)))
    for i in range(len(points)):
        for j in range(i + 1, len(points)):
            dx = points_5179[i][0] - points_5179[j][0]
            dy = points_5179[i][1] - points_5179[j][1]
            if (dx * dx + dy * dy) ** 0.5 <= ISOLATION_CLUSTER_RADIUS_M:
                cluster_graph.add_edge(i, j)

    clusters = []
    for component in nx.connected_components(cluster_graph):
        member_points = [points[i] for i in component]
        lons = [p[0] for p in member_points]
        lats = [p[1] for p in member_points]
        centroid = (sum(lons) / len(lons), sum(lats) / len(lats))
        bbox = (min(lons), min(lats), max(lons), max(lats))
        if len(member_points) == 1:
            lon, lat = member_points[0]
            geometry = {"type": "Point", "coordinates": [lon, lat]}
        else:
            hull = shapely.geometry.MultiPoint(member_points).convex_hull
            geometry = shapely.geometry.mapping(hull)
        clusters.append(
            {
                "geometry": geometry,
                "building_count": len(member_points),
                "member_points": member_points,
                "centroid": centroid,
                "bbox": bbox,
            }
        )
    clusters.sort(key=lambda c: c["building_count"], reverse=True)
    return clusters


def check_isolation(
    bbox: tuple[float, float, float, float],
    shelter_candidates_lonlat: list[tuple[float, float]],
    hazard_polygon: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """§7 /isolation-check의 핵심 로직. 반환: {isolated_areas, isolated_building_count, warnings}."""
    warnings: list[str] = []
    road_features = fetch_roads(bbox)
    if not road_features:
        return {"isolated_areas": {"type": "FeatureCollection", "features": []}, "isolated_building_count": 0, "warnings": ["해당 영역에 도로 데이터 없음"]}

    graph = build_road_graph(road_features)
    removed = remove_hazard_edges(graph, hazard_polygon)
    if removed:
        warnings.append(f"위험지역과 겹치는 도로 {removed}개 구간 제거")

    reachable = reachable_from_shelters(graph, shelter_candidates_lonlat)
    if not reachable:
        warnings.append("대피소 근처에서 도로 그래프를 찾지 못함 — 도달가능성 계산 불가")

    building_features = fetch_buildings(bbox)
    isolated_points = find_isolated_buildings(building_features, graph, reachable)
    clusters = cluster_isolated_buildings(isolated_points)

    features = []
    building_point_features = []
    for cluster_id, c in enumerate(clusters):
        features.append(
            {
                "type": "Feature",
                "geometry": c["geometry"],
                "properties": {
                    "cluster_id": cluster_id,
                    "building_count": c["building_count"],
                    "centroid": list(c["centroid"]),
                    "bbox": list(c["bbox"]),
                },
            }
        )
        for lon, lat in c["member_points"]:
            building_point_features.append(
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [lon, lat]},
                    "properties": {"cluster_id": cluster_id},
                }
            )

    return {
        "isolated_areas": {"type": "FeatureCollection", "features": features},
        "isolated_buildings": {"type": "FeatureCollection", "features": building_point_features},
        "isolated_building_count": len(isolated_points),
        "warnings": warnings,
    }
