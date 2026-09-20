"""
41_backtest_metrics.py  (bt-metric: decision_latency + hazard_lead 확정)

두 리드타임은 '무엇보다 빠른가'가 달라서 절대 섞으면 안 된다.

  decision_latency = T_official − T_agent     공식 대피경보(12:37)보다 얼마나 빠른가
  hazard_lead      = T_event    − T_agent     실제 붕괴보다 얼마나 빠른가  ← 진짜 골든타임

T_event(실제 붕괴 시각)는 확보되지 않았다. 산림청 피해기록 362건에는 일시 필드가
없고(리 단위 집계), 발생부 좌표도 없다(outputs/산림청_발생부좌표_요청서.md로 요청 중).
그래서 hazard_lead를 점추정으로 내지 않고 **상한으로 묶는다**:

  최초 신고가 07-19 08:00에 있었다 → 적어도 한 건은 08:00 이전에 이미 발생했다
  → T_event_first ≤ 08:00
  → hazard_lead = T_event_first − T_agent ≤ 08:00 − T_agent   (상한)

이 상한이 음수면 "모형 신호가 첫 신고보다 늦었다"가 확정된다(상한조차 음수이므로).
양수면 "최대 그만큼 빨랐을 수 있다"이지 그만큼 빨랐다는 뜻이 아니다.

입력: 39번이 저장한 outputs/sancheong_ablation_timeseries.csv (재계산 없음)
"""
from __future__ import annotations

import json
import sys
import warnings

warnings.filterwarnings("ignore")
from pathlib import Path

import numpy as np
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(r"G:/연구/공모전/아쿠아가드")
OUT = ROOT / "outputs"

T_OFFICIAL = pd.Timestamp("2025-07-19 12:37")    # 산청군 공식 대피경보
T_FIRST_REPORT = pd.Timestamp("2025-07-19 08:00")  # 최초 신고 → T_event 상한
ABS_THRESHOLDS = (0.01, 0.05, 0.10, 0.50)


def first_cross(times: pd.Series, frac: np.ndarray, thr: float) -> pd.Timestamp | None:
    hit = frac >= thr
    return None if not hit.any() else times.iloc[int(np.argmax(hit))]


def stability(frac: np.ndarray, thr: float, i0: int) -> float:
    """T_agent 이후 문턱 위에 머무는 비율. 낮으면 깜빡이는 경보라 실무에 못 쓴다."""
    tail = frac[i0:]
    return float(np.mean(tail >= thr)) if len(tail) else 0.0


def main() -> None:
    ts = pd.read_csv(OUT / "sancheong_ablation_timeseries.csv", parse_dates=["time"])
    times = ts["time"]
    scen_cols = [c for c in ts.columns if "|" in c]
    t0 = times.iloc[0]

    rows = []
    for col in scen_cols:
        soil, fire = col.split("|")
        frac = ts[col].to_numpy(float)
        for thr in ABS_THRESHOLDS:
            ta = first_cross(times, frac, thr)
            if ta is None:
                rows.append({"지반시나리오": soil, "산불처리": fire, "문턱_%": thr,
                             "T_agent": None, "decision_latency_h": None,
                             "hazard_lead_상한_h": None, "경보지속률": None,
                             "판정": "미도달"})
                continue

            i0 = int(times[times == ta].index[0])
            dec = (T_OFFICIAL - ta).total_seconds() / 3600.0
            haz = (T_FIRST_REPORT - ta).total_seconds() / 3600.0
            degenerate = ta == t0   # 시작부터 켜져 있으면 '예측'이 아니라 상시경보
            rows.append({
                "지반시나리오": soil, "산불처리": fire, "문턱_%": thr,
                "T_agent": ta.strftime("%m-%d %H:%M"),
                "decision_latency_h": round(dec, 2),
                "hazard_lead_상한_h": round(haz, 2),
                "경보지속률": round(stability(frac, thr, i0), 3),
                "판정": ("상시경보(시계열 시작부터 초과 — 리드타임 무의미)" if degenerate
                       else "첫신고보다 빠름" if haz > 0 else "첫신고보다 늦음"),
            })

    df = pd.DataFrame(rows)
    df.to_csv(OUT / "backtest_leadtime_metrics.csv", index=False, encoding="utf-8-sig")

    print("=== 리드타임 지표 (B_weathered, 기준선 observed) ===")
    view = df[(df["지반시나리오"] == "B_weathered") & (df["산불처리"] == "observed")]
    print(view.to_string(index=False))

    print("\n=== 16번 정의(rel50, T_agent=07-19 09:00) 재평가 ===")
    ta_rel = pd.Timestamp("2025-07-19 09:00")
    dec_rel = (T_OFFICIAL - ta_rel).total_seconds() / 3600.0
    haz_rel = (T_FIRST_REPORT - ta_rel).total_seconds() / 3600.0
    print(f"  decision_latency = {dec_rel:+.2f} h  (공식경보 12:37 대비)")
    print(f"  hazard_lead 상한 = {haz_rel:+.2f} h  (최초신고 08:00 대비)")
    print("  → 공식경보보다는 3.6h 빨랐지만, 최초 신고보다는 1h 늦었다.")

    # 유효한 조합: 상시경보가 아니고, 첫 신고보다 빠르며, 경보가 안정적인 것
    ok = df[(df["hazard_lead_상한_h"].notna())
            & (df["hazard_lead_상한_h"] > 0)
            & (~df["판정"].astype(str).str.startswith("상시경보"))
            & (df["경보지속률"] >= 0.8)]
    print(f"\n=== 첫신고를 앞서면서 안정적인(지속률≥0.8) 조합: {len(ok)}개 ===")
    if len(ok):
        print(ok.sort_values("hazard_lead_상한_h", ascending=False).to_string(index=False))

    summary = {
        "item": "bt-metric",
        "생성": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"),
        "기준시각": {
            "T_official_공식경보": str(T_OFFICIAL),
            "T_first_report_최초신고": str(T_FIRST_REPORT),
            "T_event_실제붕괴": None,
        },
        "T_event_미확보": {
            "사유": "피해기록 362건에 발생일시 필드 없음(리 단위 집계), 발생부 좌표도 없음",
            "조치": "산림청·국립산림과학원에 발생부 좌표+일시 요청 "
                  "(outputs/산림청_발생부좌표_요청서.md)",
            "대안": "최초 신고 08:00을 T_event 상한으로 삼아 hazard_lead를 상한으로만 보고",
        },
        "rel50_정의_재평가": {
            "T_agent": "2025-07-19 09:00",
            "decision_latency_h": round(dec_rel, 2),
            "hazard_lead_상한_h": round(haz_rel, 2),
            "해석": "공식경보 대비 +3.62h이지만 최초신고 대비 −1.00h. "
                  "'경보보다 3.6시간 빠른 신호'는 맞고 '붕괴보다 3.6시간 빠른 신호'는 틀리다. "
                  "발표에서 이 둘을 섞어 쓰면 안 된다.",
        },
        "유효조합수": int(len(ok)),
        "최대_hazard_lead_상한_h": (None if not len(ok)
                                else float(ok["hazard_lead_상한_h"].max())),
        "한계": [
            "hazard_lead는 상한이다 — 실제 값은 이보다 작거나 같다.",
            "절대문턱(0.01~0.5%)은 운영 경보기준이 아니라 비교용 임의 문턱이다.",
            "Rsat=200mm·Wmax=0.85·sigmoid k=6.0은 여전히 미보정.",
            "오경보율(FAR)은 단일 이벤트라 산정 불가 — 다중 이벤트 확보 시 추가.",
        ],
    }
    (OUT / "backtest_leadtime_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n저장: {OUT/'backtest_leadtime_metrics.csv'}")
    print(f"      {OUT/'backtest_leadtime_summary.json'}")


if __name__ == "__main__":
    main()
