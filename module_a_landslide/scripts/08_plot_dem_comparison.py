"""08_plot_dem_comparison.py — 토양도등급 vs DEM 경사 검증 AUC 정직 비교."""
from __future__ import annotations
import warnings; warnings.filterwarnings("ignore")
import json
from pathlib import Path
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
for f in ["Malgun Gothic","맑은 고딕","NanumGothic"]:
    try: plt.rcParams["font.family"]=f; break
    except Exception: pass
plt.rcParams["axes.unicode_minus"]=False
OUT=Path(r"G:/연구/공모전/아쿠아가드/outputs")
v04=json.loads((OUT/"andong_fos_validation_summary.json").read_text(encoding="utf-8"))
up =json.loads((OUT/"andong_fos_upslope_summary.json").read_text(encoding="utf-8"))
dem=json.loads((OUT/"andong_dem_validation_summary.json").read_text(encoding="utf-8"))

labels=["토양도등급\n지점","토양도등급\n발생부(200m)","DEM 30m\n지점","DEM 30m\n발생부(200m)"]
vals=[v04["auc_fos_prob"], up["auc_fos_upslope"], dem["auc_dem_point"], dem["auc_dem_upslope"]]
trust=[False, False, True, False]  # 신뢰 강조: DEM 지점
colors=["#e67e22" if not t else "#27ae60" for t in trust]
colors[1]="#f1c40f"  # 발생부(토양도)=과대치 경고색

fig,ax=plt.subplots(figsize=(9,5))
bars=ax.bar(labels, vals, color=colors, width=0.6, edgecolor="#34495e", linewidth=0.6)
ax.axhline(0.5, ls="--", color="#7f8c8d", lw=1.2); ax.text(3.35,0.51,"무작위 0.5",fontsize=9,color="#7f8c8d")
ax.set_ylim(0,0.8); ax.set_ylabel("AUC (=R)", fontsize=11)
ax.set_title("Module A 검증 — 안동 우려지역 299 vs 배경 599 (실데이터·무가공)", fontsize=12, fontweight="bold")
for b,v,t in zip(bars,vals,trust):
    ax.text(b.get_x()+b.get_width()/2, v+0.015, f"{v:.2f}", ha="center", fontweight="bold",
            fontsize=12, color="#196f3d" if t else "#34495e")
ax.text(1.0,0.63,"⚠ 범주 거칠어\n인위적 과대", ha="center", fontsize=8.5, color="#b9770e")
ax.text(2.0,0.60,"★ 가장 신뢰\n(연속경사)", ha="center", fontsize=8.5, color="#196f3d")
cap=("정직한 해석: DEM 지점 0.54가 신뢰값(토양도 0.41→0.54 개선). 한계=①30m DEM(발생부 급사면 뭉갬) "
     "②우려지역 좌표=수용부(발생부 아님). R 상승 레버=5m DEM + 실발생/Sentinel-1(Module V).")
fig.text(0.5,-0.02,cap,ha="center",fontsize=8.3,wrap=True,color="#555")
fig.tight_layout()
png=OUT/"andong_dem_comparison.png"
fig.savefig(png,dpi=150,bbox_inches="tight")
print(f"saved -> {png}")
