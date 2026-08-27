"""
경보 상태 저장소 — §5 Module O의 8단계 상태머신 중 "원클릭 승인 대기" 단계를
지원한다. 인메모리 dict로 충분(단일 프로세스 FastAPI 프로토타입 전제, §4.2).
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Literal

ApprovalStatus = Literal["대기", "승인", "거부", "자동승인(timeout)"]


@dataclass
class Alert:
    alert_id: str
    created_at: datetime
    auto_approve_timeout_min: int
    envelope: dict[str, Any]  # Module O의 전체 출력 envelope
    trigger_input: dict[str, Any] = field(default_factory=dict)  # run()에 원래 넘어온 input (지도 재투영용)
    approval_status: ApprovalStatus = "대기"
    approver_id: str | None = None

    def resolve_status(self) -> ApprovalStatus:
        """타임아웃 자동승인을 지연 평가한다 (§5 Module O).

        시민 역검증이 '오탐판정'이면 자동승인을 걸지 않는다.
        """
        if self.approval_status != "대기":
            return self.approval_status

        citizen = self.envelope["data"]["citizen_verification"]
        if citizen.get("verification_status") == "오탐판정":
            return self.approval_status

        deadline = self.created_at + timedelta(minutes=self.auto_approve_timeout_min)
        if datetime.now(self.created_at.tzinfo) >= deadline:
            self.approval_status = "자동승인(timeout)"
        return self.approval_status


class AlertStore:
    def __init__(self) -> None:
        self._alerts: dict[str, Alert] = {}
        self._lock = threading.Lock()

    def add(self, alert: Alert) -> None:
        with self._lock:
            self._alerts[alert.alert_id] = alert

    def get(self, alert_id: str) -> Alert | None:
        with self._lock:
            return self._alerts.get(alert_id)

    def approve(self, alert_id: str, decision: Literal["승인", "거부"], approver_id: str) -> Alert | None:
        with self._lock:
            alert = self._alerts.get(alert_id)
            if alert is None:
                return None
            # 이미 확정된 상태(자동승인 포함)는 재확정하지 않는다 — 마지막 사람 판단이 남긴 기록을 덮어쓰지 않기 위함
            if alert.resolve_status() == "대기":
                alert.approval_status = decision
                alert.approver_id = approver_id
            return alert


# 프로세스 전역 싱글턴 — api_server.py가 공유한다
alert_store = AlertStore()
