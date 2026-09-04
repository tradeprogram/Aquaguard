"""module_h_citizen_verification — 시민 신고 역검증 (§5 Module H).

§4.2 표준 진입점 run(input: dict) -> dict. Module O는 Module A의 precursor_flag가
뜬 지점 반경 내에서 이 모듈을 트리거하고, 돌아온 confidence_adjustment로
landslide_prob을 보정한다.

푸시 채널(문자·알림톡)은 구현하지 않는다 — 데모는 웹 대시보드 시뮬레이션으로
대체하기로 팀 문서(§10 TODO 6)에 합의돼 있다. 이 모듈은 이미 수집된 신고를
집계하는 순수 함수이며 네트워크를 타지 않는다.

폴백 계층 (§7의 Module H 행 그대로):
  tier 1  시민 응답 다수 확보 (유효 신고 >= full_weight_min_reports)
  tier 2  응답 소수 — shrinkage가 자동으로 낮은 가중치를 만든다
  tier 3  응답 0건 → 미확인 + confidence_adjustment 0.0 (원래 임계치 로직 유지)
  error   입력 구조가 깨진 경우

어느 경로든 스키마를 만족하는 봉투를 내고 예외를 밖으로 던지지 않는다.
"""
from __future__ import annotations

from typing import Any

from . import aggregate as aggregate_module
from . import policy, reports
from .envelope import EMPTY_DATA, envelope, error_envelope

__all__ = ["run", "explain"]


class _InputError(ValueError):
    """복구 불가능한 입력 — error 봉투로 나간다."""


def _read_input(raw: Any) -> tuple[dict[str, float], float, list[Any]]:
    if not isinstance(raw, dict):
        raise _InputError(f"입력이 dict가 아님({type(raw).__name__}) → 판정 불가")

    trigger_location = raw.get("trigger_location")
    if (
        not isinstance(trigger_location, dict)
        or not reports._is_number(trigger_location.get("x_5179"))
        or not reports._is_number(trigger_location.get("y_5179"))
    ):
        raise _InputError("trigger_location이 없거나 x_5179/y_5179가 숫자가 아님 → 거리 계산 불가")

    citizen_reports = raw.get("citizen_reports")
    if not isinstance(citizen_reports, list):
        raise _InputError(
            f"citizen_reports가 배열이 아님({type(citizen_reports).__name__}) → 판정 불가"
        )

    radius = raw.get("trigger_radius_m")
    if not reports._is_number(radius) or radius <= 0:
        raise _InputError(f"trigger_radius_m가 양수가 아님({radius!r}) → 반경 판정 불가")

    return trigger_location, float(radius), citizen_reports


def _evaluate(raw: Any) -> tuple[dict[str, Any], int, list[str], dict[str, Any]]:
    """(data, fallback_tier, warnings, 상세) — run과 explain이 함께 쓴다."""
    pol = policy.active_policy()
    trigger_location, radius, citizen_reports = _read_input(raw)

    warnings: list[str] = []
    alert_time = reports.resolve_alert_time(raw, pol, warnings)

    normalized = reports.normalize(citizen_reports, trigger_location, radius, alert_time, pol)
    warnings.extend(normalized.warnings)

    result = aggregate_module.aggregate(normalized.valid, pol)
    tier = aggregate_module.fallback_tier(
        result.report_count, normalized.degraded or alert_time.degraded, pol
    )

    data = {
        "report_count": result.report_count,
        "verification_status": result.verification_status,
        "confidence_adjustment": result.confidence_adjustment,
        "response_latency_min": result.response_latency_min,
    }
    detail = {
        "policy": pol.summary(),
        "alert_time": {
            "value": None if alert_time.value is None else alert_time.value.isoformat(),
            "source": alert_time.source,
        },
        "received_count": normalized.received_count,
        "valid_count": result.report_count,
        "excluded": normalized.excluded,
        "before_alert_count": normalized.before_alert_count,
        "type_counts": result.type_counts,
        "weighted_positive": result.weighted_positive,
        "weighted_net": result.weighted_net,
        "raw_ratio": result.raw_ratio,
        "photo_count": result.photo_count,
        "latency_stats": result.latency_stats,
        "trace": result.trace,
        "is_model": False,
    }
    return data, tier, warnings, detail


def run(input: dict) -> dict:  # noqa: A002 - §4.2 규약이 지정한 이름
    try:
        data, tier, warnings, _ = _evaluate(input)
        return envelope(
            status="ok" if tier == 1 else "degraded",
            fallback_tier=tier,
            data=data,
            warnings=warnings,
        )
    except _InputError as exc:
        return error_envelope([str(exc)])
    except Exception as exc:  # noqa: BLE001 - §4.2: 모듈은 예외로 죽지 않는다
        return error_envelope(
            [f"Module H 내부 오류({type(exc).__name__}: {exc}) → error 봉투로 폴백"]
        )


def explain(input: dict) -> dict[str, Any]:
    """계약 밖 판정 근거 — 총 수신·제외 내역, 사진 첨부 건수, 지연 통계, 정책 출처.

    계약의 data는 4개 필드뿐이라(§6.1 — 필드 추가는 4인 합의 사안) 여기로 뺀다.
    """
    try:
        data, tier, warnings, detail = _evaluate(input)
    except _InputError as exc:
        return {"data": dict(EMPTY_DATA), "fallback_tier": 3, "warnings": [str(exc)], "detail": None}
    return {"data": data, "fallback_tier": tier, "warnings": warnings, "detail": detail}
