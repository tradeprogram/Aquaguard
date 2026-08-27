"""
FastAPI 서버 — §4.2: 각 모듈을 REST로 쪼개지 않고 이 프로세스가 import해서
순서대로 호출한다(MOFOM 패턴). 지금은 module_o_orchestrator만 연결돼 있고,
다른 트랙 모듈이 준비되면 module_o_orchestrator/modules_client.py의
MODULE_PACKAGES를 통해 그대로 실제 모듈로 교체된다.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

import geopandas as gpd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from module_o_orchestrator import geo
from module_o_orchestrator.orchestrator import DEFAULT_SHELTER_CANDIDATES, run as run_orchestrator
from module_o_orchestrator.store import alert_store

DATA_VECTOR_DIR = Path(__file__).resolve().parent / "data" / "vector"

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


_AOI_CACHE: dict[str, dict] = {}


@app.get("/aoi/{name}")
def get_aoi(name: str) -> dict:
    """행정동 경계 실데이터(data/vector/*_5179.geojson, EPSG:5179 원본)를 3D 지도용으로
    EPSG:4326 재투영해 반환한다 — §4.1: 재투영은 UI 출력 직전에만.

    지원: "saengbiryang" (§9 데모 AOI — 산청군 생비량면), "sancheong_gun" (군 전체, 맥락용)
    """
    if name in _AOI_CACHE:
        return _AOI_CACHE[name]

    filenames = {
        "saengbiryang": "saengbiryang_myeon_5179.geojson",
        "sancheong_gun": "sancheong_gun_dong_5179.geojson",
    }
    if name not in filenames:
        raise HTTPException(status_code=404, detail=f"unknown AOI '{name}', choose from {list(filenames)}")

    path = DATA_VECTOR_DIR / filenames[name]
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"{path} not found on disk")

    gdf = gpd.read_file(path)
    geojson = json.loads(gdf.to_crs("EPSG:4326").to_json())
    _AOI_CACHE[name] = geojson
    return geojson


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
