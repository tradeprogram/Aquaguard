"""`/alerts/{id}/timeline` — 지도가 "지금 몇 시의 예측인가"를 쓰기 위해 읽는 곳.

이 엔드포인트가 조용히 망가지면 화면은 그냥 시간축이 사라질 뿐이라(에러도 안 난다)
아무도 모른다. 그래서 여기서 계약을 못 박아 둔다.
"""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import api_server

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def client() -> TestClient:
    return TestClient(api_server.app)


@pytest.fixture()
def demo_input() -> dict:
    with open(ROOT / "contracts" / "module_o.example.json", encoding="utf-8") as f:
        return json.load(f)["input"]


def test_timeline_available_without_alert(client: TestClient) -> None:
    """경보를 트리거하기 전에도 프레임과 위험영역은 나와야 한다.

    지도는 mount 즉시 이걸 부른다 — 여기서 404가 나면 데모를 돌리기 전까지 시간축이
    통째로 비어 "지금 뭘 보고 있는지"를 알 수 없게 된다. 프레임·폴리곤은 사전계산물이라
    경보와 무관하고, 경보에서 오는 건 탐지/발송 시각뿐이다.
    """
    body = client.get("/alerts/NO-SUCH-ALERT/timeline").json()

    assert body["available"] is True
    assert len(body["frames"]) > 0
    # 경보가 없으니 시각 표시는 비어 있을 뿐, 응답 자체가 실패하지는 않는다
    assert body["markers"]["detected"] is None


def test_timeline_frames_are_hourly_and_ordered(client: TestClient) -> None:
    frames = client.get("/alerts/NO-SUCH-ALERT/timeline").json()["frames"]

    hours = [f["hour"] for f in frames]
    assert hours == sorted(hours)
    assert hours == list(range(hours[0], hours[0] + len(hours)))
    for f in frames:
        assert f["rn_mm"] >= 0
        assert f["cum24_mm"] >= 0
        assert f["time"].endswith("+09:00")


def test_timeline_risk_is_lonlat_with_arrival_hour(client: TestClient) -> None:
    """위험영역은 4326이어야 하고 폴리곤마다 도달시각이 붙어 있어야 한다.

    UI는 arrival_hour로만 "이 시각까지 도달한 영역"을 거른다 — 이게 없으면 스크러버가
    시간을 움직여도 화면이 그대로다. 5179 좌표(백만 단위)가 그대로 새어 나가면
    MapLibre가 지도 밖에 그려서 아무것도 안 보인다.
    """
    body = client.get("/alerts/NO-SUCH-ALERT/timeline").json()
    frames = body["frames"]
    features = body["risk"]["features"]
    assert features, "위험영역이 하나도 없으면 시간축을 보여줄 이유가 없다"

    last_hour = frames[-1]["hour"]
    for feat in features:
        props = feat["properties"]
        assert props["kind"] == "landslide_risk"
        assert isinstance(props["arrival_hour"], int)
        assert frames[0]["hour"] <= props["arrival_hour"] <= last_hour

        coords = feat["geometry"]["coordinates"]
        while isinstance(coords[0], list):
            coords = coords[0]
        lon, lat = coords[0], coords[1]
        assert 124.0 < lon < 132.0, f"경도가 4326이 아님: {lon}"
        assert 33.0 < lat < 39.0, f"위도가 4326이 아님: {lat}"


def test_timeline_carries_a_flood_time_series(client: TestClient) -> None:
    """침수에 시간축이 붙었는지, 그리고 그게 무엇인지 화면이 알 수 있는지.

    예전에는 SFINCS 최대침수심 한 장뿐이라 flood_is_max=True로 "시간축 없음"을
    알렸다. 지금은 같은 모의의 경호교 시간별 수위로 준정적 근사를 만들어 시각별
    침수를 그린다. **근사라는 사실이 응답에 같이 실려야 한다** — 시각마다 SFINCS를
    다시 돌린 것처럼 읽히면 안 된다.
    """
    body = client.get("/alerts/NO-SUCH-ALERT/timeline").json()
    series = body["flood_series"]

    if not series.get("available"):
        # 저장본이 없는 환경 — 그때는 최대 범위 고정이라고 정직하게 말해야 한다
        assert body["flood_is_max"] is True
        return

    assert body["flood_is_max"] is False
    assert series["contours"]["features"], "등고선이 없으면 어느 시각도 그릴 수 없다"
    assert series["한계"], "근사라는 설명이 빠지면 모의 산출로 읽힌다"
    assert any("준정적" in line or "다시 돌린 것이 아니" in line for line in series["한계"])


def test_flood_stage_drops_track_the_frames(client: TestClient) -> None:
    """수위강하가 프레임 시각과 맞물려 있고, 강우 첨두 뒤에 하천이 차오르는지.

    강우가 09:00에 첨두인데 하천 수위가 그보다 **먼저** 최고가 되면 시간 관계가
    뒤집힌 것이고, 화면은 원인과 결과가 거꾸로인 애니메이션을 보여주게 된다.
    """
    body = client.get("/alerts/NO-SUCH-ALERT/timeline").json()
    series = body["flood_series"]
    if not series.get("available"):
        pytest.skip("침수 시간축 없음")

    drops = series["stage_drop_by_hour"]
    frames = {str(f["hour"]): f for f in body["frames"]}
    assert drops, "시각별 수위강하가 비어 있으면 시간축이 멈춘다"
    for hour in drops:
        assert hour in frames, f"프레임에 없는 시각 {hour}에 수위가 붙어 있다"
        assert drops[hour] >= 0, "강하는 첨두 대비 값이라 음수일 수 없다"

    # 강우 첨두 시각과 침수 최대(=강하 최소) 시각
    rain_peak = max(body["frames"], key=lambda f: f["rn_mm"])["hour"]
    flood_peak = int(min(drops, key=lambda h: drops[h]))
    assert flood_peak >= rain_peak, (
        f"하천 첨두(h{flood_peak})가 강우 첨두(h{rain_peak})보다 빠르다 — 인과가 뒤집혔다"
    )


def test_flood_extent_grows_toward_the_peak(client: TestClient) -> None:
    """시간을 넘기면 침수가 실제로 넓어지는지 — 이게 안 되면 시간축을 돌릴 이유가 없다."""
    body = client.get("/alerts/NO-SUCH-ALERT/timeline").json()
    series = body["flood_series"]
    if not series.get("available"):
        pytest.skip("침수 시간축 없음")

    from shapely.geometry import shape
    from shapely.ops import unary_union

    def extent_at(drop: float) -> float:
        visible = [
            shape(f["geometry"])
            for f in series["contours"]["features"]
            if f["properties"]["level_m"] >= drop + 0.3
        ]
        return unary_union(visible).area if visible else 0.0

    drops = series["stage_drop_by_hour"]
    early = extent_at(max(drops.values()))   # 수위가 가장 낮은 시각
    peak = extent_at(min(drops.values()))    # 첨두
    assert peak > early * 1.2, f"첨두 침수가 저수위 때보다 거의 안 넓다 ({early:.0f} -> {peak:.0f})"


def test_timeline_markers_come_from_the_alert(client: TestClient, demo_input: dict) -> None:
    client.post("/alerts/trigger", json=demo_input)
    body = client.get(f"/alerts/{demo_input['alert_id']}/timeline").json()

    markers = body["markers"]
    assert markers["detected"] is not None
    assert markers["alert_sent"] is not None
    # 우리 탐지가 공식 경보보다 빨랐다는 것이 이 데모의 요지 — 뒤집히면 서사가 깨진다
    assert markers["detected"] < markers["official_warning"]

    frame_times = {f["time"] for f in body["frames"]}
    assert markers["detected"] in frame_times, "탐지 시각이 프레임에 없으면 스크러버가 그 시각을 못 가리킨다"
