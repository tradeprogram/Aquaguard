"""Module O 테스트 공용 픽스처."""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _pin_mock_mode(monkeypatch):
    """AQUAGUARD_MOCK_MODE를 목업으로 고정한다.

    대부분의 테스트가 contracts/module_o.example.json 기준으로 status/warnings까지
    단언하는데, 이건 전 모듈이 example로 갈 때만 성립한다. 이 값을 고정하지 않으면
    쉘에 AQUAGUARD_MOCK_MODE=0이 떠 있는 개발자에게만 실패하는 테스트가 된다
    (실제로 그렇게 실패하는 걸 확인하고 넣었다).

    실 모드 동작을 보는 테스트는 각자 monkeypatch.setenv로 이 값을 덮어쓴다.
    """
    monkeypatch.setenv("AQUAGUARD_MOCK_MODE", "1")
