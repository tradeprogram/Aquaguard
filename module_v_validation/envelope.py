"""module_v_validation.envelope — §4.2 공통 봉투 + 계약 입력 정규화 (Module V).

여기가 계약 경계다 — contracts/module_v.* 필드명을 아는 유일한 곳.
metrics.py(공간 혼동행렬)와 leadtime.py는 계약 필드명을 모른다.

폴백 계층(§7, 관측 참값 품질 순):
  tier 1  observed = sentinel1_sar_change (SAR 변화탐지, 정밀)
  tier 2  observed = landslide_inventory (실측 인벤토리)
  tier 3  observed = river_gauge (수위 점/선, 공간 IoU 제한)
  error   alert_id / predicted.geometry / observed.geometry 결측
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

OBS_TIER = {"sentinel1_sar_change": 1, "landslide_inventory": 2, "river_gauge": 3}


def envelope(status: str, fallback_tier: int, data: dict[str, Any],
             warnings: list[str]) -> dict[str, Any]:
    """§4.2 공통 봉투. 키 순서까지 문서 예시와 맞춘다."""
    return {"status": status, "fallback_tier": fallback_tier, "data": data, "warnings": warnings}


def _empty_fc() -> dict[str, Any]:
    return {"type": "FeatureCollection", "features": []}


def error_envelope(warnings: list[str]) -> dict[str, Any]:
    """실패해도 스키마를 만족하는 봉투 — §4.2 '예외로 죽지 않는다'."""
    return envelope(
        status="error", fallback_tier=3,
        data={"iou": 0.0, "f1": 0.0, "precision": 0.0, "recall": 0.0,
              "confusion_geometry_5179": {"true_positive": _empty_fc(),
                                          "false_positive": _empty_fc(),
                                          "false_negative": _empty_fc()},
              "lead_time_min": None},
        warnings=warnings,
    )


@dataclass
class NormalizedInput:
    alert_id: str | None
    source_module: str | None      # "A" | "B"
    predicted_fc: dict | None
    observed_type: str | None
    observed_fc: dict | None
    observed_timestamp: str | None
    observed_source: str | None
    fallback_tier: int
    warnings: list[str] = field(default_factory=list)
    fatal: bool = False


def _is_fc(g: Any) -> bool:
    return isinstance(g, dict) and g.get("type") == "FeatureCollection" and isinstance(g.get("features"), list)


def normalize(input: dict) -> NormalizedInput:  # noqa: A002
    warnings: list[str] = []
    alert_id = input.get("alert_id")
    pred = input.get("predicted") or {}
    obs = input.get("observed") or {}

    src_mod = pred.get("source_module")
    pred_fc = pred.get("geometry_5179")
    obs_type = obs.get("type")
    obs_fc = obs.get("geometry_5179")

    tier = OBS_TIER.get(str(obs_type), 3)
    if obs_type not in OBS_TIER:
        warnings.append(f"observed.type 미지정/미지({obs_type}) → tier3(제한적 검증)")
    elif tier == 3:
        warnings.append("observed=river_gauge → 공간 폴리곤 아님, IoU 제한")
    elif tier == 2:
        warnings.append("observed=landslide_inventory(대체 참값) → tier2")

    fatal = (not alert_id) or (not _is_fc(pred_fc)) or (not _is_fc(obs_fc))
    if not alert_id:
        warnings.append("alert_id 결측 → error 봉투")
    if not _is_fc(pred_fc):
        warnings.append("predicted.geometry_5179 FeatureCollection 아님 → error")
    if not _is_fc(obs_fc):
        warnings.append("observed.geometry_5179 FeatureCollection 아님 → error")

    return NormalizedInput(
        alert_id=alert_id, source_module=src_mod,
        predicted_fc=pred_fc if _is_fc(pred_fc) else None,
        observed_type=obs_type, observed_fc=obs_fc if _is_fc(obs_fc) else None,
        observed_timestamp=obs.get("acquisition_timestamp"),
        observed_source=obs.get("source"),
        fallback_tier=tier, warnings=warnings, fatal=fatal,
    )
