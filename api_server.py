"""
FastAPI 서버 — §4.2: 각 모듈을 REST로 쪼개지 않고 이 프로세스가 import해서
순서대로 호출한다(MOFOM 패턴). 지금은 module_o_orchestrator만 연결돼 있고,
다른 트랙 모듈이 준비되면 module_o_orchestrator/modules_client.py의
MODULE_PACKAGES를 통해 그대로 실제 모듈로 교체된다.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Literal

import geopandas as gpd
import requests
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from module_o_orchestrator import geo
from module_o_orchestrator.orchestrator import DEFAULT_SHELTER_CANDIDATES, run as run_orchestrator
from module_o_orchestrator.store import alert_store

load_dotenv()  # .env(git-ignore됨)의 VWORLD_API_KEY 등을 os.environ으로 로드

DATA_VECTOR_DIR = Path(__file__).resolve().parent / "data" / "vector"
VWORLD_API_KEY = os.environ.get("VWORLD_API_KEY")

app = FastAPI(title="AquaGuard AI — api_server")

# ui/(Next.js dev server, 기본 3000포트)에서 로컬 개발 중 호출할 수 있도록 허용
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class TriggerRequest(BaseModel):
    alert_id: str
    trigger_location: dict[str, float]
    timestamp: str
    auto_approve_timeout_min: int = 15
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
    envelope["data"] = {**envelope["data"], "approval_status": alert.resolve_status()}
    # 계약(§4.2)의 4개 필드 밖에 붙는 부가 메타 — UI의 승인 타임아웃 카운트다운용
    envelope["meta"] = {
        "created_at": alert.created_at.isoformat(),
        "auto_approve_timeout_min": alert.auto_approve_timeout_min,
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
    upstream = f"https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"
    resp = requests.get(upstream, timeout=10)
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail="terrain tile fetch failed")
    return Response(content=resp.content, media_type="image/png", headers={"Cache-Control": "public, max-age=86400"})


VWORLD_BUILDING_LAYER = "LT_C_SPBD"  # 건물통합정보(국토교통부) — 브이월드 Data API 2.0
METERS_PER_FLOOR = 3.0
DEFAULT_BUILDING_HEIGHT_M = 4.0


@app.get("/vworld/buildings")
def get_vworld_buildings(bbox: str) -> dict:
    """§2.3 1순위(V-World) 실제 건물 데이터. OpenFreeMap(OSM)은 산청 같은 산간지역에
    매핑이 드문드문이라(§ 3D 지도 안내문 참조) 건물통합정보(LT_C_SPBD, 국토교통부)로
    교체 — 한 AOI(생비량면 480m² bbox)에서만 478개 건물이 나올 만큼 촘촘하다.

    bbox: "minLon,minLat,maxLon,maxLat". gro_flo_co(지상층수)를 3m/층으로 환산해
    fill-extrusion-height용 height_m 필드를 만들어 붙여준다 — 원본은 층수만 있고
    실제 높이(m)가 없어서 건축 통상값으로 근사(§6 불확실성 표기 원칙: 근사치임을 명시).
    """
    if not VWORLD_API_KEY:
        raise HTTPException(status_code=503, detail="VWORLD_API_KEY not configured (.env)")
    try:
        minx, miny, maxx, maxy = (float(v) for v in bbox.split(","))
    except ValueError:
        raise HTTPException(status_code=400, detail="bbox must be 'minLon,minLat,maxLon,maxLat'")

    resp = requests.get(
        "http://api.vworld.kr/req/data",
        params={
            "service": "data",
            "request": "GetFeature",
            "data": VWORLD_BUILDING_LAYER,
            "key": VWORLD_API_KEY,
            "domain": "localhost",
            "format": "json",
            "size": 1000,
            "geomFilter": f"BOX({minx},{miny},{maxx},{maxy})",
        },
        timeout=10,
    )
    resp.raise_for_status()
    body = resp.json()
    service = body.get("response", {})
    if service.get("status") != "OK":
        # NOT_FOUND(해당 영역에 건물 없음)는 정상적인 빈 결과로 취급
        error = service.get("error", {})
        if error.get("code") == "NOT_FOUND":
            return {"type": "FeatureCollection", "features": []}
        raise HTTPException(status_code=502, detail=f"VWorld error: {error}")

    fc = service["result"]["featureCollection"]
    for feature in fc.get("features", []):
        props = feature.get("properties", {})
        try:
            floors = int(props.get("gro_flo_co") or 0)
        except ValueError:
            floors = 0
        props["height_m"] = floors * METERS_PER_FLOOR if floors > 0 else DEFAULT_BUILDING_HEIGHT_M
    return fc


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
