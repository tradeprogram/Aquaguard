"""06_plot_validation.py — 안동 검증 결과 시각화 (ROC + AUC 비교)."""
from __future__ import annotations
import warnings; warnings.filterwarnings("ignore")
import json
from pathlib import Path
import pandas as pd, numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from sklearn.metrics import roc_curve, roc_auc_score

# 한글 폰트 (Windows Malgun Gothic)
for f in ["Malgun Gothic", "맑은 고딕", "NanumGothic"]:
    try:
        plt.rcParams["font.family"] = f; break
    except Exception: pass
plt.rcParams["axes.unicode_minus"] = False

OUT = Path(r"G:/연구/공모전/아쿠아가드/outputs")
df = pd.read_csv(OUT / "andong_fos_validation.csv")
up = json.loads((OUT / "andong_fos_upslope_summary.json").read_text(encoding="utf-8"))

y = df.label.values; p = df.prob_sat.values
fpr, tpr, _ = roc_curve(y, p); auc_pt = roc_auc_score(y, p)

fig, ax = plt.subplots(1, 2, figsize=(11, 4.6))

# Panel A: ROC (지점 좌표 기반)
ax[0].plot(fpr, tpr, color="#c0392b", lw=2, label=f"지점 좌표  AUC={auc_pt:.2f}")
ax[0].plot([0,1],[0,1],"--",color="#95a5a6",lw=1)
ax[0].set_xlabel("False Positive Rate"); ax[0].set_ylabel("True Positive Rate")
ax[0].set_title("ROC — Module A FoS(포화) vs 안동 우려지역", fontsize=11)
ax[0].legend(loc="lower right", fontsize=9); ax[0].set_aspect("equal")

# Panel B: AUC 비교 (지점 vs 발생부)
labels = ["지점 좌표\n(계곡·수용부)", "상부 200m\n발생부 경사"]
vals = [auc_pt, up["auc_fos_upslope"]]
colors = ["#e67e22", "#27ae60"]
bars = ax[1].bar(labels, vals, color=colors, width=0.55)
ax[1].axhline(0.5, ls="--", color="#7f8c8d", lw=1); ax[1].text(1.42, 0.51, "무작위(0.5)", fontsize=8, color="#7f8c8d")
ax[1].set_ylim(0, 0.8); ax[1].set_ylabel("AUC (=R)")
ax[1].set_title("발생부 경사로 보면 물리가 판별", fontsize=11)
for b, v in zip(bars, vals):
    ax[1].text(b.get_x()+b.get_width()/2, v+0.015, f"{v:.2f}", ha="center", fontsize=11, fontweight="bold")

fig.suptitle("Module A 검증(안동 우려지역 299 vs 배경 600) — 실데이터, 무가공",
             fontsize=12, fontweight="bold")
fig.tight_layout(rect=[0,0,1,0.95])
png = OUT / "andong_validation.png"
fig.savefig(png, dpi=150, bbox_inches="tight")
print(f"saved -> {png}")
