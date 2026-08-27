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
