"""위험 폴리곤 레이어 + 계약 risk_polygon_5179 테스트.

계약(module_a.schema.json, 안건 1 2026-09-04)은 이 필드를 Polygon/MultiPolygon/
FeatureCollection 또는 null 로 규정하고, null 일 때만 Module D 가 location 을 반경
버퍼로 흡수하도록 정했다. 그러니 여기서 지킬 것은:
  1) 산청 위험영역 근처에서는 실제 지오메트리가 나온다(= D 가 버퍼 폴백을 안 쓴다)
  2) 위험영역에서 먼 곳에서는 **없는 위험영역을 지어내지 않는다** → null
  3) arrival_hour 로 자르면 시간에 따라 누적면적이 단조증가한다(애니메이션 전제)
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import module_a_landslide as A
from module_a_landslide import risk_layers

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = json.loads((ROOT / "contracts" / "module_a.example.json").read_text(encoding="utf-8"))

# risk_landslide_index.json 의 A_soilmap_critical 대표지점
NEAR_RISK = (1046783.0, 1707543.0)
FAR_FROM_RISK = (1020800.0, 1729600.0)   # 산청 AOI 안이지만 위험영역에서 먼 곳

layer_required = pytest.mark.skipif(not risk_layers.available(),
                                    reason="위험 폴리곤 레이어 미탑재")


def _input(x, y):
    i = json.loads(json.dumps(EXAMPLE["input"]))
    i["x_5179"], i["y_5179"] = x, y
    i["static"].update(slope_deg=37.6, dnbr=0.49, dnbr_class="high", days_since_fire=121)
    i["dynamic"].update(rainfall_cumulative_24h_mm=187.3, api_index=0.81, source="observed")
    return i


@layer_required
def test_layer_loads_with_features():
    fc = risk_layers.load()
    assert fc["type"] == "FeatureCollection"
    assert len(fc["features"]) > 0
    for f in fc["features"]:
        p = f["properties"]
        assert isinstance(p["arrival_hour"], int)
        assert f["geometry"]["type"] in {"Polygon", "MultiPolygon"}


@layer_required
def test_local_near_risk_returns_geometry():
    g = risk_layers.local(*NEAR_RISK)
    assert g is not None
    assert g["type"] == "MultiPolygon"
    assert len(g["coordinates"]) > 0


@layer_required
def test_local_far_from_risk_is_none():
    """위험영역이 없는 곳에서 지어내지 않는다 — 계약이 정한 null 폴백."""
    assert risk_layers.local(*FAR_FROM_RISK, radius_m=500.0) is None


def test_local_missing_coords_is_none():
    assert risk_layers.local(None, None) is None


@layer_required
def test_arrival_hour_filter_is_monotone():
    """시간을 넘길수록 누적 위험면적은 줄지 않는다(애니메이션 전제)."""
    areas = [risk_layers.total_area_m2(arrival_hour=h) for h in (0, 20, 32, 33, 38)]
    assert areas == sorted(areas)
    assert areas[-1] > areas[0]


def test_unknown_layer_returns_empty_not_crash():
    fc = risk_layers.load(scenario="없는시나리오", level="없는등급")
    assert fc["features"] == []
    assert risk_layers.local(*NEAR_RISK, scenario="없는시나리오") is None


def test_contract_field_present_and_typed():
    """risk_polygon_5179 는 계약 required — 항상 있어야 하고 타입이 맞아야 한다."""
    for x, y in (NEAR_RISK, FAR_FROM_RISK):
        d = A.run(_input(x, y))["data"]
        assert "risk_polygon_5179" in d
        rp = d["risk_polygon_5179"]
        assert rp is None or rp["type"] in {"Polygon", "MultiPolygon", "FeatureCollection"}


def test_error_envelope_still_has_contract_field():
    d = A.run({})["data"]          # 좌표 결측 → error 봉투
    assert "risk_polygon_5179" in d and d["risk_polygon_5179"] is None


@layer_required
def test_near_risk_run_reports_layer_use():
    out = A.run(_input(*NEAR_RISK))
    assert out["data"]["risk_polygon_5179"] is not None
    assert any("risk_polygon_5179" in w for w in out["warnings"])
