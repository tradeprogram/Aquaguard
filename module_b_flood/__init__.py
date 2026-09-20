"""module_b_flood — 하천범람 예측 (§5 Module B, SFINCS 1순위 / ANUGA 대체).

§4.2 표준 진입점 run(input: dict) -> dict 하나를 노출한다. Module O는
modules_client.py가 이 패키지를 import_module로 불러 run()을 호출한다.

방법론: flood_prob·hours_to_critical은 실측 수위·강우를 홍수특보 기준·실측
홍수사례(산청 경호강 2025-07-19)로 보정한 설명가능 대리모형(flood.py).
침수범위(inundation_extent_5179)는 SFINCS/ANUGA 물리모형의 최대침수심을 폴리곤화
하거나(precomputed), 예측 수위로 HAND-FIM(fim.py) 산출. 물리 근거는 자체 solver가
아니라 Deltares SFINCS(검증: 경호교 수위 RMSE 1.42m, 2엔진 교차 IoU 0.775).

침수 지형 주입(선택): input["_terrain"] = {"depth_raster": path}  (모형 최대침수심)
  또는 {"hand_path": path, "stage_m": float}  (HAND-FIM). 미주입 시 빈 FC + warning.
"""
from __future__ import annotations

from typing import Any

from . import envelope as _env
from . import flood, fim
from .envelope import envelope as _make

__all__ = ["run", "explain"]


def _resolve_extent(input: dict, norm) -> tuple[dict, list[str]]:
    """침수 폴리곤 확정. 지형 주입 우선, 없으면 빈 FC + 안내(모듈 A 토양 폴백과 동일 원칙)."""
    warns: list[str] = []
    terrain = input.get("_terrain") or {}
    try:
        if terrain.get("depth_raster"):
            fc = fim.raster_to_featurecollection(terrain["depth_raster"],
                                                 thr=float(terrain.get("depth_thr_m", 0.3)))
            return fc, warns
        if terrain.get("hand_path"):
            fc = fim.hand_fim_featurecollection(hand_path=terrain["hand_path"],
                                                stage_m=terrain.get("stage_m"))
            return fc, warns
    except Exception as exc:  # noqa: BLE001
        warns.append(f"침수 폴리곤 생성 실패({type(exc).__name__}) → 빈 FeatureCollection")
        return {"type": "FeatureCollection", "features": []}, warns
    warns.append("침수 지형(_terrain) 미주입 → inundation_extent 빈 FC. "
                 "SFINCS 최대침수심 래스터 또는 HAND 주입 시 폴리곤 산출")
    return {"type": "FeatureCollection", "features": []}, warns


def run(input: dict) -> dict:  # noqa: A002 - §4.2 규약이 지정한 이름
    """§4.2 공통 봉투를 반환한다. 어떤 경우에도 예외를 밖으로 던지지 않는다."""
    norm = None
    try:
        norm = _env.normalize(input)
        if norm.fatal:
            return _env.error_envelope(norm.reach_id, norm.warnings)

        res = flood.evaluate(river_level_m=norm.river_level_m, rain_24h_mm=norm.rain_24h_mm,
                             river_order=norm.river_order, widen_ci=(norm.fallback_tier == 3))
        extent, extent_warns = _resolve_extent(input, norm)

        return _make(
            status="ok" if norm.fallback_tier == 1 else "degraded",
            fallback_tier=norm.fallback_tier,
            data={
                "flood_prob": res.flood_prob,
                "confidence_interval": [res.confidence_interval[0], res.confidence_interval[1]],
                "hours_to_critical": res.hours_to_critical,
                "inundation_extent_5179": extent,
            },
            warnings=norm.warnings + extent_warns,
        )
    except Exception as exc:  # noqa: BLE001 - §4.2: 모듈은 예외로 죽지 않는다
        rid = norm.reach_id if norm else input.get("reach_id")
        prior = list(norm.warnings) if norm else []
        return _env.error_envelope(rid, prior + [
            f"Module B 내부 오류({type(exc).__name__}: {exc}) → error 봉투로 폴백"])


def explain(input: dict) -> dict[str, Any]:
    """계약 밖 판정 근거 — UI Provenance 배지(§6.1)·설명가능성용."""
    norm = _env.normalize(input)
    z = flood.logit_score(norm.river_level_m, norm.rain_24h_mm)
    res = flood.evaluate(norm.river_level_m, norm.rain_24h_mm, norm.river_order,
                        widen_ci=(norm.fallback_tier == 3))
    return {
        "method": "설명가능 로지스틱(수위·강우) + SFINCS/ANUGA 물리검증 + HAND-FIM 침수",
        "inputs": {"river_level_m": norm.river_level_m, "rain_24h_mm": norm.rain_24h_mm,
                   "river_order": norm.river_order},
        "logit_score": round(z, 3),
        "flood_prob": res.flood_prob,
        "calibration": {"L_REF_m": flood.L_REF, "R_REF_mm": flood.R_REF,
                        "validation": "산청 경호강 2025-07-19: 수위 RMSE 1.42m(SFINCS), 2엔진 교차 IoU 0.775"},
        "fallback_tier": norm.fallback_tier,
        "warnings": norm.warnings,
        "is_model": True,
    }
