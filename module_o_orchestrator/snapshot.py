"""사전계산 저장본의 위치·지문·적재 — 만드는 쪽과 내주는 쪽이 같은 코드를 쓰게.

지문이 갈라지면 기능이 **조용히** 꺼진다. 예외도 경고도 없이 그냥 매번 실시간으로
돌아가고, 아무도 저장본이 안 쓰이는 걸 모른다. 실제로 그렇게 됐었다(2026-09-20):
빌더는 `scripts/`에, 판정은 `api_server.py`에 각각 있었고 둘이 같은 규칙인 줄 알았다.

그때 물린 함정이 지문 규칙 자체에 있다 — **JSON은 `12.0`과 `12`를 구분하지 못한다.**
`contracts/module_o.example.json`에는 `12.0`으로 적혀 있지만 브라우저가
`JSON.stringify` 로 보내면 `12`가 되고, 파이썬은 그걸 int로 받는다. 같은 입력인데
정규화 문자열이 달라져 지문이 어긋났다. 그래서 여기서는 숫자를 전부 float으로
맞춘 뒤에 해시한다.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_PATH = REPO_ROOT / "data" / "precomputed" / "demo_snapshot.json"


def _canonical(value: Any) -> Any:
    """지문 계산 전에 숫자 표기를 하나로 맞춘다.

    bool을 먼저 걸러야 한다 — 파이썬에서 bool은 int의 하위형이라 True가 1.0이 되면
    `known_risk: true` 와 `known_risk: 1` 이 같은 지문을 받게 된다.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return float(value)
    if isinstance(value, float):
        return value
    if isinstance(value, dict):
        return {k: _canonical(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_canonical(v) for v in value]
    return value


def input_fingerprint(payload: dict) -> str:
    """입력이 저장본과 같은 질문인지 가르는 지문.

    다르면 저장본을 쓰지 않고 실시간으로 돈다 — 좌표를 옮겼거나 강우를 바꿨으면
    다른 질문이고, 저장본을 내주면 화면이 질문과 다른 답을 보여주게 된다.
    """
    canonical = json.dumps(_canonical(payload), sort_keys=True, ensure_ascii=False,
                           separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def load() -> dict | None:
    """저장본. 없거나 깨졌으면 None이고, 그러면 호출부는 실시간으로 돈다."""
    if not SNAPSHOT_PATH.exists():
        return None
    try:
        with open(SNAPSHOT_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def matching(payload: dict, snapshot: dict | None) -> dict | None:
    """입력이 저장본과 **정확히 같은 질문일 때만** 저장본을 돌려준다."""
    if not snapshot:
        return None
    return snapshot if input_fingerprint(payload) == snapshot.get("input_sha") else None
