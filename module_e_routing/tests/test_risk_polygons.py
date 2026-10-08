"""대피 후보에서 위험영역 안 대피소를 빼는 규칙.

Module B는 침수범위를 FeatureCollection(깊이 구간별 폴리곤 수백 개)으로 준다. 예전에는
그걸 shapely.geometry.shape()에 바로 넘겨 예외가 났고, 그 예외가 조용히 삼켜져서
침수범위가 대피소를 한 번도 걸러내지 못했다.
"""
from module_e_routing import _shelter_blocked_by_risk

SHELTER = {"shelter_id": "S", "x_5179": 1000.0, "y_5179": 1000.0}
SQUARE = {"type": "Polygon", "coordinates": [[[900, 900], [1100, 900], [1100, 1100], [900, 1100], [900, 900]]]}


def test_featurecollection_risk_excludes_shelter():
    fc = {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": SQUARE, "properties": {}}]}
    assert _shelter_blocked_by_risk(SHELTER, [{"geometry_5179": fc}]) is True


def test_feature_risk_excludes_shelter():
    ft = {"type": "Feature", "geometry": SQUARE, "properties": {}}
    assert _shelter_blocked_by_risk(SHELTER, [{"geometry_5179": ft}]) is True


def test_plain_polygon_still_excludes():
    assert _shelter_blocked_by_risk(SHELTER, [{"geometry_5179": SQUARE}]) is True


def test_empty_geometries_do_not_exclude():
    empty_fc = {"type": "FeatureCollection", "features": []}
    assert _shelter_blocked_by_risk(SHELTER, [{"geometry_5179": {}}, {"geometry_5179": empty_fc}]) is False
