"""10_plot_sancheong_goldentime.py — 산청 2025-07-19 실측강우 + 골든타임 시각화."""
from __future__ import annotations
import warnings; warnings.filterwarnings("ignore")
from pathlib import Path
import pandas as pd, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
for f in ["Malgun Gothic","맑은 고딕","NanumGothic"]:
    try: plt.rcParams["font.family"]=f; break
    except Exception: pass
plt.rcParams["axes.unicode_minus"]=False

ROOT=Path(r"G:/연구/공모전/아쿠아가드")
df=pd.read_csv(ROOT/"data/kma/sancheong_asos_2025071819.csv", parse_dates=["time_kst"])
df=df[(df.time_kst>="2025-07-18 12:00")&(df.time_kst<="2025-07-19 18:00")].copy()
df["cum"]=df["rn_mm"].cumsum()

fig,ax=plt.subplots(figsize=(12,5.2))
ax.bar(df.time_kst, df.rn_mm, width=0.03, color="#2b7bba", label="시간강수 (mm/h)")
ax2=ax.twinx()
ax2.plot(df.time_kst, df.cum, color="#c0392b", lw=2, label="누적강수 (mm)")

# 골든타임 마커
report=pd.Timestamp("2025-07-19 08:00"); alert=pd.Timestamp("2025-07-19 12:37")
ax.axvspan(report, alert, color="#f1c40f", alpha=0.18, zorder=0)
ax.axvline(report, color="#e67e22", ls="--", lw=1.6); ax.axvline(alert, color="#7f8c8d", ls="--", lw=1.6)
ax.annotate("주민 신고 시작 08:00", (report, 62), fontsize=9.5, color="#b9560f", ha="right", rotation=0)
ax.annotate("공식 경보 격상 12:37", (alert, 62), fontsize=9.5, color="#555", ha="left")
ax.annotate("골든타임 격차\n4시간 37분", ((report.value+alert.value)//2, 40),
            xytext=(0,0), textcoords="offset points", ha="center", fontsize=11, fontweight="bold", color="#b9560f")

# 피크 주석
pk=df.loc[df.rn_mm.idxmax()]
ax.annotate(f"피크 {pk.rn_mm:.0f} mm/h", (pk.time_kst, pk.rn_mm), xytext=(8,6),
            textcoords="offset points", fontsize=10, fontweight="bold", color="#1a5276")

ax.set_ylabel("시간강수 (mm/h)", color="#2b7bba"); ax2.set_ylabel("누적강수 (mm)", color="#c0392b")
ax.set_ylim(0,75); ax2.set_ylim(0,450)
ax.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d %H시"))
ax.xaxis.set_major_locator(mdates.HourLocator(interval=3))
fig.autofmt_xdate(rotation=30)
ax.set_title("산청 2025-07-19 실측강우와 골든타임 — 기상청 ASOS(289), 누적 416.9mm  [실데이터]",
             fontsize=12.5, fontweight="bold")
l1,la1=ax.get_legend_handles_labels(); l2,la2=ax2.get_legend_handles_labels()
ax.legend(l1+l2, la1+la2, loc="upper left", fontsize=9)
fig.tight_layout()
png=ROOT/"outputs/sancheong_goldentime_rainfall.png"
fig.savefig(png,dpi=150,bbox_inches="tight")
print(f"saved -> {png}")
