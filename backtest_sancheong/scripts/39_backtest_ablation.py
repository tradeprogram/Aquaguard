"""
39_backtest_ablation.py  (산청 백테스트 — bt-abl: ±dNBR 민감도/제거 실험)

질문: "산불(dNBR)을 모형에서 빼거나 흔들면 골든타임이 얼마나 달라지는가?"
산불→뿌리점착력 약화(Cr_eff = Cr/f(dNBR))가 이 모형에서 산불이 들어오는 유일한
경로다. 그래서 f만 바꿔 끼우면 순수한 산불 기여도가 분리된다.

계산 트릭(결과는 16번과 동일, 속도만 다름):
  FoS(m) = (C + A − m·B) / D   — m에 대해 선형.
  FoS < 1  ⟺  m > (C + A − D)/B  ≡  m_crit   (B>0)
  m(t) = clip(m0 + rain_term(t), 0, 1)  이고 rain_term은 공간불변이므로
  임계초과 ⟺ rain_term(t) > m_crit − m0 ≡ margin.
  → margin을 픽셀당 한 번만 구해두면 시간루프가 단순 비교 한 줄이 된다.

시나리오(가로축 = 산불 처리):
  fire_off      f≡1        산불 없음(반사실). 산불 기여 0
  observed      f(dNBR)    기준선 — 16번과 동일
  dnbr_m0.10    dNBR−0.10  위성 dNBR 산출 불확실성 하한
  dnbr_p0.10    dNBR+0.10  상한
  no_roots      Cr_eff=0   전소 상한(뿌리 완전 소실) — 물리적 최악경계

세로축 = 지반정수 시나리오 A(토양도 토성) / B(풍화화강토) — 16번과 동일.

정직: Rsat·Wmax·시그모이드 k는 여전히 미보정이다. 여기서 보는 것은 절대
예측력이 아니라 '산불을 빼면 신호가 얼마나 죽는가'라는 상대 기여도다.
"""
from __future__ import annotations

import json
import sys
import warnings

warnings.filterwarnings("ignore")
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(r"G:/연구/공모전/아쿠아가드")
FOS = ROOT / "data" / "sancheong_fos"
OUT = ROOT / "outputs"

GW = 9.81
CR_HEALTHY = 3.0
RSAT = 200.0
WMAX = 0.85
SLOPE_MIN = 15.0

T_OFFICIAL = pd.Timestamp("2025-07-19 12:37")   # 산청군 공식 대피경보
T_REPORT = pd.Timestamp("2025-07-19 08:00")     # 최초 신고


def _read(path: Path) -> np.ndarray:
    with rasterio.open(path) as ds:
        return ds.read(1).astype("float32")


def fire_f(dnbr: np.ndarray) -> np.ndarray:
    """Key&Benson 2006 dNBR 등급 → 증폭계수 f. 16·18번과 동일한 문턱값."""
    f = np.ones_like(dnbr, dtype="float32")
    f[dnbr >= 0.10] = 1.2
    f[dnbr >= 0.27] = 2.0
    f[dnbr >= 0.44] = 3.75
    f[~np.isfinite(dnbr)] = 1.0
    return f


def load_valid() -> dict:
    """유효 픽셀(급사면)만 1-D로 뽑아 메모리를 줄인다. 47M → 유효분만."""
    slope = _read(ROOT / "data" / "dem" / "산청_slope_5m_5179.tif")
    z_full = _read(FOS / "z_m.tif")
    valid = np.isfinite(slope) & (slope >= SLOPE_MIN) & np.isfinite(z_full)

    out = {"n": int(valid.sum())}
    out["slope"] = slope[valid]
    out["z"] = z_full[valid]
    del slope, z_full

    for key, name in [("c", "c_kpa.tif"), ("phi", "phi_deg.tif"),
                      ("gam", "gamma.tif"), ("m0", "m0.tif"), ("dnbr", "dnbr.tif")]:
        arr = _read(FOS / name)
        out[key] = arr[valid]
        del arr
    return out


def margin_array(d: dict, *, cr_eff: np.ndarray, soil: str) -> np.ndarray:
    """rain_term이 이 값을 넘으면 그 픽셀은 FoS<1. (= m_crit − m0)

    m_crit > 1 인 픽셀은 완전포화로도 안 무너진다 → margin이 커져 자연히 제외된다.
    """
    beta = np.deg2rad(np.clip(d["slope"], 0.1, 89.0))
    cosb, sinb = np.cos(beta), np.sin(beta)
    z = d["z"]

    if soil == "A_soilmap":
        c, phi, gam = d["c"], np.deg2rad(d["phi"]), d["gam"]
    else:  # B_weathered — 풍화화강토(P3 부산 실측), 급사면 실제 파괴재료
        c = np.float32(2.0)
        phi = np.deg2rad(np.float32(36.0))
        gam = np.float32(19.0)

    tanphi = np.tan(phi)
    C = c + cr_eff
    A = gam * z * cosb ** 2 * tanphi
    B = GW * z * cosb ** 2 * tanphi
    D = gam * z * sinb * cosb

    with np.errstate(divide="ignore", invalid="ignore"):
        m_crit = (C + A - D) / B
    # B<=0(φ=0 등)이면 m으로 무너뜨릴 수 없음 → 도달불가로 밀어낸다
    m_crit = np.where(B > 0, m_crit, np.inf)
    return (m_crit - d["m0"]).astype("float32")


def scenarios_cr(d: dict) -> dict[str, np.ndarray]:
    """산불 처리별 Cr_eff 배열. 산불은 이 경로로만 모형에 들어온다."""
    dnbr = d["dnbr"]
    return {
        "fire_off":   np.full(d["n"], CR_HEALTHY, dtype="float32"),
        "observed":   CR_HEALTHY / fire_f(dnbr),
        "dnbr_m0.10": CR_HEALTHY / fire_f(dnbr - 0.10),
        "dnbr_p0.10": CR_HEALTHY / fire_f(dnbr + 0.10),
        "no_roots":   np.zeros(d["n"], dtype="float32"),
    }


def rain_series() -> pd.DataFrame:
    rain = pd.read_csv(ROOT / "data" / "kma" / "sancheong_asos_2025071819.csv",
                       parse_dates=["time_kst"]).sort_values("time_kst").reset_index(drop=True)
    rain["cum24"] = rain["rn_mm"].rolling(24, min_periods=1).sum()
    rain["rain_term"] = np.minimum(WMAX, rain["cum24"] / RSAT)
    return rain


# 절대 문턱(급사면 중 임계초과 비율, %). 시나리오 간 비교가 가능한 유일한 기준.
# 0.01은 보수적인 시나리오 A(peak<0.05%)도 비교 가능하게 하려고 넣었다.
ABS_THRESHOLDS = (0.01, 0.05, 0.10, 0.50)


def t_agent_relative(times: pd.Series, frac: np.ndarray) -> tuple[pd.Timestamp | None, float]:
    """16번 정의: 임계초과율이 '그날 최대'의 50%에 처음 도달한 시각.

    ⚠ 이 정의는 자기정규화라 위험도장을 통째로 몇 배 키우거나 줄여도 시각이
    변하지 않는다. 따라서 ablation(산불 제거) 효과를 구조적으로 못 잡는다 —
    비교에는 아래 t_agent_absolute를 써야 한다. 16번과의 연속성을 위해 남긴다.
    """
    peak = float(np.nanmax(frac)) if len(frac) else 0.0
    if peak <= 0:
        return None, 0.0
    idx = int(np.argmax(frac >= 0.5 * peak))
    return times.iloc[idx], peak


def t_agent_absolute(times: pd.Series, frac: np.ndarray,
                     thr: float) -> pd.Timestamp | None:
    """고정 문턱 thr(%)를 처음 넘은 시각. 모든 시나리오에 같은 자를 댄다."""
    hit = frac >= thr
    if not hit.any():
        return None
    return times.iloc[int(np.argmax(hit))]


def main() -> None:
    print("래스터 적재 중...")
    d = load_valid()
    print(f"산사태 가능사면(≥{SLOPE_MIN}°) 픽셀: {d['n']:,}")

    burned = np.isfinite(d["dnbr"]) & (d["dnbr"] >= 0.10)
    print(f"그중 산불영향(dNBR≥0.10): {int(burned.sum()):,} ({100*burned.mean():.2f}%)")

    rain = rain_series()
    cr_map = scenarios_cr(d)

    rows, series_out = [], {}
    for soil in ("A_soilmap", "B_weathered"):
        for name, cr in cr_map.items():
            margin = margin_array(d, cr_eff=cr, soil=soil)
            frac = np.array([100.0 * np.mean(margin < rt) for rt in rain["rain_term"]])
            series_out[f"{soil}|{name}"] = frac

            ta, peak = t_agent_relative(rain["time_kst"], frac)
            lead = None if ta is None else (T_OFFICIAL - ta).total_seconds() / 3600.0
            row = {
                "지반시나리오": soil,
                "산불처리": name,
                "peak_crit_%": round(peak, 4),
                "T_agent_rel50": None if ta is None else ta.strftime("%m-%d %H:%M"),
                "골든타임_rel50_h": None if lead is None else round(lead, 2),
            }
            abs_txt = []
            for thr in ABS_THRESHOLDS:
                tb = t_agent_absolute(rain["time_kst"], frac, thr)
                lb = None if tb is None else (T_OFFICIAL - tb).total_seconds() / 3600.0
                row[f"T_agent_abs{thr}"] = None if tb is None else tb.strftime("%m-%d %H:%M")
                row[f"골든타임_abs{thr}_h"] = None if lb is None else round(lb, 2)
                abs_txt.append(f"{thr}%:{'--' if lb is None else f'{lb:.2f}h'}")
            rows.append(row)
            print(f"  {soil:12s} {name:11s} peak={peak:7.4f}%  "
                  f"rel50={'--' if lead is None else f'{lead:.2f}h'}  "
                  f"abs[{' '.join(abs_txt)}]")

    abl = pd.DataFrame(rows)
    abl.to_csv(OUT / "sancheong_ablation_dnbr.csv", index=False, encoding="utf-8-sig")

    ts = pd.DataFrame({"time": rain["time_kst"], "rn_mm": rain["rn_mm"],
                       "cum24": rain["cum24"].round(1)})
    for k, v in series_out.items():
        ts[k] = np.round(v, 4)
    ts.to_csv(OUT / "sancheong_ablation_timeseries.csv", index=False, encoding="utf-8-sig")

    def _n(v):
        """pandas 왕복에서 None이 NaN이 된다. NaN은 유효 JSON이 아니라 되돌린다."""
        return None if v is None or (isinstance(v, float) and np.isnan(v)) else v

    # 산불 기여도 = observed 대비 fire_off의 손실분
    delta = {}
    for soil in ("A_soilmap", "B_weathered"):
        sub = abl[abl["지반시나리오"] == soil].set_index("산불처리")
        obs, off = sub.loc["observed"], sub.loc["fire_off"]
        delta[soil] = {
            "peak_observed_%": obs["peak_crit_%"],
            "peak_fire_off_%": off["peak_crit_%"],
            "peak_배수": (round(obs["peak_crit_%"] / off["peak_crit_%"], 2)
                        if off["peak_crit_%"] > 0 else None),
            "골든타임_rel50_h": {"observed": _n(obs["골든타임_rel50_h"]),
                              "fire_off": _n(off["골든타임_rel50_h"])},
            "골든타임_abs_h": {
                f"{thr}%": {
                    "observed": _n(obs[f"골든타임_abs{thr}_h"]),
                    "fire_off": _n(off[f"골든타임_abs{thr}_h"]),
                    "산불이_앞당긴_h": (
                        None if (_n(obs[f"골든타임_abs{thr}_h"]) is None
                                 or _n(off[f"골든타임_abs{thr}_h"]) is None)
                        else round(obs[f"골든타임_abs{thr}_h"]
                                   - off[f"골든타임_abs{thr}_h"], 2)),
                    "산불없으면_미도달": _n(off[f"골든타임_abs{thr}_h"]) is None
                                   and _n(obs[f"골든타임_abs{thr}_h"]) is not None,
                } for thr in ABS_THRESHOLDS
            },
            "dNBR±0.10_peak_%": [sub.loc["dnbr_m0.10", "peak_crit_%"],
                                 sub.loc["dnbr_p0.10", "peak_crit_%"]],
            "no_roots_상한_peak_%": sub.loc["no_roots", "peak_crit_%"],
        }

    meta = {
        "item": "bt-abl",
        "생성": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"),
        "정의": {
            "T_agent_rel50": "임계초과율이 당일 최대의 50%에 처음 도달한 시각(16번과 동일)",
            "T_agent_abs": f"임계초과율이 고정 문턱{list(ABS_THRESHOLDS)}%를 처음 넘은 시각",
            "골든타임_h": "공식경보 2025-07-19 12:37 − T_agent",
            "임계초과": "FoS<1, 급사면(≥15°) 픽셀 기준",
        },
        "방법론_주의": "rel50은 자기정규화 지표라 위험도장의 스케일 변화에 불변이다. "
                  "즉 산불 제거(fire_off)에도 T_agent가 그대로 나온다 — ablation "
                  "비교에는 abs 문턱만 유효하다. 이 사실 자체가 이 실험의 산출물이다.",
        "유효픽셀": d["n"],
        "산불영향픽셀": int(burned.sum()),
        "산불기여도": delta,
        "미보정_파라미터": ["Rsat=200mm", "Wmax=0.85", "sigmoid k=6.0"],
        "한계": "dNBR 등급 문턱(0.10/0.27/0.44)은 Key&Benson 2006 고정값이며 "
              "산청 현지 보정값이 아니다. ±0.10은 산출 불확실성 대리이지 실측 오차범위가 아니다.",
    }
    (OUT / "sancheong_ablation_summary.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n=== 산불 기여도 (observed vs fire_off) ===")
    print(json.dumps(delta, ensure_ascii=False, indent=2))
    print(f"\n저장: {OUT/'sancheong_ablation_dnbr.csv'}")
    print(f"      {OUT/'sancheong_ablation_timeseries.csv'}")
    print(f"      {OUT/'sancheong_ablation_summary.json'}")


if __name__ == "__main__":
    main()
