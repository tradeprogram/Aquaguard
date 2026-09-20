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
