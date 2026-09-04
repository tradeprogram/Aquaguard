"""module_e_routing.isolation의 고립마을 탐지가 실제 VWorld 데이터로 동작하는지 확인."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv()

from module_e_routing import isolation  # noqa: E402

# 상능마을회관(S001)·생비량초등학교(S002) 주변 작은 bbox — EvacuationPanel.tsx §6.2와 동일 지점
bbox = (128.045, 35.343, 128.065, 35.358)
shelters = [(128.057, 35.349), (128.052, 35.353)]

print("=== 위험지역 없음(베이스라인) ===")
result = isolation.check_isolation(bbox, shelters, hazard_polygon=None)
print(f"고립 건물 수: {result['isolated_building_count']}")
print(f"경고: {result['warnings']}")

print()
print("=== 마을 중앙을 가로지르는 위험폴리곤 적용 ===")
# bbox를 세로로 가르는 좁고 긴 폴리곤 — 진입로를 끊는 상황을 흉내
hazard = {
    "type": "Polygon",
    "coordinates": [[[128.054, 35.343], [128.056, 35.343], [128.056, 35.358], [128.054, 35.358], [128.054, 35.343]]],
}
result2 = isolation.check_isolation(bbox, shelters, hazard_polygon=hazard)
print(f"고립 건물 수: {result2['isolated_building_count']}")
print(f"경고: {result2['warnings']}")
print(f"고립 구역 수: {len(result2['isolated_areas']['features'])}")
for f in result2["isolated_areas"]["features"][:5]:
    print(" -", f["properties"])
