"""
산청군·서울특별시 AOI의 Esri World_Imagery(위성사진) 타일을 z6~16 구간만 미리
받아 ui/public/satellite/{region}/{z}/{x}/{y}.jpg로 정적 캐싱한다 (2026-08-29).

배경: 건물·도로·토지피복은 이미 정적 벡터타일로 캐싱했는데(fetch_aoi_data.py,
build_vector_tiles.mjs) 위성 배경만 여전히 브라우저가 매번 Esri에 직접 라이브로
요청한다. 확대 시 pitch가 커지면(원근 투영으로 지평선까지 화면에 잡혀) 위성
래스터 타일 요청이 한 번에 수백 개까지 튀는 게 실측으로 확인됐고(§MapExplorer.tsx
DEFAULT_PITCH 주석), pitch 상한을 낮춰도 근본적으로는 라이브 네트워크 의존이라
데모 당일 Esri 쪽 지연·레이트리밋에 계속 노출된다. 같은 논리로 이것도 통째로
미리 받아버리면 그 의존성 자체가 없어진다.

z17~18은 타일 수가 기하급수적으로 늘어나서(두 지역 합쳐 9만개+) 제외 — 대신
MapLibre 래스터 소스는 maxzoom을 넘는 줌에서 마지막 유효 타일을 그대로 확대해
쓰기 때문에(§MapExplorer.tsx 위성 소스 주석 참고) z16까지만 있어도 그 이상
줌에서 추가 네트워크 요청 없이 자연스럽게 커버된다.

실행: python scripts/fetch_aoi_satellite.py [--region sancheong|seoul|all]
"""
from __future__ import annotations

import argparse
import math
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import geopandas as gpd
import requests
from shapely.ops import unary_union

REPO_ROOT = Path(__file__).resolve().parent.parent
VECTOR_DIR = REPO_ROOT / "data" / "vector"
OUT_DIR = REPO_ROOT / "ui" / "public" / "satellite"

ESRI_URL_TEMPLATE = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
ZOOM_MIN = 6
ZOOM_MAX = 16
WORKERS = 6  # 앞서 세션 실측: 반복 요청을 짧은 시간에 몰아치면 Esri 쪽이 느려지는
# 정황이 있었다(§MapExplorer.tsx 대화 기록) — 공손하게 적은 동시성 유지.

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
    return unary_union(gdf4326.geometry.tolist())


def lonlat_to_tile(lon: float, lat: float, z: int) -> tuple[int, int]:
    n = 2**z
    x = int((lon + 180) / 360 * n)
    lat_rad = math.radians(lat)
    y = int((1 - math.log(math.tan(lat_rad) + 1 / math.cos(lat_rad)) / math.pi) / 2 * n)
    return max(0, min(n - 1, x)), max(0, min(n - 1, y))


def list_tiles(geom) -> list[tuple[int, int, int]]:
    # 2026-08-29: 처음엔 건물/도로처럼 실제 폴리곤과 겹치는 타일만 받았는데, 벡터와
    # 달리 래스터는 "빈 타일"이 조용히 사라지는 게 아니라 흰 구멍으로 보인다(위성은
    # 스택 제일 아래 레이어라 그 밑엔 아무것도 없음) — 실측으로 산청 AOI 우하단
    # 모서리에 흰 삼각형이 나타난 걸 확인. bbox 사각형 전체를 채우는 걸로 변경
    # (타일 수는 늘지만 여전히 가벼움: 15,205개, ~200MB).
    minx, miny, maxx, maxy = geom.bounds
    tiles = []
    for z in range(ZOOM_MIN, ZOOM_MAX + 1):
        x1, y1 = lonlat_to_tile(minx, maxy, z)
        x2, y2 = lonlat_to_tile(maxx, miny, z)
        for x in range(x1, x2 + 1):
            for y in range(y1, y2 + 1):
                tiles.append((z, x, y))
    return tiles


def fetch_tile(z: int, x: int, y: int, out_dir: Path, max_retries: int = 4) -> bool:
    dest = out_dir / str(z) / str(x) / f"{y}.jpg"
    if dest.exists() and dest.stat().st_size > 0:
        return True
    url = ESRI_URL_TEMPLATE.format(z=z, x=x, y=y)
    for attempt in range(max_retries):
        try:
            resp = requests.get(url, timeout=15)
            if resp.status_code == 200 and resp.content:
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(resp.content)
                return True
        except Exception:
            pass
        time.sleep(1.0 * (attempt + 1))
    print(f"    [WARN] failed after retries: z{z}/{x}/{y}")
    return False


def fetch_region(region_key: str):
    geom = load_region_polygon(region_key)
    tiles = list_tiles(geom)
    out_dir = OUT_DIR / region_key
    print(f"=== {region_key}: {len(tiles)} tiles (z{ZOOM_MIN}-{ZOOM_MAX}) ===")

    done = 0
    with ThreadPoolExecutor(max_workers=WORKERS) as executor:
        futures = [executor.submit(fetch_tile, z, x, y, out_dir) for z, x, y in tiles]
        for future in as_completed(futures):
            future.result()
            done += 1
            if done % 500 == 0 or done == len(tiles):
                print(f"  {done}/{len(tiles)} done")

    total_bytes = sum(f.stat().st_size for f in out_dir.rglob("*.jpg"))
    print(f"  {region_key}: {total_bytes / 1e6:.1f} MB on disk")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--region", choices=["sancheong", "seoul", "all"], default="all")
    args = parser.parse_args()
    region_keys = ["sancheong", "seoul"] if args.region == "all" else [args.region]
    for region_key in region_keys:
        fetch_region(region_key)
    print("done")


if __name__ == "__main__":
    main()
