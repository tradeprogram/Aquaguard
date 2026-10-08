"""재구성 전후로 산청군 전체 · 실제 침수 고립 수치가 같아야 한다.

제안서와 화면이 이 숫자(2,445동)를 쓴다. 고립 판정 내부를 바꿀 때 이 값이 움직이면
기능 추가가 아니라 판정이 바뀐 것이다. VWorld 캐시(data/cache/isolation/)가 없으면
건너뛴다 — 이 테스트는 네트워크를 쓰지 않는다.
"""
import json
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SNAP = REPO / "data" / "precomputed" / "demo_snapshot.json"


def _inputs():
    snap = json.loads(SNAP.read_text(encoding="utf-8"))
    ent = snap["isolation"]["sancheong_all:flood"]
    hz = [f for f in snap["flood_display"]["features"] if f["properties"].get("band") == 0][0]["geometry"]
    ts = (REPO / "ui/src/lib/demoShelters.ts").read_text(encoding="utf-8")
    blk = ts[ts.index("sancheong_all: {"):]
    blk = blk[: blk.index("isolationBbox")]
    sh = [(float(a), float(b)) for a, b in re.findall(r"lon: ([\d.]+), lat: ([\d.]+)", blk)]
    return tuple(ent["bbox"]), sh, hz, ent["result"]


def test_county_flood_isolation_unchanged():
    from module_e_routing import isolation as iso

    bbox, sh, hz, stored = _inputs()
    if not iso.cache_file(iso.VWORLD_ROAD_LAYER, bbox).exists():
        pytest.skip("VWorld 캐시 없음")
    fresh = iso.check_isolation(bbox, sh, hz)
    assert fresh["isolated_building_count"] == stored["isolated_building_count"] == 2445
    assert len(fresh["blocked_roads"]["features"]) == len(stored["blocked_roads"]["features"])
    assert len(fresh["isolated_areas"]["features"]) == len(stored["isolated_areas"]["features"])
