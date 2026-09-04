"""B. 불변식(임계값 무관, 영구) + C. 임계값 스냅샷(룰셋 버전에 묶임)."""
from __future__ import annotations

import pytest

from module_c_urban_rule import run
from module_c_urban_rule.rules import LEVELS, level_index

DRAINAGE = ("low", "medium", "high")
COMBOS = [(d, k) for d in DRAINAGE for k in (True, False)]


def _level(rainfall, known_risk, drainage, underpass_id="SC-UP-TEST"):
    result = run(
        {
            "underpass_id": underpass_id,
            "rainfall_intensity_1h_mm": rainfall,
            "known_risk": known_risk,
            "drainage_capacity_class": drainage,
        }
    )
    assert result["status"] == "ok", result
    return result["data"]["alert_level"]


# --- B. 불변식 ---------------------------------------------------------------------


@pytest.mark.parametrize("drainage,known_risk", COMBOS)
def test_monotonic_in_rainfall(drainage, known_risk, any_ruleset):
    """4. 강수가 늘 때 등급은 절대 내려가지 않는다 (0~200mm/h, 6조합 × 2룰셋)."""
    previous = -1
    for tenth_mm in range(0, 2001, 5):
        current = level_index(_level(tenth_mm / 10, known_risk, drainage))
        assert current >= previous, (
            f"{tenth_mm / 10}mm/h에서 등급이 하락 (ruleset={any_ruleset}, "
            f"drainage={drainage}, known_risk={known_risk})"
        )
        previous = current


@pytest.mark.parametrize("known_risk", [True, False])
@pytest.mark.parametrize("rainfall", [0.0, 5.0, 15.0, 25.0, 35.0, 45.0, 60.0, 71.9, 72.0, 120.0])
def test_monotonic_in_drainage_capacity(rainfall, known_risk, any_ruleset):
    """5. 같은 강수라면 배수능력이 나쁠수록 등급이 높거나 같다 (low >= medium >= high)."""
    low, medium, high = (level_index(_level(rainfall, known_risk, d)) for d in DRAINAGE)
    assert low >= medium >= high, f"ruleset={any_ruleset}, rainfall={rainfall}"


@pytest.mark.parametrize("drainage", DRAINAGE)
@pytest.mark.parametrize("rainfall", [0.0, 5.0, 15.0, 25.0, 35.0, 45.0, 60.0, 71.9, 72.0, 120.0])
def test_monotonic_in_known_risk(rainfall, drainage, any_ruleset):
    """6. 지정 위험 지하차도는 같은 조건의 비지정보다 등급이 높거나 같다."""
    assert level_index(_level(rainfall, True, drainage)) >= level_index(
        _level(rainfall, False, drainage)
    ), f"ruleset={any_ruleset}, rainfall={rainfall}, drainage={drainage}"


@pytest.mark.parametrize("drainage,known_risk", COMBOS)
def test_output_domain_and_zero_rainfall(drainage, known_risk, any_ruleset):
    """7. 출력은 항상 4개 enum 안이고, 무강우면 지정 위험이어도 '정상'이다.

    known_risk_min_level 정책은 '강수 > 0'을 요구하므로 0.0mm에서는 발동하지 않는다.
    """
    for tenth_mm in range(0, 2001, 25):
        assert _level(tenth_mm / 10, known_risk, drainage) in LEVELS
    assert _level(0.0, known_risk, drainage) == "정상"


# --- C. 임계값 스냅샷 (근거 주입/룰셋 교체 시 함께 갱신) ---------------------------


@pytest.mark.parametrize(
    "rainfall,expected",
    [
        (20.0 - 1e-9, "정상"),
        (20.0, "주의"),
        (30.0 - 1e-9, "주의"),
        (30.0, "경계"),
        (50.0 - 1e-9, "경계"),
        (50.0, "위험"),
    ],
)
def test_cutpoint_boundaries_are_inclusive(rainfall, expected):
    """8. 절단점 경계는 >= 로 통일. medium(1.0) + known_risk=False(1.0)라 원시값 = effective."""
    assert _level(rainfall, False, "medium") == expected


@pytest.mark.parametrize(
    "rainfall,known_risk,drainage,expected",
    [
        (45.0, True, "low", "위험"),      # 계약 예시: 45 × 1.30 × 1.15 = 67.275
        (45.0, False, "medium", "경계"),  # 45.0
        (45.0, False, "high", "경계"),    # 38.25
        (25.0, False, "medium", "주의"),  # 25.0
        (10.0, False, "low", "정상"),     # 13.0
        (10.0, True, "low", "주의"),      # 14.95 → 정상이지만 min_level 하한으로 주의
        (0.0, True, "low", "정상"),       # 무강우 → 하한 미발동
    ],
)
def test_representative_cases_snapshot(rainfall, known_risk, drainage, expected):
    """9. 대표 케이스 스냅샷 — 임계값이 바뀌면 여기가 깨지는 게 정상이다."""
    assert _level(rainfall, known_risk, drainage) == expected


# --- extreme_override (v1 신규) ----------------------------------------------------


def test_extreme_override_forces_danger_in_v1(monkeypatch):
    """추가. 72.0mm/h + 배수 high + known_risk false → 계수와 무관하게 '위험'.

    가중 적용 시 72 × 0.85 = 61.2로 '위험' 절단점(50)을 넘긴 하지만, override가
    실제로 원시값 기준으로 먼저 작동하는지는 아래 v0 대비 테스트가 확인한다.
    """
    monkeypatch.setenv("AQUAGUARD_MODULE_C_RULESET", "v1_kma_mois")
    assert _level(72.0, False, "high") == "위험"


def test_extreme_override_beats_drainage_capacity(monkeypatch):
    """추가-b. 배수능력이 아무리 좋아도 극한호우 단독 기준은 우회되지 않는다.

    극단적으로 유리한 가중을 넣어도(effective가 절단점 미만이 되도록) override가
    이긴다 — 원시 강우강도로 비교한다는 규칙이 실제로 지켜지는지 확인.
    """
    monkeypatch.setenv("AQUAGUARD_MODULE_C_RULESET", "v1_kma_mois")
    import module_c_urban_rule.ruleset as ruleset_module
    from module_c_urban_rule import rules

    rs = ruleset_module.active_ruleset()
    monkeypatch.setattr(type(rs), "drainage_factor", lambda self, cls: 0.01)
    decision = rules.evaluate(72.0, False, "high", rs)
    assert decision.alert_level == "위험"
    assert decision.decisive_rule == "extreme_override"
    assert decision.effective_mm < 50.0


def test_v0_has_no_extreme_override(monkeypatch):
    """추가-c. v0에는 override 행이 없다 — 룰셋 간 판정 차이를 실제로 만들 수 있어야 한다."""
    from module_c_urban_rule import ruleset as ruleset_module

    monkeypatch.setenv("AQUAGUARD_MODULE_C_RULESET", "v0_placeholder")
    assert ruleset_module.active_ruleset().extreme_override_mm() is None
    monkeypatch.setenv("AQUAGUARD_MODULE_C_RULESET", "v1_kma_mois")
    assert ruleset_module.active_ruleset().extreme_override_mm() == 72.0
