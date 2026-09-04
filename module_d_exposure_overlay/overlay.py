"""공간연산 엔진 (Module D).

계약 필드명도 공통 봉투도 모른다 — 정규화된 shapely 지오메트리를 받아 노출자산을
계산하는 순수 함수들만 둔다. 좌표는 전부 EPSG:5179 미터라 면적이 곧 ㎡다(§4.1).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union
from shapely.strtree import STRtree

from .policy import ExposurePolicy

SQUARE_METERS_PER_HECTARE = 10_000.0


@dataclass
class RiskArea:
    geometry: BaseGeometry
    risk_prob: float
    source_module: str


@dataclass
class OverlayResult:
    exposed_buildings: list[dict[str, Any]] = field(default_factory=list)
    exposed_farmland_ha: float = 0.0
    risk_union_area_m2: float = 0.0
    notes: list[str] = field(default_factory=list)


def build_risk_union(areas: list[RiskArea]) -> BaseGeometry | None:
    """위험영역들의 합집합.

    합치지 않고 폴리곤별로 농경지를 교차시키면 A와 B가 겹치는 구간이 두 번
    계산된다 — exposed_farmland_ha 정확도의 핵심이라 반드시 먼저 합친다.
    """
    if not areas:
        return None
    union = unary_union([a.geometry for a in areas])
    return None if union.is_empty else union


def _really_intersects(a: BaseGeometry, b: BaseGeometry) -> bool:
    """경계만 맞닿은 경우는 노출로 치지 않는다 — 면이 겹쳐야 침수 노출이다."""
    return a.intersects(b) and not a.touches(b)


def _first_present(properties: dict[str, Any], keys: list[str]) -> Any:
    for key in keys:
        if key in properties and properties[key] not in (None, ""):
            return properties[key]
    return None


def extract_building_id(feature: dict[str, Any], index: int, policy: ExposurePolicy) -> str:
    properties = feature.get("properties") or {}
    if isinstance(properties, dict):
        found = _first_present(properties, policy.building_id_keys)
        if found is not None:
            return str(found)
    if feature.get("id") not in (None, ""):
        return str(feature["id"])
    # 결정적 합성 id — 같은 입력이면 항상 같은 값이 나와야 재현 가능한 테스트가 된다.
    return f"D-AUTO-{index:04d}"


def extract_use_type(feature: dict[str, Any], policy: ExposurePolicy) -> str:
    properties = feature.get("properties") or {}
    raw = _first_present(properties, policy.use_type_keys) if isinstance(properties, dict) else None
    if raw is None:
        return policy.use_type_when_no_attribute
    text = str(raw).strip()
    for canonical, candidates in policy.source_value_mapping.items():
        if text in candidates:
            return canonical
    return policy.use_type_when_unrecognized


def find_exposed_buildings(
    areas: list[RiskArea],
    features: list[dict[str, Any]],
    geometries: list[BaseGeometry | None],
    policy: ExposurePolicy,
) -> list[dict[str, Any]]:
    """위험영역과 실제로 겹치는 건물만 골라 risk_prob를 배정한다.

    한 건물이 여러 위험영역에 걸치면 risk_prob는 최댓값을 쓴다(보수적).
    """
    if not areas:
        return []

    usable = [(index, geom) for index, geom in enumerate(geometries) if geom is not None]
    if not usable:
        return []

    tree = STRtree([geom for _, geom in usable])
    best: dict[int, float] = {}

    for area in areas:
        for position in tree.query(area.geometry):
            index, geom = usable[position]
            if _really_intersects(area.geometry, geom):
                if area.risk_prob > best.get(index, -1.0):
                    best[index] = area.risk_prob

    exposed = [
        {
            "building_id": extract_building_id(features[index], index, policy),
            "risk_prob": risk_prob,
            "use_type": extract_use_type(features[index], policy),
        }
        for index, risk_prob in best.items()
        if risk_prob >= policy.min_risk_prob
    ]
    # 호출할 때마다 순서가 흔들리면 Module G·UI가 흔들린다.
    exposed.sort(key=lambda item: item["building_id"])
    return exposed


def farmland_area_ha(
    risk_union: BaseGeometry | None,
    parcels: list[BaseGeometry | None],
    policy: ExposurePolicy,
) -> float:
    """위험영역 ∩ 농경지 면적(ha). 농경지끼리도 먼저 합쳐 필지 중복을 없앤다."""
    if risk_union is None:
        return 0.0
    usable = [p for p in parcels if p is not None]
    if not usable:
        return 0.0
    farmland_union = unary_union(usable)
    if farmland_union.is_empty:
        return 0.0
    area_m2 = risk_union.intersection(farmland_union).area
    return round(area_m2 / SQUARE_METERS_PER_HECTARE, policy.area_round_digits)
