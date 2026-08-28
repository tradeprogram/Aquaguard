"""
경보 상태 저장소 — §5 Module O의 8단계 상태머신 중 "원클릭 승인 대기" 단계를
지원한다. 인메모리 dict로 충분(단일 프로세스 FastAPI 프로토타입 전제, §4.2).

2026-08-29: 무응답 시 자동승인 로직을 삭제하고 escalation으로 교체했다(심층
경쟁기술 리서치 반영, ARCHITECTURE.md §5 Module O 참조) — 생명안전 관련 공공
의사결정에서 "무응답 시 자동승인"은 책임성 공격을 정면으로 받는다. 이 시스템은
어떤 경우에도 공식 대피명령을 독자 발령하지 않는다: 타임아웃이 지나도 상태는
"승인"이 되지 않고 "권고중(escalation)"으로만 바뀌며, 사람은 escalation 이후에도
언제든 승인/거부할 수 있다(resolve_status()가 "승인"/"거부"가 아니면 approve()가
계속 받아준다 — 자동승인 시절과 달리 escalation은 판단을 가로채지 않는다).
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Literal

ApprovalStatus = Literal["대기", "승인", "거부", "권고중(escalation)"]


@dataclass
class Alert:
    alert_id: str
    created_at: datetime
    escalation_timeout_min: int
    envelope: dict[str, Any]  # Module O의 전체 출력 envelope
    trigger_input: dict[str, Any] = field(default_factory=dict)  # run()에 원래 넘어온 input (지도 재투영용)
    approval_status: ApprovalStatus = "대기"
    escalation_level: int = 0
    approver_id: str | None = None

    def resolve_status(self) -> ApprovalStatus:
        """타임아웃 escalation을 지연 평가한다 (§5 Module O).

        시민 역검증이 '오탐판정'이면 escalation을 걸지 않는다 — 이미 오탐 신호가
        있는 상태에서 담당자를 다급하게 재촉할 이유가 없다.
        """
        if self.approval_status in ("승인", "거부"):
            return self.approval_status

        citizen = self.envelope["data"]["citizen_verification"]
        if citizen.get("verification_status") == "오탐판정":
            return self.approval_status

        elapsed = datetime.now(self.created_at.tzinfo) - self.created_at
        timeout = timedelta(minutes=self.escalation_timeout_min)
        if elapsed >= timeout:
            self.approval_status = "권고중(escalation)"
            self.escalation_level = int(elapsed / timeout)  # 타임아웃을 몇 번째 넘겼는지 — 재알림 강도용
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
            # 이미 사람이 확정한 상태(승인/거부)만 재확정하지 않는다 — "권고중(escalation)"은
            # 여전히 판단 대기 중인 상태이므로 escalation 이후에도 승인/거부를 받아준다.
            if alert.resolve_status() not in ("승인", "거부"):
                alert.approval_status = decision
                alert.approver_id = approver_id
            return alert


# 프로세스 전역 싱글턴 — api_server.py가 공유한다
alert_store = AlertStore()
