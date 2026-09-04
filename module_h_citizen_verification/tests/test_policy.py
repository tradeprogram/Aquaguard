"""F. 정책 파일 무결성 + 근거(provenance) 기록."""
from __future__ import annotations

import json

import jsonschema
import pytest

from module_h_citizen_verification import explain, policy

from .conftest import payload, sightings


def test_policy_file_validates_and_loads():
    """29. 정책 JSON이 자체 스키마와 의미 검증을 모두 통과한다."""
    with open(policy.POLICY_SCHEMA_PATH, encoding="utf-8") as f:
        schema = json.load(f)
    with open(policy.POLICIES_DIR / f"{policy.DEFAULT_POLICY}.json", encoding="utf-8") as f:
        jsonschema.validate(json.load(f), schema)
    assert policy.load(policy.DEFAULT_POLICY).version == "module_h_v1"


def test_policy_lives_inside_the_package_not_the_shared_dir():
    """30. H의 정책은 패키지 안에 둔다 — 다른 모듈과 공유할 정책이 없기 때문.

    저장소 최상위 policies/는 Module D와 G가 use_type 어휘를 공유해야 해서 만든
    자리다. H가 거기 끼면 track2/module-d 브랜치와 같은 경로를 두 갈래로 추가하게 된다.
    """
    package_dir = policy.Path(policy.__file__).resolve().parent
    assert policy.POLICIES_DIR.parent == package_dir


def test_shrinkage_k_is_flagged_as_a_back_calculated_placeholder():
    """31. k=9는 계약 예시 역산값이며 검증된 모델이 아님을 note가 명시한다."""
    row = policy.load(policy.DEFAULT_POLICY).row("shrinkage_k")
    assert row.status == "PLACEHOLDER"
    assert row.is_settled is False
    assert row.value == 9.0
    assert "계약 예시 역산값" in row.note
    assert "검증된 신뢰도 모델이 아니며" in row.note
    assert "실제 파일럿 응답 데이터 확보 시 재보정" in row.note


def test_evacuation_weight_records_why_it_is_halved():
    """32. 이미_대피함 0.5의 근거가 note에 남아 있다."""
    row = policy.load(policy.DEFAULT_POLICY).row("report_type_weights")
    assert row.status == "TEAM_DECISION"
    assert row.value["이미_대피함"] == 0.5
    assert "경보 순응 신호 성격이 있어" in row.note
    assert "현장 위험의 독립 확인이 아님" in row.note
    assert "경보 전/후 시각별 차등 가중은 향후 검토 항목" in row.note


def test_max_adjustment_is_derived_from_the_contract_not_chosen():
    """33. ±0.3은 계약 스키마가 못박은 값이라 우리가 고른 값이 아니다."""
    row = policy.load(policy.DEFAULT_POLICY).row("max_adjustment")
    assert row.status == "DERIVED"
    assert row.source["document"] == "contracts/module_h.schema.json"
    assert "-0.3" in row.source["clause"]


def test_photo_policy_records_the_no_fetch_rule():
    """34. 사진 미가중과 'fetch 금지' 방침이 정책 파일에 기록돼 있다."""
    row = policy.load(policy.DEFAULT_POLICY).row("photo_weight_bonus")
    assert row.value == 0.0
    assert "절대 fetch하지 않는다" in row.note


def test_unsettled_rows_are_exactly_the_ones_we_admit_are_unfounded():
    """35. 근거 없는 행(PLACEHOLDER) 목록을 고정한다 — 조용히 늘어나지 않게."""
    unsettled = {r.id for r in policy.load(policy.DEFAULT_POLICY).unsettled_rows()}
    assert unsettled == {
        "shrinkage_k",
        "confirm_threshold",
        "false_positive_threshold",
        "full_weight_min_reports",
        "valid_window_min",
    }


def test_explain_exposes_policy_provenance(documented_case):
    """36. explain()이 정책 근거 상태를 그대로 들고 나온다(§6.1 Provenance)."""
    detail = explain(documented_case)["detail"]
    assert detail["is_model"] is False
    assert detail["policy"]["policy_version"] == "module_h_v1"
    assert detail["policy"]["status_counts"]["PLACEHOLDER"] == 5
    assert detail["trace"]


@pytest.mark.parametrize(
    "row_id,broken",
    [
        ("shrinkage_k", -1.0),
        ("max_adjustment", 0.9),
        ("full_weight_min_reports", 0),
        ("valid_window_min", 0),
    ],
)
def test_invalid_policy_values_are_rejected(row_id, broken, tmp_path, monkeypatch):
    """37. 정책값을 잘못 넣으면 조용히 통과하지 않고 PolicyError로 걸린다."""
    with open(policy.POLICIES_DIR / f"{policy.DEFAULT_POLICY}.json", encoding="utf-8") as f:
        doc = json.load(f)
    for row in doc["rows"]:
        if row["id"] == row_id:
            row["value"] = broken
    doc["policy_version"] = "broken"
    (tmp_path / "broken.json").write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")

    monkeypatch.setattr(policy, "POLICIES_DIR", tmp_path)
    policy.load.cache_clear()
    try:
        with pytest.raises(policy.PolicyError):
            policy.load("broken")
    finally:
        policy.load.cache_clear()
