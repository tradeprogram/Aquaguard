"""E. 룰셋 무결성 + 근거(provenance) 노출."""
from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from module_c_urban_rule import explain, run, ruleset

RULESETS_DIR = Path(ruleset.RULESETS_DIR)
BASE = {
    "underpass_id": "SC-UP-003",
    "rainfall_intensity_1h_mm": 45.0,
    "known_risk": True,
    "drainage_capacity_class": "low",
}


def test_every_ruleset_file_validates_and_loads(any_ruleset):
    """15. 룰셋 JSON이 자체 스키마를 통과하고, 절단점 오름차순·계수 양수 검증을 통과한다."""
    with open(ruleset.RULESET_SCHEMA_PATH, encoding="utf-8") as f:
        schema = json.load(f)
    with open(RULESETS_DIR / f"{any_ruleset}.json", encoding="utf-8") as f:
        doc = json.load(f)

    jsonschema.validate(doc, schema)
    loaded = ruleset.load(any_ruleset)  # _validate_semantics까지 통과해야 성공
    assert loaded.version == any_ruleset
    values = [v for _, v in loaded.cutpoints()]
    assert values == sorted(values)


def test_descending_cutpoints_are_rejected(tmp_path, monkeypatch):
    """15-b. 절단점을 잘못 넣으면 조용히 통과하지 않고 RulesetError로 걸린다."""
    with open(RULESETS_DIR / "v1_kma_mois.json", encoding="utf-8") as f:
        doc = json.load(f)
    for row in doc["rows"]:
        if row["id"] == "cutpoint_주의":
            row["value"] = 999.0
    doc["ruleset_version"] = "broken"
    (tmp_path / "broken.json").write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")

    monkeypatch.setattr(ruleset, "RULESETS_DIR", tmp_path)
    ruleset.load.cache_clear()
    try:
        with pytest.raises(ruleset.RulesetError, match="오름차순"):
            ruleset.load("broken")
    finally:
        ruleset.load.cache_clear()


def test_strict_provenance_warning_is_opt_in(monkeypatch):
    """16. PLACEHOLDER 경고는 기본 off(계약 예시의 warnings=[]와 충돌하므로), 스위치로 켠다."""
    assert run(BASE)["warnings"] == []

    monkeypatch.setenv("AQUAGUARD_MODULE_C_STRICT_PROVENANCE", "1")
    warnings = run(BASE)["warnings"]
    assert len(warnings) == 1
    assert "근거 미확정" in warnings[0]
    assert "drainage_factor=PLACEHOLDER" in warnings[0]


def test_v1_confirms_the_rows_we_claimed_to_source():
    """16-b. v1에서 근거를 주입했다고 말한 행이 실제로 그 상태·출처를 갖고 있다."""
    rs = ruleset.load("v1_kma_mois")
    expected = {
        "cutpoint_주의": "DERIVED",
        "cutpoint_경계": "DERIVED",
        "cutpoint_위험": "CONFIRMED_COMPONENT",
        "extreme_override": "CONFIRMED",
        "known_risk_min_level": "POLICY_CONFIRMED_DIRECTION",
        "drainage_factor": "PLACEHOLDER",
        "known_risk_factor": "PLACEHOLDER",
    }
    assert {rid: rs.row(rid).status for rid in expected} == expected

    # 출처가 있다고 표시한 행은 최소한 기관·문서가 채워져 있어야 한다.
    for row_id, status in expected.items():
        source = rs.row(row_id).source
        if status == "PLACEHOLDER":
            assert source["agency"] is None, row_id
        else:
            assert source["agency"] and source["document"], row_id


def test_v0_is_entirely_unsourced():
    """16-c. v0는 기준선이므로 전 행이 PLACEHOLDER여야 비교 대상으로 의미가 있다."""
    rs = ruleset.load("v0_placeholder")
    assert {r.status for r in rs.rows.values()} == {"PLACEHOLDER"}
    assert all(r.source["agency"] is None for r in rs.rows.values())


def test_explain_carries_provenance_without_touching_contract():
    """추가. 판정 근거는 data가 아니라 explain()으로만 나간다 (§6.1)."""
    detail = explain(BASE)
    assert detail["is_model"] is False
    assert detail["decision"]["alert_level"] == "위험"
    assert detail["decision"]["applied_factors"] == {
        "drainage_factor": 1.3,
        "known_risk_factor": 1.15,
    }
    assert detail["ruleset"]["ruleset_version"] == "v1_kma_mois"
    assert detail["ruleset"]["status_counts"]["PLACEHOLDER"] == 2
    urls = {r["source"]["url"] for r in detail["ruleset"]["rows"] if r["source"]["url"]}
    assert urls == {
        "https://www.kma.go.kr/kma/news/press.jsp?mode=view&num=1194492",  # 극한호우 보도자료
        "https://www.weather.go.kr/w/forecast/guide/standard.do",           # 기상특보 발표기준
    }


def test_explain_reports_fallbacks_for_broken_input():
    """추가-b. 폴백이 걸린 입력도 explain()으로 왜 그렇게 판정됐는지 추적할 수 있다."""
    detail = explain({"underpass_id": "SC-UP-003", "rainfall_intensity_1h_mm": 45.0})
    assert detail["fallback_tier"] == 2
    assert detail["normalized_input"]["known_risk"] is True
    assert detail["normalized_input"]["drainage_capacity_class"] == "low"
    assert len(detail["input_warnings"]) == 2


def test_sourced_rows_record_when_the_url_was_verified(any_ruleset):
    """추가-c. URL을 적어둔 행은 retrieved(검증 시점)도 반드시 채워져 있어야 한다.

    출처 URL만 적고 실제로 열어보지 않은 상태를 룰셋에 남기지 않기 위한 불변식.
    심사 제출 시 '이 숫자 근거 있나요'에 대한 답이 링크 하나로 끝나지 않으려면
    누가 언제 확인했는지가 파일에 남아 있어야 한다.
    """
    rs = ruleset.load(any_ruleset)
    for row in rs.rows.values():
        if row.source["url"]:
            assert row.source["retrieved"], f"{row.id}: URL은 있는데 retrieved가 비어 있다"
            assert row.source["agency"] and row.source["document"], row.id


def test_kma_rows_cite_the_verified_press_release():
    """추가-d. 기상청 근거 2행이 검증된 보도자료 제목·시행일을 그대로 들고 있다."""
    rs = ruleset.load("v1_kma_mois")
    for row_id in ("cutpoint_위험", "extreme_override"):
        source = rs.row(row_id).source
        assert source["agency"] == "기상청"
        assert "호우 긴급재난문자 전국 확대 운영" in source["document"]
        assert "2025-05-14" in source["document"]
        assert source["effective"] == "2025-05-15"
        assert source["retrieved"] == "2026-09-04"
        assert "URL 접속 검증 완료" in rs.row(row_id).note


def test_corroborating_sources_are_verified_and_quoted(any_ruleset):
    """추가-e. 보도 확인 근거도 URL·검증시점·원문 인용을 반드시 갖춘다."""
    rs = ruleset.load(any_ruleset)
    for row in rs.rows.values():
        for item in row.corroborating_sources:
            assert item["url"].startswith("http"), f"{row.id}: 보도 URL 형식 오류"
            assert item["retrieved"], f"{row.id}: 보도 근거에 retrieved가 없다"
            assert item["quote"].strip(), f"{row.id}: 인용문이 비어 있다"


def test_policy_row_cites_two_verified_reports_but_no_primary_url():
    """추가-f. known_risk_min_level은 보도 2건으로 뒷받침되지만 1차 자료 URL은 아직 없다.

    2차 출처가 1차 자료 자리를 슬쩍 차지하지 않도록 source.url이 null인 것까지 고정한다.
    """
    row = ruleset.load("v1_kma_mois").row("known_risk_min_level")
    assert row.status == "POLICY_CONFIRMED_DIRECTION"
    assert row.source["agency"] == "행정안전부"
    assert row.source["url"] is None, "행안부 1차 자료 URL은 아직 미확보 상태여야 한다"

    outlets = [c["outlet"] for c in row.corroborating_sources]
    assert outlets == ["뉴시스", "아시아경제"]
    assert all("5㎝" in c["quote"] or "5㎝로" in c["quote"] for c in row.corroborating_sources)
    assert "침수 초기단계부터 통제" in row.corroborating_sources[1]["quote"]


def test_special_report_cutpoints_cite_the_official_standard_page():
    """추가-g. 주의/경계 절단점이 기상청 공식 '기상특보 발표기준' 페이지를 출처로 갖는다.

    공식 페이지 접속이 확인돼 source.url을 채웠지만, 공식 기준은 3시간·12시간 누적이고
    계약 입력에는 1시간 강우강도뿐이라 시간 균등환산 가정은 그대로 남는다 —
    그래서 status는 CONFIRMED가 아니라 DERIVED로 고정한다.
    """
    rs = ruleset.load("v1_kma_mois")
    expected_clause = {"cutpoint_주의": ("60mm", 20.0), "cutpoint_경계": ("90mm", 30.0)}

    for row_id, (needle, value) in expected_clause.items():
        row = rs.row(row_id)
        assert row.status == "DERIVED", "환산 가정이 남아 있는 한 CONFIRMED로 올리지 않는다"
        assert row.value == value
        assert row.source["agency"] == "기상청"
        assert row.source["url"] == "https://www.weather.go.kr/w/forecast/guide/standard.do"
        assert row.source["retrieved"] == "2026-09-04"
        assert needle in row.source["clause"]
        assert "3시간" in row.source["clause"] and "12시간" in row.source["clause"]
        assert "시간 균등환산" in row.note

        outlets = [c["outlet"] for c in row.corroborating_sources]
        assert outlets == ["세계일보", "YTN"]


def test_twelve_hour_criterion_is_documented_as_unusable():
    """추가-h. 공식 기준의 12시간 조건을 계약 입력으로 못 쓴다는 사실을 note에 남긴다.

    cutpoint_위험의 3시간 조건과 같은 구조적 한계다 — 계약에 누적강우 필드가 추가되면
    세 절단점 모두 승격 검토 대상이 된다(TRACK2_CONTRACT_AGENDA.md 1·6번).
    """
    rs = ruleset.load("v1_kma_mois")
    for row_id in ("cutpoint_주의", "cutpoint_경계"):
        assert "1시간 강우강도밖에" in rs.row(row_id).note
