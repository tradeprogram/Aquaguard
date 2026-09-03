"""
Module E — 대피경로·고립분석 (§5, contracts/module_e.schema.json).

run(input)이 이 패키지의 유일한 공개 인터페이스다 — module_o_orchestrator/modules_client.py가
AQUAGUARD_MOCK_MODE=0일 때 importlib로 이 패키지를 불러와 run()만 호출한다(§4.2 공통 봉투 규약).

1단계 구현: 위험폴리곤에 걸친 대피소 제외 → 네이버 Directions 5(자동차)로 실제 도로
경로/시간 조회, 실패 시 직선거리 근사로 폴백 → 시간예산 내 도달 가능한 곳 중 최단 선택.
도보 시간은 §6.3 원칙대로 공개 API가 없어 하버사인 직선거리 ÷ 4km/h 근사로만 계산한다
(contracts에는 아직 없지만 UI가 필요로 하는 값이라 output.modes에 부가 정보로 얹는다 —
module_e.schema.json은 output.data에 additionalProperties 제한이 없어 안전하게 확장 가능).
"""
from __future__ import annotations

import math
import os
from typing import Any

import requests
from pyproj import Transformer

_TO_WGS84 = Transformer.from_crs("EPSG:5179", "EPSG:4326", always_xy=True)
_TO_5179 = Transformer.from_crs("EPSG:4326", "EPSG:5179", always_xy=True)

NAVER_DIRECTIONS_URL = "https://maps.apigw.ntruss.com/map-direction/v1/driving"
WALK_KMH = 4.0  # §6.3 — 공개 API에 도보 경로가 없어 직선거리 근사에 쓰는 가정 속도
CAR_KMH_FALLBACK = 30.0  # 네이버 API 호출 실패 시 직선거리 근사에 쓰는 가정 속도(산간도로 보정 반영)


def point_5179_to_lonlat(x_5179: float, y_5179: float) -> tuple[float, float]:
    lon, lat = _TO_WGS84.transform(x_5179, y_5179)
    return lon, lat


def point_lonlat_to_5179(lon: float, lat: float) -> tuple[float, float]:
    x, y = _TO_5179.transform(lon, lat)
    return x, y


def _haversine_km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    r = 6371.0
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lon / 2) ** 2
    )
    return 2 * r * math.asin(math.sqrt(a))


def _shelter_blocked_by_risk(shelter: dict[str, Any], risk_polygons: list[dict[str, Any]]) -> bool:
    """대피소 좌표가 위험폴리곤 내부에 있으면 후보에서 제외한다.

    geometry_5179가 빈 dict({})인 경우가 흔하다(Module A/B가 아직 실제 폴리곤을 안 주고
    location 점 좌표만 주는 목업 단계 — module_o_orchestrator/orchestrator.py 참조).
    그런 경우 형체가 없어 판별 불가하므로 안전하게 "제외 안 함"으로 둔다(§6 불확실성 원칙:
    모르면 폴백하되 침묵하지 않음 — 판단 근거 없음을 warnings로 alert에 남길지는 상위(Module O)의
    risk_prob 값으로 이미 표현되므로 여기서 추가 경고는 만들지 않는다).
    """
    import shapely.geometry

    for risk in risk_polygons:
        geom = risk.get("geometry_5179")
        if not geom or not geom.get("type"):
            continue
        try:
            polygon = shapely.geometry.shape(geom)
            point = shapely.geometry.Point(shelter["x_5179"], shelter["y_5179"])
            if polygon.contains(point):
                return True
        except Exception:
            continue
    return False


def _naver_driving_route(origin_lonlat: tuple[float, float], dest_lonlat: tuple[float, float]) -> dict[str, Any] | None:
    """네이버 Directions 5 API로 실제 도로 경로/시간을 조회한다. 키 미설정·호출 실패 시 None."""
    client_id = os.environ.get("NAVER_CLIENT_ID")
    client_secret = os.environ.get("NAVER_CLIENT_SECRET")
    if not client_id or not client_secret:
        return None
    try:
        resp = requests.get(
            NAVER_DIRECTIONS_URL,
            params={
                "start": f"{origin_lonlat[0]},{origin_lonlat[1]}",
                "goal": f"{dest_lonlat[0]},{dest_lonlat[1]}",
                "option": "trafast",  # 실시간 빠른길 — 재난 대피 상황에 맞는 옵션
            },
            headers={
                "x-ncp-apigw-api-key-id": client_id,
                "x-ncp-apigw-api-key": client_secret,
            },
            timeout=5,
        )
        resp.raise_for_status()
        body = resp.json()
        if body.get("code") != 0:
            return None
        route = body["route"]["trafast"][0]
        duration_min = route["summary"]["duration"] / 1000 / 60  # ms -> min
        path_lonlat = route["path"]  # [[lon, lat], ...]
        return {"duration_min": duration_min, "path_lonlat": path_lonlat}
    except (requests.RequestException, KeyError, IndexError):
        return None


def evaluate_candidates(input: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:  # noqa: A002
    """대피소 후보 전체 각각의 경로/시간을 계산해서 돌려준다 (run()이 내부에서 최적 1곳만
    고르기 전 단계 — EvacuationPanel처럼 여러 후보를 동시에 비교해서 보여주는 화면은
    이 함수를 직접 쓴다). 반환: (결과 리스트, 경고 리스트).
    """
    origin = input["origin"]
    risk_polygons = input.get("risk_polygons", [])
    shelter_candidates = input.get("shelter_candidates", [])
    time_budget_hours = input.get("time_budget_hours")
    time_budget_min = time_budget_hours * 60 if time_budget_hours is not None else None

    warnings: list[str] = []
    origin_lonlat = point_5179_to_lonlat(origin["x_5179"], origin["y_5179"])

    candidates = [s for s in shelter_candidates if not _shelter_blocked_by_risk(s, risk_polygons)]
    if not candidates:
        return [], ["모든 대피소 후보가 위험지역 내부에 있어 제외됨 — 안전지대 재탐색 필요"]

    results = []
    any_naver_used = False
    for shelter in candidates:
        dest_lonlat = point_5179_to_lonlat(shelter["x_5179"], shelter["y_5179"])
        distance_km = _haversine_km(*origin_lonlat, *dest_lonlat)
        walk_min = (distance_km / WALK_KMH) * 60

        naver = _naver_driving_route(origin_lonlat, dest_lonlat)
        if naver is not None:
            any_naver_used = True
            car_min = naver["duration_min"]
            route_confidence = "high"
            fallback_used = False
            route_coords_5179 = [list(point_lonlat_to_5179(lon, lat)) for lon, lat in naver["path_lonlat"]]
        else:
            car_min = (distance_km / CAR_KMH_FALLBACK) * 60
            route_confidence = "low"
            fallback_used = True
            route_coords_5179 = [
                [origin["x_5179"], origin["y_5179"]],
                [shelter["x_5179"], shelter["y_5179"]],
            ]

        time_feasible = car_min <= time_budget_min if time_budget_min is not None else True
        time_margin_min = (time_budget_min - car_min) if time_budget_min is not None else None

        results.append(
            {
                "shelter_id": shelter["shelter_id"],
                "route_5179": {"type": "LineString", "coordinates": route_coords_5179},
                "eta_min": round(car_min, 1),
                "route_confidence": route_confidence,
                "time_feasible": time_feasible,
                "time_margin_min": round(time_margin_min, 1) if time_margin_min is not None else None,
                "fallback_used": fallback_used,
                "modes": {
                    "car": {"eta_min": round(car_min, 1), "source": "naver_directions" if not fallback_used else "straight_line_approx"},
                    "walk": {"eta_min": round(walk_min, 1), "source": "straight_line_approx"},
                },
            }
        )

    if not any_naver_used:
        warnings.append("네이버 Directions API 미사용(키 없음 또는 호출 실패) — 전 후보 직선거리 근사")

    return results, warnings


def run(input: dict[str, Any]) -> dict[str, Any]:  # noqa: A002 - §4.2 규약이 지정한 이름
    results, warnings = evaluate_candidates(input)
    if not results:
        return {
            "status": "degraded",
            "fallback_tier": 3,
            "data": {
                "shelter_id": None,
                "route_5179": {"type": "LineString", "coordinates": []},
                "eta_min": None,
                "route_confidence": "low",
                "time_feasible": False,
                "time_margin_min": None,
                "fallback_used": True,
            },
            "warnings": warnings,
        }

    feasible = [r for r in results if r["time_feasible"]]
    pool = feasible if feasible else results
    best = min(pool, key=lambda r: r["eta_min"])
    if not feasible:
        warnings.append("시간예산 내 도달 가능한 대피소 없음 — 가장 빠른 후보로 대체")

    status = "ok" if not best["fallback_used"] and feasible else "degraded"
    fallback_tier = 1 if (not best["fallback_used"] and feasible) else 2

    return {
        "status": status,
        "fallback_tier": fallback_tier,
        "data": best,
        "warnings": warnings,
    }
