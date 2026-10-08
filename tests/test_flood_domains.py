"""침수 모형 영역 목록과 계산 범위(현장조사 반영 ④⑤).

침수 래스터는 nodata=0이라 "안 잠김"과 "계산 안 함"이 같은 값이다. 어디까지 계산했는지는
래스터 밖에서 따로 알아야 하고, 그게 이 목록이다.
"""
import subprocess
import sys

import pytest
from shapely.geometry import box

from module_b_flood import domains


def test_registry_lists_both_domains():
    ds = {d.id: d for d in domains.load_domains()}
    assert ds["gyeongho_reach"].available
    assert ds["gyeongho_reach"].stage_series["gauge"] == "경호교"
    assert "deokcheon_upper" in ds


def test_gyeongho_footprint_is_model_grid():
    d = next(d for d in domains.load_domains() if d.id == "gyeongho_reach")
    assert domains.footprint_5179(d) == pytest.approx((1028000, 1703000, 1042000, 1723000))


def test_planned_domain_has_footprint_before_it_is_run():
    d = next(d for d in domains.load_domains() if d.id == "deokcheon_upper")
    fp = domains.footprint_5179(d)
    assert fp is not None and fp[0] < fp[2] and fp[1] < fp[3]


def test_coverage_splits_county():
    county = box(1020000, 1700000, 1050000, 1730000)
    cov = domains.coverage(county)
    assert cov["covered"].area + cov["uncovered"].area == pytest.approx(county.area)
    covered_expected = sum(
        box(*domains.footprint_5179(d)).intersection(county).area for d in domains.load_domains() if d.available
    )
    assert cov["covered"].area == pytest.approx(covered_expected)


def test_sancheong_coverage_is_about_a_third():
    cov = domains.coverage(domains.county_5179("38570"))
    assert 0.30 < cov["covered_ratio"] < 0.40


def test_deokcheon_build_script_dry_run():
    r = subprocess.run(
        [sys.executable, "module_b_flood/scripts/33d_sfincs_build_deokcheon.py", "--dry-run"],
        capture_output=True, text=True, encoding="utf-8", cwd=domains.REPO,
    )
    assert r.returncode == 0, r.stderr
    assert "격자" in r.stdout
