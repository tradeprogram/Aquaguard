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


def test_timeline_marks_flood_as_max_not_animated(client: TestClient) -> None:
    """침수는 시간축이 없다는 사실 자체가 계약이다.

    Module B는 SFINCS 최대침수심 래스터 한 장만 낸다. 프레임을 넘길 때 침수도 같이
    번지는 것처럼 보이면 없는 모형을 있다고 말하는 셈이라, UI가 "최대 범위"로 표기할
    수 있게 이 플래그를 준다. 시계열 산출이 생기면 이 테스트부터 바뀌어야 한다.
    """
    assert client.get("/alerts/NO-SUCH-ALERT/timeline").json()["flood_is_max"] is True


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
