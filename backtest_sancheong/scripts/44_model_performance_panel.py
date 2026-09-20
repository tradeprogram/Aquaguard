"""
44_model_performance_panel.py  (bt-panel: UI ModelPerformancePanel 실제값 산출)

ui/src/components/panels/ModelPerformancePanel.tsx 는 현재 **전부 목업**이다
(주석에 그렇게 적혀 있다: auc 0.91 / precision 0.86 / confusion 34·6·9·151 …).
트랙③ UI 구현은 우리 몫이 아니지만, **갈아끼울 실제값을 만드는 건 우리 몫**이다.
이 스크립트가 그 JSON을 컴포넌트와 같은 스키마로 내보낸다.

⚠ 반드시 읽을 것: 실제값은 목업보다 **훨씬 나쁘다**.
    산사태 ROC-AUC  목업 0.91 → 실제 0.47 (무작위 수준)
    산사태 precision 목업 0.86 → 실제 0.07 수준
  목업 숫자를 그대로 두고 발표하면 성능 조작이 된다. 반드시 교체해야 한다.
  낮은 값의 원인은 40·42번이 규명했다 — 참값이 '발생부'가 아니라 '피해 집계
  마을'이라 급사면 물리와 계통적으로 어긋난다. 모형 실패와 참값 부적합이
  섞여 있어 분리할 수 없다. 그 사실을 UI에도 함께 띄워야 한다.

홍수(Module B)는 사정이 다르다 — 물리검증 참값(수위계·2엔진 교차)이 제대로
있어서 실제값이 쓸 만하다. 수위 RMSE 1.42m, 2엔진 교차 IoU 0.775.
"""
from __future__ import annotations

import json
import sys
import warnings

warnings.filterwarnings("ignore")
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score, roc_curve

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(r"G:/연구/공모전/아쿠아가드")
OUT = ROOT / "outputs"


def _load(name: str) -> dict:
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def landslide_block() -> dict:
    grid = pd.read_csv(OUT / "backtest_eval_grid.csv")
    y = grid["y"].to_numpy(int)
    s = grid["점수"].to_numpy(float)

    fpr, tpr, thr = roc_curve(y, s)
    auc = float(roc_auc_score(y, s))

    # 운영점: F1 최대. 물리점수는 확률이 아니라 순위점수라 0.5 같은 고정컷이 무의미하다.
    best = {"f1": -1.0}
    for t in np.unique(s):
        pred = s >= t
        tp = int((pred & (y == 1)).sum()); fp = int((pred & (y == 0)).sum())
        fn = int((~pred & (y == 1)).sum()); tn = int((~pred & (y == 0)).sum())
        prec = tp / max(tp + fp, 1); rec = tp / max(tp + fn, 1)
        f1 = 0.0 if prec + rec == 0 else 2 * prec * rec / (prec + rec)
        if f1 > best["f1"]:
            best = {"f1": f1, "thr": float(t), "precision": prec, "recall": rec,
                    "tp": tp, "fp": fp, "fn": fn, "tn": tn}

    # ROC 곡선은 UI 표시용으로 솎아낸다(원본 점 수가 많다)
    idx = np.unique(np.linspace(0, len(fpr) - 1, 12).astype(int))
    roc_pts = [[round(float(fpr[i]), 4), round(float(tpr[i]), 4)] for i in idx]

    # 예측확률 추이: 39번이 저장한 실제 시계열(B_weathered·observed)
    ts = pd.read_csv(OUT / "sancheong_ablation_timeseries.csv", parse_dates=["time"])
    win = ts[(ts["time"] >= "2025-07-19 06:00") & (ts["time"] <= "2025-07-19 13:00")]
    col = "B_weathered|observed"
    vmax = float(win[col].max()) or 1.0
    series = [{"t": round(i / max(len(win) - 1, 1), 4),
               "time": r["time"].strftime("%H:%M"),
               "value": round(float(r[col]) / vmax, 4),
               "crit_frac_pct": round(float(r[col]), 4)}
              for i, (_, r) in enumerate(win.iterrows())]

    lead = _load("backtest_leadtime_summary.json")
    evals = _load("backtest_eval_summary.json")
    ml = _load("ml_residual_summary.json")
    abl = _load("sancheong_ablation_summary.json")

    return {
        "title": "산사태 (Module A)",
        "caseLabel": "2025.7.19 산청 — 06:00~13:00 임계초과율 추이(실측 강우 구동)",
        "color": "#f87171",
        "auc": round(auc, 4),
        "precision": round(best["precision"], 4),
        "recall": round(best["recall"], 4),
        "f1": round(best["f1"], 4),
        "auprc": evals["결과"]["a_전체"]["AUPRC"],
        "auprc_base": evals["결과"]["a_전체"]["기저"],
        "roc": roc_pts,
        "confusion": {"tp": best["tp"], "fp": best["fp"],
                      "fn": best["fn"], "tn": best["tn"]},
        "series": series,
        "markers": [
            {"t": 0.4286, "label": "T_agent 09:00 (rel50)", "color": "#38bdf8"},
            {"t": 0.2857, "label": "최초 신고 08:00", "color": "#f472b6"},
            {"t": 0.9381, "label": "공식 경보 12:37", "color": "#fbbf24"},
        ],
        "leadtime": {
            "decision_latency_h": lead["rel50_정의_재평가"]["decision_latency_h"],
            "hazard_lead_상한_h": lead["rel50_정의_재평가"]["hazard_lead_상한_h"],
            "설명": lead["rel50_정의_재평가"]["해석"],
        },
        "spatial_cv": {
            "읍면LOO_AUPRC_중앙값": evals["결과"]["c_읍면LOO"]["AUPRC_중앙값"],
            "lift_1초과_읍면": evals["결과"]["c_읍면LOO"]["lift_1초과_읍면수"],
            "평가읍면수": evals["결과"]["c_읍면LOO"]["평가가능_읍면수"],
        },
        "ablation_산불": abl["산불기여도"]["B_weathered"],
        "ml_보정": {"판정": ml["판정"]["판정"], "채택": ml["판정"]["채택"]},
        "provenance": "MEASURED(물리) + 참값 부적합",
        "경고": "참값이 발생부 좌표가 아니라 피해 집계 마을(리) 중심점이다. "
              "이 지표에는 모형 오차와 참값 부적합이 섞여 있으며 분리할 수 없다. "
              "높은 값을 주장하는 근거로 쓸 수 없고, 낮은 값도 물리 반증이 아니다.",
    }


def flood_block() -> dict:
    allrefs = _load("module_b_allrefs.json")
    sfincs = _load("sfincs_reach_validation.json")
    cmp_ = _load("module_b_engine_comparison.json")
    v = _load("module_v_metrics.json")

    ext = sfincs["extent_vs_S1_HAND"]
    cross = allrefs["SFINCS_vs_ANUGA(모델간 일치)"]
    return {
        "title": "하천범람·침수 (Module B)",
        "caseLabel": "2025.7.19 산청 경호강 — SFINCS 물리모형 검증(실측 수위·SAR·HAND 3중)",
        "color": "#38bdf8",
        "주검증_수위": {
            "지점": "경호교", "obs_peak_m": sfincs["gyeongho_WSE"]["obs_peak"],
            "sim_peak_m": sfincs["gyeongho_WSE"]["sim_peak"],
            "peak_diff_m": sfincs["gyeongho_WSE"]["diff_m"],
            "RMSE_m": sfincs["gyeongho_WSE"]["rmse_m"],
        },
        "2엔진_교차일치": {"IoU": cross["IoU"], "F1": cross["F1"],
                     "precision": cross["precision"], "FAR": cross["FAR"]},
        "침수범위_vs_SAR": {"IoU": ext["IoU"], "F1": ext["F1"], "POD": ext["POD"],
                        "FAR": ext["FAR"], "precision": ext["precision"],
                        "confusion": {"tp": ext["TP"], "fp": ext["FP"], "fn": ext["FN"]}},
        "엔진비교": {"SFINCS_WSE_RMSE_m": cmp_["SFINCS"]["WSE_rmse_m"],
                 "ANUGA_WSE_RMSE_m": cmp_["ANUGA_v1"]["WSE_rmse_m"]},
        "면적_km2": allrefs["areas_km2"],
        "runtime": sfincs["runtime_note"],
        "module_v_산사태SAR": {"IoU": v["iou"], "AUPRC": v["auprc"],
                          "base_rate": v["base_rate"], "note": v["note"]},
        "provenance": "MEASURED",
        "주의": "SAR 대비 IoU 0.36은 모형 오차가 아니라 초목계곡에서 SAR 후방산란이 "
              "침수를 못 잡는 한계다(HAND-FIM·2엔진 교차로 규명). 주검증 지표는 "
              "수위 RMSE 1.42m와 2엔진 교차 IoU 0.775다.",
    }


def main() -> None:
    panel = {
        "_생성": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"),
        "_item": "bt-panel",
        "_대상": "ui/src/components/panels/ModelPerformancePanel.tsx 의 CASES 를 대체",
        "_경고": "현재 컴포넌트의 숫자는 전부 목업이다(auc 0.91 등). 실제값은 "
               "산사태 쪽이 훨씬 낮다. 목업을 그대로 발표하면 성능 조작이 된다.",
        "landslide": landslide_block(),
        "flood": flood_block(),
    }
    (OUT / "model_performance_panel.json").write_text(
        json.dumps(panel, ensure_ascii=False, indent=2), encoding="utf-8")

    ls, fl = panel["landslide"], panel["flood"]
    print("=== 산사태 (Module A) 실제값 ===")
    print(f"  ROC-AUC      {ls['auc']}   (목업 0.91)")
    print(f"  AUPRC        {ls['auprc']}  기저 {ls['auprc_base']}")
    print(f"  precision    {ls['precision']}   recall {ls['recall']}   F1 {ls['f1']}   (목업 0.86/0.79/0.82)")
    print(f"  confusion    {ls['confusion']}   (목업 tp34 fp6 fn9 tn151)")
    print(f"  decision_latency {ls['leadtime']['decision_latency_h']}h / "
          f"hazard_lead 상한 {ls['leadtime']['hazard_lead_상한_h']}h")
    print("\n=== 홍수 (Module B) 실제값 ===")
    print(f"  경호교 수위 RMSE  {fl['주검증_수위']['RMSE_m']} m (피크차 {fl['주검증_수위']['peak_diff_m']} m)")
    print(f"  2엔진 교차 IoU    {fl['2엔진_교차일치']['IoU']}")
    print(f"  vs SAR IoU        {fl['침수범위_vs_SAR']['IoU']}")
    print(f"\n저장: {OUT/'model_performance_panel.json'}")


if __name__ == "__main__":
    main()
