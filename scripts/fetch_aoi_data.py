"""
산청군·서울특별시 전역의 건물·도로·하천·토지피복을 미리 통째로 받아 정적
GeoJSON으로 저장하는 1회성 배치 스크립트 (2026-08-28).

배경: 실시간 뷰포트 쿼리 방식은 V-World Data API의 bbox 10km² 한도 때문에
화면 중심 근처 좁은 창만 매번 갱신돼 패닝할 때마다 데이터가 깜빡였다(§HANDOFF).
"정밀 3D 지도"가 목표가 아니라 "산청·서울 두 시뮬레이션 지역의 피해규모 재현"이
목표라는 게 명확해졌으므로, 그 두 지역만 미리 통째로 받아 정적 파일로 캐싱해
실시간 쿼리 의존성 자체를 없앤다.

방식:
1. data/vector/adm_sigungu_5179.geojson·adm_sido_5179.geojson에서 산청군·
   서울특별시 실제 행정경계 폴리곤을 가져온다(어림한 bbox 아님).
2. 그 경계의 bbox를 ~7km²급 타일 그리드로 나누고, 실제 경계와 안 겹치는
   타일은 건너뛴다(V-World 10km² 한도 회피).
3. 타일마다 건물(LT_C_SPBD)·도로(LT_L_MOCTLINK)·하천(LT_C_WKMSTRM)을
   페이지네이션까지 끝까지 따라가며 전부 받는다 — 재시도·속도제한 포함,
   타일별 캐시 파일에 저장해 중간에 끊겨도 이어서 할 수 있게 함.
4. 로컬 토지피복도(GeoPackage)는 API가 아니라 파일이라 rate limit 없이
   바로 해당 폴리곤으로 클립 + L2_CODE 기준으로 dissolve(폴리곤 개수를
   크게 줄여 렌더링·용량에 부담 없게 함).
5. 각 지역·레이어별로 병합·중복제거해 data/precomputed/{region}_{layer}.geojson
   으로 저장.

실행: python scripts/fetch_aoi_data.py [--region sancheong|seoul|all]
"""
from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path

import geopandas as gpd
import requests
from shapely.geometry import box
from shapely.ops import unary_union

REPO_ROOT = Path(__file__).resolve().parent.parent
VECTOR_DIR = REPO_ROOT / "data" / "vector"
PRECOMPUTED_DIR = REPO_ROOT / "data" / "precomputed"
TILE_CACHE_DIR = REPO_ROOT / "data" / "precomputed" / "_tile_cache"
LANDCOVER_PATH = r"C:\Users\user\AppData\Local\Temp\claude\C--aquaguard\9b9367ba-7153-4083-88cb-99e8bfb90915\scratchpad\landcover_local\landcover_m_2025_5179.gpkg"
# 2026-08-28: 원래 네트워크 공유(\\192.168.0.26\...) 경로였으나 SQLite/GeoPackage가
# SMB 네트워크 드라이브에서 심하게 느리다(파일 잠금 방식 때문 — 잘 알려진 문제).
# 메타데이터 조회 하나에 60초 넘게 걸리고 robocopy도 두 번이나 멈췄다 — 대신 파이썬
# 순수 청크 복사(8MB 단위 read/write)로 로컬에 옮긴 뒤 그 사본을 쓴다.

VWORLD_API_KEY = "762921C3-C162-3D9D-A9E7-8B83E6641A2D"
VWORLD_URL = "http://api.vworld.kr/req/data"
VWORLD_PAGE_SIZE = 1000
TILE_DEG = 0.027  # 위도 35~38°N 범위에서 대략 7~7.5km² — 10km² 한도에 여유

LAYERS = {
    "buildings": "LT_C_SPBD",
    "roads": "LT_L_MOCTLINK",
    "rivers": "LT_C_WKMSTRM",
}

REGIONS = {
    "sancheong": {"source": "sigungu", "match_col": "name", "match_val": "산청"},
    "seoul": {"source": "sido", "match_col": "sidonm", "match_val": "서울"},
}


def load_region_polygon(region_key: str):
    cfg = REGIONS[region_key]
    path = VECTOR_DIR / f"adm_{cfg['source']}_5179.geojson"
    gdf = gpd.read_file(path)
    row = gdf[gdf[cfg["match_col"]].astype(str).str.contains(cfg["match_val"])]
    if len(row) == 0:
        raise SystemExit(f"region not found: {region_key}")
    gdf4326 = row.to_crs(4326)
    geom = unary_union(gdf4326.geometry.tolist())
    return geom


def make_tiles(geom) -> list[tuple[float, float, float, float]]:
    minx, miny, maxx, maxy = geom.bounds
    tiles = []
    x = minx
    while x < maxx:
        y = miny
        while y < maxy:
            cell = box(x, y, x + TILE_DEG, y + TILE_DEG)
            if geom.intersects(cell):
                tiles.append((x, y, x + TILE_DEG, y + TILE_DEG))
            y += TILE_DEG
        x += TILE_DEG
    return tiles


def fetch_layer_tile(layer_code: str, bbox: tuple[float, float, float, float], max_retries: int = 4) -> list[dict]:
    minx, miny, maxx, maxy = bbox
    features: list[dict] = []
    page = 1
    while True:
        params = {
            "service": "data",
            "request": "GetFeature",
            "data": layer_code,
            "key": VWORLD_API_KEY,
            "domain": "localhost",
            "format": "json",
            "size": VWORLD_PAGE_SIZE,
            "page": page,
            "geomFilter": f"BOX({minx},{miny},{maxx},{maxy})",
        }
        body = None
        for attempt in range(max_retries):
            try:
                resp = requests.get(VWORLD_URL, params=params, timeout=15)
                resp.raise_for_status()
                body = resp.json()
                break
            except Exception:
                time.sleep(1.5 * (attempt + 1))
        if body is None:
            print(f"    [WARN] tile fetch failed after retries: {layer_code} {bbox} page={page}")
            break
        service = body.get("response", {})
        status = service.get("status")
        if status == "NOT_FOUND":
            break
        if status != "OK":
            print(f"    [WARN] non-OK status={status} for {layer_code} {bbox} page={page}: {service.get('error')}")
            break
        fc = service["result"]["featureCollection"]
        features.extend(fc["features"])
        total_pages = int(service.get("page", {}).get("total", 1))
        if page >= total_pages:
            break
        page += 1
        time.sleep(0.15)
    return features


TILE_WORKERS = 4  # 서울처럼 밀도 높은 지역은 타일당 페이지네이션이 많아 순차 처리가
# 너무 느리다(15타일/25분 실측 — 전체 완료에 5시간 가까이 걸릴 속도). V-World가
# 동시 요청에 약한 건 이미 알지만(과거 Render 세션에서 관측), 이건 우리 쪽에서
# 완만하게 몇 개만 동시에 보내는 것이라 이전에 문제였던 "타일 수백 개가 한꺼번에"
# 상황과는 다르다 — 안전하게 4개 정도로 제한.


def fetch_region_layer(region_key: str, layer_name: str, layer_code: str, tiles: list[tuple[float, float, float, float]]):
    from concurrent.futures import ThreadPoolExecutor, as_completed

    cache_dir = TILE_CACHE_DIR / region_key / layer_name
    cache_dir.mkdir(parents=True, exist_ok=True)
    pending = [(i, tile) for i, tile in enumerate(tiles) if not (cache_dir / f"tile_{i:04d}.json").exists()]
    if not pending:
        print(f"  [{region_key}/{layer_name}] all {len(tiles)} tiles already cached, skipping")
        return

    done_count = len(tiles) - len(pending)

    def work(item):
        i, tile = item
        feats = fetch_layer_tile(layer_code, tile)
        (cache_dir / f"tile_{i:04d}.json").write_text(json.dumps(feats, ensure_ascii=False), encoding="utf-8")
        return i, len(feats)

    with ThreadPoolExecutor(max_workers=TILE_WORKERS) as executor:
        futures = [executor.submit(work, item) for item in pending]
        for future in as_completed(futures):
            i, n = future.result()
            done_count += 1
            if done_count % 5 == 0 or done_count == len(tiles):
                print(f"  [{region_key}/{layer_name}] tile {done_count}/{len(tiles)} done (tile {i}: {n} features)")


def merge_region_layer(region_key: str, layer_name: str, region_geom) -> dict:
    cache_dir = TILE_CACHE_DIR / region_key / layer_name
    seen: dict[str, dict] = {}
    for f in sorted(cache_dir.glob("tile_*.json")):
        feats = json.loads(f.read_text(encoding="utf-8"))
        for feat in feats:
            key = feat.get("id") or json.dumps(feat.get("properties", {}), sort_keys=True)
            seen[key] = feat
    features = list(seen.values())
    print(f"  [{region_key}/{layer_name}] merged {len(features)} unique features")
    return {"type": "FeatureCollection", "features": features}


def process_landcover(region_key: str, region_geom):
    # 2026-08-28: fiona로 피처를 하나씩 순회하며 shapely 변환+intersects 검사하는
    # 방식은 989만 행짜리 파일에서 CPU를 거의 안 쓰면서(대부분 파이썬 루프 오버헤드·
    # 개별 지오메트리 파싱 대기) 10분 넘게도 안 끝났다. geopandas의 기본 엔진인
    # pyogrio는 GDAL 벡터 I/O를 C 레벨에서 배치로 읽어 훨씬 빠르다 — bbox 필터만
    # GDAL에 맡기고, 정밀한 경계 클립은 이후 벡터화된 gpd.clip()으로 한 번에 처리.
    minx, miny, maxx, maxy = region_geom.bounds
    region_gdf_4326 = gpd.GeoDataFrame({"geometry": [region_geom]}, crs=4326)
    region_5179 = region_gdf_4326.to_crs(5179)
    b5179 = tuple(region_5179.total_bounds)

    print(f"  [{region_key}/landcover] reading from GeoPackage (pyogrio bulk read, bbox filter)...")
    gdf = gpd.read_file(LANDCOVER_PATH, layer="landcover_2025", bbox=b5179, engine="pyogrio")
    print(f"  [{region_key}/landcover] {len(gdf)} raw features in bbox, clipping to boundary + dissolving...")
    gdf["geometry"] = gdf.geometry.make_valid()
    clipped = gpd.clip(gdf, region_5179)
    dissolved = clipped.dissolve(by="L2_CODE", as_index=False)
    dissolved["geometry"] = dissolved.geometry.simplify(2.0, preserve_topology=True)
    dissolved4326 = dissolved.to_crs(4326)
    print(f"  [{region_key}/landcover] dissolved to {len(dissolved4326)} category polygons")
    return json.loads(dissolved4326.to_json())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--region", choices=["sancheong", "seoul", "all"], default="all")
    args = parser.parse_args()
    region_keys = ["sancheong", "seoul"] if args.region == "all" else [args.region]

    PRECOMPUTED_DIR.mkdir(parents=True, exist_ok=True)

    for region_key in region_keys:
        print(f"=== {region_key} ===")
        geom = load_region_polygon(region_key)
        tiles = make_tiles(geom)
        print(f"  {len(tiles)} tiles covering {region_key} boundary")

        for layer_name, layer_code in LAYERS.items():
            print(f"  fetching {layer_name} ({layer_code})...")
            fetch_region_layer(region_key, layer_name, layer_code, tiles)
            fc = merge_region_layer(region_key, layer_name, geom)
            out_path = PRECOMPUTED_DIR / f"{region_key}_{layer_name}.geojson"
            out_path.write_text(json.dumps(fc, ensure_ascii=False), encoding="utf-8")
            print(f"  wrote {out_path} ({out_path.stat().st_size / 1024:.0f} KB)")

        landcover_fc = process_landcover(region_key, geom)
        out_path = PRECOMPUTED_DIR / f"{region_key}_landcover.geojson"
        out_path.write_text(json.dumps(landcover_fc, ensure_ascii=False), encoding="utf-8")
        print(f"  wrote {out_path} ({out_path.stat().st_size / 1024:.0f} KB)")

    print("done")


if __name__ == "__main__":
    main()
