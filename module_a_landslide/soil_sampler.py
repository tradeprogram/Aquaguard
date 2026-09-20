"""module_a_landslide.soil_sampler — 좌표 → 부지 지반정수 (A-1 정밀토양도 샘플러).

계약 input에는 토성·토심이 없다. Module A가 좌표에서 직접 샘플링하는 게 원칙인데
(README §2), 전국 정밀토양도 shapefile이 대용량이라 그동안 연결을 못 하고 전국
대표 폴백(식양질)을 써 왔다. 그 폴백은 **완전포화에서도 FoS≈1.9**라 어떤 비가 와도
landslide_prob이 0.7을 못 넘는다 — Module O의 트리거(orchestrator LANDSLIDE_THRESHOLD)
가 영영 안 걸려 하류 모듈(D/E/G)과 3D 시뮬레이터가 아무것도 못 받는 원인이었다.

그래서 산청 AOI 격자를 저장소에 넣었다(`data/sancheong_soil_grid_5m.npz`).

저장 형식 — rasterio 의존성을 새로 들이지 않으려고 numpy만으로 읽는다:
  soil_idx    uint8  (H,W)   토양조합 인덱스, 255=nodata
  soil_lut    f32    (33,5)  [c_kpa, phi_deg, gamma_kn_m3, z_m, m0]
  transform   f64    (6,)    GDAL affine (originX, pxW, 0, originY, 0, pxH)

**원해상도 5m 그대로** 넣었다(6180×7619 = 47M셀). 조합이 33개뿐이라 uint8
인덱스 + 룩업으로 압축하면 2.1MB다 — 25m로 줄인 것보다 오히려 작으면서
다운샘플이 고위험 포켓을 뭉개는 문제가 없다(25m 최근접에서 한 셀이 0.744→0.391로
떨어지는 걸 확인하고 되돌렸다).

dNBR은 일부러 넣지 않았다. 산불 등급은 계약 input(static.dnbr_class)이 주는
값이고, 격자가 그걸 덮어쓰면 계약 밖 데이터로 결과가 바뀐다. 격자는 계약에
없는 것(토성·토심·배수)만 채운다.

AOI 밖 좌표는 None을 반환하고 호출부가 기존 전국 폴백으로 되돌아간다 —
다른 지역에서 조용히 틀린 값을 쓰지 않는다.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

_GRID = Path(__file__).resolve().parent / "data" / "sancheong_soil_grid_5m.npz"
_SLOPE_GRID = Path(__file__).resolve().parent / "data" / "sancheong_slope_5m.npz"


@lru_cache(maxsize=1)
def _grid():
    """격자를 한 번만 메모리에 올린다. 파일이 없거나 numpy가 없으면 None."""
    try:
        import numpy as np
    except ImportError:
        return None
    if not _GRID.exists():
        return None
    try:
        z = np.load(_GRID, allow_pickle=False)
        return {
            "idx": z["soil_idx"],
            "lut": z["soil_lut"],
            "tr": z["transform"],
            "fields": [str(f) for f in z["fields"]],
        }
    except Exception:  # noqa: BLE001 - 격자가 깨졌어도 Module A는 폴백으로 살아야 한다
        return None


def available() -> bool:
    return _grid() is not None


def sample(x_5179: float | None, y_5179: float | None) -> dict[str, Any] | None:
    """좌표의 부지 지반정수. AOI 밖이거나 nodata면 None(→ 호출부가 전국 폴백).

    반환 키는 __init__._resolve_soil 이 그대로 _soil 로 쓰는 원시 지반정수다:
    c_kpa · phi_deg · gamma_kn_m3 · z_m · m0.
    """
    g = _grid()
    if g is None or x_5179 is None or y_5179 is None:
        return None

    ox, pw, _, oy, _, ph = (float(v) for v in g["tr"])
    if pw == 0 or ph == 0:
        return None
    col = int((float(x_5179) - ox) / pw)
    row = int((float(y_5179) - oy) / ph)

    h, w = g["idx"].shape
    if not (0 <= row < h and 0 <= col < w):
        return None

    i = int(g["idx"][row, col])
    if i == 255:
        return None

    vals = g["lut"][i]
    out: dict[str, Any] = {name: float(v) for name, v in zip(g["fields"], vals)}

    out["provenance"] = "MEASURED"
    out["source"] = "산청 정밀토양도 유래 지반정수 격자 5m (scripts/15_sancheong_soil_grid.py)"
    return out


# ---------------------------------------------------------------------------
# 경사 격자 (2차 작업지시서, 2026-09-20)
#
# slope_deg 는 계약 static 의 **필수 입력**이라 Module A 가 격자로 조용히 덮어쓰면
# 계약이 깨진다(dNBR 을 격자에서 뺀 것과 같은 이유). 그래서 run() 은 이 함수를 쓰지
# 않는다 — 호출자(Module O)가 slope_at() 으로 값을 읽어 static.slope_deg 에 넣는다.
#
# 5m 원해상도를 그대로 담았다. 10m 로 줄이면 파일이 26MB→10MB 로 작아지지만,
# 계약 example 좌표에서 실제 5m 경사 32.67°가 10m 부분추출로 33.3°가 되어
# **트리거 판정이 샘플링 오차로 뒤집힌다**(0.5°가 판정을 가른다는 지시서 표 참조).
# 급사면 20만 점 실측 오차: 10m nearest 중앙 0.75°·p90 3.60°. 판정이 걸린 값이라
# 크기보다 정확도를 택했다. 저장소에 이미 27.6MB aoi_buildings_seoul 이 있다.
#
# 인코딩: uint8 × 0.3° (0~76.2°, 산청 최대 74.85° 를 잘림 없이 덮는다. 0.25°는
# 63.75°까지라 절벽 2,161 픽셀이 잘린다) + 행방향 차분. 차분은 행 하나만 되돌리면
# 되므로 임의접근 비용이 사실상 없다.
_SLOPE_NODATA = 255


@lru_cache(maxsize=1)
def _slope_grid():
    try:
        import numpy as np
    except ImportError:
        return None
    if not _SLOPE_GRID.exists():
        return None
    try:
        z = np.load(_SLOPE_GRID, allow_pickle=False)
        return {"d8": z["slope_d8"], "step": float(z["slope_step_deg"]),
                "tr": z["transform"], "nodata": int(z["nodata_code"])}
    except Exception:  # noqa: BLE001 - 격자가 깨져도 호출부는 계약값으로 살아야 한다
        return None


@lru_cache(maxsize=256)
def _slope_row(row: int):
    """행 하나를 차분에서 복원. 같은 행 반복 질의는 캐시로 값싸진다."""
    import numpy as np
    g = _slope_grid()
    return (np.cumsum(g["d8"][row].astype(np.uint16)) % 256).astype(np.uint8)


def slope_available() -> bool:
    return _slope_grid() is not None


def slope_at(x_5179: float, y_5179: float) -> float | None:
    """좌표의 지표경사(도). AOI 밖이거나 격자 미탑재면 None.

    None 이면 호출부가 기존 계약값을 그대로 쓰고 경고를 남기면 된다 —
    남의 지역 지형을 쓰지 않는다는 점에서 sample() 과 같은 규약이다.
    """
    g = _slope_grid()
    if g is None or x_5179 is None or y_5179 is None:
        return None
    ox, pw, _, oy, _, ph = (float(v) for v in g["tr"])
    if pw == 0 or ph == 0:
        return None
    col = int((float(x_5179) - ox) / pw)
    row = int((float(y_5179) - oy) / ph)
    h, w = g["d8"].shape
    if not (0 <= row < h and 0 <= col < w):
        return None
    code = int(_slope_row(row)[col])
    if code == g["nodata"]:
        return None
    return round(code * g["step"], 2)

