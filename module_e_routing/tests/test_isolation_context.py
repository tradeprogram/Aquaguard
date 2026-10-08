"""고립 판정 — 문맥 1회 구축, 끊긴 도로 속성, 구조차량 진입 곤란 판정.

구조차량 판정은 도로 폭이 아니라 높이 제한(rest_h)과 현장 보정 기록으로만 한다.
표준노드링크에 폭·차로 수가 없고, rest_veh_h="이륜차"는 이륜차 통행 **금지**(고속국도)라
구조차량과 무관하기 때문이다.
"""
from module_e_routing import isolation as iso
from module_e_routing.tests.conftest import HAZARD_E2, A, B, road


def test_toy_village_isolated_when_e2_cut(toy):
    r = iso.check_isolation(toy["bbox"], toy["shelters"], HAZARD_E2)
    assert r["isolated_building_count"] == 1
    assert r["rescue_limited_count"] == 0


def test_blocked_road_carries_link_attributes(toy):
    r = iso.check_isolation(toy["bbox"], toy["shelters"], HAZARD_E2)
    props = r["blocked_roads"]["features"][0]["properties"]
    assert props == {
        "kind": "blocked_road",
        "link_id": "e2",
        "road_name": "길e2",
        "rd_type_h": "일반도로",
        "rd_rank_h": "시·군도",
    }


def test_low_clearance_link_is_rescue_limited(monkeypatch, toy):
    toy["roads"][1] = road("e2", A, B, rest_h="350")  # 3.5m 높이 제한 < 구조차량 3.8m
    monkeypatch.setattr(iso, "fetch_roads", lambda bbox: toy["roads"])
    r = iso.check_isolation(toy["bbox"], toy["shelters"], None)
    assert r["isolated_building_count"] == 0  # 주민은 갈 수 있다
    assert r["rescue_limited_count"] == 1  # 구조차량은 못 들어간다
    assert len(r["rescue_limited_buildings"]["features"]) == 1


def test_high_clearance_and_motorcycle_ban_do_not_limit_rescue(monkeypatch, toy):
    # 산청의 실제 값들: 높이 제한 4.5m, 이륜차 통행 금지(고속국도) — 둘 다 구조차량엔 무관
    toy["roads"][1] = road("e2", A, B, rest_h="450", rest_veh_h="이륜차")
    monkeypatch.setattr(iso, "fetch_roads", lambda bbox: toy["roads"])
    r = iso.check_isolation(toy["bbox"], toy["shelters"], None)
    assert r["rescue_limited_count"] == 0


def test_field_override_marks_link_impassable(monkeypatch, toy):
    monkeypatch.setattr(
        iso,
        "load_road_overrides",
        lambda: {"e2": {"link_id": "e2", "vehicle_passable": False, "note": "차 한 대 폭", "source": "현장조사"}},
    )
    r = iso.check_isolation(toy["bbox"], toy["shelters"], None)
    assert r["rescue_limited_count"] == 1
    assert any("현장 보정" in w for w in r["warnings"])


def test_context_evaluate_matches_check_isolation(toy):
    ctx = iso.build_context(toy["roads"], toy["buildings"])
    ev = iso.evaluate(ctx, toy["shelters"], iso.hazard_shape(HAZARD_E2))
    assert len(ev["isolated_idx"]) == 1
    assert ev["direct_idx"] == []
