"""
FastAPI 서버 — §4.2: 각 모듈을 REST로 쪼개지 않고 이 프로세스가 import해서
순서대로 호출한다(MOFOM 패턴). 지금은 module_o_orchestrator만 연결돼 있고,
다른 트랙 모듈이 준비되면 module_o_orchestrator/modules_client.py의
MODULE_PACKAGES를 통해 그대로 실제 모듈로 교체된다.
"""
from __future__ import annotations

import json
import math
import os
import re
from pathlib import Path
from typing import Literal

import geopandas as gpd
import requests
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from google import genai
from google.genai import types as genai_types
from pydantic import BaseModel

import module_e_routing
from module_e_routing import isolation as module_e_isolation
from module_o_orchestrator import geo
from module_o_orchestrator.orchestrator import DEFAULT_SHELTER_CANDIDATES, run as run_orchestrator
from module_o_orchestrator.store import alert_store

load_dotenv()  # .env(git-ignore됨)의 VWORLD_API_KEY 등을 os.environ으로 로드

DATA_VECTOR_DIR = Path(__file__).resolve().parent / "data" / "vector"
VWORLD_API_KEY = os.environ.get("VWORLD_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-flash-latest")

app = FastAPI(title="AquaGuard AI — api_server")

# ui/(Next.js dev server, 기본 3000포트)에서 로컬 개발 중 호출할 수 있도록 허용 +
# Vercel 배포 도메인(프로덕션 URL은 매번 같지만 프리뷰 배포마다 서브도메인이 바뀌므로
# 정규식으로 *.vercel.app 전체를 허용 — 이 백엔드는 인증이 없어 오리진 제한이
# 유일한 방어선은 아니지만, 최소한 임의 사이트의 크로스오리진 호출은 막아둔다).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_methods=["*"],
    allow_headers=["*"],
)


class TriggerRequest(BaseModel):
    alert_id: str
    trigger_location: dict[str, float]
    timestamp: str
    escalation_timeout_min: int = 15
    safety_margin_hours: float = 0.5


class ApproveRequest(BaseModel):
    decision: Literal["승인", "거부"]
    approver_id: str


@app.post("/alerts/trigger")
def trigger_alert(req: TriggerRequest) -> dict:
    """Module A/B 감시 결과 임계치를 넘었다고 가정하고 Module O 파이프라인을 실행한다.
    (실제 연동 시에는 Module A/B의 상시 감시 루프가 임계치 초과를 감지했을 때 이 함수를 내부 호출하게 된다.)
    """
    return run_orchestrator(req.model_dump())


@app.get("/alerts/{alert_id}")
def get_alert(alert_id: str) -> dict:
    alert = alert_store.get(alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="alert not found")
    envelope = dict(alert.envelope)
    envelope["data"] = {
        **envelope["data"],
        "approval_status": alert.resolve_status(),
        "escalation_level": alert.escalation_level,
    }
    # 계약(§4.2)의 4개 필드 밖에 붙는 부가 메타 — UI의 escalation 카운트다운용
    envelope["meta"] = {
        "created_at": alert.created_at.isoformat(),
        "escalation_timeout_min": alert.escalation_timeout_min,
    }
    return envelope


@app.post("/approve/{alert_id}")
def approve_alert(alert_id: str, req: ApproveRequest) -> dict:
    """§5 Module O — 원클릭 승인 엔드포인트."""
    alert = alert_store.approve(alert_id, req.decision, req.approver_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="alert not found")
    return {
        "alert_id": alert.alert_id,
        "approval_status": alert.resolve_status(),
        "escalation_level": alert.escalation_level,
        "approver_id": alert.approver_id,
    }


@app.get("/alerts/{alert_id}/geojson")
def get_alert_geojson(alert_id: str) -> dict:
    """§5 Module UI-3D 입력 — 여기서만 EPSG:5179 → EPSG:4326 재투영을 수행한다(§4.1).

    Module B의 inundation_extent_5179, Module E의 route_5179는 아직 목업 단계라
    좌표가 비어있으므로(contracts/module_b·e.example.json 참조), 산사태 지점 반경
    버퍼 원과 출발지→대피소 직선을 시각적 placeholder로 대신 그린다.
    """
    alert = alert_store.get(alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="alert not found")

    landslide = alert.envelope["data"]["alert_package"]["landslide"]
    shelter_route = alert.envelope["data"]["alert_package"].get("shelter_route") or {}
    # landslide["location"]이 아니라 원래 요청의 trigger_location을 쓴다 — 목업 모드에서는
    # Module A가 입력을 무시하고 contracts/module_a.example.json의 고정 location을 돌려주므로
    # (문서가 명시한 "예시 값"), 지도에는 실제 질의 위치(AOI 내부)를 그리는 게 맞다.
    loc = alert.trigger_input.get("trigger_location")
    features: list[dict] = []

    if loc:
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": geo.point_5179_to_lonlat(loc["x_5179"], loc["y_5179"])},
                "properties": {
                    "kind": "landslide_point",
                    "landslide_prob": landslide["landslide_prob"],
                    "precursor_flag": landslide["precursor_flag"],
                },
            }
        )
        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [geo.circle_5179_to_lonlat(loc["x_5179"], loc["y_5179"], radius_m=500)],
                },
                "properties": {
                    "kind": "risk_buffer_placeholder",
                    "note": "실제 risk_polygons 지오메트리 연동 전 시각적 근사(§5 Module H trigger_radius_m=500m 기준)",
                    "risk_prob": landslide["landslide_prob"],
                },
            }
        )

    shelter = (alert.trigger_input.get("shelter_candidates") or DEFAULT_SHELTER_CANDIDATES)[0]
    features.append(
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": geo.point_5179_to_lonlat(shelter["x_5179"], shelter["y_5179"])},
            "properties": {"kind": "shelter_point", "shelter_id": shelter["shelter_id"]},
        }
    )

    if loc and shelter_route.get("shelter_id"):
        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [
                        geo.point_5179_to_lonlat(loc["x_5179"], loc["y_5179"]),
                        geo.point_5179_to_lonlat(shelter["x_5179"], shelter["y_5179"]),
                    ],
                },
                "properties": {
                    "kind": "route_placeholder",
                    "note": "실제 route_5179(위험가중 A*) 연동 전 직선 placeholder",
                    "eta_min": shelter_route.get("eta_min"),
                    "time_feasible": shelter_route.get("time_feasible"),
                    "fallback_used": shelter_route.get("fallback_used"),
                },
            }
        )

    return {"type": "FeatureCollection", "features": features}


ADM_LEVELS = ("sido", "sigungu", "dong")
ADM_GEOJSON_PATHS = {level: DATA_VECTOR_DIR / f"adm_{level}_5179.geojson" for level in ADM_LEVELS}
ADM_SEARCH_INDEX_PATH = DATA_VECTOR_DIR / "adm_index.json"
MAX_BOUNDARY_FEATURES_PER_LEVEL = 500

_adm_gdf_4326_cache: dict[str, gpd.GeoDataFrame] = {}
_adm_search_index: list[dict] | None = None


def _get_adm_gdf(level: str) -> gpd.GeoDataFrame:
    """전국 행정경계 3계층(사용자 제공 BND_ADM_DONG_PG를 §4.1 규약대로 EPSG:5179에 저장,
    시군구·시도는 그 원본 지오메트리를 dissolve해서 만듦 — data/vector/README나 커밋
    메시지 참조)을 프로세스 시작 후 최초 요청 시 한 번만 읽어 4326으로 캐시한다
    (§4.1: 재투영은 UI 출력 직전에만).
    """
    if level not in _adm_gdf_4326_cache:
        gdf = gpd.read_file(ADM_GEOJSON_PATHS[level])
        _adm_gdf_4326_cache[level] = gdf.to_crs("EPSG:4326")
    return _adm_gdf_4326_cache[level]


def _get_adm_search_index() -> list[dict]:
    global _adm_search_index
    if _adm_search_index is None:
        with open(ADM_SEARCH_INDEX_PATH, encoding="utf-8") as f:
            _adm_search_index = json.load(f)
    return _adm_search_index


@app.get("/boundaries")
def get_boundaries(bbox: str) -> dict:
    """현재 지도 뷰포트에 걸리는 행정경계를 시도/시군구/읍면동 3계층 모두 반환한다
    (EPSG:4326, {"sido": FeatureCollection, "sigungu": ..., "dong": ...}).

    bbox: "minLon,minLat,maxLon,maxLat" — 전국 데이터를 한 번에 안 내려주고 뷰포트
    기준으로 잘라주는 이유는 프론트가 나라 전체를 한 번에 로드하지 않게 하기 위함
    (§4.1 재투영 규약 + 성능). 검색으로 지역 이동한 뒤 moveend에서 다시 호출하면 됨.
    """
    try:
        minx, miny, maxx, maxy = (float(v) for v in bbox.split(","))
    except ValueError:
        raise HTTPException(status_code=400, detail="bbox must be 'minLon,minLat,maxLon,maxLat'")

    result: dict[str, dict] = {}
    for level in ADM_LEVELS:
        clipped = _get_adm_gdf(level).cx[minx:maxx, miny:maxy]
        if len(clipped) > MAX_BOUNDARY_FEATURES_PER_LEVEL:
            clipped = clipped.iloc[:MAX_BOUNDARY_FEATURES_PER_LEVEL]
        result[level] = json.loads(clipped.to_json())
    return result


@app.get("/search")
def search_admin(q: str) -> list[dict]:
    """행정구역 이름 검색(도/광역시, 시/군/구, 읍/면/동 3계층 모두, 부분일치) — 검색창에서
    지역 이동에 사용. 각 결과: {level, code, name, full_name, center:[lon,lat],
    bbox:[minLon,minLat,maxLon,maxLat]}. full_name이 "경상남도 산청군 생비량면"처럼
    상위 지명까지 포함돼 있어 동명이지(예: 여러 시/군의 "중앙동")를 구분할 수 있다 —
    data/vector/adm_index.json이 사용자 제공 데이터의 코드 체계를 vuski/admdongkor
    (동일 SGIS adm_cd 스킴, MIT 라이선스)와 매칭해 상위 지명을 붙인 결과.
    """
    q = q.strip()
    if not q:
        return []
    index = _get_adm_search_index()
    matches = [row for row in index if q in row["name"] or q in row["full_name"]]
    matches.sort(key=lambda r: (not r["name"].startswith(q), len(r["full_name"])))
    return matches[:20]


@app.get("/terrain-tiles/{z}/{x}/{y}.png")
def get_terrain_tile(z: int, x: int, y: int) -> Response:
    """AWS 공개 지형 타일(elevation-tiles-prod, terrarium 인코딩) 프록시.

    브라우저가 직접 이 S3 버킷을 호출하면 Access-Control-Allow-Origin 헤더가
    없어서 MapLibre가 지형 고도값을 읽지 못해(캔버스 오염) 3D 렌더링이 조용히
    실패한다. 서버 간 호출은 CORS 제약이 없으므로 여기서 대신 가져와 우리
    CORSMiddleware가 붙인 헤더로 돌려준다. V-World API 키가 생기면(§2.3 1순위)
    이 프록시를 그쪽으로 바꿔치기하면 된다.
    """
    cache_key = ("terrain", z, x, y)
    cached = _IMAGERY_CACHE.get(cache_key)
    if cached is not None:
        return Response(content=cached, media_type="image/png", headers={"Cache-Control": "public, max-age=86400"})

    upstream = f"https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"
    try:
        resp = requests.get(upstream, timeout=5)
    except requests.RequestException as e:
        # 2026-08-28: 전에는 여기 예외 처리가 없어서 S3가 잠깐 끊기면 ConnectionError가
        # 그대로 위로 새서 500이 되던 것과 별개로, Render 무료 인스턴스에서 헬스체크가
        # 5초 타임아웃으로 반복 실패하는 원인 중 하나였다(느린/끊긴 업스트림 호출이
        # 스레드를 오래 붙잡음) — timeout을 10s→5s로 줄이고 예외도 명시적으로 처리.
        raise HTTPException(status_code=502, detail=f"terrain tile upstream failed: {e}")
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail="terrain tile fetch failed")
    if len(_IMAGERY_CACHE) < _IMAGERY_CACHE_MAX_ENTRIES:
        _IMAGERY_CACHE[cache_key] = resp.content
    return Response(content=resp.content, media_type="image/png", headers={"Cache-Control": "public, max-age=86400"})


ESRI_IMAGERY_TILE_URL = (
    "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
)
# Esri는 커버리지가 없는 위치·줌에서도 에러가 아니라 HTTP 200으로 이 고정 회색
# "Image Not Available" 플레이스홀더 타일을 돌려준다(2026-08-28, 산청 등 3개
# 서로 다른 좌표에서 동일 MD5로 확인) — 그래서 상태코드만으로는 실패를 못 걸러낸다.
ESRI_PLACEHOLDER_MD5 = "f27d9de7f80c13501f470595e327aa6d"
ESRI_FALLBACK_MAX_ZOOM_STEPS = 3

# 2026-08-28: 위성영상은 더 이상 이 백엔드를 거치지 않는다(아래 §연혁) — 이 캐시는
# 이제 /terrain-tiles 전용. 같은 타일은 같은 결과가 나오므로(고도값은 안 바뀜)
# 메모리 캐시로 재요청 자체를 없애 응답을 빠르게 하고 업스트림(S3) 부하도 줄인다.
#
# §연혁: 위성영상을 V-World WMTS(§2.3 1순위)로 프록시하고, 실패 시 Esri로 폴백,
# Esri도 커버리지 없는 곳은 placeholder라 낮은 줌에서 잘라 확대하는 캐스케이드까지
# 만들었다가 전부 되돌렸다. 이유: (1) V-World WMTS가 Render(싱가포르 리전)에서
# 항상 502로 실패(Data API는 정상 — WMTS만 리전 제약, 원인 불명·우리가 못 고침),
# (2) Esri 캐스케이드는 타일마다 순차 HTTP 요청+PIL 이미지처리(CPU-bound)를 거치는
# 무거운 경로라, 지도 로드 한 번에 타일 수십~수백 개가 몰리면 Render 무료 인스턴스가
# 감당을 못 해 헬스체크 타임아웃("Instance failed")과 브라우저 쪽 CORS-처럼-보이는
# 에러(실제로는 응답을 아예 못 준 것)로 이어짐, (3) 세마포어로 동시처리를 제한해도
# Render 엣지 자체가 요청 "개수"에 429를 걸어 소용없었음. 결론: 타일 트래픽을 우리
# 백엔드에 태우는 구조 자체가 무료 인스턴스와 안 맞는다 — Esri 직결(아래 MapExplorer.tsx)
# 이 더 빠르고 안정적이다. V-World 재도전은 우리 백엔드가 한국 리전에 있을 때만 재검토.
_IMAGERY_CACHE: dict[tuple, bytes] = {}
_IMAGERY_CACHE_MAX_ENTRIES = 4000


VWORLD_BUILDING_LAYER = "LT_C_SPBD"  # 건물통합정보(국토교통부) — 브이월드 Data API 2.0
VWORLD_ROAD_LAYER = "LT_L_MOCTLINK"  # 국가교통정보센터 표준노드링크(§2.6이 원래 지정한 소스)
METERS_PER_FLOOR = 3.0
DEFAULT_BUILDING_HEIGHT_M = 4.0
VWORLD_PAGE_SIZE = 1000
# 2026-08-28 발견(오늘 새로 생긴 문제 아니라 이 통합 시점부터 있던 버그) — V-World
# Data API GetFeature는 geomFilter bbox 면적이 10km²를 넘으면 무조건
# INVALID_RANGE 에러를 낸다(HTTP 200으로 status:"ERROR" 반환 — 상태코드로는 못
# 걸러짐). 건물 압출을 켜는 최소 줌(z13)에서도 화면 전체 뷰포트 면적은 보통
# 수백 km²라, 실제로는 거의 항상 이 한도에 걸려 실패 → OSM 폴백(더 성긴 데이터)
# 으로 떨어지고 있었다 — "건물 로딩이 오래 걸린다"는 체감은 사실 매번 실패한
# 뒤 폴백하는 것이었을 가능성이 큼. 뷰포트가 한도를 넘으면 같은 중심점을 유지한
# 채로 9km²(한도보다 살짝 여유) 정사각형으로 줄여서 보낸다 — 화면 전체가 아니라
# 중심 근처 건물만 받게 되지만, 매번 실패하는 것보다는 훨씬 낫다.
VWORLD_MAX_QUERY_AREA_KM2 = 9.0


def _clamp_bbox_to_area(bbox: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    minx, miny, maxx, maxy = bbox
    center_lat = (miny + maxy) / 2
    width_km = (maxx - minx) * 111.32 * math.cos(math.radians(center_lat))
    height_km = (maxy - miny) * 110.54
    if width_km * height_km <= VWORLD_MAX_QUERY_AREA_KM2:
        return bbox
    center_lon = (minx + maxx) / 2
    half_side_km = math.sqrt(VWORLD_MAX_QUERY_AREA_KM2) / 2
    half_lon = half_side_km / (111.32 * math.cos(math.radians(center_lat)))
    half_lat = half_side_km / 110.54
    return (center_lon - half_lon, center_lat - half_lat, center_lon + half_lon, center_lat + half_lat)


def _vworld_get_feature(data_layer: str, bbox: tuple[float, float, float, float]) -> dict:
    """VWorld Data API 2.0 GetFeature 공통 호출. bbox=(minx,miny,maxx,maxy)."""
    if not VWORLD_API_KEY:
        raise HTTPException(status_code=503, detail="VWORLD_API_KEY not configured (.env)")
    minx, miny, maxx, maxy = _clamp_bbox_to_area(bbox)
    try:
        resp = requests.get(
            "http://api.vworld.kr/req/data",
            params={
                "service": "data",
                "request": "GetFeature",
                "data": data_layer,
                "key": VWORLD_API_KEY,
                "domain": "localhost",
                "format": "json",
                "size": VWORLD_PAGE_SIZE,
                "geomFilter": f"BOX({minx},{miny},{maxx},{maxy})",
            },
            timeout=5,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        # 2026-08-28: 전에는 여기 예외 처리가 없어서 ConnectionError 등이 그대로
        # 위로 새어나갔다(Render 헬스체크 5초 타임아웃 반복 실패와 함께 관찰된
        # "raise ConnectionError" 스택트레이스가 아마 여기) — timeout도 10s→5s로 낮춤.
        raise HTTPException(status_code=502, detail=f"VWorld data API request failed: {e}")
    body = resp.json()
    service = body.get("response", {})
    status = service.get("status")
    if status != "OK":
        # 2026-08-28 버그 수정: NOT_FOUND(해당 영역에 건물/도로가 없는 정상적인 빈
        # 결과)는 V-World 응답에서 response.status == "NOT_FOUND"로 온다 —
        # response.error.code가 아니다(그쪽엔 애초에 error 필드 자체가 없음).
        # 이전 코드는 error.code를 확인해서 항상 거짓이 됐고, 그 결과 확대해서
        # 건물이 없는 좁은 구역을 볼 때마다 정상적인 "빈 결과"를 502 에러로
        # 취급해버렸다 — "확대하면 건물이 사라진다"는 증상의 실제 원인.
        if status == "NOT_FOUND":
            return {"type": "FeatureCollection", "features": []}
        error = service.get("error", {})
        raise HTTPException(status_code=502, detail=f"VWorld error: {error}")
    return service["result"]["featureCollection"]


def _parse_bbox(bbox: str) -> tuple[float, float, float, float]:
    try:
        minx, miny, maxx, maxy = (float(v) for v in bbox.split(","))
    except ValueError:
        raise HTTPException(status_code=400, detail="bbox must be 'minLon,minLat,maxLon,maxLat'")
    return minx, miny, maxx, maxy


@app.get("/vworld/buildings")
def get_vworld_buildings(bbox: str) -> dict:
    """§2.3 1순위(V-World) 실제 건물 데이터. OpenFreeMap(OSM)은 산청 같은 산간지역에
    매핑이 드문드문이라(§ 3D 지도 안내문 참조) 건물통합정보(LT_C_SPBD, 국토교통부)로
    교체 — 한 AOI(생비량면 480m² bbox)에서만 478개 건물이 나올 만큼 촘촘하다.

    bbox: "minLon,minLat,maxLon,maxLat". gro_flo_co(지상층수)를 3m/층으로 환산해
    fill-extrusion-height용 height_m 필드를 만들어 붙여준다 — 원본은 층수만 있고
    실제 높이(m)가 없어서 건축 통상값으로 근사(§6 불확실성 표기 원칙: 근사치임을 명시).
    """
    fc = _vworld_get_feature(VWORLD_BUILDING_LAYER, _parse_bbox(bbox))
    for feature in fc.get("features", []):
        props = feature.get("properties", {})
        try:
            floors = int(props.get("gro_flo_co") or 0)
        except ValueError:
            floors = 0
        props["height_m"] = floors * METERS_PER_FLOOR if floors > 0 else DEFAULT_BUILDING_HEIGHT_M
    return fc


VWORLD_RIVER_LAYER = "LT_C_WKMSTRM"  # 하천(수계망) 폴리곤 — riv_nm(하천명)·cat_nam(하천 등급)


@app.get("/vworld/rivers")
def get_vworld_rivers(bbox: str) -> dict:
    """실폭하천 폴리곤(2026-08-28 신규) — 지금까지 지도에 하천이 아예 안 그려져
    있었다(토사·침수 시뮬레이터의 손으로 그은 흐름경로만 있음). riv_nm(하천명)·
    cat_nam(국가하천/지방하천 등급)을 포함한 실제 하천 폴리곤이라 실제 강 이름과
    형태가 그대로 나온다 — 홍수(Module B) 앱 성격에 직접 맞닿는 데이터."""
    return _vworld_get_feature(VWORLD_RIVER_LAYER, _parse_bbox(bbox))


@app.get("/vworld/roads")
def get_vworld_roads(bbox: str) -> dict:
    """§2.6이 원래 지정한 도로망 소스 — 국가교통정보센터 표준노드링크(LT_L_MOCTLINK).

    OpenFreeMap(OSM) 벡터타일은 transportation 레이어가 z14까지만 있어서, 그보다 확대한
    화면(서울 강남처럼 z16 테스트 지점 포함)에서는 그 성긴 지오메트리가 늘어나 보이며
    도로가 구불구불하게 뒤틀려 보인다 — 표준노드링크는 그 확대 배율에서도 실제 도로
    형상 그대로 나온다. rd_type_h 필드에 "교량"/"고가차도"/"터널" 구분이 직접 있어서
    OSM의 brunnel 태그보다 신뢰도 높게 교량 판별에 쓸 수 있다(프론트의 다리 압출 로직 참조).
    """
    return _vworld_get_feature(VWORLD_ROAD_LAYER, _parse_bbox(bbox))


class ChatHistoryTurn(BaseModel):
    role: str  # "user" | "bot"
    text: str


class ChatRequest(BaseModel):
    message: str
    alert_id: str | None = None
    history: list[ChatHistoryTurn] | None = None


def _rule_based_chat_reply(message: str) -> str:
    """규칙 기반 폴백 응답기 — Gemini API 키가 없거나 호출이 실패했을 때만 쓰인다
    (§7 폴백 계층과 같은 원칙: LLM 하나에 단일 실패점을 두지 않는다).
    """
    text = message.strip()
    if not text:
        return "무엇이 궁금하신가요? 골든타임, 대피소, 산사태·침수 시뮬레이터에 대해 물어보세요."
    if "골든타임" in text:
        return (
            "골든타임은 재해 감지부터 주민 대피 완료까지 확보해야 하는 시간이에요. "
            "대시보드 상단의 골든타임 카운터에서 현재 경보의 남은 시간을 확인할 수 있어요."
        )
    if "대피소" in text or "대피" in text:
        return (
            "지금은 사전 등록된 대피소 후보를 기준으로 안내하고 있어요. "
            "차량/도보 이동시간까지 계산해주는 길찾기 연동은 아직 준비 중이에요."
        )
    if "산사태" in text or "토사" in text:
        return (
            "3D 지도의 '토사 깊이' 슬라이더로 토사 유실 예상 범위를 확인할 수 있어요. "
            "다만 실제 예측 모델(Module A/B) 연동 전 what-if 값이에요."
        )
    if "침수" in text or "홍수" in text:
        return (
            "3D 지도의 '침수 수위' 슬라이더로 침수 예상 범위를 확인할 수 있어요. "
            "마찬가지로 실제 예측 모델 연동 전 what-if 값이에요."
        )
    if "고립" in text:
        return "그래프 연결성 분석 기반 고립마을 자동탐지 기능은 아직 개발 중이에요."
    if "승인" in text:
        return "'원클릭 승인' 메뉴에서 escalation 대기 중인 경보를 확인하고 승인/거부할 수 있어요."
    return (
        "저는 Aqua Guard.AI예요. 지금은 정해둔 답변만 드릴 수 있는 상태지만, "
        "골든타임 / 대피소 / 산사태 / 침수 / 고립마을 / 승인 절차에 대해 물어보시면 안내해드릴게요."
    )


# §5 Module UI "LLM 채팅"·§15 AI Agent Architecture — "LLM이 FoS나 flood depth를
# 직접 계산하지 않는다. LLM은 도구 선택·결과 해석·보고서 조합만 한다"는 원칙을
# 시스템 프롬프트에 그대로 명시한다. Module O의 alert_package(§5)를 컨텍스트로
# 넣어주면 그 안의 숫자만 해석하게 하고, 모델이 직접 확률·수치를 지어내지 않도록
# 막는 것이 핵심 — 그래야 Provenance 배지(§6.1)가 약속하는 "이 숫자는 MODEL이
# 계산했다"는 신뢰가 챗봇 답변에서도 깨지지 않는다.
_CHAT_SYSTEM_INSTRUCTION = """너는 AquaGuard AI(아쿠아가드)의 챗봇 해설층이다.
AquaGuard는 산불로 훼손된 사면 위에 집중호우가 떨어졌을 때 산사태·하천범람 위험을 감지하고,
대피소·경로·피해비용을 자동 계산해 관(官)과 시민에게 전파하는 재난 의사결정지원시스템(DSS)이다.

반드시 지킬 것:
- 너는 산사태 확률이나 침수 범위 같은 예측 수치를 절대 스스로 만들어내지 않는다. 아래
  "현재 경보 데이터"로 주어진 값만 인용해서 설명한다. 그 데이터가 없으면 "지금 실행된
  시나리오가 없다"고 말하고, 대시보드에서 시나리오를 먼저 실행해보라고 안내한다.
- 너는 대피 명령이나 승인 같은 공식 결정을 스스로 내리지 않는다. 최종 판단은 항상
  담당자(관공서 모드) 또는 사용자 본인(시민 모드)의 몫이라고 명확히 한다.
- 지금 Module A(산사태)·B(홍수)·C~H는 목업(예시 데이터) 단계인 경우가 있다 — "현재 경보
  데이터"에 그렇게 표시돼 있으면 반드시 그대로 사용자에게 알려주고, 실제 관측값처럼
  포장하지 않는다.
- AquaGuard와 무관한 질문(일반 상식, 다른 서비스 등)에는 짧게 범위 밖이라고 안내하고
  이 서비스로 화제를 되돌린다.
- 한국어로 답한다. 짧게 끝낼 질문은 짧게, 근거를 풀어 설명해야 하는 질문은 여러 문장으로
  충분히 답하되 전체 답변은 공백 포함 800자를 넘기지 않는다. 별표(**)나 #, - 같은 마크다운
  기호는 쓰지 않고 자연스러운 대화체 문장으로만 쓴다. 이모지는 쓰지 않는다.
- 바로 위 [이전 대화]가 주어지면 그 흐름을 이어서 답한다(같은 이야기를 처음부터 다시
  설명하지 않는다).
"""


def _format_alert_context(alert_id: str) -> str | None:
    """Module O 경보 상태를 LLM 프롬프트에 넣을 한국어 컨텍스트로 요약한다.

    필드 의미는 §5 Module O 계약(ARCHITECTURE.md) 그대로 — 여기서 새 숫자를
    계산하지 않고 이미 계산된 값만 옮겨 적는다(위 시스템 프롬프트 원칙과 동일).
    """
    alert = alert_store.get(alert_id)
    if alert is None:
        return None
    data = alert.envelope.get("data", {})
    package = data.get("alert_package", {})
    landslide = package.get("landslide", {})
    flood = package.get("flood", {})
    shelter = package.get("shelter_route", {})
    citizen = data.get("citizen_verification", {})
    mock_note = "(현재 목업/example 데이터 — 트랙①②④ 실제 모델 연동 전)" if os.environ.get("AQUAGUARD_MOCK_MODE", "1") != "0" else ""

    lines = [f"alert_id: {alert_id} {mock_note}".strip()]
    if "golden_time_saved_min" in data:
        lines.append(f"골든타임 확보: {data['golden_time_saved_min']}분")
    if "landslide_prob" in landslide:
        lines.append(
            f"산사태 위험확률(Module A, MODEL): {landslide['landslide_prob']*100:.0f}% "
            f"(신뢰구간 {landslide.get('confidence_interval')})"
        )
    if "flood_prob" in flood:
        lines.append(f"하천범람 위험확률(Module B, MODEL): {flood['flood_prob']*100:.0f}%")
    if "verification_status" in citizen:
        lines.append(f"시민 신고 역검증(Module H, OBSERVED): {citizen['verification_status']}")
    if "time_feasible" in shelter:
        margin = shelter.get("time_margin_min")
        lines.append(
            f"대피 경로(Module E, MODEL): {'시간 내 도달 가능' if shelter['time_feasible'] else '시간 부족'}"
            + (f", 여유 {margin:.0f}분" if margin is not None else "")
        )
    approval = alert.resolve_status()
    lines.append(f"승인 상태: {approval}" + (f" (escalation {alert.escalation_level}차)" if alert.escalation_level else ""))
    return "\n".join(lines)


_MAX_CHAT_REPLY_CHARS = 800


def _format_history(history: list[ChatHistoryTurn] | None) -> str | None:
    """직전 대화 몇 턴을 프롬프트에 넣어 멀티턴 맥락을 유지한다.

    전체 히스토리를 다 보내면 프롬프트가 무한정 커지므로 최근 6턴만 자른다 —
    "그럼 얼마나 남았어?" 같은 후속 질문이 이전 turn을 참조할 수 있을 만큼만.
    """
    if not history:
        return None
    recent = history[-6:]
    lines = [f"{'사용자' if t.role == 'user' else '챗봇'}: {t.text.strip()[:300]}" for t in recent if t.text.strip()]
    return "\n".join(lines) if lines else None


def _strip_markdown(text: str) -> str:
    """LLM이 시스템 프롬프트를 어기고 마크다운을 섞어 보내는 경우를 대비한 방어막 —
    ChatWidget은 plain text만 렌더링하므로 별표/헤더/불릿 기호가 그대로 노출되면 지저분해진다.
    """
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"(?m)^\s*[*#-]\s+", "", text)
    return text.replace("**", "").strip()


def _clip_reply(text: str, limit: int = _MAX_CHAT_REPLY_CHARS) -> str:
    """800자 지시를 모델이 안 지켰을 때를 대비한 서버 측 안전망(§7 폴백 계층과 같은 원칙:
    프롬프트 지시 하나에 기대지 않는다). 문장 경계에서 자르고, 못 찾으면 말줄임표로 끊는다.
    """
    if len(text) <= limit:
        return text
    window = text[:limit]
    cut = max(window.rfind("."), window.rfind("!"), window.rfind("?"), window.rfind("\n"))
    if cut >= limit * 0.5:
        return window[: cut + 1].strip()
    return window.rstrip() + "…"


def _chat_reply(message: str, alert_id: str | None, history: list[ChatHistoryTurn] | None = None) -> str:
    if not GEMINI_API_KEY:
        return _clip_reply(_rule_based_chat_reply(message))
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        contents = message.strip()[:2000] or "안녕"
        context = _format_alert_context(alert_id) if alert_id else None
        history_block = _format_history(history)
        parts = []
        if context:
            parts.append(f"[현재 경보 데이터]\n{context}")
        if history_block:
            parts.append(f"[이전 대화]\n{history_block}")
        parts.append(f"[사용자 질문]\n{contents}")
        contents = "\n\n".join(parts)
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=contents,
            config=genai_types.GenerateContentConfig(
                system_instruction=_CHAT_SYSTEM_INSTRUCTION,
                temperature=0.3,
                # gemini-3.6-flash는 reasoning 모델이라 답변 전에 내부적으로 "생각"하는
                # 토큰을 max_output_tokens에서 먼저 소비한다 — 예산이 너무 작으면(예: 400)
                # 그 사고 과정 중간에 잘리거나 체크리스트 형태 그대로 응답에 새어나온다
                # (실측 확인됨). thinking_budget=0으로 꺼보려 했으나 이 모델은 그 값 자체를
                # 거부한다(400 INVALID_ARGUMENT) — 대신 max_output_tokens를 넉넉히 줘서
                # (800자 목표 답변 + 사고 과정 모두 감당할 여유를) 확보한다.
                max_output_tokens=2048,
            ),
        )
        reply = _strip_markdown((response.text or "").strip())
        return _clip_reply(reply) if reply else _clip_reply(_rule_based_chat_reply(message))
    except Exception as e:
        # LLM 호출 실패(키 오류·네트워크·레이트리밋 등)는 단일 실패점이 되면 안 된다 —
        # §7 폴백 계층과 같은 원칙으로 규칙 기반 응답으로 내려간다. 단, 조용히 삼키면
        # 디버깅이 불가능해지므로 서버 콘솔에는 실제 원인을 남긴다.
        print(f"[chat] Gemini call failed, falling back to rule-based reply: {type(e).__name__}: {e}")
        return _clip_reply(_rule_based_chat_reply(message))


@app.post("/chat")
def chat(req: ChatRequest) -> dict:
    return {"reply": _chat_reply(req.message, req.alert_id, req.history)}


class EvacuationRouteShelter(BaseModel):
    shelter_id: str
    lon: float
    lat: float
    capacity: int


class EvacuationRouteRequest(BaseModel):
    origin: dict[str, float]  # {"lon": ..., "lat": ...} — 브라우저 Geolocation/지도 클릭 좌표(EPSG:4326)
    shelter_candidates: list[EvacuationRouteShelter]
    time_budget_hours: float = 2.0


@app.post("/evacuation-route")
def evacuation_route(req: EvacuationRouteRequest) -> dict:
    """§6.4 — module_e_routing.evaluate_candidates()를 감싸는 REST 엔드포인트.

    module_e_routing 자체는(오케스트레이터의 module_e.schema.json 계약대로) EPSG:5179만
    주고받으므로, 여기서만 브라우저가 보낸 4326 좌표를 5179로 바꿔 넣고, 결과 경로도
    지도에 바로 그릴 수 있게 4326으로 다시 붙여서 돌려준다(§4.1: 재투영은 UI 출력
    직전에만 — 이 엔드포인트가 그 "직전" 지점).
    """
    origin_x, origin_y = module_e_routing.point_lonlat_to_5179(req.origin["lon"], req.origin["lat"])
    shelter_candidates_5179 = []
    for s in req.shelter_candidates:
        x, y = module_e_routing.point_lonlat_to_5179(s.lon, s.lat)
        shelter_candidates_5179.append({"shelter_id": s.shelter_id, "x_5179": x, "y_5179": y, "capacity": s.capacity})

    results, warnings = module_e_routing.evaluate_candidates(
        {
            "origin": {"x_5179": origin_x, "y_5179": origin_y},
            "risk_polygons": [],
            "shelter_candidates": shelter_candidates_5179,
            "road_graph_source": "standard_node_link_v1",
            "time_budget_hours": req.time_budget_hours,
        }
    )
    for r in results:
        r["route_lonlat"] = [
            list(module_e_routing.point_5179_to_lonlat(x, y)) for x, y in r["route_5179"]["coordinates"]
        ]

    return {"results": results, "warnings": warnings}


class IsolationCheckRequest(BaseModel):
    bbox: tuple[float, float, float, float]  # (minLon, minLat, maxLon, maxLat)
    shelter_candidates: list[dict[str, float]]  # [{"lon": ..., "lat": ...}, ...]
    hazard_polygon: dict | None = None  # GeoJSON Polygon, EPSG:4326 — 없으면 베이스라인 연결성만 계산


@app.post("/isolation-check")
def isolation_check(req: IsolationCheckRequest) -> dict:
    """§7 — module_e_routing.isolation.check_isolation()을 감싸는 REST 엔드포인트.
    bbox가 넓으면(VWorld 9km² 한도) 내부에서 자동으로 타일을 나눠 순차 조회하므로
    화면 뷰포트가 클수록 응답이 느려진다(캐싱은 아직 없음 — TODO).
    """
    try:
        shelters_lonlat = [(s["lon"], s["lat"]) for s in req.shelter_candidates]
        return module_e_isolation.check_isolation(req.bbox, shelters_lonlat, req.hazard_polygon)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
