"""고립 판정 단위 테스트용 합성 도로·건물. 네트워크를 쓰지 않는다.

   S(대피소) ── e1 ── A ── e2 ── B ── e3 ── C
                                 │
                             마을 건물(B 옆 약 20m)

e2가 끊기면 마을은 고립된다. 경도 0.001° ≈ 91m (35.4°N).
"""
import pytest

LAT = 35.4
S, A, B, C = (128.000, LAT), (128.001, LAT), (128.002, LAT), (128.003, LAT)
VILLAGE = (128.0021, LAT + 0.0002)


def road(link_id, a, b, **props):
    return {
        "type": "Feature",
        "geometry": {"type": "LineString", "coordinates": [list(a), list(b)]},
        "properties": {
            "link_id": link_id,
            "road_name": f"길{link_id}",
            "rd_type_h": "일반도로",
            "rd_rank_h": "시·군도",
            "rest_veh_h": "모두통행가능",
            "rest_h": "0",
            **props,
        },
    }


def building(lon, lat, d=0.00003):
    ring = [[lon - d, lat - d], [lon + d, lat - d], [lon + d, lat + d], [lon - d, lat + d], [lon - d, lat - d]]
    return {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [ring]}, "properties": {}}


def box(lon0, lat0, lon1, lat1):
    return {"type": "Polygon", "coordinates": [[[lon0, lat0], [lon1, lat0], [lon1, lat1], [lon0, lat1], [lon0, lat0]]]}


# e2 중간만 덮는 위험 (마을 건물은 덮지 않는다)
HAZARD_E2 = box(128.0013, LAT - 0.0001, 128.0017, LAT + 0.0001)


@pytest.fixture
def toy(monkeypatch):
    from module_e_routing import isolation as iso

    roads = [road("e1", S, A), road("e2", A, B), road("e3", B, C)]
    blds = [building(*VILLAGE)]
    monkeypatch.setattr(iso, "fetch_roads", lambda bbox: roads)
    monkeypatch.setattr(iso, "fetch_buildings", lambda bbox: blds)
    # 현장 보정 파일이 실제로 무엇을 담고 있든 단위 테스트가 흔들리지 않게 비운다.
    monkeypatch.setattr(iso, "load_road_overrides", lambda: {}, raising=False)
    return {"roads": roads, "buildings": blds, "bbox": (127.99, 35.39, 128.01, 35.41), "shelters": [S]}
