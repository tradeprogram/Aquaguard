"""G. 건축물대장 주용도 필지 조인 (2026-09-05 배선).

우선순위: ① feature 속성의 use_type_keys ② 필지 단위 조인 매핑 ③ '미상'.
매핑 파일은 API 산출물이라 저장소에 없다 — 없어도 이 테스트들은 전부 돈다(§4.2).
"""
from __future__ import annotations

from module_d_exposure_overlay import explain, run

from .conftest import collection, feature, offset_rect, risk, write_parcel_mapping

# 산청 실데이터와 같은 형식: 25자리 bd_mgt_sn, 앞 19자리가 필지키
SN_HOUSE = "4886037023100010002" + "000001"
SN_WAREHOUSE = "4886037023100010003" + "000002"
SN_SHORT = "48860370231"  # 19자리 미만 - 조인 불가


def _payload(*buildings):
    return {
        "risk_polygons": [risk(offset_rect(0, 0, 300, 300), 0.78)],
        "building_footprints_5179": collection(*buildings),
        "farmland_parcels_5179": collection(),
    }


def _use_types(payload):
    return {b["building_id"]: b["use_type"] for b in run(payload)["data"]["exposed_buildings"]}


def test_parcel_join_fills_use_type_when_property_is_missing(isolated_repo_root):
    """1. 속성에 용도가 없으면 bd_mgt_sn 앞 19자리로 조인해 채운다."""
    write_parcel_mapping(isolated_repo_root, {SN_HOUSE[:19]: "단독주택"})
    payload = _payload(
        feature(offset_rect(10, 10, 20, 20), building_id="B-001", bd_mgt_sn=SN_HOUSE)
    )
    assert _use_types(payload) == {"B-001": "주거"}
    assert explain(payload)["use_type_join"]["from_parcel_join"] == 1


def test_feature_property_wins_over_the_join(isolated_repo_root):
    """2. 속성이 있으면 조인하지 않는다 — 데이터가 직접 실어온 값이 더 정확하다."""
    write_parcel_mapping(isolated_repo_root, {SN_HOUSE[:19]: "창고시설"})
    payload = _payload(
        feature(offset_rect(10, 10, 20, 20), building_id="B-001",
                bd_mgt_sn=SN_HOUSE, **{"주용도": "공동주택"})
    )
    assert _use_types(payload) == {"B-001": "주거"}
    detail = explain(payload)["use_type_join"]
    assert detail["from_property"] == 1
    assert detail["from_parcel_join"] == 0


def test_unmatched_parcel_stays_unknown(isolated_repo_root):
    """3. 속성도 없고 매핑에도 없으면 '미상'."""
    write_parcel_mapping(isolated_repo_root, {SN_HOUSE[:19]: "단독주택"})
    payload = _payload(
        feature(offset_rect(10, 10, 20, 20), building_id="B-001", bd_mgt_sn=SN_WAREHOUSE)
    )
    assert _use_types(payload) == {"B-001": "미상"}
    assert explain(payload)["use_type_join"]["unknown"] == 1


def test_joined_value_outside_the_vocabulary_becomes_other(isolated_repo_root):
    """4. 매핑 파일의 값이 7종 어휘에 없으면 '기타'(속성 경로와 같은 규칙)."""
    write_parcel_mapping(isolated_repo_root, {SN_HOUSE[:19]: "정체불명시설"})
    payload = _payload(
        feature(offset_rect(10, 10, 20, 20), building_id="B-001", bd_mgt_sn=SN_HOUSE)
    )
    assert _use_types(payload) == {"B-001": "기타"}


def test_missing_mapping_file_falls_back_with_a_warning():
    """5. 매핑 파일이 없으면 error가 아니라 폴백 + warning. 판정은 계속된다."""
    payload = _payload(
        feature(offset_rect(10, 10, 20, 20), building_id="B-001", bd_mgt_sn=SN_HOUSE)
    )
    result = run(payload)
    assert result["status"] in ("ok", "degraded")
    assert result["data"]["exposed_buildings"][0]["use_type"] == "미상"
    assert any("주용도 매핑" in w and "읽을 수 없음" in w for w in result["warnings"])
    assert explain(payload)["use_type_join"]["mapping_available"] is False


def test_no_warning_when_the_join_is_not_needed():
    """5-b. 모든 건물이 속성으로 해결되면 파일이 없어도 조용하다.

    계약 예시(모든 건물에 주용도 속성)가 개발자 머신의 산출물 유무에 따라
    흔들리지 않는 근거다.
    """
    payload = _payload(
        feature(offset_rect(10, 10, 20, 20), building_id="B-001", **{"주용도": "단독주택"})
    )
    assert run(payload)["warnings"] == []


def test_malformed_join_key_is_ignored(isolated_repo_root):
    """6. bd_mgt_sn이 19자 미만이거나 문자열이 아니면 조인하지 않는다."""
    write_parcel_mapping(isolated_repo_root, {SN_HOUSE[:19]: "단독주택"})
    payload = _payload(
        feature(offset_rect(10, 10, 20, 20), building_id="SHORT", bd_mgt_sn=SN_SHORT),
        feature(offset_rect(30, 30, 40, 40), building_id="NUMERIC", bd_mgt_sn=12345),
        feature(offset_rect(50, 50, 60, 60), building_id="NONE"),
    )
    assert _use_types(payload) == {"SHORT": "미상", "NUMERIC": "미상", "NONE": "미상"}


def test_explain_reports_join_coverage_and_assumption(isolated_repo_root):
    """7. explain()이 조인 커버리지와 필지 단위 조인이라는 가정을 함께 노출한다."""
    write_parcel_mapping(isolated_repo_root, {SN_HOUSE[:19]: "단독주택"})
    payload = _payload(
        feature(offset_rect(10, 10, 20, 20), building_id="JOINED", bd_mgt_sn=SN_HOUSE),
        feature(offset_rect(30, 30, 40, 40), building_id="PROP", **{"주용도": "창고시설"}),
        feature(offset_rect(50, 50, 60, 60), building_id="UNKNOWN", bd_mgt_sn=SN_WAREHOUSE),
    )
    detail = explain(payload)["use_type_join"]
    assert detail["buildings"] == 3
    assert (detail["from_property"], detail["from_parcel_join"], detail["unknown"]) == (1, 1, 1)
    assert detail["resolved_ratio_pct"] == 66.7
    assert detail["granularity"] == "parcel"
    assert detail["is_assumption"] is True
    assert "동 단위 아님" in detail["assumption"]


def test_same_parcel_different_buildings_share_the_use_type(isolated_repo_root):
    """8. 한 필지의 여러 동은 같은 주용도를 받는다 — 필지 단위 조인의 직접적 결과."""
    write_parcel_mapping(isolated_repo_root, {SN_HOUSE[:19]: "단독주택"})
    same_parcel_other_dong = SN_HOUSE[:19] + "999999"
    payload = _payload(
        feature(offset_rect(10, 10, 20, 20), building_id="DONG-1", bd_mgt_sn=SN_HOUSE),
        feature(offset_rect(30, 30, 40, 40), building_id="DONG-2", bd_mgt_sn=same_parcel_other_dong),
    )
    assert _use_types(payload) == {"DONG-1": "주거", "DONG-2": "주거"}
