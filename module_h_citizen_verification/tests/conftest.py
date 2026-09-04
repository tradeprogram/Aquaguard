"""Module H 테스트 공용 픽스처.

§4.2 "각 모듈 폴더는 pytest로 독립 테스트 가능해야 한다" — contracts/와
module_h_citizen_verification만 읽고 다른 모듈은 import하지 않는다.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

CONTRACTS_DIR = Path(__file__).resolve().parent.parent.parent / "contracts"

KST = timezone(timedelta(hours=9))
ALERT_AT = datetime(2025, 7, 19, 9, 15, tzinfo=KST)
ALERT_ID = "AL-20250719-0915"

# contracts/module_h.example.json의 trigger_location
ORIGIN_X = 1_090_452.3
ORIGIN_Y = 1_662_188.7


def at(minutes_from_alert: float) -> str:
    """경보 발송 기준 상대 시각을 ISO 8601 KST 문자열로."""
    return (ALERT_AT + timedelta(minutes=minutes_from_alert)).isoformat()


def report(
    report_id: str,
    minutes_from_alert: float = 5.0,
    report_type: str = "이상징후_목격",
    distance_m: float = 30.0,
    photo_url: str | None = None,
) -> dict:
    """신고 1건. distance_m만큼 동쪽으로 떨어진 지점에 둔다(EPSG:5179 미터)."""
    return {
        "report_id": report_id,
        "x_5179": ORIGIN_X + distance_m,
        "y_5179": ORIGIN_Y,
        "timestamp": at(minutes_from_alert),
        "report_type": report_type,
        "photo_url": photo_url,
    }


def payload(reports: list[dict], *, with_alert_issued_at: bool = True, radius_m: float = 500) -> dict:
    body = {
        "alert_id": ALERT_ID,
        "trigger_location": {"x_5179": ORIGIN_X, "y_5179": ORIGIN_Y},
        "trigger_radius_m": radius_m,
        "citizen_reports": reports,
    }
    if with_alert_issued_at:
        # 계약에 경보 시각 필드가 없어 트랙②가 제안한 optional 입력(TRACK2_CONTRACT_AGENDA.md 7번).
        body["alert_issued_at"] = ALERT_AT.isoformat()
    return body


def sightings(count: int, first_at: float = 5.0, **kwargs) -> list[dict]:
    return [report(f"R{i:03d}", minutes_from_alert=first_at + i, **kwargs) for i in range(count)]


@pytest.fixture
def contract() -> dict:
    with open(CONTRACTS_DIR / "module_h.example.json", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def contract_schema() -> dict:
    with open(CONTRACTS_DIR / "module_h.schema.json", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def documented_case() -> dict:
    """contracts/module_h.example.json이 문서화한 output을 실제로 만들어내는 입력.

    example.json의 input은 신고 1건인데 output은 report_count 6이고, 경보 발송
    시각 필드가 아예 없어 response_latency_min 4.5도 유도되지 않는다 — 계약 파일은
    4인 합의 없이 못 고치므로(§4.3) 여기서 입력을 만들어 문서가 말하는 출력을 재현한다.

      이상징후_목격 6건, 전부 반경 500m 안, 첫 응답이 경보 +4.5분
      가중 긍정 = 6.0 >= 3.0            → 현장확인
      raw = 6 / (6 + 9) = 0.4, × 0.3    → confidence_adjustment 0.12
      첫 응답                            → response_latency_min 4.5
    """
    return payload(sightings(6, first_at=4.5))


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch):
    monkeypatch.delenv("AQUAGUARD_MODULE_H_POLICY", raising=False)
