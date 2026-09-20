"""module_v_validation.leadtime — 골든타임(lead_time_min) 산출 (계약 무관).

lead_time_min = 관측시각 − 예측경보시각 (분). 양수 = 예측이 관측보다 앞섬(골든타임).
- 예측경보시각: alert_id "AL-YYYYMMDD-HHMM" 파싱, 또는 predicted.alert_timestamp.
- 관측시각: observed.acquisition_timestamp (ISO8601).
둘 다 파싱 가능할 때만 산출, 아니면 None.
"""
from __future__ import annotations

import re
from datetime import datetime

_ALERT_RE = re.compile(r"(\d{8})-(\d{4})")


def _parse_alert(alert_id: str | None, alert_ts: str | None):
    if alert_ts:
        try:
            return datetime.fromisoformat(alert_ts.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            pass
    if alert_id:
        m = _ALERT_RE.search(alert_id)
        if m:
            try:
                return datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M")
            except ValueError:
                return None
    return None


def _parse_iso(ts: str | None):
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def lead_time_min(alert_id: str | None, observed_timestamp: str | None,
                  alert_timestamp: str | None = None) -> float | None:
    """관측시각 − 예측경보시각 (분). 파싱 불가·음수(관측이 먼저)면 None/0 처리."""
    t_alert = _parse_alert(alert_id, alert_timestamp)
    t_obs = _parse_iso(observed_timestamp)
    if t_alert is None or t_obs is None:
        return None
    # tz 혼용 방지: 둘 다 naive로 비교(정보 있으면 유지)
    if (t_alert.tzinfo is None) != (t_obs.tzinfo is None):
        t_alert = t_alert.replace(tzinfo=None)
        t_obs = t_obs.replace(tzinfo=None)
    delta_min = (t_obs - t_alert).total_seconds() / 60.0
    return round(delta_min, 1) if delta_min >= 0 else None
