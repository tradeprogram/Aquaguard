import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from module_o_orchestrator.orchestrator import run
from module_o_orchestrator.store import Alert, AlertStore

CONTRACTS_DIR = Path(__file__).resolve().parent.parent.parent / "contracts"


def _load_example(name: str) -> dict:
    with open(CONTRACTS_DIR / f"module_{name}.example.json", encoding="utf-8") as f:
        return json.load(f)


def test_run_matches_contract_shape():
    example = _load_example("o")
    envelope = run(example["input"])

    assert envelope["status"] == "ok"
    assert envelope["fallback_tier"] == 1
    assert envelope["warnings"] == []

    data = envelope["data"]
    for key in ("timeline_actual", "timeline_agent", "golden_time_saved_min", "approval_status", "citizen_verification", "alert_package"):
        assert key in data
    assert data["approval_status"] == "대기"
    for key in ("landslide", "flood", "shelter_route", "damage_cost"):
        assert key in data["alert_package"]


def test_golden_time_matches_documented_example():
    """contracts/module_o.example.json의 기본 입력값은 golden_time_saved_min=197을 문서화하고 있다."""
    example = _load_example("o")
    envelope = run(example["input"])
    assert envelope["data"]["golden_time_saved_min"] == 197.0


def test_alert_registered_for_approval():
    example = _load_example("o")
    alert_id = example["input"]["alert_id"]
    run(example["input"])

    from module_o_orchestrator.store import alert_store

    alert = alert_store.get(alert_id)
    assert alert is not None
    assert alert.approval_status == "대기"


def test_manual_approval_overrides_pending():
    store = AlertStore()
    now = datetime.now(timezone(timedelta(hours=9)))
    envelope = {
        "data": {"citizen_verification": {"verification_status": "미확인", "confidence_adjustment": 0}}
    }
    store.add(Alert(alert_id="X1", created_at=now, auto_approve_timeout_min=15, envelope=envelope))

    result = store.approve("X1", "거부", approver_id="tester")
    assert result.approval_status == "거부"
    assert result.resolve_status() == "거부"


def test_auto_approve_after_timeout():
    store = AlertStore()
    past = datetime.now(timezone(timedelta(hours=9))) - timedelta(minutes=20)
    envelope = {
        "data": {"citizen_verification": {"verification_status": "미확인", "confidence_adjustment": 0}}
    }
    store.add(Alert(alert_id="X2", created_at=past, auto_approve_timeout_min=15, envelope=envelope))

    alert = store.get("X2")
    assert alert.resolve_status() == "자동승인(timeout)"


def test_no_auto_approve_when_false_positive():
    store = AlertStore()
    past = datetime.now(timezone(timedelta(hours=9))) - timedelta(minutes=20)
    envelope = {
        "data": {"citizen_verification": {"verification_status": "오탐판정", "confidence_adjustment": -0.2}}
    }
    store.add(Alert(alert_id="X3", created_at=past, auto_approve_timeout_min=15, envelope=envelope))

    alert = store.get("X3")
    assert alert.resolve_status() == "대기"
