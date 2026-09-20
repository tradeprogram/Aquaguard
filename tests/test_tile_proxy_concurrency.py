"""타일 프록시가 다른 요청을 막지 않는지.

지도는 한 화면에 지형 타일을 수백 장 부른다. 이 엔드포인트가 동기(`def`)면 FastAPI가
스레드풀(40칸)에서 돌리는데, 업스트림을 기다리는 동안 칸을 붙잡으므로 41번째부터는
줄을 선다. 그러면 **그 뒤에 온 경보 요청이 앞이 다 끝날 때까지 시작조차 못 한다** —
배포본에서 "우리 동네 위험 현황"이 201초 걸리고 타일이 허옇게 비던 실체가 이것이다
(2026-09-20). 흰 타일과 공중에 뜬 건물도 같은 뿌리다: 지형 타일이 늦으면 MapLibre가
고도를 못 읽는다.

이건 코드를 읽어서는 안 보이고, `async def`를 `def`로 되돌리는 순간 조용히 재발한다.
"""

import asyncio
import inspect

import pytest

import api_server


def test_tile_proxy_is_async() -> None:
    """동기로 되돌아가면 스레드풀을 먹는다 — 가장 직접적인 회귀 감시."""
    assert inspect.iscoroutinefunction(api_server.get_terrain_tile), (
        "지형 타일 프록시가 동기 함수다 — 스레드풀 40칸을 타일이 다 차지하면 "
        "경보 요청이 그 뒤에서 기다린다"
    )


def test_tile_cache_evicts_instead_of_filling_up() -> None:
    """캐시가 차면 오래된 것을 버려야 한다.

    예전에는 가득 차면 더 넣지도, 버리지도 않았다 — 한 지역을 보고 나면 그 뒤로는
    캐시가 사실상 꺼진 채로 돌았다. 상한 자체도 중요하다: 40KB짜리 타일이라
    칸수 × 40KB가 상주 메모리이고, 이 서버는 RAM 908MB에서 이미 OOM으로 죽은 적이 있다.
    """
    cache = api_server._IMAGERY_CACHE
    before = dict(cache)
    try:
        cache.clear()
        limit = api_server._IMAGERY_CACHE_MAX_ENTRIES
        assert limit * 40_000 < 100e6, f"상한 {limit}칸이면 최악 {limit * 40_000 / 1e6:.0f}MB"

        for i in range(limit + 50):
            api_server._remember_tile(("terrain", 12, i, 0), b"x" * 16)
        assert len(cache) <= limit
        assert ("terrain", 12, limit + 49, 0) in cache, "새로 들어온 타일이 캐시에 없다"
        assert ("terrain", 12, 0, 0) not in cache, "가장 오래된 타일이 안 버려졌다"
    finally:
        cache.clear()
        cache.update(before)


@pytest.mark.anyio
async def test_a_flood_of_tiles_does_not_block_the_alert() -> None:
    """타일이 쏟아지는 동안에도 경보 요청이 즉시 처리되는지 — 실제 동작으로 확인."""
    import httpx

    calls = {"n": 0}

    async def slow_upstream(url: str):  # 업스트림이 느린 상황을 흉내
        calls["n"] += 1
        await asyncio.sleep(0.2)
        raise httpx.ConnectError("test")

    class FakeClient:
        get = staticmethod(slow_upstream)

    original = api_server._tile_client
    api_server._tile_client = lambda: FakeClient()
    try:
        transport = httpx.ASGITransport(app=api_server.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t", timeout=60) as c:
            tiles = [asyncio.create_task(c.get(f"/terrain-tiles/12/{3000 + i}/900.png"))
                     for i in range(120)]
            await asyncio.sleep(0.05)

            started = asyncio.get_event_loop().time()
            health = await c.get("/health")
            waited = asyncio.get_event_loop().time() - started

            await asyncio.gather(*tiles, return_exceptions=True)

        assert health.status_code == 200
        assert calls["n"] >= 100, "타일 요청이 실제로 나가지 않았다 — 테스트가 헛돈다"
        assert waited < 0.5, (
            f"타일 120개가 떠 있는 동안 /health가 {waited:.2f}초 걸렸다 — 요청이 막히고 있다"
        )
    finally:
        api_server._tile_client = original


@pytest.fixture
def anyio_backend():
    return "asyncio"
