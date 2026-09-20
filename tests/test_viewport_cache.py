"""뷰포트 응답 캐시 — 지도가 서버를 두드릴 때 같은 답을 다시 만들지 않게.

지도를 움직일 때마다 /boundaries + /vworld/* 네 개가 한꺼번에 나가고, /boundaries는
0.84MB를 매번 새로 잘라 만든 뒤 매번 새로 압축했다(2026-09-20 실측: 3ms + 96ms).
2코어 배포 서버에서 이게 줄을 서면 그 뒤에 들어온 경보 요청이 몇십 초를 기다린다 —
사전계산으로 계산 자체는 0.03초가 됐는데도 화면이 여전히 느렸던 이유다.

캐시가 조용히 꺼지면 증상이 "좀 느리다"뿐이라 아무도 모른다. 그래서 못 박아 둔다.
"""

import json

import pytest
from fastapi.testclient import TestClient

import api_server

BBOX = "127.74243930757973,35.31224397141614,128.1053868449966,35.595307505649714"


@pytest.fixture()
def client() -> TestClient:
    api_server._VIEWPORT_CACHE.clear()
    return TestClient(api_server.app)


def test_same_viewport_is_served_from_cache(client: TestClient) -> None:
    first = client.get(f"/boundaries?bbox={BBOX}")
    assert first.status_code == 200
    entries = len(api_server._VIEWPORT_CACHE)
    assert entries == 1

    second = client.get(f"/boundaries?bbox={BBOX}")
    assert json.loads(second.content) == json.loads(first.content)
    assert len(api_server._VIEWPORT_CACHE) == entries, "같은 뷰포트인데 칸이 늘었다"


def test_small_pans_mostly_reuse_entries(client: TestClient) -> None:
    """조금씩 움직이는 동안 칸이 요청 수만큼 늘지는 않아야 한다.

    키는 bbox를 0.005°(약 500m) 격자로 반올림해 만든다. 격자선을 넘는 순간은 새로
    계산하는 게 맞으므로 "항상 같은 칸"을 주장하지는 않는다 — 주장할 수 있는 건
    "매번 새로 만들지는 않는다"까지다. 이게 무너지면 캐시가 있으나 마나다.
    """
    base = [float(v) for v in BBOX.split(",")]
    requests = 20
    for i in range(requests):
        moved = [v + i * 0.0002 for v in base]
        client.get("/boundaries?bbox=" + ",".join(str(v) for v in moved))
    assert len(api_server._VIEWPORT_CACHE) < requests / 2, (
        f"작은 이동 {requests}번에 캐시 칸이 {len(api_server._VIEWPORT_CACHE)}개 — 거의 안 걸린다"
    )


def test_a_different_region_is_computed_fresh(client: TestClient) -> None:
    """많이 움직이면 새로 계산해야 한다 — 안 그러면 엉뚱한 지역이 화면에 남는다."""
    seoul = client.get("/boundaries?bbox=126.9,37.4,127.2,37.6")
    sancheong = client.get(f"/boundaries?bbox={BBOX}")
    assert len(api_server._VIEWPORT_CACHE) == 2
    assert json.loads(seoul.content) != json.loads(sancheong.content)


def test_cache_does_not_grow_without_bound(client: TestClient) -> None:
    """RAM 908MB짜리 서버다 — 0.84MB짜리 응답을 무한정 쌓으면 OOM으로 죽는다.

    실제로 OOM으로 죽은 전력이 있어서 상한을 둔다.
    """
    for i in range(api_server._VIEWPORT_CACHE_MAX + 8):
        lon = 126.0 + i * 0.5
        client.get(f"/boundaries?bbox={lon},35.0,{lon + 0.2},35.2")
    assert len(api_server._VIEWPORT_CACHE) <= api_server._VIEWPORT_CACHE_MAX


def test_gzip_body_matches_the_plain_body(client: TestClient) -> None:
    """압축본을 따로 캐시하므로 둘이 어긋날 수 있다 — 어긋나면 지도가 깨진다."""
    packed = client.get(f"/boundaries?bbox={BBOX}", headers={"Accept-Encoding": "gzip"})
    plain = client.get(f"/boundaries?bbox={BBOX}", headers={"Accept-Encoding": "identity"})
    assert plain.headers.get("content-encoding") is None
    assert json.loads(packed.content) == json.loads(plain.content)
    assert set(json.loads(plain.content)) == {"sido", "sigungu", "dong"}
