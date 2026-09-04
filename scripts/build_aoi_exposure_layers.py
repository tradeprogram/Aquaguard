"""
데모 AOI(산청군 생비량면) 안의 건축물 footprint를 EPSG:5179로 잘라
data/vector/aoi_buildings_5179.geojson으로 저장하는 1회성 배치 스크립트.

왜 별도 파일로 커밋하는가:
Module O가 Module D에 넘겨야 할 building_footprints_5179를 그동안 빈 dict로
비워두고 있었다(§10 "데이터 접근 계층" TODO). 원본은
data/precomputed/sancheong_buildings.geojson(57,681건)이지만 그 디렉토리는
.gitignore라 배포 서버에 없고, 전국/시군 단위를 통째로 커밋하기에는 크다.
그래서 데모가 실제로 도는 범위인 생비량면(44km², 2,409건)만 잘라 커밋한다.

좌표계: 원본은 EPSG:4326이고 Module D 계약은 5179 미터를 요구하므로 여기서
변환해 저장한다(§4.1 — 재투영은 UI 출력 직전에만 하되, 이건 UI가 아니라
모듈 입력이라 5179로 맞추는 게 맞다).

농경지(farmland_parcels_5179)는 이 스크립트가 만들지 않는다. 저장소에 농경지
레이어가 아예 없어서(data/vector에는 행정경계·대피소뿐) 지어낼 근거가 없다.
Module D는 농경지가 비면 exposed_farmland_ha를 0으로 두고 경고를 남긴다.

실행: python scripts/build_aoi_exposure_layers.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from pyproj import Transformer
from shapely.geometry import mapping, shape
from shapely.ops import transform as shapely_transform
from shapely.prepared import prep

REPO_ROOT = Path(__file__).resolve().parent.parent
ADM_DONG_PATH = REPO_ROOT / "data" / "vector" / "adm_dong_5179.geojson"
SOURCE_PATH = REPO_ROOT / "data" / "precomputed" / "sancheong_buildings.geojson"
OUTPUT_PATH = REPO_ROOT / "data" / "vector" / "aoi_buildings_5179.geojson"

# 산청군 생비량면 — §9 데모 시나리오의 trigger_location이 속한 행정동
AOI_DONG_CODE = "38570390"

_TO_5179 = Transformer.from_crs("EPSG:4326", "EPSG:5179", always_xy=True).transform

# 원본(VWorld LT_C_SPBD)에서 실어 나를 속성만 남긴다 — 나머지는 Module D가 안 쓴다.
# bd_mgt_sn은 건축물대장 주용도를 붙일 조인키라 반드시 유지한다
# (scripts/fetch_building_use_types.py 참조).
KEPT_PROPERTIES = ("bd_mgt_sn", "buld_nm", "gro_flo_co", "height_m", "sigungu", "gu")


def load_aoi():
    with open(ADM_DONG_PATH, encoding="utf-8") as f:
        dong = json.load(f)
    for feature in dong["features"]:
        if feature["properties"].get("code") == AOI_DONG_CODE:
            return shape(feature["geometry"]), feature["properties"].get("full_nm", "")
    raise SystemExit(f"행정동 코드 {AOI_DONG_CODE}를 {ADM_DONG_PATH}에서 못 찾았다.")


def main() -> None:
    if not SOURCE_PATH.exists():
        print(f"{SOURCE_PATH} 없음 — python scripts/fetch_aoi_data.py로 먼저 생성할 것.",
              file=sys.stderr)
        sys.exit(1)

    aoi_geom, aoi_name = load_aoi()
    prepared = prep(aoi_geom)
    print(f"AOI: {aoi_name} ({aoi_geom.area / 1e6:.1f}km²)")

    with open(SOURCE_PATH, encoding="utf-8") as f:
        source = json.load(f)
    print(f"원본 건물: {len(source['features']):,}건 (EPSG:4326)")

    kept: list[dict] = []
    skipped_invalid = 0
    for feature in source["features"]:
        try:
            geom_5179 = shapely_transform(_TO_5179, shape(feature["geometry"]))
        except Exception:  # noqa: BLE001 - 깨진 지오메트리는 조용히 버리되 세어둔다
            skipped_invalid += 1
            continue
        # 폴리곤 전체가 아니라 대표점으로 판정한다 — 경계에 걸친 건물을 양쪽 AOI가
        # 중복으로 갖지 않게 하고, 44km² 폴리곤과의 교차 연산도 아낀다.
        if not prepared.contains(geom_5179.representative_point()):
            continue
        props = feature.get("properties") or {}
        kept.append({
            "type": "Feature",
            "geometry": mapping(geom_5179),
            "properties": {k: props.get(k) for k in KEPT_PROPERTIES if k in props},
        })

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": kept}, f, ensure_ascii=False)

    size_mb = OUTPUT_PATH.stat().st_size / 1e6
    print(f"AOI 내부: {len(kept):,}건"
          + (f" (지오메트리 오류 {skipped_invalid:,}건 제외)" if skipped_invalid else ""))
    print(f"저장: {OUTPUT_PATH} ({size_mb:.1f}MB, EPSG:5179)")


if __name__ == "__main__":
    main()
