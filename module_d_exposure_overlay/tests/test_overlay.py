"""B. 공간연산 정확성."""
from __future__ import annotations

from module_d_exposure_overlay import explain, run

from .conftest import collection, feature, offset_rect, risk


def _data(payload):
    result = run(payload)
    assert result["status"] in ("ok", "degraded"), result
    return result["data"]


def test_farmland_area_is_arithmetically_exact(documented_case):
    """5. 210m × 200m 교차 = 42,000㎡ = 4.2ha. EPSG:5179 미터라 재투영 없음(§4.1)."""
    assert _data(documented_case)["exposed_farmland_ha"] == 4.2


def test_overlapping_risk_polygons_are_not_double_counted():
    """6. 겹치는 A·B 위험영역에서 농경지가 두 번 계산되면 안 된다 — 면적 정확도의 핵심.

      A  x[0, 300]   B  x[150, 450]   (x[150,300] 구간이 겹침)
      농경지가 x[0, 450] y[0, 300]을 전부 덮음
      합집합 기준 정답 = 450 × 300 = 135,000㎡ = 13.5ha
      이중계산 시 = 90,000 + 90,000 = 180,000㎡ = 18.0ha
    """
    payload = {
        "risk_polygons": [
            risk(offset_rect(0, 0, 300, 300), 0.78, "A"),
            risk(offset_rect(150, 0, 450, 300), 0.61, "B"),
        ],
        "building_footprints_5179": collection(),
        "farmland_parcels_5179": collection(feature(offset_rect(0, 0, 450, 300))),
    }
    assert _data(payload)["exposed_farmland_ha"] == 13.5


def test_overlapping_farmland_parcels_are_not_double_counted():
    """6-b. 농경지 필지끼리 겹쳐도 마찬가지 — 필지도 먼저 합친다."""
    payload = {
        "risk_polygons": [risk(offset_rect(0, 0, 300, 300), 0.78)],
        "building_footprints_5179": collection(),
        "farmland_parcels_5179": collection(
            feature(offset_rect(0, 0, 200, 300)),
            feature(offset_rect(100, 0, 300, 300)),
        ),
    }
    # 합집합 300 × 300 = 90,000㎡ = 9.0ha (이중계산이면 12.0ha)
    assert _data(payload)["exposed_farmland_ha"] == 9.0


def test_edge_touching_building_is_not_exposed():
    """7. 경계만 맞닿은 건물은 노출이 아니다 — 면이 겹쳐야 침수 노출이다."""
    payload = {
        "risk_polygons": [risk(offset_rect(0, 0, 100, 100), 0.78)],
        "building_footprints_5179": collection(
            feature(offset_rect(100, 0, 120, 100), building_id="TOUCH"),
            feature(offset_rect(90, 0, 110, 100), building_id="OVERLAP"),
        ),
        "farmland_parcels_5179": collection(),
    }
    ids = [b["building_id"] for b in _data(payload)["exposed_buildings"]]
    assert ids == ["OVERLAP"]


def test_partially_and_fully_contained_buildings_are_both_exposed():
    """8. 완전 포함이든 일부만 겹치든 노출로 센다."""
    payload = {
        "risk_polygons": [risk(offset_rect(0, 0, 100, 100), 0.78)],
        "building_footprints_5179": collection(
            feature(offset_rect(10, 10, 20, 20), building_id="INSIDE"),
            feature(offset_rect(95, 10, 130, 20), building_id="PARTIAL"),
            feature(offset_rect(200, 200, 210, 210), building_id="OUTSIDE"),
        ),
        "farmland_parcels_5179": collection(),
    }
    ids = [b["building_id"] for b in _data(payload)["exposed_buildings"]]
    assert ids == ["INSIDE", "PARTIAL"]


def test_building_in_multiple_risk_areas_takes_the_maximum_probability():
    """9. 여러 위험영역에 걸친 건물의 risk_prob는 최댓값(보수적)."""
    payload = {
        "risk_polygons": [
            risk(offset_rect(0, 0, 200, 200), 0.61, "B"),
            risk(offset_rect(100, 100, 300, 300), 0.78, "A"),
        ],
        "building_footprints_5179": collection(
            feature(offset_rect(120, 120, 140, 140), building_id="BOTH"),
            feature(offset_rect(10, 10, 20, 20), building_id="ONLY_B"),
        ),
        "farmland_parcels_5179": collection(),
    }
    by_id = {b["building_id"]: b["risk_prob"] for b in _data(payload)["exposed_buildings"]}
    assert by_id == {"BOTH": 0.78, "ONLY_B": 0.61}


def test_self_intersecting_polygon_is_repaired_not_dropped():
    """10. 자기교차(bowtie) 폴리곤은 make_valid로 복구해서 쓴다.

    (0,0)-(100,100)-(100,0)-(0,100) 나비넥타이는 두 대각선이 (50,50)에서 만나
    좌·우 삼각형 2개(각 2,500㎡)로 복구된다 — 위아래가 아니라 좌우다.
    """
    bowtie = {
        "type": "Polygon",
        "coordinates": [[[0.0, 0.0], [100.0, 100.0], [100.0, 0.0], [0.0, 100.0], [0.0, 0.0]]],
    }
    shifted = {
        "type": "Polygon",
        "coordinates": [[[x + 1_050_000.0, y + 1_707_000.0] for x, y in bowtie["coordinates"][0]]],
    }
    payload = {
        "risk_polygons": [risk(shifted, 0.78)],
        "building_footprints_5179": collection(
            feature(offset_rect(5, 40, 15, 60), building_id="IN_LEFT_TRIANGLE"),
            feature(offset_rect(40, 5, 60, 15), building_id="IN_THE_GAP"),
        ),
        "farmland_parcels_5179": collection(),
    }
    result = run(payload)
    assert result["fallback_tier"] == 2
    assert any("복구" in w for w in result["warnings"])
    # 복구된 면적만 노출로 세고, 나비넥타이의 빈 구간(아래 중앙)은 세지 않는다.
    assert [b["building_id"] for b in result["data"]["exposed_buildings"]] == ["IN_LEFT_TRIANGLE"]
    assert explain(payload)["risk_union_area_m2"] == 5000.0


def test_exposed_buildings_order_is_deterministic():
    """11. Module G·UI가 흔들리지 않도록 출력 순서를 building_id로 고정한다."""
    payload = {
        "risk_polygons": [risk(offset_rect(0, 0, 300, 300), 0.78)],
        "building_footprints_5179": collection(
            feature(offset_rect(200, 200, 210, 210), building_id="B-003"),
            feature(offset_rect(10, 10, 20, 20), building_id="B-001"),
            feature(offset_rect(100, 100, 110, 110), building_id="B-002"),
        ),
        "farmland_parcels_5179": collection(),
    }
    ids = [b["building_id"] for b in _data(payload)["exposed_buildings"]]
    assert ids == ["B-001", "B-002", "B-003"]


def test_use_type_mapping_and_fallbacks():
    """12. 주용도 문자열 → 7종 어휘. 속성 없음은 '미상', 매핑에 없는 값은 '기타'."""
    payload = {
        "risk_polygons": [risk(offset_rect(0, 0, 300, 300), 0.78)],
        "building_footprints_5179": collection(
            feature(offset_rect(10, 10, 20, 20), building_id="B-RES", **{"주용도": "공동주택"}),
            feature(offset_rect(30, 30, 40, 40), building_id="B-PUB", **{"주용도": "의료시설"}),
            feature(offset_rect(50, 50, 60, 60), building_id="B-ODD", **{"주용도": "천체투시장"}),
            feature(offset_rect(70, 70, 80, 80), building_id="B-NONE"),
        ),
        "farmland_parcels_5179": collection(),
    }
    by_id = {b["building_id"]: b["use_type"] for b in _data(payload)["exposed_buildings"]}
    assert by_id == {"B-RES": "주거", "B-PUB": "공공", "B-ODD": "기타", "B-NONE": "미상"}


def test_synthetic_building_id_is_deterministic():
    """13. id 속성이 없어도 같은 입력이면 항상 같은 id가 나온다."""
    payload = {
        "risk_polygons": [risk(offset_rect(0, 0, 300, 300), 0.78)],
        "building_footprints_5179": collection(feature(offset_rect(10, 10, 20, 20))),
        "farmland_parcels_5179": collection(),
    }
    first = _data(payload)["exposed_buildings"]
    assert first == _data(payload)["exposed_buildings"]
    assert first[0]["building_id"] == "D-AUTO-0000"


def test_explain_reports_union_area_and_buffer_flag(documented_case):
    """14. 합집합 면적·버퍼 사용 여부는 data가 아니라 explain()으로 나간다."""
    detail = explain(documented_case)
    assert detail["risk_union_area_m2"] == 300 * 300
    assert detail["used_point_buffer"] is False
    assert detail["result"]["exposed_farmland_ha"] == 4.2
