"""위험영역 격자 필터 — 걸러낸 것이 정말로 안 겹치는 것뿐인지.

이 필터는 Module D에 넘길 노출자산을 6%로 줄인다(건물 8,026 → 500). 속도와 메모리를
위한 것이지 판정을 바꾸려는 게 아니므로, **실제로 겹치는 feature를 하나라도 버리면
피해 규모가 조용히 줄어든다**. 조용히 틀리는 쪽이라 테스트로 못 박아 둔다.
"""

import random

from module_o_orchestrator.exposure_layers import (
    RISK_CELL_M,
    _clip_to_bounds,
    _feature_bounds,
    _subgeometry_bounds,
    risk_cells,
)


def square(x: float, y: float, size: float) -> dict:
    return {
        "type": "Polygon",
        "coordinates": [[[x, y], [x + size, y], [x + size, y + size], [x, y + size], [x, y]]],
    }


def feature(geometry: dict) -> dict:
    return {"type": "Feature", "geometry": geometry, "properties": {}}


def boxes_overlap(a, b) -> bool:
    return not (a[2] < b[0] or a[0] > b[2] or a[3] < b[1] or a[1] > b[3])


def test_subgeometry_bounds_splits_instead_of_enveloping():
    """멀리 떨어진 두 폴리곤은 bbox 두 개여야 한다 — 하나로 감싸면 사이의 빈 땅까지 든다.

    이게 이 변경의 핵심이다. Module B의 침수범위는 하천을 따라 길게 뻗고 Module A의
    산사태는 반대편 비탈에 있어서, 감싸는 bbox 하나는 363km²가 되는데 실제 위험영역은
    58km²였다.
    """
    multi = {
        "type": "MultiPolygon",
        "coordinates": [square(0, 0, 100)["coordinates"], square(10_000, 10_000, 100)["coordinates"]],
    }
    boxes = _subgeometry_bounds(multi)

    assert len(boxes) == 2
    assert max(b[2] - b[0] for b in boxes) == 100  # 각자 작은 채로 남는다


def test_subgeometry_bounds_reads_featurecollection():
    """Module B는 위험영역을 FeatureCollection으로 준다 — 이걸 놓치면 필터가 무력해진다."""
    fc = {
        "type": "FeatureCollection",
        "features": [feature(square(0, 0, 50)), feature(square(500, 500, 50))],
    }
    assert len(_subgeometry_bounds(fc)) == 2


def test_clip_keeps_every_feature_whose_bbox_touches_a_risk_polygon():
    """무작위 배치에서도 '실제로 겹치는 것'은 절대 안 버려지는지.

    격자 판정은 실제 교차의 상위집합이어야 한다. 넉넉하게 남기는 건 괜찮고(느려질 뿐),
    하나라도 빠뜨리면 노출자산이 누락된다.
    """
    rng = random.Random(20260920)
    risk = [
        square(rng.uniform(0, 20_000), rng.uniform(0, 20_000), rng.uniform(50, 400))
        for _ in range(30)
    ]
    cells = risk_cells(risk)
    risk_boxes = [_feature_bounds(g) for g in risk]

    parcels = [
        feature(square(rng.uniform(0, 20_000), rng.uniform(0, 20_000), rng.uniform(20, 200)))
        for _ in range(2_000)
    ]
    collection = {"type": "FeatureCollection", "features": parcels}

    kept = _clip_to_bounds(collection, None, cells)["features"]
    kept_ids = {id(f) for f in kept}

    must_keep = [
        f for f in parcels
        if any(boxes_overlap(_feature_bounds(f["geometry"]), rb) for rb in risk_boxes)
    ]
    assert must_keep, "겹치는 게 하나도 없으면 이 테스트가 아무것도 검증하지 않는다"
    missing = [f for f in must_keep if id(f) not in kept_ids]
    assert not missing, f"위험영역과 겹치는 feature {len(missing)}개가 버려졌다"

    # 그리고 실제로 걸러내기는 해야 의미가 있다
    assert len(kept) < len(parcels) * 0.5


def test_clip_drops_far_away_features():
    cells = risk_cells([square(0, 0, 100)])
    far = feature(square(50_000, 50_000, 100))
    near = feature(square(50, 50, 100))
    kept = _clip_to_bounds(
        {"type": "FeatureCollection", "features": [far, near]}, None, cells
    )["features"]
    assert kept == [near]


def test_clip_keeps_features_with_unreadable_geometry():
    """판단 못 하면 남긴다 — 누락이 과다계상보다 나쁘다(기존 규칙 유지)."""
    broken = {"type": "Feature", "geometry": None, "properties": {}}
    kept = _clip_to_bounds(
        {"type": "FeatureCollection", "features": [broken]}, None, risk_cells([square(0, 0, 10)])
    )["features"]
    assert kept == [broken]


def test_no_cells_means_no_filtering():
    """위험영역이 없으면(격자 None) 아무것도 버리지 않는다 — 필터가 조용히 전부 지우면 안 된다."""
    assert risk_cells([]) is None
    feats = [feature(square(0, 0, 10)), feature(square(99_999, 99_999, 10))]
    kept = _clip_to_bounds({"type": "FeatureCollection", "features": feats}, None, None)["features"]
    assert kept == feats


def test_point_geometry_still_produces_a_cell():
    """점 좌표({x_5179,y_5179})가 아니라 GeoJSON Point로 온 경우도 격자에 들어가야 한다."""
    cells = risk_cells([{"type": "Point", "coordinates": [1_000_000.0, 1_700_000.0]}])
    assert cells == {(int(1_000_000.0 // RISK_CELL_M), int(1_700_000.0 // RISK_CELL_M))}


def test_feature_bounds_fast_path_matches_generic_walk():
    """Polygon/MultiPolygon 빠른 경로가 일반 재귀와 같은 값을 내는지.

    속도 때문에 갈라놓은 경로라 둘이 어긋나면 그때부터 조용히 다른 걸 거른다.
    """
    rng = random.Random(7)
    for _ in range(200):
        ring = [[rng.uniform(-1e6, 1e6), rng.uniform(-1e6, 1e6)] for _ in range(5)]
        ring.append(ring[0])
        poly = {"type": "Polygon", "coordinates": [ring]}
        xs = [c[0] for c in ring]
        ys = [c[1] for c in ring]
        assert _feature_bounds(poly) == (min(xs), min(ys), max(xs), max(ys))

        multi = {"type": "MultiPolygon", "coordinates": [[ring], [ring]]}
        assert _feature_bounds(multi) == _feature_bounds(poly)
