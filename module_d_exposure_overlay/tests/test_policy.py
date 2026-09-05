"""D. 정책 파일 무결성 + D/G 공유 구조."""
from __future__ import annotations

import json

import jsonschema
import pytest

from module_d_exposure_overlay import explain, policy

from .conftest import collection, feature, offset_rect, risk


@pytest.mark.parametrize("name", [policy.MODULE_D_POLICY, policy.USE_TYPE_POLICY])
def test_policy_files_validate_and_load(name):
    """21. 정책 JSON이 자체 스키마를 통과하고 의미 검증까지 통과한다."""
    with open(policy.POLICY_SCHEMA_PATH, encoding="utf-8") as f:
        schema = json.load(f)
    with open(policy.POLICIES_DIR / f"{name}.json", encoding="utf-8") as f:
        jsonschema.validate(json.load(f), schema)
    assert policy.load(name).rows


def test_use_type_policy_lives_outside_module_d_so_module_g_can_share_it():
    """22. use_type 어휘는 D 패키지 밖(저장소 최상위 policies/)에 있다.

    Module O가 call_module("g", {**exposure, ...})로 D의 출력을 G의 입력에 그대로
    펼치므로 use_type은 두 모듈의 공유 어휘다. 한쪽 패키지 안에 두면 다른 쪽이
    그 패키지에 의존하게 되고 §4.2의 모듈 독립성이 깨진다.
    """
    module_d_dir = policy.Path(policy.__file__).resolve().parent
    shared = (policy.POLICIES_DIR / f"{policy.USE_TYPE_POLICY}.json").resolve()
    assert shared.is_file()
    assert module_d_dir not in shared.parents
    assert shared.parent.name == "policies"
    assert shared.parent.parent == module_d_dir.parent


def test_use_type_vocabulary_is_the_approved_seven():
    """23. 2026-09-04 승인된 7종 어휘. 계약 예시의 '주거'를 포함한다."""
    vocabulary = policy.load(policy.USE_TYPE_POLICY).value("vocabulary")
    assert vocabulary == ["주거", "상업", "공업", "농업", "공공", "기타", "미상"]


def test_mapping_and_fallbacks_stay_inside_the_vocabulary():
    """23-b. 매핑 분류와 폴백 값이 어휘 밖으로 새지 않는다 — G가 모르는 키를 받지 않게."""
    pol = policy.active_policy()  # _validate가 여기서 돌아간다
    assert set(pol.source_value_mapping) <= set(pol.vocabulary)
    assert pol.use_type_when_no_attribute in pol.vocabulary
    assert pol.use_type_when_unrecognized in pol.vocabulary


def test_buffer_row_is_flagged_as_an_assumption():
    """24. 점 버퍼 반경은 PLACEHOLDER이고, note가 폴백 전락 계획을 명시한다."""
    row = policy.load(policy.MODULE_D_POLICY).row("point_buffer_radius_m")
    assert row.status == "PLACEHOLDER"
    assert row.is_settled is False
    assert row.value == {"enabled": True, "radius_m": 100.0}
    assert "산사태 도달거리 자릿수 가정" in row.note
    assert "버퍼 경로는 폴백으로만 남음" in row.note


def test_team_decisions_are_recorded_as_such():
    """25. 팀 결정값은 PLACEHOLDER가 아니라 TEAM_DECISION으로 구분해 기록한다.

    '아직 근거를 못 찾은 값'과 '찾을 근거가 없어 팀이 정한 값'은 후속 조치가
    다르다 — 전자는 조사 대상, 후자는 조사해도 안 나온다.
    """
    module_d = policy.load(policy.MODULE_D_POLICY)
    assert module_d.row("min_risk_prob").status == "TEAM_DECISION"
    assert module_d.row("min_risk_prob").value == 0.0
    assert module_d.row("farmland_area_round_digits").status == "TEAM_DECISION"


def test_explain_exposes_both_policy_files(documented_case):
    """26. explain()이 두 정책 파일의 근거 상태를 모두 들고 나온다(§6.1 Provenance)."""
    summary = explain(documented_case)["policy"]
    assert summary["module_d"]["policy_version"] == "module_d_v1"
    assert summary["use_type"]["policy_version"] == "use_type_v1"
    unsettled = {r["id"] for r in summary["module_d"]["rows"] if r["status"] == "PLACEHOLDER"}
    assert "point_buffer_radius_m" in unsettled


def test_explain_marks_module_d_as_not_a_model(documented_case):
    """추가. D는 공간 오버레이지 학습된 모델이 아니다 - C/G/H와 같은 표기를 낸다.

    §6.1 Provenance 배지가 네 모듈을 같은 방식으로 읽을 수 있어야 한다.
    """
    assert explain(documented_case)["is_model"] is False
