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

# 커밋된 AOI 건물 레이어 — 이 안의 건물이 쓰는 키만 남긴다
AOI_BUILDING_LAYERS = [
    REPO_ROOT / "data" / "vector" / "aoi_buildings_sancheong_5179.geojson",
    REPO_ROOT / "data" / "vector" / "aoi_buildings_seoul_5179.geojson",
]

KEY_PROPERTY = "bd_mgt_sn"
KEY_PREFIX_LEN = 19  # policies/module_d.json의 use_type_key_prefix_len과 같아야 한다


def parcel_keys() -> set[str]:
    keys: set[str] = set()
    for path in AOI_BUILDING_LAYERS:
        if not path.exists():
            print(f"  건너뜀(없음): {path.name}", file=sys.stderr)
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        before = len(keys)
        for feature in data.get("features", []):
            raw = (feature.get("properties") or {}).get(KEY_PROPERTY)
            if isinstance(raw, str) and len(raw) >= KEY_PREFIX_LEN:
                keys.add(raw[:KEY_PREFIX_LEN])
        print(f"  {path.name}: 건물 {len(data.get('features', [])):,}동 → 필지키 +{len(keys) - before:,}")
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
