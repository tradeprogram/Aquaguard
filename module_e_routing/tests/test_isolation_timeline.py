"""시각별 고립 판정 → 군집별 진입로 단절 시각.

단절 시각은 '처음 끊긴 시각'이 아니라 '기준 시각(침수가 가장 넓은 시각)을 포함하는 고립
구간이 시작된 시각'이다.

그리고 그 구간이 저수위 시각(창 안에서 수위가 가장 낮은 시각)까지 거슬러 올라가면, 이번
홍수가 끊은 것이 아니라 '늘 끊긴' 것이다(persistent). 시각별 침수는 최대침수심에서 수위강하를
빼는 근사라 하천 본류가 최저 수위에도 물로 남고, 본류를 건너는 길은 하루 종일 끊긴 것으로
계산된다(산청: 저수위에도 약 700동). 그런 군집에 대피 시한을 매기면 탐지보다 하루 이른
시한이 나와 버린다 — 실제로 그랬다(2026-10-08).
"""
from module_e_routing import isolation as iso
from module_e_routing.tests.conftest import HAZARD_E2


def run(toy, hazards, ref, low=None):
    return iso.isolation_timeline(toy["bbox"], toy["shelters"], hazards, reference_hour=ref, low_water_hour=low)


def test_cut_hour_is_start_of_episode(toy):
    t = run(toy, {2: None, 3: HAZARD_E2, 4: HAZARD_E2}, ref=4, low=2)
    c = t["clusters"][0]
    assert (c["cut_hour"], c["persistent"]) == (3, False)
    assert t["isolated_count_by_hour"] == {2: 0, 3: 1, 4: 1}


def test_reconnection_resets_episode(toy):
    t = run(toy, {2: HAZARD_E2, 3: None, 4: HAZARD_E2}, ref=4, low=3)
    c = t["clusters"][0]
    assert (c["cut_hour"], c["persistent"]) == (4, False)  # 2시의 단절은 다른 구간이다


def test_isolated_at_low_water_is_persistent(toy):
    t = run(toy, {2: None, 3: HAZARD_E2, 4: HAZARD_E2, 5: HAZARD_E2}, ref=5, low=4)
    c = t["clusters"][0]
    assert c["persistent"] is True  # 저수위(4시)에도 끊겨 있었다 — 이번 홍수의 단절이 아니다


def test_without_low_water_hour_window_start_is_the_boundary(toy):
    t = run(toy, {2: HAZARD_E2, 3: HAZARD_E2}, ref=3)
    assert t["clusters"][0]["persistent"] is True


def test_nothing_isolated_at_reference_gives_no_clusters(toy):
    t = run(toy, {2: HAZARD_E2, 3: None}, ref=3, low=2)
    assert t["clusters"] == []


def test_reference_hour_matches_static_check(toy):
    t = run(toy, {2: None, 3: HAZARD_E2}, ref=3, low=2)
    static = iso.check_isolation(toy["bbox"], toy["shelters"], HAZARD_E2)
    assert t["isolated_count_by_hour"][3] == static["isolated_building_count"]
