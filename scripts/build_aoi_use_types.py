"""AOI 건물이 실제로 쓰는 필지키만 남긴 주용도 매핑을 만든다.

배경: 원본 data/precomputed/building_use_types.json은 전국 624,749필지·27MB라
.gitignore 대상이고, 그래서 배포 서버(EC2)에 없다. 그 결과 배포본에서는 모든 건물이
'미상'이 되어 피해비용 점추정에서 빠진다 — 실제로 로컬 3.74억 vs 배포 1.11억으로
갈렸다. 건물·농경지를 AOI만 잘라 커밋한 것과 같은 이유로 이것도 잘라 커밋한다.

커밋된 AOI 건물 레이어의 bd_mgt_sn 앞 19자리(필지키)에 해당하는 항목만 남기므로,
용량이 27MB에서 수백 KB로 줄고 판정 결과는 원본과 동일하다.

    python scripts/build_aoi_use_types.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE = REPO_ROOT / "data" / "precomputed" / "building_use_types.json"
OUTPUT = REPO_ROOT / "data" / "vector" / "aoi_building_use_types.json"

# 커밋된 AOI 건물 레이어 — 이 안의 건물이 쓰는 키만 남긴다.
#
# .ndjson과 .geojson 둘 다 본다. 산청이 군 전체로 넓어지면서 .ndjson으로 바뀌었는데
# (한 줄에 feature 하나, 스트리밍으로 읽으려고) 여기가 .geojson만 보고 있어서 산청이
# 통째로 빠졌고, 그 결과 노출 건물의 87%가 '미상'이 됐다(2026-09-21). 조용히 비어도
# 파일은 정상으로 보이므로 아래에서 레이어별 건수를 찍고, 하나도 못 읽으면 실패시킨다.
AOI_BUILDING_LAYERS = [
    REPO_ROOT / "data" / "vector" / "aoi_buildings_sancheong_5179.ndjson",
    REPO_ROOT / "data" / "vector" / "aoi_buildings_sancheong_5179.geojson",
    REPO_ROOT / "data" / "vector" / "aoi_buildings_seoul_5179.ndjson",
    REPO_ROOT / "data" / "vector" / "aoi_buildings_seoul_5179.geojson",
]

KEY_PROPERTY = "bd_mgt_sn"
KEY_PREFIX_LEN = 19  # policies/module_d.json의 use_type_key_prefix_len과 같아야 한다


def _iter_features(path: Path):
    """.ndjson이면 한 줄씩, .geojson이면 통째로. 건물 파일이 70MB까지 커져서 필요하다."""
    if path.suffix == ".ndjson":
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        yield json.loads(line)
                    except ValueError:
                        continue
    else:
        yield from json.loads(path.read_text(encoding="utf-8")).get("features", [])


def parcel_keys() -> set[str]:
    keys: set[str] = set()
    seen_regions: set[str] = set()
    for path in AOI_BUILDING_LAYERS:
        if not path.exists():
            continue
        region = path.stem.replace("aoi_buildings_", "").replace("_5179", "")
        if region in seen_regions:
            continue  # 같은 지역을 .ndjson과 .geojson 양쪽에서 세지 않는다
        seen_regions.add(region)
        before, count = len(keys), 0
        for feature in _iter_features(path):
            count += 1
            raw = (feature.get("properties") or {}).get(KEY_PROPERTY)
            if isinstance(raw, str) and len(raw) >= KEY_PREFIX_LEN:
                keys.add(raw[:KEY_PREFIX_LEN])
        print(f"  {path.name}: 건물 {count:,}동 → 필지키 +{len(keys) - before:,}")
    if not seen_regions:
        raise SystemExit("AOI 건물 레이어를 하나도 못 읽었다 — "
                         "python scripts/build_aoi_exposure_layers.py 로 먼저 생성")
    return keys


def main() -> int:
    if not SOURCE.exists():
        print(f"원본이 없다: {SOURCE}\n"
              f"먼저 생성: python scripts/fetch_building_use_types.py", file=sys.stderr)
        return 1

    print(f"원본 읽는 중: {SOURCE.name} ({SOURCE.stat().st_size / 1e6:.1f}MB)")
    full: dict[str, str] = json.loads(SOURCE.read_text(encoding="utf-8"))
    print(f"  전국 필지 {len(full):,}개")

    print("AOI 건물의 필지키 수집:")
    keys = parcel_keys()
    if not keys:
        print("AOI 건물 레이어를 하나도 못 읽었다 — 중단", file=sys.stderr)
        return 1

    clipped = {k: full[k] for k in keys if k in full}
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(clipped, ensure_ascii=False, separators=(",", ":")),
                      encoding="utf-8")

    hit = len(clipped)
    print(f"\n{OUTPUT.relative_to(REPO_ROOT)}")
    print(f"  필지키 {len(keys):,}개 중 원본에 있는 것 {hit:,}개 ({hit / len(keys) * 100:.1f}%)")
    print(f"  {SOURCE.stat().st_size / 1e6:.1f}MB → {OUTPUT.stat().st_size / 1e6:.2f}MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
