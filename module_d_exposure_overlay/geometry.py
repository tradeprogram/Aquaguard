"""입력 지오메트리 정규화 (Module D).

Module D 작업의 절반이 공간연산이 아니라 여기다. contracts/module_d.example.json은
geometry_5179를 Polygon으로 그려두지만, 실제로 Module O가 넘기는 값은 다음과 같다
(module_o_orchestrator/orchestrator.py):

    {"source_module": "A", "geometry_5179": {"x_5179": ..., "y_5179": ...}}  # 점 dict
    {"source_module": "B", "geometry_5179": {}}                              # 빈 dict
    "building_footprints_5179": {}                                           # FC 아님

Module A의 계약 출력에는 폴리곤 필드가 아예 없고 location(점)뿐이라 이건 O의 버그가
아니라 계약의 빈틈이다(TRACK2_CONTRACT_AGENDA.md 1번). 그래서 이 모듈은 점·빈값·
무효 폴리곤을 전부 흡수하되, 무엇을 어떻게 흡수했는지 반드시 밖으로 알린다.

좌표는 전부 EPSG:5179 미터이며 재투영하지 않는다(§4.1 — 재투영은 UI 출력 직전에만).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from shapely.geometry import Point, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union
from shapely.validation import make_valid

POLYGONAL = ("Polygon", "MultiPolygon")


@dataclass
class Normalized:
    """정규화 결과 — 왜 이렇게 됐는지가 결과만큼 중요하다."""

    geometry: BaseGeometry | None = None
    notes: list[str] = field(default_factory=list)
    used_point_buffer: bool = False
    repaired: bool = False


def _as_point(obj: dict[str, Any]) -> Point | None:
    """Module A의 location({x_5179, y_5179})과 GeoJSON Point를 모두 받는다."""
    if "x_5179" in obj and "y_5179" in obj:
        try:
            return Point(float(obj["x_5179"]), float(obj["y_5179"]))
        except (TypeError, ValueError):
            return None
    if obj.get("type") == "Point":
        coords = obj.get("coordinates") or []
        if len(coords) >= 2:
            try:
                return Point(float(coords[0]), float(coords[1]))
            except (TypeError, ValueError):
                return None
    return None


def _repair(geom: BaseGeometry, result: Normalized, label: str) -> BaseGeometry | None:
    """자기교차 등 무효 폴리곤 복구. 복구 후에도 면적이 없으면 버린다."""
    if geom.is_valid and not geom.is_empty:
        return geom
    if geom.is_empty:
        result.notes.append(f"{label}: 빈 지오메트리 → 제외")
        return None
    repaired = make_valid(geom)
    if repaired.is_empty or repaired.area <= 0:
        result.notes.append(f"{label}: 복구 불가능한 무효 지오메트리 → 제외")
        return None
    result.repaired = True
    result.notes.append(f"{label}: 무효 지오메트리를 make_valid로 복구")
    return repaired


def normalize(obj: Any, *, label: str, buffer_m: float | None) -> Normalized:
    """어떤 모양으로 들어오든 폴리곤 하나(또는 None)로 만든다.

    buffer_m이 주어지면 점 입력을 그 반경으로 부풀린다. None이면 점은 버린다.
    """
    result = Normalized()

    if not isinstance(obj, dict) or not obj:
        result.notes.append(f"{label}: 지오메트리가 비어 있거나 dict가 아님 → 제외")
        return result

    point = _as_point(obj)
    if point is not None:
        if buffer_m is None:
            result.notes.append(f"{label}: 점 좌표인데 버퍼가 꺼져 있음 → 제외")
            return result
        result.geometry = point.buffer(buffer_m)
        result.used_point_buffer = True
        result.notes.append(
            f"{label}: 점 좌표를 반경 {buffer_m}m로 버퍼링 — 실제 위험영역이 아니라 가정값(ASSUMPTION)"
        )
        return result

    geom_type = obj.get("type")

    if geom_type == "Feature":
        return normalize(obj.get("geometry"), label=label, buffer_m=buffer_m)

    if geom_type == "FeatureCollection":
        parts: list[BaseGeometry] = []
        for index, feature in enumerate(obj.get("features") or []):
            part = normalize(feature, label=f"{label}[{index}]", buffer_m=buffer_m)
            result.notes.extend(part.notes)
            result.used_point_buffer = result.used_point_buffer or part.used_point_buffer
            result.repaired = result.repaired or part.repaired
            if part.geometry is not None:
                parts.append(part.geometry)
        if parts:
            result.geometry = unary_union(parts)
        else:
            result.notes.append(f"{label}: 쓸 수 있는 지오메트리가 없는 FeatureCollection")
        return result

    if geom_type in POLYGONAL:
        if not obj.get("coordinates"):
            result.notes.append(f"{label}: {geom_type}인데 coordinates가 비어 있음 → 제외")
            return result
        try:
            geom = shape(obj)
        except Exception as exc:  # noqa: BLE001 - 어떤 파싱 오류든 폴백으로 흡수한다
            result.notes.append(f"{label}: 지오메트리 파싱 실패({type(exc).__name__}) → 제외")
            return result
        result.geometry = _repair(geom, result, label)
        return result

    result.notes.append(f"{label}: 지원하지 않는 지오메트리 타입({geom_type!r}) → 제외")
    return result


def iter_features(collection: Any) -> list[dict[str, Any]]:
    """FeatureCollection에서 feature 목록만 꺼낸다. 모양이 아니면 빈 목록."""
    if not isinstance(collection, dict):
        return []
    features = collection.get("features")
    if not isinstance(features, list):
        return []
    return [f for f in features if isinstance(f, dict)]
