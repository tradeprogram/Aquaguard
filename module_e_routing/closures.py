"""복구·통제 구간 — data/road_closures.geojson.

재해 복구 공사처럼 도로가 통제되는 구간을 적어 두면, 고립 판정에서 그 구간을 끊고 대피
경로가 그 구간을 지나는지 검사한다(현장조사 반영 ③). 현장조사(2026-09-25)에서 산청읍
송경천 일대는 한 해가 지나서도 복구 공사로 출입이 통제되고 있었다.

선 통제는 link_ids(표준노드링크 링크 ID)를 반드시 같이 적는다. 선 기하만으로 교차
검사하면 교차로에서 만나는 다른 도로까지 끊기기 때문이다. 면 통제(Polygon)는 그 안을
지나는 도로를 모두 끊는다.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

CLOSURES_PATH = Path(__file__).resolve().parent.parent / "data" / "road_closures.geojson"
REQUIRED = ("id", "reason", "start", "source")
LINE_TYPES = ("LineString", "MultiLineString")
AREA_TYPES = ("Polygon", "MultiPolygon")
KST = timezone(timedelta(hours=9))


class ClosureError(ValueError):
    pass


def validate(features: list[dict]) -> list[dict]:
    for f in features:
        p = f.get("properties") or {}
        missing = [k for k in REQUIRED if not p.get(k)]
        if missing:
            raise ClosureError(f"통제 구간 {p.get('id')}: 필수 속성 없음 {missing}")
        gtype = (f.get("geometry") or {}).get("type")
        if gtype in LINE_TYPES and not p.get("link_ids"):
            raise ClosureError(f"통제 구간 {p['id']}: 선 통제에는 link_ids가 필요하다(교차로에서 다른 길까지 끊기지 않게)")
        if gtype not in LINE_TYPES + AREA_TYPES:
            raise ClosureError(f"통제 구간 {p['id']}: 지원하지 않는 기하 {gtype}")
        try:
            date.fromisoformat(p["start"])
            if p.get("end"):
                date.fromisoformat(p["end"])
        except ValueError as exc:
            raise ClosureError(f"통제 구간 {p['id']}: 날짜는 YYYY-MM-DD — {exc}") from exc
    return features


def load(path: Path = CLOSURES_PATH) -> list[dict]:
    if not path.exists():
        return []
    return validate(json.loads(path.read_text(encoding="utf-8")).get("features", []))


def active(features: list[dict], on: date) -> list[dict]:
    """그 날짜에 유효한 통제만. 종료일이 없으면 계속 유효하다."""
    out = []
    for f in features:
        p = f["properties"]
        start = date.fromisoformat(p["start"])
        end = date.fromisoformat(p["end"]) if p.get("end") else None
        if start <= on and (end is None or on <= end):
            out.append(f)
    return out


def today_kst() -> date:
    return datetime.now(KST).date()
