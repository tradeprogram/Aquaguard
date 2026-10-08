"""침수 모형 영역 목록(module_b_flood/domains.json) — 어디까지 계산했는가.

침수 래스터는 nodata=0이라 "안 잠김"과 "계산 안 함"이 같은 값이다. 그래서 지도가 빈 곳을
안전한 곳처럼 보여주지 않으려면(현장조사 반영 ⑤), 계산 범위를 래스터 밖에서 따로 알아야 한다.
영역마다 래스터 파일이 있으면 '계산됨'이고, 없으면 계획만 있는 영역이다.

계산 범위는 각 영역의 격자 사각형이다. SFINCS 활성 마스크(zmin=-5)가 사실상 격자 전체라
사각형이 실제 계산 범위와 거의 같다(module_b_flood/scripts/33_sfincs_build_reach.py:56).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
REGISTRY = Path(__file__).resolve().parent / "domains.json"


@dataclass(frozen=True)
class Domain:
    id: str
    name: str
    status: str
    raster: Path
    stage_series: dict | None
    footprint: tuple | None
    built_by: str
    note: str

    @property
    def available(self) -> bool:
        return self.raster.exists()


def load_domains() -> list[Domain]:
    doc = json.loads(REGISTRY.read_text(encoding="utf-8"))
    return [
        Domain(
            d["id"], d["name"], d["status"], REPO / d["raster"], d.get("stage_series"),
            tuple(d["footprint_5179"]) if d.get("footprint_5179") else None, d["built_by"], d["note"],
        )
        for d in doc["domains"]
    ]


def footprint_5179(d: Domain) -> tuple | None:
    """계산 범위(EPSG:5179 경계 사각형). 래스터가 있으면 래스터 경계, 없으면 목록에 적힌 격자."""
    if d.available:
        import rasterio

        with rasterio.open(d.raster) as ds:
            b = ds.bounds
            return (b.left, b.bottom, b.right, b.top)
    return d.footprint


def county_5179(code: str):
    from shapely.geometry import shape

    fc = json.loads((REPO / "data" / "vector" / "adm_sigungu_5179.geojson").read_text(encoding="utf-8"))
    return next(shape(f["geometry"]) for f in fc["features"] if f["properties"].get("code") == code)


def coverage(county) -> dict:
    """군 경계를 계산된 영역 / 계산 안 된 영역으로 나눈다(EPSG:5179 shapely 도형)."""
    from shapely.geometry import box
    from shapely.ops import unary_union

    domains = load_domains()
    parts = [box(*footprint_5179(d)) for d in domains if d.available]
    covered = unary_union(parts).intersection(county) if parts else county.difference(county)
    return {
        "covered": covered,
        "uncovered": county.difference(covered),
        "covered_ratio": covered.area / county.area if county.area else 0.0,
        "domains": [
            {"id": d.id, "name": d.name, "available": d.available, "status": d.status,
             "footprint_5179": footprint_5179(d), "note": d.note}
            for d in domains
        ],
    }
