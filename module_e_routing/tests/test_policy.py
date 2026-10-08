import pytest

from module_e_routing import policy


def test_module_e_policy_rows():
    p = policy.load()
    assert p.version == "module_e_v1"
    assert p.value("evacuate_lead_before_cut_hours") == 1.0
    assert p.row("evacuate_lead_before_cut_hours").status == "TEAM_DECISION"
    assert p.value("flood_impassable_depth_m") == 0.3
    assert p.value("rescue_vehicle_height_m") == 3.8


def test_unknown_row_raises():
    with pytest.raises(policy.PolicyError):
        policy.load().value("no_such_row")
