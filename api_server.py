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


@app.get("/vworld/imagery/{z}/{x}/{y}.jpeg")
def get_vworld_imagery_tile(z: int, x: int, y: int) -> Response:
    """V-World WMTS 위성영상(Satellite 레이어) 프록시 — 2026-08-28, Esri World Imagery
    대체용. Esri는 산간지역 등 일부 위치에서 "Image Not Available" 회색 타일을
    반환하는데, V-World는 국토지리정보원 소관의 국내 정사영상이라 국내 커버리지가
    훨씬 촘촘하고 해상도도 높다 — z19까지 실측 확인(z20은 커버리지 없음).

    V-World WMTS RESTful 주소는 level/tiley/tilex 순서(일반적인 z/x/y가 아님)임에
    주의 — 이 서명의 매개변수 순서({z}/{x}/{y})는 프론트(표준 XYZ 스킴)와 맞추고,
    여기서 업스트림 호출 시에만 순서를 뒤집는다. Referer/domain 제한 없이 서버 간
    호출로 정상 동작 확인됨(2026-08-28 curl 검증) — 브라우저 직접 호출은 CORS 헤더가
    없어 막히므로 terrain-tiles와 동일한 이유로 프록시 필요.
    """
    if not VWORLD_API_KEY:
        raise HTTPException(status_code=503, detail="VWORLD_API_KEY not configured (.env)")
    upstream = f"http://api.vworld.kr/req/wmts/1.0.0/{VWORLD_API_KEY}/Satellite/{z}/{y}/{x}.jpeg"
    try:
        resp = requests.get(upstream, timeout=10)
    except requests.RequestException as e:
        # 2026-08-28: 배포 환경(Render, region=singapore)에서 502가 나던 원인 진단용 —
        # 로컬(curl)에서는 같은 호출이 항상 성공해서 원인이 코드가 아니라 네트워크
        # 경로(리전별 아웃바운드 차단/타임아웃)일 가능성이 높다고 보고 우선 원인이
        # 드러나게 detail을 남긴다. 확인되면 이 detail은 다시 좁혀도 됨.
        raise HTTPException(status_code=502, detail=f"vworld imagery upstream request failed: {e}")
    if resp.status_code != 200 or resp.headers.get("content-type", "").startswith("application/xml"):
        raise HTTPException(
            status_code=404,
            detail=f"vworld imagery tile not available (upstream status={resp.status_code}, type={resp.headers.get('content-type')})",
        )
    return Response(content=resp.content, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=86400"})


VWORLD_BUILDING_LAYER = "LT_C_SPBD"  # 건물통합정보(국토교통부) — 브이월드 Data API 2.0
VWORLD_ROAD_LAYER = "LT_L_MOCTLINK"  # 국가교통정보센터 표준노드링크(§2.6이 원래 지정한 소스)
METERS_PER_FLOOR = 3.0
DEFAULT_BUILDING_HEIGHT_M = 4.0
VWORLD_PAGE_SIZE = 1000


def _vworld_get_feature(data_layer: str, bbox: tuple[float, float, float, float]) -> dict:
    """VWorld Data API 2.0 GetFeature 공통 호출. bbox=(minx,miny,maxx,maxy)."""
    if not VWORLD_API_KEY:
        raise HTTPException(status_code=503, detail="VWORLD_API_KEY not configured (.env)")
    minx, miny, maxx, maxy = bbox
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
        timeout=10,
    )
    resp.raise_for_status()
    body = resp.json()
    service = body.get("response", {})
    if service.get("status") != "OK":
        # NOT_FOUND(해당 영역에 데이터 없음)는 정상적인 빈 결과로 취급
        error = service.get("error", {})
        if error.get("code") == "NOT_FOUND":
            return {"type": "FeatureCollection", "features": []}
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


class ChatRequest(BaseModel):
    message: str


def _chat_reply(message: str) -> str:
    """Aqua Guard.AI 챗봇 위젯용 규칙 기반 임시 응답기.

    실제 LLM(예: Module O 상황 요약) 연동 전까지의 자리표시자 — 나중에 이 함수
    본문만 그쪽 호출로 바꿔치면 프론트는 그대로 쓸 수 있다.
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
        return "'원클릭 승인' 메뉴에서 자동 승인 대기 중인 경보를 확인하고 승인/거부할 수 있어요."
    return (
        "저는 Aqua Guard.AI예요. 아직은 정해둔 답변만 드릴 수 있는 프로토타입이지만, "
        "골든타임 / 대피소 / 산사태 / 침수 / 고립마을 / 승인 절차에 대해 물어보시면 안내해드릴게요."
    )


@app.post("/chat")
def chat(req: ChatRequest) -> dict:
    return {"reply": _chat_reply(req.message)}


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
