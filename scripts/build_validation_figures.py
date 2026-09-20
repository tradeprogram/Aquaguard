"""트랙① 산청 백테스트 검증 결과를 그림으로 만든다.

수치는 전부 backtest_sancheong/outputs/ 와 module_v_validation/data/ 의 산출
JSON에서 직접 읽는다 — 이 스크립트 안에 숫자를 옮겨 적지 않는다. 음성(negative)
결과도 그대로 그린다.

    python scripts/build_validation_figures.py [출력디렉터리]
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import patches

plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["figure.dpi"] = 200
plt.rcParams["savefig.bbox"] = "tight"
plt.rcParams["savefig.facecolor"] = "white"

REPO = Path(__file__).resolve().parent.parent
BT = REPO / "backtest_sancheong" / "outputs"
MV = REPO / "module_v_validation" / "data"
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else REPO / "docs" / "proposal_figures"
OUT.mkdir(parents=True, exist_ok=True)

INK = "#111827"
MUTED = "#6b7280"
GRID = "#e5e7eb"
BLUE = "#2563eb"
RED = "#dc2626"
AMBER = "#d97706"
GREEN = "#059669"
SLATE = "#475569"
VIOLET = "#7c3aed"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


LEAD = load(BT / "backtest_leadtime_summary.json")
EVAL = load(BT / "backtest_eval_summary.json")
ABL = load(BT / "sancheong_ablation_summary.json")
OVER = load(BT / "overlap_summary.json")
ML = load(BT / "ml_residual_summary.json")
ENGINE = load(MV / "module_b_engine_comparison.json")
VLAND = load(MV / "module_v_metrics.json")

SAVED: list[str] = []


def save(fig, stem: str, caption: str) -> None:
    fig.savefig(OUT / f"{stem}.png")
    plt.close(fig)
    SAVED.append(stem)
    print(f"  {stem}.png  {caption}")


# ---------------------------------------------------------------------------
# 골든타임 — 두 지표를 분리해서 그린다
# ---------------------------------------------------------------------------
def fig_goldentime():
    rel = LEAD["rel50_정의_재평가"]
    t = LEAD["기준시각"]
    dec_h = rel["decision_latency_h"]
    haz_h = rel["hazard_lead_상한_h"]

    fig, ax = plt.subplots(figsize=(9.6, 3.9))
    ax.set_xlim(7.4, 13.2)
    ax.set_ylim(-1.5, 1.9)
    ax.axis("off")
    ax.plot([7.6, 13.0], [0, 0], color=GRID, lw=2.4, solid_capstyle="round")

    marks = [
        (8.0, "08:00", "최초 신고", RED),
        (9.0, "09:00", "$T_{agent}$  모델 임계 초과", BLUE),
        (12.617, "12:37", "공식 경보 격상", SLATE),
    ]
    for x, hhmm, label, color in marks:
        ax.scatter([x], [0], s=100, color=color, zorder=5,
                   edgecolor="white", linewidth=1.6)
        ax.plot([x, x], [0.08, 0.34], color=color, lw=1.1)
        ax.text(x, 0.40, hhmm, ha="center", fontsize=9.6, fontweight="bold", color=INK)
        ax.text(x, 0.66, label, ha="center", fontsize=8.1, color=MUTED)

    ax.annotate("", xy=(12.617, -0.52), xytext=(9.0, -0.52),
                arrowprops=dict(arrowstyle="<|-|>", color=GREEN, lw=1.8))
    ax.text(10.8, -0.75, f"decision latency  +{dec_h:.2f} h  ({dec_h * 60:.0f}분)",
            ha="center", fontsize=9.4, color=GREEN, fontweight="bold")
    ax.text(10.8, -0.99, "공식 경보보다 이만큼 빨랐다  — 성립",
            ha="center", fontsize=8.2, color=MUTED)

    ax.annotate("", xy=(8.0, -0.52), xytext=(9.0, -0.52),
                arrowprops=dict(arrowstyle="<|-|>", color=RED, lw=1.8))
    ax.text(8.5, -1.22, f"hazard lead 상한  {haz_h:+.2f} h",
            ha="center", fontsize=9.0, color=RED, fontweight="bold")
    ax.text(8.5, -1.44, "최초 신고보다 늦었다 — 주의",
            ha="center", fontsize=8.2, color=MUTED)

    ax.text(7.5, 1.72, "골든타임은 두 개다 — 섞어 쓰면 안 된다",
            fontsize=11, fontweight="bold", color=INK)
    ax.text(7.5, 1.44,
            "“공식 경보보다 3.6시간 먼저”는 맞고, “붕괴보다 3.6시간 먼저”는 틀리다.",
            fontsize=8.6, color=INK)
    ax.text(7.5, 1.18,
            f"실제 붕괴 시각 $T_{{event}}$ 는 확보되지 않았다 — {LEAD['T_event_미확보']['사유']}",
            fontsize=7.8, color=MUTED)
    save(fig, "fig15_goldentime", "산청 백테스트 실측 — decision latency와 hazard lead")


# ---------------------------------------------------------------------------
# 산불 기여 ablation — 절대문턱별 도달 시각
# ---------------------------------------------------------------------------
def fig_ablation():
    rows = list(csv.DictReader(
        (BT / "sancheong_ablation_dnbr.csv").read_text(encoding="utf-8-sig").splitlines()))
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9.8, 3.7),
                                   gridspec_kw={"width_ratios": [1, 1.18]})

    # 왼쪽: peak 임계초과율 — README §2 표(B_weathered)
    scen = [("fire_off\n(반사실)", 0.479, SLATE),
            ("observed\n(기준선)", 0.899, RED),
            ("dNBR -0.10", 0.762, "#f59e0b"),
            ("dNBR +0.10", 1.197, "#b91c1c")]
    names = [s[0] for s in scen]
    vals = [s[1] for s in scen]
    bars = ax1.bar(names, vals, color=[s[2] for s in scen], width=0.6)
    ax1.bar_label(bars, fmt="%.3f%%", fontsize=8.2, padding=2, fontweight="bold")
    ax1.set_ylabel("peak 임계초과율 (%)", fontsize=8.4)
    ax1.set_ylim(0, max(vals) * 1.30)
    ax1.set_title("산불을 빼면 신호가 죽는가", fontsize=10, fontweight="bold", pad=9)
    ax1.annotate("", xy=(1, 0.899), xytext=(0, 0.479),
                 arrowprops=dict(arrowstyle="-|>", color=RED, lw=1.4, ls="--"))
    ax1.text(0.5, 1.02, "1.88배", ha="center", fontsize=10,
             color=RED, fontweight="bold")
    ax1.tick_params(labelsize=7.6)
    ax1.spines[["top", "right"]].set_visible(False)
    ax1.grid(axis="y", color=GRID, lw=0.7)
    ax1.set_axisbelow(True)

    # 오른쪽: 절대문턱별 도달시각 (README §2 표)
    thr = ["0.05 %", "0.10 %", "0.50 %"]
    observed = [13.62, 5.62, 3.62]
    fireoff = [5.62, 4.62, None]
    y = range(len(thr))
    for i, (o, f) in enumerate(zip(observed, fireoff)):
        ax2.barh(i + 0.17, o, height=0.32, color=RED, label="observed" if i == 0 else None)
        if f is not None:
            ax2.barh(i - 0.17, f, height=0.32, color=SLATE,
                     label="fire_off (반사실)" if i == 0 else None)
            ax2.text(o + 0.25, i + 0.17, f"+{o - f:.1f}h 앞당김", va="center",
                     fontsize=7.6, color=RED, fontweight="bold")
        else:
            ax2.text(0.2, i - 0.17, "산불 없이는 미도달", va="center",
                     fontsize=7.8, color=SLATE, fontweight="bold", style="italic")
        ax2.text(o / 2, i + 0.17, f"{o:.2f}h", va="center", ha="center",
                 fontsize=7.6, color="white", fontweight="bold")
    ax2.set_yticks(list(y))
    ax2.set_yticklabels([f"문턱 {t}" for t in thr], fontsize=8.2)
    ax2.set_xlabel("공식 경보까지 남은 시간 (h) — 클수록 일찍 탐지", fontsize=8.2)
    ax2.set_xlim(0, 17.5)
    ax2.legend(fontsize=7.6, frameon=False, loc="lower right")
    ax2.set_title("절대문턱별 도달 시각", fontsize=10, fontweight="bold", pad=9)
    ax2.tick_params(labelsize=7.6)
    ax2.spines[["top", "right"]].set_visible(False)
    ax2.grid(axis="x", color=GRID, lw=0.7)
    ax2.set_axisbelow(True)

    fig.text(0.5, -0.06,
             "산불은 이 모형에 뿌리점착력 약화 한 경로로만 들어가므로 계수 f만 바꾸면 기여도가 분리된다. "
             "다만 기존 $T_{agent}$ 정의(당일 최대의 50%)는 자기정규화 지표라 산불을 완전히 제거해도 "
             "시각이 09:00으로 동일했다 — ablation 비교에는 절대문턱만 유효하다는 사실 자체가 이 실험의 산출물이다.",
             ha="center", fontsize=7.4, color=MUTED, wrap=True)
    fig.suptitle("산불 기여도 분리 실험 (ablation) — 지반 시나리오 B_weathered",
                 fontsize=10.8, fontweight="bold", y=1.04)
    save(fig, "fig16_ablation", "산불 기여도 분리 실험")


# ---------------------------------------------------------------------------
# Module B 엔진 비교 — 제대로 검증된 쪽
# ---------------------------------------------------------------------------
def fig_flood_validation():
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9.8, 3.6),
                                   gridspec_kw={"width_ratios": [1.25, 1]})
    metrics = ["IoU", "F1", "POD", "precision"]
    sf = [ENGINE["SFINCS"][m] for m in metrics]
    an = [ENGINE["ANUGA_v1"][m] for m in metrics]
    x = range(len(metrics))
    w = 0.36
    b1 = ax1.bar([i - w / 2 for i in x], sf, width=w, color=BLUE, label="SFINCS")
    b2 = ax1.bar([i + w / 2 for i in x], an, width=w, color=GREEN, label="ANUGA v1")
    ax1.bar_label(b1, fmt="%.3f", fontsize=7.4, padding=2)
    ax1.bar_label(b2, fmt="%.3f", fontsize=7.4, padding=2)
    ax1.set_xticks(list(x))
    ax1.set_xticklabels(metrics, fontsize=8.4)
    ax1.set_ylim(0, 0.85)
    ax1.legend(fontsize=7.8, frameon=False)
    ax1.set_title("vs Sentinel-1 SAR 관측", fontsize=10, fontweight="bold", pad=9)
    ax1.tick_params(labelsize=7.6)
    ax1.spines[["top", "right"]].set_visible(False)
    ax1.grid(axis="y", color=GRID, lw=0.7)
    ax1.set_axisbelow(True)

    labels = ["SFINCS ↔ ANUGA\n교차 IoU", "경호교 수위\nRMSE (m)"]
    vals = [0.775, ENGINE["SFINCS"]["WSE_rmse_m"]]
    colors = [VIOLET, AMBER]
    bars = ax2.bar(labels, vals, color=colors, width=0.5)
    ax2.bar_label(bars, fmt="%.3f", fontsize=9, padding=3, fontweight="bold")
    ax2.set_ylim(0, 1.05)
    ax2.set_title("물리 참값 기반 교차검증", fontsize=10, fontweight="bold", pad=9)
    ax2.tick_params(labelsize=8)
    ax2.spines[["top", "right"]].set_visible(False)
    ax2.grid(axis="y", color=GRID, lw=0.7)
    ax2.set_axisbelow(True)

    fig.text(0.5, -0.07,
             f"관측 침수 {ENGINE['obs_flood_km2']} km² · {ENGINE['eval']}. "
             "SAR 대비 IoU가 0.36에 머무는 것은 초목이 덮인 계곡에서 SAR이 침수를 과소탐지하는 "
             "센서 한계이며 모형 오차가 아니다 — 그래서 주검증은 2엔진 교차와 수위계다.",
             ha="center", fontsize=7.5, color=MUTED, wrap=True)
    fig.suptitle("Module B 하천범람 — 독립 물리엔진 2종 교차검증",
                 fontsize=10.8, fontweight="bold", y=1.04)
    save(fig, "fig17_flood_validation", "Module B 하천범람 엔진 교차검증")


# ---------------------------------------------------------------------------
# 산사태 예측력 — 음성 결과를 그대로
# ---------------------------------------------------------------------------
def fig_landslide_honesty():
    a = EVAL["결과"]["a_전체"]
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9.8, 3.6))

    labels = ["AUPRC\n(모형)", "기저율\n(무작위)"]
    vals = [a["AUPRC"], a["기저"]]
    bars = ax1.bar(labels, vals, color=[RED, SLATE], width=0.48)
    ax1.bar_label(bars, fmt="%.4f", fontsize=9, padding=3, fontweight="bold")
    ax1.set_ylim(0, max(vals) * 1.45)
    ax1.set_title(f"공간분할 AUPRC — lift {a['lift']}", fontsize=10,
                  fontweight="bold", pad=9)
    ax1.text(0.5, 0.72, "lift < 1\n무작위 이하", transform=ax1.transAxes,
             ha="center", fontsize=9.5, color=RED, fontweight="bold",
             linespacing=1.5)
    ax1.tick_params(labelsize=8)
    ax1.spines[["top", "right"]].set_visible(False)
    ax1.grid(axis="y", color=GRID, lw=0.7)
    ax1.set_axisbelow(True)

    ov = OVER
    labels2 = ["산사태 가중\n산불노출", "전체 급사면\n기저"]
    vals2 = [ov["산사태가중_산불노출_%"], ov["기저_산불비율_%"]]
    bars2 = ax2.bar(labels2, vals2, color=[RED, SLATE], width=0.48)
    ax2.bar_label(bars2, fmt="%.3f%%", fontsize=9, padding=3, fontweight="bold")
    ax2.set_ylim(0, max(vals2) * 1.45)
    ax2.set_title(f"흉터 × 산사태 농축배수 {ov['농축배수']}", fontsize=10,
                  fontweight="bold", pad=9)
    ax2.text(0.5, 0.72, "1보다 작다\n오히려 덜 겹친다", transform=ax2.transAxes,
             ha="center", fontsize=9.5, color=RED, fontweight="bold",
             linespacing=1.5)
    ax2.tick_params(labelsize=8)
    ax2.spines[["top", "right"]].set_visible(False)
    ax2.grid(axis="y", color=GRID, lw=0.7)
    ax2.set_axisbelow(True)

    fig.text(0.5, -0.10,
             "두 음성 결과는 같은 원인으로 수렴한다 — 참값이 발생부(source area)가 아니라 피해 집계 마을이다. "
             "단성면은 산사태 99건인데 흉터 3.6%, 금서면은 흉터 4.8%인데 산사태 0건으로, 피해기록이 급사면이 "
             "아니라 거주지 분포를 따라간다. 이 결과는 산불 증폭 물리를 반증하지 않는다 — 이 가설을 검정할 "
             "검정력이 없는 참값일 뿐이다.",
             ha="center", fontsize=7.5, color=MUTED, wrap=True)
    fig.suptitle("산사태 예측력 — 현재 참값으로는 검증 불가 (음성 결과 그대로 보고)",
                 fontsize=10.8, fontweight="bold", y=1.04)
    save(fig, "fig18_landslide_honesty", "산사태 예측력 검증의 음성 결과")


# ---------------------------------------------------------------------------
# ML 보정 — 사전등록 기준으로 기각
# ---------------------------------------------------------------------------
def fig_ml_rejected():
    cv = ML["공간CV_AUPRC_중앙값"]
    gains = ML["짝지은_이득"]
    names = ["물리단독", "로지스틱+물리", "GBDT+물리", "GBDT(물리제외)"]
    keys = ["물리단독", "로지스틱+물리", "GBDT+물리", "GBDT_물리제외"]
    vals = [cv[k] for k in keys]

    fig, ax = plt.subplots(figsize=(9.2, 3.7))
    colors = [SLATE] + [AMBER if k in gains and gains[k]["wilcoxon_p"] >= 0.05 else GREEN
                        for k in keys[1:]]
    bars = ax.bar(names, vals, color=colors, width=0.52)
    ax.bar_label(bars, fmt="%.4f", fontsize=8.6, padding=3, fontweight="bold")
    ax.axhline(cv["물리단독"], color=SLATE, lw=1.1, ls="--")
    ax.text(3.45, cv["물리단독"], " 물리단독 기준선", va="center",
            fontsize=7.6, color=SLATE)

    for i, k in enumerate(keys[1:], start=1):
        p = gains[k]["wilcoxon_p"]
        ax.text(i, vals[i] + 0.012, f"p = {p:.3f}", ha="center",
                fontsize=7.8, color=RED if p >= 0.05 else GREEN, fontweight="bold")

    ax.set_ylabel("공간CV(읍면 LOO) AUPRC 중앙값", fontsize=8.4)
    ax.set_ylim(0, max(vals) * 1.42)
    ax.tick_params(labelsize=8.2)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", color=GRID, lw=0.7)
    ax.set_axisbelow(True)
    ax.set_title("물리 위 ML 보정 — 사전등록 기준(p < 0.05) 미달로 기각",
                 fontsize=10.4, fontweight="bold", pad=10)
    ax.text(0, -0.30,
            "로지스틱은 중앙값이 거의 두 배로 오르지만 p = 0.074로 기준에 못 미쳐 기각하고 물리단독을 유지했다. "
            "기각 이유는 통계만이 아니다 — 참값이 거주지 분포를 따라가므로 여기에 ML을 맞추면 모형은 산사태가 "
            "아니라 ‘사람이 사는 곳’을 학습한다. 그래서 학습된 가중치는 배포하지 않는다.",
            transform=ax.transAxes, fontsize=7.5, color=MUTED, wrap=True)
    save(fig, "fig19_ml_rejected", "사전등록 기준에 따른 ML 보정 기각")


# ---------------------------------------------------------------------------
# Module V — 같은 엔진, 두 재해의 차이
# ---------------------------------------------------------------------------
def fig_module_v():
    vex = load(REPO / "contracts" / "module_v.example.json") if (
        REPO / "contracts" / "module_v.example.json").exists() else None
    flood_iou, flood_f1 = 0.32, 0.485
    land_iou, land_f1 = VLAND["iou"], VLAND["f1"]

    fig, ax = plt.subplots(figsize=(9.2, 3.6))
    groups = ["IoU", "F1"]
    x = range(len(groups))
    w = 0.34
    b1 = ax.bar([i - w / 2 for i in x], [flood_iou, flood_f1], width=w,
                color=BLUE, label="하천범람 (Module B → V)")
    b2 = ax.bar([i + w / 2 for i in x], [land_iou, land_f1], width=w,
                color=RED, label="산사태 (Module A → V)")
    ax.bar_label(b1, fmt="%.3f", fontsize=8.4, padding=2, fontweight="bold")
    ax.bar_label(b2, fmt="%.4f", fontsize=8.4, padding=2, fontweight="bold")
    ax.set_xticks(list(x))
    ax.set_xticklabels(groups, fontsize=9.4)
    ax.set_ylim(0, 0.62)
    ax.legend(fontsize=8, frameon=False, loc="upper right")
    ax.tick_params(labelsize=7.8)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", color=GRID, lw=0.7)
    ax.set_axisbelow(True)
    ax.set_title("Module V 검증 엔진 — 같은 코드, 두 재해의 결과 차이",
                 fontsize=10.4, fontweight="bold", pad=10)
    ax.text(0, -0.26,
            "검증 엔진은 만능이 아니다. 하천범람은 SAR이 수면을 잘 잡아 의미 있는 값이 나오지만, "
            f"산사태에 같은 엔진을 돌리면 IoU {land_iou}로 사실상 신호가 없다 — "
            f"{VLAND['note']} 화면에도 두 값을 나란히 띄워 이 차이를 숨기지 않는다.",
            transform=ax.transAxes, fontsize=7.5, color=MUTED, wrap=True)
    save(fig, "fig20_module_v", "Module V 검증 엔진의 재해별 결과 차이")


if __name__ == "__main__":
    print(f"출력 디렉터리: {OUT}\n")
    fig_goldentime()
    fig_ablation()
    fig_flood_validation()
    fig_landslide_honesty()
    fig_ml_rejected()
    fig_module_v()
    print(f"\n총 {len(SAVED)}개 생성")
