"""
전국 지진옥외대피소 포인트(재난안전데이터공유플랫폼 DSSP-IF-00103)를 한 번에 전부
받아서 data/vector/shelters_national.geojson으로 저장하는 1회성 배치 스크립트.

하루 호출 한도(1,000건)가 있는 API라 매번 실시간으로 부르지 않고, 이렇게 받아둔
정적 파일을 api_server.py의 GET /shelters가 그대로 서빙한다(§6.4).

좌표는 원본이 EPSG:3857(Web Mercator, XMAP_CRTS/YMAP_CRTS)이라 EPSG:4326으로
변환해서 저장한다 — 실측으로 서울 종로구 대신고등학교가 정확히 나오는 것으로 확인됨.

실행: python scripts/fetch_shelters.py
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import requests
from dotenv import load_dotenv
from pyproj import Transformer

load_dotenv()

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_PATH = REPO_ROOT / "data" / "vector" / "shelters_national.geojson"

API_URL = "https://www.safetydata.go.kr/V2/api/DSSP-IF-00103"
PAGE_SIZE = 1000

_TO_WGS84 = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)


def fetch_all_shelters() -> list[dict]:
    api_key = os.environ.get("SHELTER_API_KEY")
    if not api_key:
        raise SystemExit("SHELTER_API_KEY not set in .env")

    all_rows: list[dict] = []
    page = 1
    while True:
        resp = requests.get(
            API_URL,
            params={"serviceKey": api_key, "returnType": "json", "pageNo": page, "numOfRows": PAGE_SIZE},
            timeout=15,
        )
        resp.raise_for_status()
        body = resp.json()
        if body.get("header", {}).get("resultCode") != "00":
            raise SystemExit(f"API error: {body.get('header')}")
        rows = body.get("body", [])
        all_rows.extend(rows)
        total = body.get("totalCount", len(rows))
        print(f"page {page}: {len(rows)}건 받음 (누적 {len(all_rows)}/{total})", flush=True)
        if len(all_rows) >= total or not rows:
            break
        page += 1
        time.sleep(0.2)  # 과도한 연속 호출 방지
    return all_rows


def to_geojson(rows: list[dict]) -> dict:
    features = []
    for row in rows:
        x, y = row.get("XMAP_CRTS"), row.get("YMAP_CRTS")
        if x is None or y is None:
            continue
        lon, lat = _TO_WGS84.transform(x, y)
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [round(lon, 6), round(lat, 6)]},
                "properties": {
                    "shelter_id": row.get("THINGS_MNG_NO"),
                    "name": row.get("THINGS_NM"),
                    "sido": row.get("CTPV_NM"),
                    "sigungu": row.get("SGG_NM"),
                    "emd": row.get("EMD_NM"),
                    "road_name": row.get("ROAD_NM"),
                    # 이 데이터셋엔 수용인원 필드가 없음 — module_e 계약이 capacity를
                    # 요구하므로 알 수 없다는 뜻으로 null(프론트에서 "미상"으로 표시).
                    "capacity": None,
                },
            }
        )
    return {"type": "FeatureCollection", "features": features}


if __name__ == "__main__":
    rows = fetch_all_shelters()
    fc = to_geojson(rows)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(fc, f, ensure_ascii=False)
    print(f"저장 완료: {OUTPUT_PATH} ({len(fc['features'])}곳)")
