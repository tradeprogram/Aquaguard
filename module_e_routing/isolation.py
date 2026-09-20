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

import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any

import networkx as nx
import numpy as np
import requests
import shapely
from scipy.spatial import cKDTree
import shapely.geometry
import shapely.prepared
from pyproj import Transformer
from shapely.ops import unary_union

VWORLD_URL = "http://api.vworld.kr/req/data"
VWORLD_ROAD_LAYER = "LT_L_MOCTLINK"
VWORLD_BUILDING_LAYER = "LT_C_SPBD"
VWORLD_PAGE_SIZE = 1000
VWORLD_MAX_QUERY_AREA_KM2 = 9.0  # api_server.py와 동일한 VWorld 쿼리 면적 한도

NODE_SNAP_DECIMALS = 5  # 위도 35~38°N에서 소수 5자리 ≈ 1.1m — 부동소수점 오차로 끊긴 도로 병합용
ISOLATION_MAX_SNAP_M = 300.0  # 건물이 이보다 멀리 떨어진 노드에만 매핑되면 도로 데이터 밖 건물로 보고 판정에서 뺀다(산간 외딴 건물 오탐 방지)
FEATURE_CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "cache" / "isolation"  # §7.3 — VWorld 원본 응답 캐시(gitignore)
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


def _dedupe(features: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """타일 경계 여유(겹침) 때문에 같은 지물이 두 번 오는 걸 제거한다."""
    seen: set[str] = set()
    out = []
    for f in features:
        k = json.dumps(f.get("geometry"), sort_keys=True)
        if k not in seen:
            seen.add(k)
            out.append(f)
    return out


def _fetch_tiled_cached(layer: str, bbox: tuple[float, float, float, float]) -> list[dict[str, Any]]:
    """bbox를 타일로 쪼개 VWorld에서 받고 결과를 디스크에 캐시한다(§7.3 — 같은 bbox 재요청은
    API를 다시 안 부른다). 캐시를 비우려면 data/cache/isolation/ 폴더를 지우면 된다."""
    key = hashlib.md5(f"{layer}|{tuple(round(v, 5) for v in bbox)}".encode()).hexdigest()[:16]
    cache_file = FEATURE_CACHE_DIR / f"{layer}_{key}.json"
    if cache_file.exists():
        try:
            return json.loads(cache_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
    features: list[dict[str, Any]] = []
    for tile in _split_bbox(bbox):
        features.extend(_vworld_get_feature(layer, tile))
    features = _dedupe(features)
    try:
        FEATURE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(features), encoding="utf-8")
    except OSError:
        pass
    return features


def fetch_roads(bbox: tuple[float, float, float, float]) -> list[dict[str, Any]]:
    return _fetch_tiled_cached(VWORLD_ROAD_LAYER, bbox)


def fetch_buildings(bbox: tuple[float, float, float, float]) -> list[dict[str, Any]]:
    return _fetch_tiled_cached(VWORLD_BUILDING_LAYER, bbox)


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


def remove_hazard_edges(graph: nx.Graph, hazard_polygon: dict[str, Any] | None) -> list[tuple]:
    """위험폴리곤(GeoJSON, lon/lat)과 교차하는 도로 엣지를 그래프에서 제거한다.

    제거된 엣지를 그대로 돌려준다 — 예전에는 개수만 반환했는데, 그러면 "어느 도로가
    끊겼는지"를 지도에 빨간색으로 칠할 방법이 없다. 고립 판정에 이미 쓴 계산이라
    추가 비용도 없다.

    Polygon 하나만이 아니라 MultiPolygon·FeatureCollection도 받는다 — Module B의
    실제 침수범위는 깊이 구간별로 쪼개진 폴리곤 수백 개로 오기 때문이다. 교차 검사는
    엣지 전체를 STRtree(공간 인덱스)에 넣고 위험 도형으로 한 번에 질의한다 — 군 전체
    (엣지 약 10만 개)에서도 엣지마다 교차 검사를 반복하지 않는다.
    """
    hazard_shape = _hazard_shape(hazard_polygon)
    if hazard_shape is None:
        return []
    edges = list(graph.edges())
    if not edges:
        return []
    segments = shapely.linestrings([[u, v] for u, v in edges])
    hit = shapely.STRtree(segments).query(hazard_shape, predicate="intersects")
    to_remove = [edges[k] for k in hit]
    graph.remove_edges_from(to_remove)
    return to_remove


def _hazard_shape(hazard_polygon: dict[str, Any] | None):
    """GeoJSON(Geometry | Feature | FeatureCollection) → 단일 shapely 도형. 실패하면 None."""
    if not isinstance(hazard_polygon, dict) or not hazard_polygon.get("type"):
        return None
    try:
        kind = hazard_polygon["type"]
        if kind == "FeatureCollection":
            parts = [
                shapely.geometry.shape(f["geometry"])
                for f in hazard_polygon.get("features") or []
                if isinstance(f, dict) and f.get("geometry")
            ]
            if not parts:
                return None
            return unary_union(parts)
        if kind == "Feature":
            return shapely.geometry.shape(hazard_polygon["geometry"])
        return shapely.geometry.shape(hazard_polygon)
    except Exception:
        return None


def blocked_road_features(removed_edges: list[tuple]) -> dict[str, Any]:
    """제거된 엣지 → GeoJSON FeatureCollection(lon/lat). 지도에서 빨간 도로로 그린다."""
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "LineString", "coordinates": [list(u), list(v)]},
                "properties": {"kind": "blocked_road"},
            }
            for u, v in removed_edges
        ],
    }


class _NodeIndex:
    """그래프 노드에 대한 KD-tree — 노드 수만 개·건물 수십만 개 규모에서도 최근접 조회가 O(log n).
    경위도를 그대로 유클리드로 쓰는 근사지만 수 km 범위에선 순위가 거의 안 바뀐다.
    실제 거리(m)는 위도 보정해서 따로 환산한다."""

    def __init__(self, graph: nx.Graph):
        self.nodes = list(graph.nodes())
        self.tree = cKDTree(np.array(self.nodes)) if self.nodes else None

    def nearest(self, points: np.ndarray) -> tuple[list[tuple[float, float]], np.ndarray]:
        """points: (N,2) lon/lat -> (최근접 노드 리스트, 거리[m] 배열)."""
        if self.tree is None or len(points) == 0:
            return [], np.array([])
        _, idx = self.tree.query(points)
        nearest = [self.nodes[i] for i in idx]
        arr = np.array(nearest)
        dx = (points[:, 0] - arr[:, 0]) * 111320.0 * np.cos(np.radians(points[:, 1]))
        dy = (points[:, 1] - arr[:, 1]) * 110540.0
        return nearest, np.hypot(dx, dy)


def reachable_from_shelters(graph: nx.Graph, shelter_lonlat: list[tuple[float, float]]) -> set[tuple[float, float]]:
    """대피소 각각에서 BFS로 도달 가능한 노드를 모두 합친다 — "최소 1곳 대피소라도 갈 수 있는 노드 집합"."""
    reachable: set[tuple[float, float]] = set()
    if not shelter_lonlat or graph.number_of_nodes() == 0:
        return reachable
    nodes, _ = _NodeIndex(graph).nearest(np.array(shelter_lonlat, dtype=float))
    for node in set(nodes):
        if node not in reachable:
            reachable |= nx.node_connected_component(graph, node)
    return reachable


def _building_centroids(building_features: list[dict[str, Any]]) -> np.ndarray:
    pts = []
    for feature in building_features:
        geometry = feature.get("geometry")
        if not geometry:
            continue
        try:
            c = shapely.geometry.shape(geometry).centroid
        except Exception:
            continue
        pts.append((c.x, c.y))
    return np.array(pts, dtype=float).reshape(-1, 2)


def find_isolated_buildings(
    centroids: np.ndarray,
    graph: nx.Graph,
    reachable: set[tuple[float, float]],
    baseline_reachable: set[tuple[float, float]] | None = None,
) -> tuple[list[tuple[float, float]], dict[str, int]]:
    """건물 무게중심 -> 최근접 도로 노드 매핑, 그 노드가 도달가능집합 밖이면 고립.

    - 최근접 노드가 ISOLATION_MAX_SNAP_M보다 멀면 도로 데이터 밖 건물이라 판정에서 뺀다.
    - baseline_reachable(위험 적용 전 도달가능집합)이 주어지면, 위험이 없어도 원래
      대피소와 안 이어져 있던 건물(데이터 끊김/외딴 도로망)은 위험 때문에 고립된 게
      아니므로 뺀다. 반환: (고립 건물 좌표, 통계 {unmapped, preexisting}).
    """
    stats = {"unmapped": 0, "preexisting": 0}
    if len(centroids) == 0:
        return [], stats
    nodes, dist_m = _NodeIndex(graph).nearest(centroids)
    isolated: list[tuple[float, float]] = []
    for k, node in enumerate(nodes):
        if dist_m[k] > ISOLATION_MAX_SNAP_M:
            stats["unmapped"] += 1
            continue
        if node in reachable:
            continue
        if baseline_reachable is not None and node not in baseline_reachable:
            stats["preexisting"] += 1
            continue
        isolated.append((float(centroids[k][0]), float(centroids[k][1])))
    return isolated, stats


def cluster_isolated_buildings(points: list[tuple[float, float]]) -> list[dict[str, Any]]:
    """고립 건물들을 ISOLATION_CLUSTER_RADIUS_M 이내끼리 묶어 구역(convex hull)으로 만든다.
    구현: 두 건물이 반경 이내면 그래프 엣지로 잇고, 연결요소(connected component)를 클러스터로 삼는다.
    """
    if not points:
        return []
    points_5179 = [_TO_5179.transform(lon, lat) for lon, lat in points]

    cluster_graph = nx.Graph()
    cluster_graph.add_nodes_from(range(len(points)))
    cluster_graph.add_edges_from(cKDTree(np.array(points_5179)).query_pairs(ISOLATION_CLUSTER_RADIUS_M))

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
    """§7 /isolation-check의 핵심 로직.

    반환: {isolated_areas, isolated_buildings, isolated_building_count,
           blocked_roads, warnings}
    """
    warnings: list[str] = []
    road_features = fetch_roads(bbox)
    if not road_features:
        return {"isolated_areas": {"type": "FeatureCollection", "features": []},
                "isolated_buildings": {"type": "FeatureCollection", "features": []},
                "isolated_building_count": 0,
                "blocked_roads": {"type": "FeatureCollection", "features": []},
                "warnings": ["해당 영역에 도로 데이터 없음"]}

    # 위험영역 안에 있는 대피소는 후보에서 뺀다 — 물에 잠기는 곳으로 대피시킬 수 없다.
    hazard_shape = _hazard_shape(hazard_polygon)
    if hazard_shape is not None:
        usable = [s for s in shelter_candidates_lonlat if not hazard_shape.contains(shapely.geometry.Point(*s))]
        if len(usable) != len(shelter_candidates_lonlat):
            warnings.append(f"위험영역 안에 든 대피소 {len(shelter_candidates_lonlat) - len(usable)}곳은 후보에서 제외")
        shelter_candidates_lonlat = usable

    graph = build_road_graph(road_features)
    baseline_reachable = reachable_from_shelters(graph, shelter_candidates_lonlat)
    removed_edges = remove_hazard_edges(graph, hazard_polygon)
    blocked_roads = blocked_road_features(removed_edges)
    if removed_edges:
        warnings.append(f"위험지역과 겹치는 도로 {len(removed_edges)}개 구간 제거")

    reachable = reachable_from_shelters(graph, shelter_candidates_lonlat)
    if not reachable:
        warnings.append("대피소 근처에서 도로 그래프를 찾지 못함 — 도달가능성 계산 불가")

    centroids = _building_centroids(fetch_buildings(bbox))
    isolated_points, stats = find_isolated_buildings(centroids, graph, reachable, baseline_reachable)
    if stats["unmapped"]:
        warnings.append(f"도로에서 {int(ISOLATION_MAX_SNAP_M)}m 넘게 떨어진 건물 {stats['unmapped']}개는 도로 데이터 밖이라 판정 제외")
    if stats["preexisting"]:
        warnings.append(f"위험과 무관하게 원래 대피소와 도로가 이어지지 않던 건물 {stats['preexisting']}개는 제외(도로 데이터 끊김 가능성)")
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
        # 위험영역과 겹쳐 그래프에서 제거된 도로 구간. 고립 판정의 부산물이지만
        # "어느 도로가 끊기는가"는 그 자체로 대피 의사결정 정보라 함께 내보낸다.
        "blocked_roads": blocked_roads,
        "warnings": warnings,
    }
