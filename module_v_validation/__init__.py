"""module_v_validation — 위성 검증 (§5 Module V, 프로젝트 승부처).

§4.2 표준 진입점 run(input: dict) -> dict 하나를 노출한다. Module O는
modules_client.py가 이 패키지를 import_module로 불러 run()을 호출한다.

방법론: A/B의 예측 폴리곤과 관측(Sentinel-1 SAR 변화탐지/인벤토리) 폴리곤을 같은
격자에 rasterize → IoU/F1/precision/recall + confusion_geometry(TP/FP/FN 분리) + lead_time.
★ data-leakage 금지: observed(사건 후 취득)는 A/B '예측'을 만드는 데 절대 안 쓰인다.
  이 모듈은 이미 만들어진 예측 vs 관측을 '사후 채점'만 한다(계약으로 A/B와 분리).

물리·검증 근거(오프라인): 산청 하천범람은 SFINCS/ANUGA 2엔진 교차 IoU 0.775, 수위 RMSE
1.42m. 산사태는 발생부 참값 부재로 SAR IoU 낮음(3중 참값으로 한계 규명, DATA_SOURCES).
"""
from __future__ import annotations

from typing import Any

from . import envelope as _env
from . import metrics, leadtime
from .envelope import envelope as _make

__all__ = ["run", "explain"]


def run(input: dict) -> dict:  # noqa: A002 - §4.2 규약이 지정한 이름
    """§4.2 공통 봉투를 반환한다. 어떤 경우에도 예외를 밖으로 던지지 않는다."""
    norm = None
    try:
        norm = _env.normalize(input)
        if norm.fatal:
            return _env.error_envelope(norm.warnings)

        conf = metrics.confusion(norm.predicted_fc, norm.observed_fc)
        lt = leadtime.lead_time_min(
            norm.alert_id, norm.observed_timestamp,
            (input.get("predicted") or {}).get("alert_timestamp"))

        warnings = list(norm.warnings)
        if conf.get("note") == "no geometry":
            warnings.append("예측·관측 폴리곤 비어있음 → 지표 0")
        if lt is None:
            warnings.append("lead_time 산출 불가(시각 파싱 실패 또는 관측이 예측보다 앞섬)")

        return _make(
            status="ok" if norm.fallback_tier == 1 else "degraded",
            fallback_tier=norm.fallback_tier,
            data={
                "iou": conf["iou"], "f1": conf["f1"],
                "precision": conf["precision"], "recall": conf["recall"],
                "confusion_geometry_5179": conf["confusion_geometry"],
                "lead_time_min": lt,
            },
            warnings=warnings,
        )
    except ImportError as exc:
        prior = list(norm.warnings) if norm else []
        return _env.error_envelope(prior + [
            f"공간연산 의존성 미설치({exc}) → error 봉투(rasterio/shapely 필요)"])
    except Exception as exc:  # noqa: BLE001 - §4.2: 모듈은 예외로 죽지 않는다
        prior = list(norm.warnings) if norm else []
        return _env.error_envelope(prior + [
            f"Module V 내부 오류({type(exc).__name__}: {exc}) → error 봉투로 폴백"])


def explain(input: dict) -> dict[str, Any]:
    """계약 밖 판정 근거 — UI Provenance 배지(§6.1)용."""
    norm = _env.normalize(input)
    return {
        "method": "예측·실측 폴리곤 공통격자 rasterize → 혼동행렬(IoU/F1/P/R) + lead_time",
        "predicted_source_module": norm.source_module,
        "observed_type": norm.observed_type,
        "observed_source": norm.observed_source,
        "fallback_tier": norm.fallback_tier,
        "anti_leakage": "observed는 예측 입력에 미사용 — 사후 채점 전용",
        "offline_validation": "산청 홍수 2엔진 교차 IoU 0.775·수위 RMSE 1.42m",
        "warnings": norm.warnings,
        "is_model": False,
    }
