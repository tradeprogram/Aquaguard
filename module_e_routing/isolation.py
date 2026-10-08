"""
고립마을 자동탐지 (§7 — 트랙④ 소유).

VWorld 도로망(LT_L_MOCTLINK)으로 networkx 그래프를 만들고, 위험폴리곤과 겹치는
도로를 제거한 뒤, 대피소들로부터 역방향 도달가능성을 계산한다. 그 도달 가능
집합에 들지 못한 건물(VWorld LT_C_SPBD)이 "고립"이다.

착수 순서(설계 문서 §7 그대로): 노드 스냅 → 위험 엣지 제거 → 역방향 도달가능성
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
from dataclasses import dataclass
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


def cache_file(layer: str, bbox: tuple[float, float, float, float]) -> Path:
    """VWorld 응답 캐시 파일 경로. 테스트가 캐시 유무로 건너뛸지 정할 때도 쓴다."""
    key = hashlib.md5(f"{layer}|{tuple(round(v, 5) for v in bbox)}".encode()).hexdigest()[:16]
    return FEATURE_CACHE_DIR / f"{layer}_{key}.json"


def _fetch_tiled_cached(layer: str, bbox: tuple[float, float, float, float]) -> list[dict[str, Any]]:
    """bbox를 타일로 쪼개 VWorld에서 받고 결과를 디스크에 캐시한다(§7.3 — 같은 bbox 재요청은
    API를 다시 안 부른다). 캐시를 비우려면 data/cache/isolation/ 폴더를 지우면 된다."""
    path = cache_file(layer, bbox)
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
    features: list[dict[str, Any]] = []
    for tile in _split_bbox(bbox):
        features.extend(_vworld_get_feature(layer, tile))
    features = _dedupe(features)
    try:
        FEATURE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(features), encoding="utf-8")
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
            graph.add_edge(
                na, nb, weight=weight,
                link_id=props.get("link_id"), road_name=props.get("road_name"),
                rd_type_h=props.get("rd_type_h"), rd_rank_h=props.get("rd_rank_h"),
                rest_h=props.get("rest_h"),
            )
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
    shape = hazard_shape(hazard_polygon)
    if shape is None:
        return []
    edges = list(graph.edges())
    if not edges:
        return []
    segments = shapely.linestrings([[u, v] for u, v in edges])
    hit = shapely.STRtree(segments).query(shape, predicate="intersects")
    to_remove = [edges[k] for k in hit]
    graph.remove_edges_from(to_remove)
    return to_remove


def hazard_shape(hazard_polygon: dict[str, Any] | None):
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


ROAD_ATTRS = ("link_id", "road_name", "rd_type_h", "rd_rank_h")


def blocked_road_features(removed_edges: list[tuple], graph: nx.Graph | None = None,
                          kind: str = "blocked_road", extra: dict | None = None) -> dict[str, Any]:
    """제거된 엣지 → GeoJSON FeatureCollection(lon/lat). 지도에서 빨간 도로로 그린다.

    graph를 주면 도로명·교량 여부·등급을 함께 싣는다 — "통행 불가"만 적힌 빨간 선으로는
    담당자가 어느 길인지, 다리인지 알 수 없다(현장조사 반영 ②)."""
    features = []
    for u, v in removed_edges:
        props: dict[str, Any] = {"kind": kind}
        if graph is not None and graph.has_edge(u, v):
            data = graph.edges[u, v]
            props.update({k: data.get(k) for k in ROAD_ATTRS})
        if extra:
            props.update(extra)
        features.append({
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": [list(u), list(v)]},
            "properties": props,
        })
    return {"type": "FeatureCollection", "features": features}


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


def reachable_from_shelters(graph: nx.Graph, shelter_lonlat: list[tuple[float, float]],
                            index: "_NodeIndex | None" = None) -> set[tuple[float, float]]:
    """대피소 각각에서 BFS로 도달 가능한 노드를 모두 합친다 — "최소 1곳 대피소라도 갈 수 있는 노드 집합".

    graph는 엣지를 숨긴 읽기 전용 뷰(nx.restricted_view)여도 된다. 노드 집합은 그대로라
    같은 노드 색인(index)을 재사용할 수 있다."""
    reachable: set[tuple[float, float]] = set()
    if not shelter_lonlat or graph.number_of_nodes() == 0:
        return reachable
    nodes, _ = (index or _NodeIndex(graph)).nearest(np.array(shelter_lonlat, dtype=float))
    for node in set(nodes):
        if node not in reachable:
            reachable |= nx.node_connected_component(graph, node)
    return reachable


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


ROAD_OVERRIDES_PATH = Path(__file__).resolve().parent.parent / "data" / "road_overrides.json"

# 구조차량 판정의 한계 — 응답마다 붙여, 0동이 "구조차량은 어디든 들어간다"로 읽히지 않게 한다.
RESCUE_LIMIT_NOTE = (
    "구조차량 판정은 높이 제한과 현장 보정 기록만 쓴다 — 도로 데이터에 폭 정보가 없고 "
    "마을안길은 도로망에 없다"
)


def load_road_overrides() -> dict[str, dict]:
    """현장 보정 기록 {link_id: {vehicle_passable, two_way, note, source, observed}}. 파일이 없으면 빈 dict.

    지도에서는 큰길과 똑같은 선 하나로 그려지지만 실제로는 차 한 대 폭이라 교행이 안 되는
    길이 있다(현장조사 2026-09-25). 도로 데이터에 폭이 없으니 현장에서 본 것을 여기 적는다.
    """
    if not ROAD_OVERRIDES_PATH.exists():
        return {}
    doc = json.loads(ROAD_OVERRIDES_PATH.read_text(encoding="utf-8"))
    return {str(r["link_id"]): r for r in doc.get("links", [])}


@dataclass
class IsolationContext:
    """그래프·건물 매핑처럼 위험과 무관한 것. 한 번만 만들고 위험 도형마다 evaluate()로 판정한다.

    시각별 판정(37시각)에서 이걸 매번 다시 만들면 군 전체에서 시각당 8초가 걸린다."""

    graph: nx.Graph
    index: _NodeIndex
    edges: list
    edge_tree: Any
    building_tree: Any
    centroids: np.ndarray
    node_of: list
    dist_m: np.ndarray
    vehicle_blocked: list
    override_links: set


def build_context(road_features: list[dict[str, Any]], building_features: list[dict[str, Any]]) -> IsolationContext:
    from . import policy

    graph = build_road_graph(road_features)
    edges = list(graph.edges())
    edge_tree = shapely.STRtree(shapely.linestrings([[u, v] for u, v in edges])) if edges else None

    shapes = []
    for feature in building_features:
        geometry = feature.get("geometry")
        if not geometry:
            continue
        try:
            shapes.append(shapely.geometry.shape(geometry))
        except Exception:
            continue
    building_tree = shapely.STRtree(shapes) if shapes else None
    centroids = np.array([(g.centroid.x, g.centroid.y) for g in shapes], dtype=float).reshape(-1, 2)
    index = _NodeIndex(graph)
    node_of, dist_m = index.nearest(centroids)

    # 구조차량 통행 불가 엣지. rest_veh_h("이륜차")는 쓰지 않는다 — 이륜차 통행 **금지**(고속국도)라
    # 구조차량과 무관하다. 높이 제한(cm)이 구조차량 높이보다 낮거나, 현장에서 통행 불가로 적은 링크만.
    height_cm = float(policy.load().value("rescue_vehicle_height_m")) * 100
    overrides = load_road_overrides()
    vehicle_blocked, override_links = [], set()
    for u, v, data in graph.edges(data=True):
        override = overrides.get(str(data.get("link_id")))
        try:
            rest_cm = float(data.get("rest_h") or 0)
        except (TypeError, ValueError):
            rest_cm = 0.0
        if override is not None and override.get("vehicle_passable") is False:
            vehicle_blocked.append((u, v))
            override_links.add(str(data.get("link_id")))
        elif 0 < rest_cm < height_cm:
            vehicle_blocked.append((u, v))
    return IsolationContext(graph, index, edges, edge_tree, building_tree, centroids, node_of,
                            dist_m if len(node_of) else np.array([]), vehicle_blocked, override_links)


def evaluate(ctx: IsolationContext, shelters: list[tuple[float, float]], hazard,
             closed_edges: list[tuple] | tuple = ()) -> dict[str, Any]:
    """위험 도형 하나(shapely 또는 None)에 대한 고립 판정.

    반환: isolated_idx(도로가 끊겨 고립된 건물 인덱스), direct_idx(위험영역에 겹친 건물),
    rescue_limited_idx(주민은 갈 수 있지만 구조차량은 못 들어가는 건물), removed_edges,
    usable_shelters, reachable, stats{unmapped, preexisting}.
    """
    usable = [s for s in shelters if hazard is None or not hazard.contains(shapely.geometry.Point(*s))]
    closed = list(closed_edges)

    # 기준 도달성은 통제·위험 적용 **전**이다. 통제 때문에 끊긴 건물이 "원래 끊겨 있던
    # 건물"로 숨으면 안 된다.
    baseline = reachable_from_shelters(ctx.graph, usable, ctx.index)
    removed: list[tuple] = []
    if hazard is not None and ctx.edge_tree is not None:
        removed = [ctx.edges[k] for k in ctx.edge_tree.query(hazard, predicate="intersects")]
    cut = nx.restricted_view(ctx.graph, [], closed + removed)
    reach = reachable_from_shelters(cut, usable, ctx.index)
    if ctx.vehicle_blocked:
        reach_vehicle = reachable_from_shelters(
            nx.restricted_view(ctx.graph, [], closed + removed + ctx.vehicle_blocked), usable, ctx.index)
    else:
        reach_vehicle = reach

    direct: set[int] = set()
    if hazard is not None and ctx.building_tree is not None:
        direct = {int(k) for k in ctx.building_tree.query(hazard, predicate="intersects")}

    isolated, rescue_limited = [], []
    stats = {"unmapped": 0, "preexisting": 0}
    for k, node in enumerate(ctx.node_of):
        if k in direct:
            continue
        if ctx.dist_m[k] > ISOLATION_MAX_SNAP_M:
            stats["unmapped"] += 1
            continue
        if node not in baseline:
            stats["preexisting"] += 1
            continue
        if node not in reach:
            isolated.append(k)
        elif node not in reach_vehicle:
            rescue_limited.append(k)
    return {
        "isolated_idx": isolated,
        "direct_idx": sorted(direct),
        "rescue_limited_idx": rescue_limited,
        "removed_edges": removed,
        "usable_shelters": usable,
        "reachable": reach,
        "stats": stats,
    }


def closed_edges_for(ctx: IsolationContext, closure_features: list[dict]) -> list[tuple[tuple, dict]]:
    """통제 구간 → [(엣지, 통제 속성)]. link_ids는 그 링크만 정확히, Polygon은 교차하는 엣지 전부.

    선 기하로 교차 검사하지 않는 이유: 교차로에서 만나는 다른 도로까지 끊긴다."""
    if not closure_features:
        return []
    by_link: dict[str, list[tuple]] = {}
    for u, v, data in ctx.graph.edges(data=True):
        by_link.setdefault(str(data.get("link_id")), []).append((u, v))
    out: list[tuple[tuple, dict]] = []
    seen: set[tuple] = set()
    for feature in closure_features:
        props = feature.get("properties") or {}
        hits: list[tuple] = []
        for link_id in props.get("link_ids") or []:
            hits.extend(by_link.get(str(link_id), []))
        if (feature.get("geometry") or {}).get("type") in ("Polygon", "MultiPolygon") and ctx.edge_tree is not None:
            zone = shapely.geometry.shape(feature["geometry"])
            hits.extend(ctx.edges[k] for k in ctx.edge_tree.query(zone, predicate="intersects"))
        for edge in hits:
            if edge not in seen:
                seen.add(edge)
                out.append((edge, props))
    return out


def _points(ctx: IsolationContext, idx: list[int]) -> list[tuple[float, float]]:
    return [(float(ctx.centroids[k][0]), float(ctx.centroids[k][1])) for k in idx]


def _point_fc(points: list[tuple[float, float]], **props) -> dict[str, Any]:
    return {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "geometry": {"type": "Point", "coordinates": [lon, lat]}, "properties": dict(props)}
            for lon, lat in points
        ],
    }


def check_isolation(
    bbox: tuple[float, float, float, float],
    shelter_candidates_lonlat: list[tuple[float, float]],
    hazard_polygon: dict[str, Any] | None = None,
    closures: list[dict] | None = None,
) -> dict[str, Any]:
    """§7 /isolation-check의 핵심 로직.

    closures: 그 시점에 유효한 통제 구간(module_e_routing.closures.active 결과). 위험과 별개로
    도로망에서 끊고, 침수로 끊긴 길(blocked_roads)과 따로 closed_roads로 보고한다.

    반환: {isolated_areas, isolated_buildings, isolated_building_count,
           blocked_roads, closed_roads, rescue_limited_buildings, rescue_limited_count, warnings}
    """
    warnings: list[str] = []
    road_features = fetch_roads(bbox)
    if not road_features:
        return {"isolated_areas": {"type": "FeatureCollection", "features": []},
                "isolated_buildings": {"type": "FeatureCollection", "features": []},
                "isolated_building_count": 0,
                "blocked_roads": {"type": "FeatureCollection", "features": []},
                "closed_roads": {"type": "FeatureCollection", "features": []},
                "rescue_limited_buildings": {"type": "FeatureCollection", "features": []},
                "rescue_limited_count": 0,
                "warnings": ["해당 영역에 도로 데이터 없음"]}

    hazard = hazard_shape(hazard_polygon)
    ctx = build_context(road_features, fetch_buildings(bbox))
    closed = closed_edges_for(ctx, closures or [])
    closed_set = {edge for edge, _ in closed}
    ev = evaluate(ctx, shelter_candidates_lonlat, hazard, list(closed_set))
    closed_roads = {"type": "FeatureCollection", "features": [
        f for edge, props in closed
        for f in blocked_road_features([edge], ctx.graph, kind="closed_road",
                                       extra={"closure_id": props.get("id"), "reason": props.get("reason")})["features"]
    ]}
    if closures:
        reasons = sorted({c["properties"]["reason"] for c in closures})
        warnings.append(f"통제 구간 {len(closures)}곳 반영(사유: {', '.join(reasons)})")

    # 위험영역 안에 있는 대피소는 후보에서 뺀다 — 물에 잠기는 곳으로 대피시킬 수 없다.
    excluded = len(shelter_candidates_lonlat) - len(ev["usable_shelters"])
    if excluded:
        warnings.append(f"위험영역 안에 든 대피소 {excluded}곳은 후보에서 제외")
    removed_edges = [e for e in ev["removed_edges"] if e not in closed_set]
    blocked_roads = blocked_road_features(removed_edges, ctx.graph)
    if removed_edges:
        warnings.append(f"위험지역과 겹치는 도로 {len(removed_edges)}개 구간 제거")
    if not ev["reachable"]:
        warnings.append("대피소 근처에서 도로 그래프를 찾지 못함 — 도달가능성 계산 불가")

    # 위험영역(침수)에 조금이라도 겹치는 건물은 도로 연결 여부와 무관하게 "대피소 도달 불가"로 센다 —
    # 건물 자체가 물에 잠기는데, 도로 데이터가 성겨서 가장 가까운 노드가 멀리 있는 마른 도로에
    # 이어져 있다는 이유로 안전해 보이면 안 된다(2026-09-21 산청 실측: 침수 건물 805채 중 179채가
    # 이 이유로 "도달 가능"으로 빠졌다). 도로 끊김으로 인한 고립과는 성격이 달라 개수를 따로 적는다.
    isolated_points = _points(ctx, ev["isolated_idx"])
    direct_points = _points(ctx, ev["direct_idx"])
    stats = ev["stats"]
    if direct_points:
        warnings.append(f"위험영역에 조금이라도 겹치는 건물 {len(direct_points)}채는 도로 연결과 무관하게 직접 피해로 포함(길이 끊겨서가 아니라 건물이 잠기는 경우)")
        isolated_points = isolated_points + direct_points
    if stats["unmapped"]:
        warnings.append(f"도로에서 {int(ISOLATION_MAX_SNAP_M)}m 넘게 떨어진 건물 {stats['unmapped']}개는 도로 데이터 밖이라 판정 제외")
    if stats["preexisting"]:
        warnings.append(f"위험과 무관하게 원래 대피소와 도로가 이어지지 않던 건물 {stats['preexisting']}개는 제외(도로 데이터 끊김 가능성)")

    rescue_points = _points(ctx, ev["rescue_limited_idx"])
    if rescue_points:
        warnings.append(f"주민은 대피소까지 갈 수 있지만 구조차량이 들어가기 어려운 건물 {len(rescue_points)}동(높이 제한·현장 보정 기록 기준)")
    if ctx.override_links:
        warnings.append(f"현장 보정 기록 {len(ctx.override_links)}개 링크 반영")
    warnings.append(RESCUE_LIMIT_NOTE)

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
        "closed_roads": closed_roads,
        "rescue_limited_buildings": _point_fc(rescue_points, kind="rescue_limited"),
        "rescue_limited_count": len(rescue_points),
        "warnings": warnings,
    }


def isolation_timeline(
    bbox: tuple[float, float, float, float],
    shelter_candidates_lonlat: list[tuple[float, float]],
    hazards_by_hour: dict[int, dict[str, Any] | None],
    reference_hour: int,
    low_water_hour: int | None = None,
    closures: list[dict] | None = None,
) -> dict[str, Any]:
    """시각별 위험으로 고립을 다시 판정해 군집별 진입로 단절 시각을 낸다(현장조사 반영 ①).

    건물의 단절 구간 = 기준 시각(침수가 가장 넓은 시각)에 고립된 건물에 대해, 기준 시각부터
    거꾸로 거슬러 올라가며 계속 고립이던 구간. 그 구간이 low_water_hour(창 안의 저수위
    시각, 없으면 자료의 첫 시각)까지 이어지면 '늘 끊긴' 건물(persistent)이다 — 이번 홍수가
    끊은 것이 아니므로 대피 시한을 매기지 않는다.

    군집의 단절 시각 = 늘 끊긴 건물을 뺀 구성 건물들의 구간 시작 중 가장 이른 값. 마을의
    일부라도 먼저 끊기면 그때가 마을 대피의 기준이다. 구성 건물이 모두 늘 끊긴 건물이면
    군집도 persistent다.

    그래프·건물 매핑은 한 번만 만든다(build_context). 시각마다 다시 만들면 군 전체에서
    시각당 8초가 걸린다.

    반환: {hours, reference_hour, low_water_hour, isolated_count_by_hour,
           clusters: [{geometry, building_count, centroid, bbox, cut_hour, persistent, persistent_count}]}
    """
    ctx = build_context(fetch_roads(bbox), fetch_buildings(bbox))
    closed = [edge for edge, _ in closed_edges_for(ctx, closures or [])]
    hours = sorted(hazards_by_hour)
    flags: dict[int, set[int]] = {}
    for hour in hours:
        ev = evaluate(ctx, shelter_candidates_lonlat, hazard_shape(hazards_by_hour[hour]), closed)
        flags[hour] = set(ev["isolated_idx"]) | set(ev["direct_idx"])

    boundary = hours.index(low_water_hour) if low_water_hour is not None else 0
    ref_pos = hours.index(reference_hour)
    start_of: dict[int, int] = {}
    persistent: set[int] = set()
    for k in flags[reference_hour]:
        pos = ref_pos
        while pos - 1 >= 0 and k in flags[hours[pos - 1]]:
            pos -= 1
        start_of[k] = hours[pos]
        if pos <= boundary:
            persistent.add(k)

    idx = sorted(flags[reference_hour])
    points = _points(ctx, idx)
    # 건물 기록 두 개가 무게중심을 공유할 수 있어(같은 건물의 중복 등록) 점 하나에 여러 건물을 단다.
    by_point: dict[tuple[float, float], list[int]] = {}
    for point, k in zip(points, idx):
        by_point.setdefault(point, []).append(k)
    clusters = []
    for c in cluster_isolated_buildings(points):
        members = [k for p in set(c["member_points"]) for k in by_point[p]]
        event = [k for k in members if k not in persistent]
        clusters.append({
            "geometry": c["geometry"],
            "building_count": c["building_count"],
            "centroid": c["centroid"],
            "bbox": c["bbox"],
            "cut_hour": min(start_of[k] for k in (event or members)),
            "persistent": not event,
            "persistent_count": len(members) - len(event),
        })
    return {
        "hours": hours,
        "reference_hour": reference_hour,
        "low_water_hour": low_water_hour,
        "isolated_count_by_hour": {h: len(flags[h]) for h in hours},
        "clusters": clusters,
    }
