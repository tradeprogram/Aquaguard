"""사전계산 저장본이 **지금 코드가 내는 값**과 같은지.

이 테스트가 이 기능의 정직성 장치 전부다. 저장본을 내주는 건 "같은 입력에 같은 결과"라는
전제 위에서만 정당한데, 모듈이 바뀌면 그 전제가 조용히 깨진다. 화면은 여전히 옛 숫자를
자신 있게 보여주고, 아무도 모른다.

그래서 여기서 파이프라인을 실제로 다시 돌려 저장본과 대조한다. 깨지면 고칠 게 아니라
다시 만들면 된다:

    python scripts/build_demo_snapshot.py
"""

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_PATH = ROOT / "data" / "precomputed" / "demo_snapshot.json"

pytestmark = pytest.mark.skipif(
    not SNAPSHOT_PATH.exists(),
    reason="저장본 없음 — python scripts/build_demo_snapshot.py 로 생성",
)


def as_transported(value):
    """JSON을 거친 형태로 맞춘다.

    rasterio.features.shapes()는 좌표를 **튜플**로 내는데 저장본은 JSON을 거치면서
    리스트가 된다. 값은 같고 타입만 다른데 ==는 거짓이 되므로, 실제로 화면에 전달되는
    형태(JSON)로 양쪽을 맞춘 뒤 비교한다.
    """
    return json.loads(json.dumps(value, ensure_ascii=False, sort_keys=True))


@pytest.fixture(scope="module")
def snapshot() -> dict:
    with open(SNAPSHOT_PATH, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def fresh_envelope() -> dict:
    """실모듈 모드로 파이프라인을 다시 돌린다.

    저장본이 실모듈 결과이므로 대조도 같은 모드여야 한다. 목업 모드(테스트 기본값)로
    비교하면 contracts 예시와 대조하는 셈이라 아무것도 검증하지 못한다.
    """
    import os

    from dotenv import load_dotenv

    # 저장본을 만든 쪽(scripts/build_demo_snapshot.py)은 .env를 읽는다. 여기서 안 읽으면
    # 재실행만 NAVER 키가 없어 대피 경로가 직선으로 떨어지고, 저장본은 실도로라
    # **경로 때문에** 불일치가 난다 — 실제로 어긋난 건 아무것도 없는데 말이다.
    load_dotenv(ROOT / ".env")

    from module_o_orchestrator.orchestrator import run as run_orchestrator

    if not (os.environ.get("NAVER_CLIENT_ID") and os.environ.get("NAVER_CLIENT_SECRET")):
        pytest.skip(
            "NAVER_CLIENT_ID/SECRET 없음 — 키 없이 재실행하면 대피 경로가 직선으로 "
            "떨어져서 저장본과 대조할 수가 없다(.env에 키를 넣으면 이 테스트가 돈다)"
        )

    with open(ROOT / "contracts" / "module_o.example.json", encoding="utf-8") as f:
        payload = json.load(f)["input"]

    before = os.environ.get("AQUAGUARD_MOCK_MODE")
    os.environ["AQUAGUARD_MOCK_MODE"] = "0"
    try:
        return run_orchestrator(payload)
    finally:
        if before is None:
            os.environ.pop("AQUAGUARD_MOCK_MODE", None)
        else:
            os.environ["AQUAGUARD_MOCK_MODE"] = before


def test_snapshot_input_matches_the_demo_contract(snapshot: dict) -> None:
    """저장본은 계약 예시 입력으로 만들어졌어야 한다.

    api_server가 입력 지문으로 저장본을 고르므로, 계약 예시가 바뀌면 지문이 어긋나
    저장본이 조용히 안 쓰이게 된다(그 자체는 안전하지만, 그러면 느린 채로 돌아간다).
    """
    from scripts.build_demo_snapshot import demo_input, input_fingerprint
    assert snapshot["input_sha"] == input_fingerprint(demo_input())
    assert snapshot["alert_id"] == demo_input()["alert_id"]


# 네이버 Directions는 option=trafast(실시간 빠른길)로 부르므로 같은 좌표라도 호출
# 시점의 교통 상황에 따라 소요시간이 조금씩 달라진다(실측 14.1 vs 14.2분). 값이
# 흔들리는 건 이 API를 쓰는 이상 정상이고, 저장본이 낡았다는 신호가 아니다.
TRAFFIC_DEPENDENT = ("eta_min", "time_margin_min")
ETA_TOLERANCE_MIN = 2.0


def split_route_times(package: dict) -> tuple[dict, dict]:
    """교통에 따라 흔들리는 시간값을 따로 떼어낸다. 나머지는 정확히 같아야 한다."""
    package = as_transported(package)
    route = package.get("shelter_route") or {}
    times = {k: route.pop(k, None) for k in TRAFFIC_DEPENDENT}
    for name, mode in (route.get("modes") or {}).items():
        times[f"modes.{name}.eta_min"] = mode.pop("eta_min", None)
    return package, times


def test_snapshot_alert_package_matches_a_fresh_run(snapshot: dict, fresh_envelope: dict) -> None:
    """핵심 — 저장된 경보 내용이 지금 파이프라인 결과와 같은가.

    alert_package 안에 산사태 확률·침수 확률·노출자산·피해액·대피경로가 전부 들어 있다.
    여기가 어긋나면 화면에 뜨는 숫자가 코드와 다른 것이다.

    소요시간만 허용오차를 둔다 — 실시간 교통이 섞여 호출마다 몇 초씩 다르다.
    경로 좌표·모드·폴백 여부 같은 나머지는 전부 정확히 일치해야 한다.
    """
    stored, stored_times = split_route_times(snapshot["envelope"]["data"]["alert_package"])
    fresh, fresh_times = split_route_times(fresh_envelope["data"]["alert_package"])

    assert stored == fresh

    for key, stored_value in stored_times.items():
        fresh_value = fresh_times.get(key)
        if stored_value is None or fresh_value is None:
            assert stored_value == fresh_value, f"{key}: 한쪽에만 값이 있다"
            continue
        assert abs(stored_value - fresh_value) <= ETA_TOLERANCE_MIN, (
            f"{key}: 저장본 {stored_value}분 vs 재실행 {fresh_value}분 — "
            f"교통 변동으로 보기엔 차이가 크다({ETA_TOLERANCE_MIN}분 초과). "
            f"저장본을 다시 구우십시오."
        )


def test_snapshot_status_and_sources_match(snapshot: dict, fresh_envelope: dict) -> None:
    """어느 모듈이 실물로 돌았는지까지 같아야 한다.

    모듈 하나가 example로 떨어지면 값은 그럴듯하게 나오지만 의미가 달라진다 —
    저장본이 real이던 시절 값을 계속 보여주면 그 저하를 못 알아챈다.
    """
    assert snapshot["envelope"]["status"] == fresh_envelope["status"]
    assert snapshot["envelope"]["fallback_tier"] == fresh_envelope["fallback_tier"]
    assert as_transported((snapshot["envelope"].get("meta") or {}).get("module_sources")) == (
        as_transported((fresh_envelope.get("meta") or {}).get("module_sources"))
    )


def test_snapshot_warnings_match(snapshot: dict, fresh_envelope: dict) -> None:
    """경고 문구도 같아야 한다 — 경고는 이 시스템이 자기 한계를 말하는 방식이다."""
    assert as_transported(snapshot["envelope"]["warnings"]) == as_transported(
        fresh_envelope["warnings"]
    )


def test_display_flood_is_lonlat_and_banded(snapshot: dict) -> None:
    """표시용 침수는 4326이고 구간이 누적으로 쌓여 있어야 한다.

    누적이 아니면(배타 구간) 이웃한 색 띠 사이에 틈이 벌어진다 — 스무딩으로 서로
    반대쪽으로 깎이기 때문이다. display_geometry의 설계 근거이므로 못 박아 둔다.
    """
    features = snapshot["flood_display"]["features"]
    assert features, "표시용 침수가 비어 있으면 지도에 물이 안 뜬다"

    bands = sorted({f["properties"]["band"] for f in features})
    assert bands == list(range(len(bands))), "구간 번호가 0부터 연속이어야 한다"
    assert all(f["properties"].get("cumulative") for f in features)

    for feature in features:
        coords = feature["geometry"]["coordinates"]
        while isinstance(coords[0], list):
            coords = coords[0]
        assert 124.0 < coords[0] < 132.0 and 33.0 < coords[1] < 39.0

    # 누적이면 깊은 구간의 면적이 얕은 구간보다 클 수 없다
    from collections import defaultdict
    from shapely.geometry import shape
    area_by_band: dict[int, float] = defaultdict(float)
    for feature in features:
        area_by_band[feature["properties"]["band"]] += shape(feature["geometry"]).area
    areas = [area_by_band[b] for b in bands]
    assert areas == sorted(areas, reverse=True), f"누적 구간인데 면적이 단조감소가 아님: {areas}"


def test_display_flood_extent_stays_close_to_the_model(snapshot: dict) -> None:
    """다듬은 침수 범위가 모형 산출과 사실상 같은가.

    표시용이라도 범위가 달라지면 그건 다른 예측이다. 보간만 하고 원본 발자국으로
    자르지 않으면 13.7% 넓어지는 걸 실측했으므로(display_geometry 주석), 그 회귀를
    여기서 잡는다. 허용치는 원본 셀 한 변(50m)에서 오는 경계 재배치 수준이다.
    """
    from shapely.geometry import shape
    from shapely.ops import unary_union

    from module_b_flood import fim
    from module_o_orchestrator import geo
    from module_o_orchestrator.exposure_layers import flood_depth_raster

    raster_path, _ = flood_depth_raster("sancheong")
    if not raster_path:
        pytest.skip("침수심 래스터 없음")

    exact = unary_union([
        shape(f["geometry"])
        for f in geo.featurecollection_5179_to_lonlat(fim.raster_to_featurecollection(raster_path))
    ])
    display = unary_union([
        shape(f["geometry"])
        for f in snapshot["flood_display"]["features"]
        if f["properties"]["band"] == 0
    ])

    iou = display.intersection(exact).area / display.union(exact).area
    assert iou > 0.90, f"침수 범위가 모형과 어긋남 (IoU {iou:.3f})"
    ratio = display.area / exact.area
    assert 0.97 < ratio < 1.03, f"침수 면적이 {100 * (ratio - 1):+.1f}% 변했다"


def test_display_risk_keeps_arrival_hours(snapshot: dict) -> None:
    """다듬은 위험영역이 도달시각을 잃지 않았는지 — 잃으면 시간축이 멈춘다."""
    features = snapshot["risk_display"]["features"]
    assert features
    assert {f["properties"]["level"] for f in features} == {"warning", "critical"}
    for feature in features:
        assert isinstance(feature["properties"]["arrival_hour"], int)
        assert feature["properties"]["area_m2"] is not None


def test_snapshot_records_how_it_was_made(snapshot: dict) -> None:
    """언제·어느 커밋으로 만들었는지가 남아 있어야 한다 — 화면이 근거를 댈 수 있어야 한다."""
    assert snapshot["built_at"]
    assert snapshot["built_commit"]
    assert snapshot["pipeline_seconds"] > 0


def test_snapshot_is_not_a_mock_run(snapshot: dict) -> None:
    """목업 모드로 만든 저장본이면 화면이 예시값을 실측인 양 보여주게 된다."""
    assert snapshot.get("mock_mode") is False
    sources = (snapshot["envelope"].get("meta") or {}).get("module_sources") or {}
    assert sources, "module_sources가 없으면 어느 모듈이 실물이었는지 알 수 없다"
    assert "real" in sources.values(), f"실물 모듈이 하나도 없다: {sources}"


def test_fingerprint_ignores_int_float_spelling() -> None:
    """`12.0`과 `12`가 같은 지문이어야 한다.

    JSON은 둘을 구분하지 못한다. 계약 예시에는 `12.0`으로 적혀 있지만 브라우저가
    JSON.stringify 로 보내면 `12`가 되고, 파이썬은 int로 받는다. 이걸 다르게 보면
    실제 UI에서만 저장본이 안 쓰이고 — 예외도 경고도 없이 조용히 느려진다.
    2026-09-20에 정확히 이렇게 당했다.
    """
    from module_o_orchestrator.snapshot import input_fingerprint
    from scripts.build_demo_snapshot import demo_input

    def as_javascript_would_send(value):
        if isinstance(value, bool):
            return value
        if isinstance(value, float) and value.is_integer():
            return int(value)
        if isinstance(value, dict):
            return {k: as_javascript_would_send(v) for k, v in value.items()}
        if isinstance(value, list):
            return [as_javascript_would_send(v) for v in value]
        return value

    payload = demo_input()
    assert input_fingerprint(payload) == input_fingerprint(as_javascript_would_send(payload))


def test_fingerprint_still_separates_true_from_one() -> None:
    """숫자를 뭉개면서 bool까지 뭉개면 안 된다 — `true`와 `1`은 다른 값이다."""
    from module_o_orchestrator.snapshot import input_fingerprint
    assert input_fingerprint({"known_risk": True}) != input_fingerprint({"known_risk": 1})


def test_fingerprint_changes_when_the_question_changes() -> None:
    """좌표를 옮기면 다른 질문이므로 저장본을 쓰면 안 된다."""
    from module_o_orchestrator.snapshot import input_fingerprint, matching
    from scripts.build_demo_snapshot import demo_input

    payload = demo_input()
    moved = {**payload, "trigger_location": {"x_5179": 1_000_000.0, "y_5179": 1_700_000.0}}
    assert input_fingerprint(moved) != input_fingerprint(payload)
    assert matching(moved, {"input_sha": input_fingerprint(payload)}) is None
    assert matching(payload, {"input_sha": input_fingerprint(payload)}) is not None


def test_geojson_serves_flood_before_the_demo_is_triggered() -> None:
    """경보가 없어도 침수는 지도에 떠야 한다.

    경보 저장소는 메모리에 있어서 서버를 재시작하면 비는데, 침수 폴리곤은 경보와
    무관한 사전계산물이다. 그때 지도만 비워 두면 "재시작했더니 물이 사라졌다"가 되고,
    실제로 배포 서버를 재시작한 직후 /geojson이 404를 냈다(2026-09-20).
    시간축(/timeline)이 경보 없이 응답하는 것과 같은 이유다.
    """
    from fastapi.testclient import TestClient

    import api_server

    client = TestClient(api_server.app)
    api_server.alert_store._alerts.clear()  # 재시작 직후 상태

    with open(SNAPSHOT_PATH, encoding="utf-8") as f:
        alert_id = json.load(f)["alert_id"]

    body = client.get(f"/alerts/{alert_id}/geojson").json()
    flood = [f for f in body["features"] if f["properties"].get("kind") == "inundation"]
    assert flood, "트리거 전이라고 침수까지 비우면 지도가 빈 채로 시작한다"
    assert len({f["properties"]["band"] for f in flood}) > 1

    # 저장본에 없는 경보는 여전히 404 — 아무 id나 물으면 침수를 주면 안 된다
    assert client.get("/alerts/NO-SUCH-ALERT/geojson").status_code == 404


def test_snapshot_route_is_a_real_road_route(snapshot: dict) -> None:
    """저장된 대피 경로가 실도로여야 한다 — 직선거리 근사는 받지 않는다.

    대피 경로는 이 시스템이 시민에게 "이 길로 가세요"라고 말하는 부분이다. 직선은
    강을 건너고 산을 넘는 선이라 안내로 쓸 수 없고, 저장본에 한 번 구워지면 화면이
    계속 그걸 보여준다.

    깨지면 고칠 게 아니라 키를 넣고 다시 구우면 된다:
        1. .env 에 NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 추가 (채팅에 붙여넣지 말 것)
        2. python scripts/build_demo_snapshot.py
    """
    route = snapshot["envelope"]["data"]["alert_package"].get("shelter_route") or {}
    assert route, "대피 경로가 아예 없다"

    assert not route.get("fallback_used"), (
        "대피 경로가 직선거리 근사다 — .env에 NAVER_CLIENT_ID/SECRET을 넣고 "
        "python scripts/build_demo_snapshot.py 로 다시 구우십시오"
    )

    coords = (route.get("route_5179") or {}).get("coordinates") or []
    assert len(coords) > 2, f"경로 점이 {len(coords)}개뿐 — 실도로라면 꺾임이 있어야 한다"

    for name, mode in (route.get("modes") or {}).items():
        assert mode.get("source") != "straight_line_approx", (
            f"{name} 모드가 직선 근사다 — 직선은 강을 건너고 능선을 넘는 선이라 "
            f"시간이 늘 짧게 나오고, 대피 가능 시간을 실제보다 낙관적으로 보이게 한다"
        )
