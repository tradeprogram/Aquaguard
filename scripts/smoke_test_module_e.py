"""module_e_routing.run()이 실제 네이버 Directions API로 잘 동작하는지 확인하는 1회성 스모크 테스트.

EvacuationPanel.tsx의 산청 상능마을/생비량초등학교/산청군청 대피소 좌표(§6.2)를 그대로 5179로
변환해 써서, 화면에 보이는 데모 시나리오와 같은 지점을 검증한다.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
from pyproj import Transformer

load_dotenv()

import module_e_routing  # noqa: E402

_TO_5179 = Transformer.from_crs("EPSG:4326", "EPSG:5179", always_xy=True)


def ll(lon: float, lat: float) -> dict:
    x, y = _TO_5179.transform(lon, lat)
    return {"x_5179": x, "y_5179": y}


origin = ll(128.055, 35.347)  # 상능마을 근처, 대피소들 사이 임의 출발점

shelter_candidates = [
    {"shelter_id": "S001", **ll(128.057, 35.349), "capacity": 200},
    {"shelter_id": "S002", **ll(128.052, 35.353), "capacity": 300},
    {"shelter_id": "S003", **ll(127.900325, 35.40737), "capacity": 500},
]

result = module_e_routing.run(
    {
        "origin": origin,
        "risk_polygons": [],
        "shelter_candidates": shelter_candidates,
        "road_graph_source": "standard_node_link_v1",
        "time_budget_hours": 2.0,
    }
)

print(json.dumps(result, indent=2, ensure_ascii=False))
