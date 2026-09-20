"""
좌표 재투영 — §4.1: "이 재투영은 Module UI/UI-3D 쪽 출력 직전에만 수행".
내부 모듈 교환은 전부 EPSG:5179(미터)이고, 이 파일이 3D 지도(deck.gl/MapLibre)에
내보내기 직전 EPSG:4326([lon, lat], RFC 7946)으로 바꾸는 유일한 지점이다.
"""
from __future__ import annotations

import math

from pyproj import Transformer

_to_wgs84 = Transformer.from_crs("EPSG:5179", "EPSG:4326", always_xy=True)


def point_5179_to_lonlat(x_5179: float, y_5179: float) -> list[float]:
    lon, lat = _to_wgs84.transform(x_5179, y_5179)
    return [round(lon, 6), round(lat, 6)]


def geometry_5179_to_lonlat(geometry: dict | None) -> dict | None:
    """GeoJSON 지오메트리(EPSG:5179) → EPSG:4326. 좌표 중첩 깊이에 무관하게 동작한다.

    Point/LineString/Polygon/Multi*를 전부 받는다 — coordinates 트리를 내려가다
    [x, y] 쌍을 만나면 그 자리에서 변환한다. 지오메트리가 없거나 coordinates가
    비면 None을 돌려주어 호출부가 feature를 만들지 않게 한다.
    """
    if not isinstance(geometry, dict):
        return None
    coords = geometry.get("coordinates")
    if coords is None:
        return None

    def walk(node):
        if (isinstance(node, (list, tuple)) and len(node) >= 2
                and all(isinstance(v, (int, float)) for v in node[:2])):
            return point_5179_to_lonlat(float(node[0]), float(node[1]))
        if isinstance(node, (list, tuple)):
            return [walk(item) for item in node]
        return node

    return {"type": geometry.get("type"), "coordinates": walk(coords)}


def featurecollection_5179_to_lonlat(fc: dict | None) -> list[dict]:
    """FeatureCollection(EPSG:5179) → 4326 feature 리스트. properties는 그대로 둔다."""
    if not isinstance(fc, dict) or fc.get("type") != "FeatureCollection":
        return []
    out: list[dict] = []
    for feature in fc.get("features") or []:
        geometry = geometry_5179_to_lonlat(feature.get("geometry"))
        if geometry is None:
            continue
        out.append({"type": "Feature", "geometry": geometry,
                    "properties": dict(feature.get("properties") or {})})
    return out


def circle_5179_to_lonlat(x_5179: float, y_5179: float, radius_m: float, n_points: int = 48) -> list[list[float]]:
    """중심(x_5179,y_5179), 반경 radius_m인 원을 5179(미터) 평면에서 근사한 뒤 4326으로 재투영.

    실제 산사태 위험 폴리곤 지오메트리(risk_polygons[].geometry_5179)가 아직 비어있는
    목업 단계라, InSAR 트리거 반경(§5 Module H trigger_radius_m)을 시각적 근사치로 쓴다.
    """
    ring = []
    for i in range(n_points + 1):
        angle = 2 * math.pi * i / n_points
        px = x_5179 + radius_m * math.cos(angle)
        py = y_5179 + radius_m * math.sin(angle)
        ring.append(point_5179_to_lonlat(px, py))
    return ring
