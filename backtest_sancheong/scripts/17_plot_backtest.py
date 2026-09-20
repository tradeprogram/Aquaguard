"""17_plot_backtest.py — 산청 백테스트 골든타임 시각화 (강우 + FoS 임계초과율 + 타임라인)."""
from __future__ import annotations
import warnings; warnings.filterwarnings("ignore")
from pathlib import Path
import pandas as pd, matplotlib
matplotlib.use("Agg"); import matplotlib.pyplot as plt
import matplotlib.dates as mdates
for f in ["Malgun Gothic","맑은 고딕","NanumGothic"]:
    try: plt.rcParams["font.family"]=f; break
    except Exception: pass
plt.rcParams["axes.unicode_minus"]=False
ROOT=Path(r"G:/연구/공모전/아쿠아가드")
df=pd.read_csv(ROOT/"outputs/sancheong_backtest_timeseries.csv", parse_dates=["time"])
df=df[(df.time>="2025-07-18 12:00")&(df.time<="2025-07-19 16:00")]

fig,ax=plt.subplots(figsize=(12.5,5.6))
ax.bar(df.time, df.rn, width=0.03, color="#9ec9e8", label="시간강우 (mm/h)", zorder=1)
ax.set_ylabel("시간강우 (mm/h)", color="#2b7bba"); ax.set_ylim(0,75)
ax2=ax.twinx()
ax2.plot(df.time, df["critB_%"], color="#c0392b", lw=2.2, marker="o", ms=3, label="위험사면 임계초과율 B:풍화화강토 (%)")
ax2.plot(df.time, df["critA_%"], color="#e67e22", lw=1.8, ls="--", marker="s", ms=2.5, label="위험사면 임계초과율 A:토양도토성 (%)")
ax2.set_ylabel("위험사면 FoS<1 비율 (%)", color="#c0392b"); ax2.set_yscale("log"); ax2.set_ylim(0.001,2)

# 타임라인 마커
report=pd.Timestamp("2025-07-19 08:00"); tagent=pd.Timestamp("2025-07-19 09:00"); alert=pd.Timestamp("2025-07-19 12:37")
ax.axvspan(tagent, alert, color="#f1c40f", alpha=0.15, zorder=0)
for t,c,lab,dy in [(report,"#e67e22","주민신고 08:00",0),(tagent,"#c0392b","T_agent 09:00\n(모델 위험급증)",0),(alert,"#7f8c8d","공식경보 12:37",0)]:
    ax.axvline(t, color=c, ls="--", lw=1.6)
ax.text(report,70,"신고 08:00",color="#b9560f",fontsize=9,ha="center")
ax.text(tagent,63,"★T_agent 09:00",color="#c0392b",fontsize=9.5,ha="center",fontweight="bold")
ax.text(alert,70,"공식경보 12:37",color="#555",fontsize=9,ha="center")
ax.annotate("골든타임 3.6h\n(모델이 공식경보보다 먼저)", ((tagent.value+alert.value)//2,1),
            xytext=(0,0), textcoords="offset points", ha="center", fontsize=10.5, fontweight="bold", color="#b9560f")

ax.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d %H시")); ax.xaxis.set_major_locator(mdates.HourLocator(interval=3))
fig.autofmt_xdate(rotation=25)
ax.set_title("산청 2025-07-19 백테스트 — 실측강우→5m FoS 시계열, 위험 급증 09:00 (공식경보 12:37보다 3.6h 앞섬)\n[실데이터: ASOS강우·5m DEM·정밀토양도·Sentinel-2 dNBR / 지반정수 2시나리오 민감도]",
             fontsize=11, fontweight="bold")
l1,la1=ax.get_legend_handles_labels(); l2,la2=ax2.get_legend_handles_labels()
ax.legend(l1+l2,la1+la2,loc="upper left",fontsize=8.5)
fig.tight_layout()
png=ROOT/"outputs/sancheong_backtest_goldentime.png"; fig.savefig(png,dpi=150,bbox_inches="tight")
print("saved ->", png)
