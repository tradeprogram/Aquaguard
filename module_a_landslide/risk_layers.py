"""module_a_landslide.risk_layers — 사전계산 위험 폴리곤 로더.

`scripts/45_risk_polygons_timeseries.py` 가 산청 전역 5m 격자를 실측 강우로 구동해
만든 GeoJSON(EPSG:5179)을 읽어, Module O 가 `risk_polygons[].geometry_5179` 에 그대로
넣을 수 있는 FeatureCollection 으로 돌려준다.

이게 없으면 Module O 는 트리거 지점을 반경 100m 로 버퍼링한 원을 위험영역으로 쓴다
(orchestrator 경고: "점 좌표를 반경 100.0m로 버퍼링 — 실제 위험영역이 아니라 가정값").
3D 시뮬레이터도 마찬가지로 손으로 배치한 흐름 경로를 써 왔다.

시나리오를 섞지 말 것:
  A_soilmap    토양도 토성 — Module A(soil_sampler)가 실제로 쓰는 값. **기본값**
  B_weathered  풍화화강토 가정 — 면적이 100배 크다. 명시적으로 고를 때만 쓴다

각 feature 의 `arrival_hour` 는 그 영역이 임계를 **처음 넘은 시각**이다(붕괴 시각이
아니다). 시점을 주면 그 시각까지 도달한 영역만 누적해서 돌려주므로, 시간을 넘기며
호출하면 위험이 번져가는 애니메이션이 된다.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_DIR = Path(__file__).resolve().parent / "data" / "risk_polygons"

DEFAULT_SCENARIO = "A_soilmap"   # Module A 가 실제로 쓰는 지반정수와 정합
DEFAULT_LEVEL = "critical"       # landslide_prob >= 0.7 — Module O 트리거와 같은 임계

_EMPTY: dict[str, Any] = {"type": "FeatureCollection", "features": []}


def _path(scenario: str, level: str) -> Path:
    return _DIR / f"risk_landslide_{scenario}_{level}_5179.geojson"


@lru_cache(maxsize=8)
def _load_raw(scenario: str, level: str) -> str | None:
    p = _path(scenario, level)
    if not p.exists():
        return None
    try:
        return p.read_text(encoding="utf-8")
    except OSError:
        return None


def available(scenario: str = DEFAULT_SCENARIO, level: str = DEFAULT_LEVEL) -> bool:
    return _load_raw(scenario, level) is not None


def load(scenario: str = DEFAULT_SCENARIO, level: str = DEFAULT_LEVEL,
         arrival_hour: int | None = None) -> dict[str, Any]:
    """위험 폴리곤 FeatureCollection(EPSG:5179).

    arrival_hour 를 주면 그 시각까지 임계에 도달한 영역만 누적해서 돌려준다.
    레이어가 없으면 빈 FeatureCollection — 호출부는 종전 폴백(점 버퍼)으로 돌아간다.
    """
    raw = _load_raw(scenario, level)
    if raw is None:
        return dict(_EMPTY)
    try:
        fc = json.loads(raw)
    except json.JSONDecodeError:
        return dict(_EMPTY)

    feats = fc.get("features") or []
    if arrival_hour is not None:
        feats = [f for f in feats
                 if (f.get("properties") or {}).get("arrival_hour", 0) <= arrival_hour]
    return {
        "type": "FeatureCollection",
        "crs": fc.get("crs"),
        "properties": fc.get("properties"),
        "features": feats,
    }


def total_area_m2(scenario: str = DEFAULT_SCENARIO, level: str = DEFAULT_LEVEL,
                  arrival_hour: int | None = None) -> float:
    fc = load(scenario, level, arrival_hour)
    return round(sum(float((f.get("properties") or {}).get("area_m2", 0.0))
                     for f in fc["features"]), 1)


# 계약(module_a.schema.json, 안건 1 2026-09-04 합의)이 요구하는 risk_polygon_5179 는
# "이 경보의 산사태 위험영역"이다. 전 군(郡) 레이어를 통째로 넘기면 경보 지점과
# 무관한 반대편 사면까지 노출·대피 계산에 들어가므로, 질의 지점 주변만 잘라 준다.
LOCAL_RADIUS_M = 2000.0


def _ring_bbox(ring: list) -> tuple[float, float, float, float]:
    xs = [c[0] for c in ring]
    ys = [c[1] for c in ring]
    return min(xs), min(ys), max(xs), max(ys)


def _bbox_distance(bbox: tuple[float, float, float, float], x: float, y: float) -> float:
    """점에서 bbox 까지의 거리. 안에 있으면 0. (shapely 없이 순수 파이썬)"""
    minx, miny, maxx, maxy = bbox
    dx = max(minx - x, 0.0, x - maxx)
    dy = max(miny - y, 0.0, y - maxy)
    return (dx * dx + dy * dy) ** 0.5


def local(x_5179: float | None, y_5179: float | None,
          radius_m: float = LOCAL_RADIUS_M,
          scenario: str = DEFAULT_SCENARIO, level: str = DEFAULT_LEVEL,
          arrival_hour: int | None = None) -> dict[str, Any] | None:
    """질의 지점 반경 안의 위험영역만 MultiPolygon 으로. 없으면 None.

    None 이면 계약대로 Module D 가 location 을 반경 버퍼로 흡수하고 degraded 로
    내린다 — 없는 위험영역을 지어내지 않는다.
    """
    if x_5179 is None or y_5179 is None:
        return None
    fc = load(scenario, level, arrival_hour)
    parts: list = []
    for feat in fc.get("features") or []:
        geom = feat.get("geometry") or {}
        gtype = geom.get("type")
        if gtype == "Polygon":
            polys = [geom.get("coordinates") or []]
        elif gtype == "MultiPolygon":
            polys = geom.get("coordinates") or []
        else:
            continue
        for poly in polys:
            if not poly or not poly[0]:
                continue
            if _bbox_distance(_ring_bbox(poly[0]), float(x_5179), float(y_5179)) <= radius_m:
                parts.append(poly)
    if not parts:
        return None
    return {"type": "MultiPolygon", "coordinates": parts}

