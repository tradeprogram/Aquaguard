"""시민 신고 정규화 (Module H).

집계 이전 단계 — 좌표·시각·유형을 검증하고, 반경·시간창·중복으로 걸러낸다.
거리는 EPSG:5179 미터 위 유클리드로 계산하며 재투영하지 않는다(§4.1). 시각은
KST 기준이며 UTC를 쓰지 않는다(§4.1).

경보 이전에 들어온 신고는 버리지 않는다 — 산청 사건이 정확히 그 형태(신고 08:00,
경보 12:37)라, 경보보다 먼저 온 신고를 버리는 모듈은 이 프로젝트의 전제와 모순된다.
집계에는 포함하고 응답 지연(latency) 계산에서만 제외한다.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from .policy import REPORT_TYPES, Policy

KST = timezone(timedelta(hours=9))


@dataclass(frozen=True)
class Report:
    report_id: str
    x_5179: float
    y_5179: float
    timestamp: datetime
    report_type: str
    has_photo: bool
    distance_m: float
    minutes_from_alert: float | None


@dataclass
class AlertTime:
    """경보 발송 시각과 그 출처. 계약에 필드가 없어 3단으로 확보한다."""

    value: datetime | None = None
    source: str = "unavailable"  # "alert_issued_at" | "alert_id_pattern" | "unavailable"
    degraded: bool = False


@dataclass
class Normalized:
    valid: list[Report] = field(default_factory=list)
    excluded: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    degraded: bool = False
    received_count: int = 0
    before_alert_count: int = 0


def _parse_timestamp(raw: Any, policy: Policy, warnings: list[str], label: str) -> datetime | None:
    if not isinstance(raw, str):
        return None
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        warnings.append(f"{label}: 타임존 없는 timestamp → KST로 가정(§4.1은 타임존 명시를 요구)")
        return parsed.replace(tzinfo=KST)
    if parsed.utcoffset() != KST.utcoffset(None):
        warnings.append(f"{label}: KST가 아닌 타임존({raw}) → KST로 변환(§4.1은 UTC 금지)")
        return parsed.astimezone(KST)
    return parsed


def resolve_alert_time(raw_input: dict[str, Any], policy: Policy, warnings: list[str]) -> AlertTime:
    """1순위 alert_issued_at → 2순위 alert_id 패턴 → 3순위 없음.

    계약(contracts/module_h.*)에는 경보 발송 시각 필드가 없다. 스키마가 추가 속성을
    막지 않으므로 alert_issued_at을 받되, 없으면 alert_id의 네이밍 관습에서 뽑고
    그 경우 반드시 degraded로 내린다(관습은 계약이 아니다).
    """
    issued_at = _parse_timestamp(
        raw_input.get("alert_issued_at"), policy, warnings, "alert_issued_at"
    )
    if issued_at is not None:
        return AlertTime(issued_at, "alert_issued_at", degraded=False)

    if raw_input.get("alert_issued_at") is not None:
        warnings.append("alert_issued_at을 해석할 수 없음 → alert_id 패턴으로 폴백")

    alert_id = raw_input.get("alert_id")
    if isinstance(alert_id, str):
        match = re.match(policy.alert_id_pattern, alert_id)
        if match:
            try:
                parsed = datetime.strptime(f"{match.group(1)}{match.group(2)}", "%Y%m%d%H%M")
            except ValueError:
                parsed = None
            if parsed is not None:
                warnings.append(
                    f"경보 시각을 alert_id 네이밍 관습에서 추출({alert_id} → "
                    f"{parsed.replace(tzinfo=KST).isoformat()}) — 계약 필드가 아니므로 degraded"
                )
                return AlertTime(parsed.replace(tzinfo=KST), "alert_id_pattern", degraded=True)

    warnings.append(
        "경보 발송 시각을 알 수 없음(alert_issued_at 없음, alert_id 패턴 불일치)"
        " → response_latency_min=null, 시간창 필터 미적용"
    )
    return AlertTime(None, "unavailable", degraded=True)


def _exclude(normalized: Normalized, report_id: str, reason: str) -> None:
    normalized.excluded.append({"report_id": report_id, "reason": reason})
    normalized.warnings.append(f"신고 {report_id} 제외: {reason}")
    normalized.degraded = True


def normalize(
    raw_reports: list[Any],
    trigger_location: dict[str, float],
    trigger_radius_m: float,
    alert_time: AlertTime,
    policy: Policy,
) -> Normalized:
    normalized = Normalized(received_count=len(raw_reports))
    origin_x = float(trigger_location["x_5179"])
    origin_y = float(trigger_location["y_5179"])
    seen: set[str] = set()

    for index, raw in enumerate(raw_reports):
        label = f"citizen_reports[{index}]"
        if not isinstance(raw, dict):
            _exclude(normalized, label, "항목이 dict가 아님")
            continue

        report_id = raw.get("report_id")
        if not isinstance(report_id, str) or not report_id.strip():
            _exclude(normalized, label, "report_id가 비었거나 문자열이 아님")
            continue
        if report_id in seen:
            _exclude(normalized, report_id, "report_id 중복")
            continue
        seen.add(report_id)

        report_type = raw.get("report_type")
        if report_type not in REPORT_TYPES:
            _exclude(normalized, report_id, f"report_type이 계약 enum 밖({report_type!r})")
            continue

        x, y = raw.get("x_5179"), raw.get("y_5179")
        if not _is_number(x) or not _is_number(y):
            _exclude(normalized, report_id, "좌표가 숫자가 아님")
            continue
        distance = math.hypot(float(x) - origin_x, float(y) - origin_y)
        if distance > trigger_radius_m:
            _exclude(
                normalized,
                report_id,
                f"trigger_radius_m({trigger_radius_m}m) 밖 — 거리 {distance:.1f}m",
            )
            continue

        timestamp_warnings: list[str] = []
        timestamp = _parse_timestamp(raw.get("timestamp"), policy, timestamp_warnings, report_id)
        if timestamp is None:
            _exclude(normalized, report_id, f"timestamp를 해석할 수 없음({raw.get('timestamp')!r})")
            continue
        if timestamp_warnings:
            normalized.warnings.extend(timestamp_warnings)
            normalized.degraded = True

        minutes_from_alert: float | None = None
        if alert_time.value is not None:
            minutes_from_alert = (timestamp - alert_time.value).total_seconds() / 60.0
            if minutes_from_alert > policy.valid_window_min:
                _exclude(
                    normalized,
                    report_id,
                    f"유효 시간창({policy.valid_window_min}분) 밖 — 경보 후 {minutes_from_alert:.1f}분",
                )
                continue
            if minutes_from_alert < 0:
                # 버리지 않는다 — 산청처럼 신고가 경보보다 먼저 온 경우가 이 프로젝트의 핵심 서사다.
                normalized.before_alert_count += 1

        photo_url = raw.get("photo_url")
        if not (photo_url is None or isinstance(photo_url, str)):
            normalized.warnings.append(
                f"신고 {report_id}: photo_url이 문자열도 null도 아님 → 첨부 없음으로 처리"
            )
            normalized.degraded = True
            photo_url = None

        normalized.valid.append(
            Report(
                report_id=report_id,
                x_5179=float(x),
                y_5179=float(y),
                timestamp=timestamp,
                report_type=report_type,
                # photo_url은 시민이 제출한 미검증 외부 URL이라 절대 fetch하지 않는다.
                has_photo=bool(photo_url),
                distance_m=distance,
                minutes_from_alert=minutes_from_alert,
            )
        )

    if normalized.before_alert_count:
        normalized.warnings.append(
            f"경보 발송 이전 신고 {normalized.before_alert_count}건 — 집계에는 포함하되"
            " response_latency_min 계산에서는 제외한다"
        )
    return normalized


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
