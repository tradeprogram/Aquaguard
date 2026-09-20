"""계약 준수 테스트 — contracts/module_a.{schema,example}.json 대조."""
from __future__ import annotations

import json
from pathlib import Path

import module_a_landslide as A

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = json.loads((ROOT / "contracts" / "module_a.example.json").read_text(encoding="utf-8"))


def _run_example():
    return A.run(EXAMPLE["input"])


def test_envelope_shape():
    out = _run_example()
    assert set(out) == {"status", "fallback_tier", "data", "warnings"}
    assert out["status"] in {"ok", "degraded", "error"}
    assert out["fallback_tier"] in {1, 2, 3}
    assert isinstance(out["warnings"], list)


def test_data_fields_match_contract():
    required = set(EXAMPLE["output"]["data"])
    out = _run_example()
    assert required.issubset(set(out["data"])), required - set(out["data"])


def test_prob_and_ci_ranges():
    d = _run_example()["data"]
    assert 0.0 <= d["landslide_prob"] <= 1.0
    lo, hi = d["confidence_interval"]
    assert 0.0 <= lo <= hi <= 1.0
    assert d["source"] in {"observed", "forecast"}
    assert isinstance(d["amplification_factor"], (int, float))
    assert isinstance(d["precursor_flag"], bool)


def test_location_preserved():
    d = _run_example()["data"]
    assert d["location"]["x_5179"] == EXAMPLE["input"]["x_5179"]
    assert d["location"]["y_5179"] == EXAMPLE["input"]["y_5179"]


def test_never_raises_on_garbage():
    for bad in [{}, {"static": None}, {"x_5179": 1}, {"x_5179": 1, "y_5179": 2}]:
        out = A.run(bad)
        assert out["status"] in {"ok", "degraded", "error"}


def test_missing_location_is_error():
    out = A.run({"static": {"slope_deg": 30}})
    assert out["status"] == "error"


# --- 값까지 검사 (1차 작업지시서 P0-3) --------------------------------------
#
# 종전 test_contract 는 **필드 존재만** 봐서, 계약 예시의 landslide_prob 0.78 과
# 실제 A.run() 의 0.007 이 어긋난 채로 통과하고 있었다(목업 시절 값이 남아 있었다).
# 다른 모듈의 example 은 "자기 input 으로 자기 output 을 재현하는지"가 테스트로
# 고정돼 있는데 A 만 빠져 있었다 — 여기서 맞춘다.

def test_example_output_is_reproducible():
    """example.input 을 넣으면 example.output 이 그대로 나와야 한다."""
    got = _run_example()
    want = EXAMPLE["output"]
    assert got["status"] == want["status"]
    assert got["fallback_tier"] == want["fallback_tier"]

    gd, wd = got["data"], want["data"]
    for k in ("landslide_prob", "amplification_factor"):
        assert abs(gd[k] - wd[k]) < 1e-9, (k, gd[k], wd[k])
    for k in ("source", "precursor_flag", "hours_to_critical"):
        assert gd[k] == wd[k], (k, gd[k], wd[k])
    assert gd["confidence_interval"] == wd["confidence_interval"]
    assert gd["location"] == wd["location"]


def test_example_prob_is_not_a_mockup():
    """예시 확률이 '그럴듯한 숫자'가 아니라 실제 산출값인지 — 회귀 방지.

    0.78 은 목업 시절 값이었다. 실제 좌표·실측 static 으로 재현되지 않는 값이
    다시 들어오면 여기서 걸린다.
    """
    d = _run_example()["data"]
    assert abs(d["landslide_prob"] - EXAMPLE["output"]["data"]["landslide_prob"]) < 1e-9


def test_example_risk_polygon_shape():
    """risk_polygon_5179 은 계약이 정한 타입이거나 null."""
    rp = _run_example()["data"]["risk_polygon_5179"]
    assert rp is None or rp["type"] in {"Polygon", "MultiPolygon", "FeatureCollection"}
