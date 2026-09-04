"""D. 신고 정규화 — 반경·시간창·시각 규약·중복·사진."""
from __future__ import annotations

from module_h_citizen_verification import explain, run

from .conftest import ALERT_AT, ORIGIN_X, ORIGIN_Y, at, payload, report, sightings


def test_reports_outside_the_radius_are_excluded():
    """14. trigger_radius_m 밖 신고는 제외하고 그 사실을 남긴다."""
    result = run(
        payload(
            [
                report("IN", distance_m=499.0),
                report("OUT", distance_m=501.0),
            ]
        )
    )
    assert result["data"]["report_count"] == 1
    assert any("OUT" in w and "밖" in w for w in result["warnings"])

    excluded = explain(payload([report("IN", distance_m=499.0), report("OUT", distance_m=501.0)]))
    assert [e["report_id"] for e in excluded["detail"]["excluded"]] == ["OUT"]
    assert excluded["detail"]["received_count"] == 2


def test_reports_outside_the_time_window_are_excluded():
    """15. 유효 시간창(기본 60분) 밖 신고는 제외한다."""
    result = run(payload([report("EARLY", minutes_from_alert=10), report("LATE", minutes_from_alert=61)]))
    assert result["data"]["report_count"] == 1
    assert any("LATE" in w and "시간창" in w for w in result["warnings"])


def test_reports_before_the_alert_are_counted_but_excluded_from_latency():
    """16. 경보 이전 신고는 버리지 않는다 — 산청이 정확히 그 형태(신고 08:00, 경보 12:37)다.

    집계에는 포함하되 response_latency_min 계산에서만 뺀다.
    """
    result = run(payload([report("BEFORE", minutes_from_alert=-30), report("AFTER", minutes_from_alert=6)]))
    assert result["data"]["report_count"] == 2
    assert result["data"]["response_latency_min"] == 6.0
    assert any("경보 발송 이전 신고 1건" in w for w in result["warnings"])


def test_all_reports_before_the_alert_gives_null_latency():
    """16-b. 전부 경보 이전이면 latency는 null이다 — 0으로 위장하지 않는다."""
    result = run(payload([report("B1", minutes_from_alert=-30), report("B2", minutes_from_alert=-10)]))
    assert result["data"]["report_count"] == 2
    assert result["data"]["response_latency_min"] is None


def test_naive_and_non_kst_timestamps_are_normalized_with_warnings():
    """17. §4.1 — 타임존 없는 값은 KST 가정, KST가 아닌 값은 KST로 변환. 둘 다 경고."""
    naive = report("NAIVE")
    naive["timestamp"] = ALERT_AT.replace(tzinfo=None).isoformat()
    utc = report("UTC")
    utc["timestamp"] = "2025-07-19T00:20:00+00:00"  # = 09:20 KST

    result = run(payload([naive, utc]))
    assert result["data"]["report_count"] == 2
    assert any("타임존 없는" in w for w in result["warnings"])
    assert any("KST가 아닌" in w for w in result["warnings"])
    assert result["status"] == "degraded"
    assert result["data"]["response_latency_min"] == 0.0


def test_duplicate_report_ids_are_folded():
    """18. 같은 report_id는 1건으로 접는다 — 중복 제출로 신뢰도가 부풀지 않게."""
    result = run(payload([report("R001"), report("R001"), report("R002")]))
    assert result["data"]["report_count"] == 2
    assert any("중복" in w for w in result["warnings"])


def test_malformed_reports_are_dropped_individually():
    """19. 한 건이 깨져도 나머지는 살린다 — 부분 실패가 전체를 죽이지 않는다."""
    broken = [
        "not a dict",
        {"report_id": "", "x_5179": 1.0, "y_5179": 2.0, "timestamp": at(1), "report_type": "이상징후_목격", "photo_url": None},
        {**report("BAD_TYPE"), "report_type": "루머"},
        {**report("BAD_COORD"), "x_5179": "동쪽"},
        {**report("BAD_TIME"), "timestamp": "어제"},
        report("GOOD"),
    ]
    result = run(payload(broken))
    assert result["data"]["report_count"] == 1
    assert result["status"] == "degraded"
    assert len(explain(payload(broken))["detail"]["excluded"]) == 5


def test_photo_url_does_not_change_the_verdict_and_is_never_fetched():
    """20. 사진 첨부는 판정에 영향을 주지 않는다. URL은 집계 대상이 아니라 건수만 센다.

    photo_url은 시민이 제출한 미검증 외부 URL이라 모듈이 절대 접근하지 않는다 —
    첨부 여부만 explain()으로 노출한다.
    """
    without = payload(sightings(4))
    with_photos = payload(sightings(4, photo_url="https://example.invalid/does-not-exist.jpg"))
    assert run(without)["data"] == run(with_photos)["data"]
    assert explain(with_photos)["detail"]["photo_count"] == 4
    assert explain(without)["detail"]["photo_count"] == 0


def test_invalid_photo_url_type_is_tolerated():
    """20-b. photo_url이 문자열도 null도 아니면 첨부 없음으로 처리하고 신고는 살린다."""
    bad = {**report("R001"), "photo_url": 12345}
    result = run(payload([bad]))
    assert result["data"]["report_count"] == 1
    assert any("photo_url" in w for w in result["warnings"])
