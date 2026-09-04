"""E. 정책 파일 무결성·출처 기록."""
from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from module_g_damage_cost import explain, policy

from .conftest import buildings, payload

REPO_ROOT = Path(policy.POLICIES_DIR).parent


@pytest.mark.parametrize("name", [policy.MODULE_G_POLICY, policy.USE_TYPE_POLICY])
def test_policy_files_validate_and_load(name):
    """28. 정책 JSON이 스키마와 의미 검증을 모두 통과한다."""
    with open(policy.POLICY_SCHEMA_PATH, encoding="utf-8") as f:
        schema = json.load(f)
    with open(policy.POLICIES_DIR / f"{name}.json", encoding="utf-8") as f:
        jsonschema.validate(json.load(f), schema)
    assert policy.load(name).rows


def test_unit_cost_rows_are_confirmed_and_cite_the_committed_pdfs():
    """29. 단가 행은 CONFIRMED이고 저장소에 커밋된 고시 PDF를 가리킨다."""
    pol = policy.load(policy.MODULE_G_POLICY)
    for row_id in ("housing_flood_unit_krw", "farmland_replant_unit_krw_per_m2"):
        row = pol.row(row_id)
        assert row.status == "CONFIRMED"
        assert row.source["agency"] and row.source["effective"]
        local = row.source.get("local_file")
        assert local and local.startswith("docs/sources/")
        assert (REPO_ROOT / local).is_file(), f"{row_id}: 고시 PDF가 저장소에 없다"


def test_notice_review_deadline_is_recorded():
    """30. 고시 재검토기한 3년이 기록돼 있다."""
    row = policy.load(policy.MODULE_G_POLICY).row("notice_review_years")
    assert row.value == 3
    assert row.status == "CONFIRMED"
    assert "2029" in row.note


def test_unknown_ratio_is_derived_with_its_measurement():
    """31. 0.744가 DERIVED이고 산청 실측 근거가 남아 있다."""
    row = policy.load(policy.MODULE_G_POLICY).row("unknown_use_type_housing_ratio")
    assert row.status == "DERIVED"
    assert row.value == 0.744
    assert "27,824" in row.source["clause"] and "37,418" in row.source["clause"]
    assert "다른 지역에 그대로 쓰면 안 된다" in row.note


def test_minimum_band_is_flagged_as_unfounded():
    """32. 최소 불확실성 폭은 PLACEHOLDER이고 근거 없음을 명시한다."""
    row = policy.load(policy.MODULE_G_POLICY).row("min_upper_band_pct")
    assert row.status == "PLACEHOLDER"
    assert row.value == 0.3
    assert "근거 없는 최소 불확실성 폭" in row.note


def test_one_building_one_household_is_an_assumption():
    """33. 1동=1세대는 ASSUMPTION이고 hhldCnt TODO가 함께 적혀 있다."""
    row = policy.load(policy.MODULE_G_POLICY).row("one_building_one_household")
    assert row.status == "ASSUMPTION"
    assert "hhldCnt" in row.note and "TODO" in row.note


def test_risk_weighting_is_recorded_as_a_team_decision():
    """34. risk_prob 미가중이 팀 결정으로 기록돼 있다."""
    row = policy.load(policy.MODULE_G_POLICY).row("risk_prob_weighting")
    assert row.status == "TEAM_DECISION"
    assert row.value is False
    assert "기대손실이 아니다" in row.note


def test_explain_exposes_policy_provenance():
    """35. explain()이 두 정책 파일의 근거 상태를 그대로 들고 나온다(§6.1)."""
    summary = explain(payload(buildings(주거=1)))["detail"]["policy"]
    assert summary["module_g"]["policy_version"] == "module_g_v1"
    assert summary["use_type"]["policy_version"] == "use_type_v1"
    assert summary["module_g"]["status_counts"]["CONFIRMED"] >= 3
    assert summary["module_g"]["status_counts"]["PLACEHOLDER"] == 1


@pytest.mark.parametrize(
    "row_id,broken",
    [("housing_flood_unit_krw", -1), ("unknown_use_type_housing_ratio", 1.5),
     ("min_upper_band_pct", -0.1)],
)
def test_invalid_policy_values_are_rejected(row_id, broken, tmp_path, monkeypatch):
    """36. 정책값을 잘못 넣으면 조용히 통과하지 않고 PolicyError로 걸린다."""
    with open(policy.POLICIES_DIR / f"{policy.MODULE_G_POLICY}.json", encoding="utf-8") as f:
        doc = json.load(f)
    for row in doc["rows"]:
        if row["id"] == row_id:
            row["value"] = broken
    (tmp_path / "broken.json").write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "policy.schema.json").write_text(
        policy.POLICY_SCHEMA_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "use_type_vocabulary.json").write_text(
        (policy.POLICIES_DIR / "use_type_vocabulary.json").read_text(encoding="utf-8"),
        encoding="utf-8")

    monkeypatch.setattr(policy, "POLICIES_DIR", tmp_path)
    monkeypatch.setattr(policy, "POLICY_SCHEMA_PATH", tmp_path / "policy.schema.json")
    monkeypatch.setattr(policy, "MODULE_G_POLICY", "broken")
    policy.load.cache_clear()
    try:
        with pytest.raises(policy.PolicyError):
            policy.active_policy()
    finally:
        policy.load.cache_clear()
