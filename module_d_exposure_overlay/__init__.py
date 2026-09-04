"""module_d_exposure_overlay — 노출자산 오버레이 (§5 Module D).

§4.2 표준 진입점 run(input: dict) -> dict. Module O는 modules_client.py가 이
패키지를 import_module로 불러 run()을 호출한다.

폴백 계층(§7에 Module D 행이 없어 트랙②가 신규 제안, Day 1 계약 회의 안건):
  tier 1  위험 폴리곤·건물·농경지 모두 정상
  tier 2  일부만 유효 — 점 버퍼 대체, 무효 지오메트리 제외·복구, 컬렉션 형식 오류
  tier 3  쓸 수 있는 위험 지오메트리가 하나도 없음 → 노출 0건
  error   입력이 dict가 아니거나 risk_polygons가 배열이 아님

어느 경로든 스키마를 만족하는 봉투를 내고 예외를 밖으로 던지지 않는다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from shapely.geometry.base import BaseGeometry

from . import geometry as geom_util
from . import overlay, policy, use_types
from .envelope import envelope, error_envelope
from .overlay import RiskArea

__all__ = ["run", "explain"]


@dataclass
class _Prepared:
    areas: list[RiskArea] = field(default_factory=list)
    building_features: list[dict[str, Any]] = field(default_factory=list)
    building_geometries: list[BaseGeometry | None] = field(default_factory=list)
    farmland_geometries: list[BaseGeometry | None] = field(default_factory=list)
    fallback_tier: int = 1
    warnings: list[str] = field(default_factory=list)
    used_point_buffer: bool = False
    fatal: bool = False
    building_use_types: list[str] = field(default_factory=list)
    use_type_origin_counts: dict[str, int] = field(default_factory=dict)
    parcel_mapping_available: bool = False
    parcel_mapping_size: int = 0
    parcel_mapping_path: str = ""


def _prepare_risk_areas(raw_polygons, pol, prepared):
    buffer_m = pol.buffer_radius_m if pol.buffer_enabled else None

    for index, entry in enumerate(raw_polygons):
        label = f"risk_polygons[{index}]"
        if not isinstance(entry, dict):
            prepared.warnings.append(f"{label}: 항목이 dict가 아님 → 제외")
            prepared.fallback_tier = max(prepared.fallback_tier, 2)
            continue

        raw_prob = entry.get("risk_prob")
        if not isinstance(raw_prob, (int, float)) or isinstance(raw_prob, bool):
            prepared.warnings.append(f"{label}: risk_prob가 숫자가 아님({raw_prob!r}) → 제외")
            prepared.fallback_tier = max(prepared.fallback_tier, 2)
            continue
        risk_prob = float(raw_prob)
        if not 0.0 <= risk_prob <= 1.0:
            clamped = min(max(risk_prob, 0.0), 1.0)
            prepared.warnings.append(
                f"{label}: risk_prob {risk_prob}가 0.0~1.0 밖 → {clamped}로 보정(§4.1 확률 표기)"
            )
            prepared.fallback_tier = max(prepared.fallback_tier, 2)
            risk_prob = clamped

        normalized = geom_util.normalize(entry.get("geometry_5179"), label=label, buffer_m=buffer_m)
        if normalized.notes:
            prepared.warnings.extend(normalized.notes)
            prepared.fallback_tier = max(prepared.fallback_tier, 2)
        prepared.used_point_buffer = prepared.used_point_buffer or normalized.used_point_buffer
        if normalized.geometry is None:
            continue

        prepared.areas.append(
            RiskArea(
                geometry=normalized.geometry,
                risk_prob=risk_prob,
                source_module=str(entry.get("source_module", "unknown")),
            )
        )


def _prepare_collection(raw, label, prepared):
    """건물·농경지 컬렉션을 feature 목록과 지오메트리 목록으로 편다."""
    if not isinstance(raw, dict) or raw.get("type") != "FeatureCollection":
        prepared.warnings.append(f"{label}: FeatureCollection이 아님 → 빈 것으로 간주")
        prepared.fallback_tier = max(prepared.fallback_tier, 2)
        return [], []

    features = geom_util.iter_features(raw)
    geometries = []
    for index, feature in enumerate(features):
        # 자산 지오메트리는 점 버퍼 대상이 아니다 — 건물·필지는 원래 면이다.
        normalized = geom_util.normalize(feature, label=f"{label}[{index}]", buffer_m=None)
        if normalized.notes:
            prepared.warnings.extend(normalized.notes)
            prepared.fallback_tier = max(prepared.fallback_tier, 2)
        geometries.append(normalized.geometry)
    return features, geometries


def _resolve_building_use_types(prepared, pol):
    """건물 용도를 한 번에 해석한다. 매핑 파일이 없으면 조용히 폴백하되,
    실제로 조인이 필요한 건물이 있을 때만 warning을 남긴다(§4.2 모듈 독립성)."""
    parcels = use_types.load(pol.use_type_join_source_file)
    prepared.parcel_mapping_available = parcels.available
    prepared.parcel_mapping_size = len(parcels)
    prepared.parcel_mapping_path = pol.use_type_join_source_file

    if not parcels.available and overlay.needs_parcel_join(prepared.building_features, pol):
        prepared.warnings.append(
            f"건축물대장 주용도 매핑({pol.use_type_join_source_file})을 읽을 수 없음"
            f"({parcels.error}) -> 속성 탐색만으로 판정, 나머지는 '미상'."
            " 재생성: python scripts/fetch_building_use_types.py"
        )

    prepared.building_use_types, prepared.use_type_origin_counts = overlay.resolve_use_types(
        prepared.building_features, pol, parcels if parcels.available else None
    )


def _prepare(raw, pol):
    prepared = _Prepared()

    if not isinstance(raw, dict):
        prepared.fatal = True
        prepared.warnings.append(f"입력이 dict가 아님({type(raw).__name__}) → 판정 불가")
        return prepared

    raw_polygons = raw.get("risk_polygons")
    if not isinstance(raw_polygons, list):
        prepared.fatal = True
        prepared.warnings.append(
            f"risk_polygons가 배열이 아님({type(raw_polygons).__name__}) → 판정 불가"
        )
        return prepared

    _prepare_risk_areas(raw_polygons, pol, prepared)
    prepared.building_features, prepared.building_geometries = _prepare_collection(
        raw.get("building_footprints_5179"), "building_footprints_5179", prepared
    )
    _resolve_building_use_types(prepared, pol)
    _, prepared.farmland_geometries = _prepare_collection(
        raw.get("farmland_parcels_5179"), "farmland_parcels_5179", prepared
    )

    if not prepared.areas:
        prepared.fallback_tier = 3
        prepared.warnings.append(
            "쓸 수 있는 위험 지오메트리가 하나도 없음 → 노출 0건으로 반환(3순위 폴백)"
        )
    return prepared


def _overlay(prepared, pol):
    risk_union = overlay.build_risk_union(prepared.areas)
    return overlay.OverlayResult(
        exposed_buildings=overlay.find_exposed_buildings(
            prepared.areas,
            prepared.building_features,
            prepared.building_geometries,
            pol,
            prepared.building_use_types,
        ),
        exposed_farmland_ha=overlay.farmland_area_ha(risk_union, prepared.farmland_geometries, pol),
        risk_union_area_m2=0.0 if risk_union is None else risk_union.area,
    )


def run(input: dict) -> dict:  # noqa: A002 - §4.2 규약이 지정한 이름
    prepared = None
    try:
        pol = policy.active_policy()
        prepared = _prepare(input, pol)
        if prepared.fatal:
            return error_envelope(prepared.warnings)

        result = _overlay(prepared, pol)
        return envelope(
            status="ok" if prepared.fallback_tier == 1 else "degraded",
            fallback_tier=prepared.fallback_tier,
            data={
                "exposed_buildings": result.exposed_buildings,
                "exposed_farmland_ha": result.exposed_farmland_ha,
            },
            warnings=prepared.warnings,
        )
    except Exception as exc:  # noqa: BLE001 - §4.2: 모듈은 예외로 죽지 않는다
        prior = list(prepared.warnings) if prepared is not None else []
        return error_envelope(
            prior + [f"Module D 내부 오류({type(exc).__name__}: {exc}) → error 봉투로 폴백"]
        )


def _use_type_join_summary(prepared) -> dict:
    """조인 커버리지 — 매핑 적용 건수/전체와 '미상' 잔여 (§6.1 Provenance)."""
    counts = prepared.use_type_origin_counts or {"property": 0, "parcel_join": 0, "none": 0}
    total = sum(counts.values())
    return {
        "source_file": prepared.parcel_mapping_path,
        "mapping_available": prepared.parcel_mapping_available,
        "mapping_size": prepared.parcel_mapping_size,
        "granularity": "parcel",
        "is_assumption": True,
        "assumption": "필지 단위 조인 - 동 단위 아님, 다중 표제부는 주건축물 우선/연면적 최대",
        "buildings": total,
        "from_property": counts.get("property", 0),
        "from_parcel_join": counts.get("parcel_join", 0),
        "unknown": counts.get("none", 0),
        "resolved_ratio_pct": round((total - counts.get("none", 0)) / total * 100, 1) if total else 0.0,
        "parcel_join_ratio_pct": round(counts.get("parcel_join", 0) / total * 100, 1) if total else 0.0,
    }


def explain(input: dict):
    """계약 밖 판정 근거 — Provenance 배지(§6.1)와 디버깅용."""
    pol = policy.active_policy()
    prepared = _prepare(input, pol)
    result = None if prepared.fatal else _overlay(prepared, pol)
    return {
        "fallback_tier": prepared.fallback_tier,
        "warnings": prepared.warnings,
        "risk_areas": [
            {"source_module": a.source_module, "risk_prob": a.risk_prob, "area_m2": a.geometry.area}
            for a in prepared.areas
        ],
        "risk_union_area_m2": None if result is None else result.risk_union_area_m2,
        "used_point_buffer": prepared.used_point_buffer,
        "buffer_is_assumption": prepared.used_point_buffer,
        "building_feature_count": len(prepared.building_features),
        "use_type_join": _use_type_join_summary(prepared),
        "farmland_feature_count": len(prepared.farmland_geometries),
        "result": None
        if result is None
        else {
            "exposed_buildings": result.exposed_buildings,
            "exposed_farmland_ha": result.exposed_farmland_ha,
        },
        "policy": pol.summary(),
    }
