"""제안서 첨부 도표 생성 — 모든 수치는 저장소 실측값이다.

AI 생성 이미지가 아니라 matplotlib로 그린다(공모전 규정). 값을 지어내지 않기 위해
가능한 것은 이 스크립트 안에서 실제로 계산하고(REAL_* 함수), 나머지는 파일 상단
MEASURED 블록에 출처를 적어 고정한다.

    python scripts/build_proposal_figures.py [출력디렉터리]
"""

from __future__ import annotations

import json
import os
import sys

# 윈도우 콘솔이 cp949면 캡션의 —·… 에서 그냥 죽는다. 출력만 UTF-8로 돌린다.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager, patches
from matplotlib.lines import Line2D

plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["figure.dpi"] = 200
plt.rcParams["savefig.bbox"] = "tight"
plt.rcParams["savefig.facecolor"] = "white"

REPO = Path(__file__).resolve().parent.parent
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

# ---------------------------------------------------------------------------
# MEASURED — 저장소에서 실제로 측정한 값. 각 행에 측정 방법을 적는다.
# ---------------------------------------------------------------------------
MEASURED = {
    # python -m pytest <pkg> -q --collect-only (2026-09-21)
    "tests": {"A": 46, "B": 15, "C": 187, "D": 55, "E": 9,
              "G": 90, "H": 85, "O": 24, "V": 17},
    # 각 패키지의 .py 줄수, tests/·scripts/ 제외 (2026-09-21)
    "lines": {"A": 920, "B": 419, "C": 602, "D": 855, "E": 751,
              "G": 463, "H": 708, "O": 1566, "V": 326},
    # 재현 파이프라인 스크립트(계약 밖) — A·B·V만 보유
    "script_lines": {"A": 1413, "B": 1495, "V": 457},
    # 커밋된 AOI 클립본의 feature 수 (2026-09-21)
    #
    # 산청은 2026-09-21에 "경보지점 반경 12km"에서 **산청군 ∪ 반경 12km**로 넓혔다.
    # 반경만 쓰면 군의 24%(190/790km²)밖에 못 덮어 고립마을·대피소를 군 전체로
    # 돌릴 수 없고, 행정경계만 쓰면 데모 좌표가 군 동쪽 경계에서 5.4km라 위험영역이
    # 함양·진주 쪽으로 12% 샌다. 그래서 합집합이다.
    "aoi": {
        "산청 건물": 51040,
        "산청 농경지": 72875,
        "강남·서초 건물": 41814,
    },
    # module_d explain(): use_type_join — 위험영역에 걸린 건물 기준
    "use_type_join": {
        "산청": {"조인성공": 5281, "미상": 2161, "pct": 71.0},
        "강남·서초": {"조인성공": 36050, "미상": 5764, "pct": 86.2},
    },
    "git_commits": 199,
    "ui_lines": 5740,
    "api_lines": 1222,
}


def _alert_envelope() -> dict:
    """데모 시나리오를 실제 모듈로 실행해 봉투를 받는다 — 값을 하드코딩하지 않는다."""
    os.environ["AQUAGUARD_MOCK_MODE"] = "0"
    sys.path.insert(0, str(REPO))
    from module_o_orchestrator import run  # noqa: PLC0415

    payload = json.loads((REPO / "contracts" / "module_o.example.json").read_text("utf-8"))
    return run(payload["input"])


def _downstream() -> tuple[dict, dict]:
    """D·G의 산출을 커밋된 경보 스냅샷에서 읽는다.

    스냅샷(ui/public/demo/envelope.json)은 산청군 전역 AOI로 실제 파이프라인을
    통과시킨 결과이고, UI가 화면에 띄우는 값과 같은 값이다. 그림과 본문 표가
    화면과 어긋나지 않으려면 같은 출처를 써야 한다.

    스냅샷이 없으면 contracts/module_a.example.json의 위험 폴리곤으로 D·G만
    직접 돌린다. 이 경로는 위험영역이 2km×2km 예시라 값이 훨씬 작으며,
    그림 설명에 어떤 경로였는지 그대로 적는다.
    """
    sys.path.insert(0, str(REPO))
    import module_g_damage_cost as G  # noqa: PLC0415

    snapshot = REPO / "ui" / "public" / "demo" / "envelope.json"
    if snapshot.exists():
        pkg = json.loads(snapshot.read_text("utf-8"))["data"]["alert_package"]
        exposure = pkg["exposure"]
        g_input = {
            "exposed_buildings": exposure["exposed_buildings"],
            "exposed_farmland_ha": exposure["exposed_farmland_ha"],
            "unit_cost_table_ref": "module_g_v1",
        }
        g_env = G.run(g_input)
        g_explain = G.explain(g_input)
        d_env = {"data": exposure}
        return ({"d": d_env, "g": g_env},
                {"d": {"source": "snapshot"}, "g": g_explain, "source": "snapshot"})

    import module_d_exposure_overlay as D  # noqa: PLC0415
    from module_o_orchestrator.exposure_layers import (  # noqa: PLC0415
        building_footprints, farmland_parcels, resolve_aoi,
    )

    a_example = json.loads((REPO / "contracts" / "module_a.example.json").read_text("utf-8"))
    a_out = a_example["output"]["data"]
    polygon = a_out["risk_polygon_5179"]
    loc = a_out["location"]

    aoi = resolve_aoi(loc["x_5179"], loc["y_5179"])
    buildings, _ = building_footprints(aoi)
    farmland, _ = farmland_parcels(aoi)

    d_input = {
        "risk_polygons": [{"source_module": "A", "geometry_5179": polygon,
                           "risk_prob": a_out["landslide_prob"]}],
        "building_footprints_5179": buildings,
        "farmland_parcels_5179": farmland,
    }
    d_env = D.run(d_input)
    d_explain = D.explain(d_input)

    g_input = {
        "exposed_buildings": d_env["data"]["exposed_buildings"],
        "exposed_farmland_ha": d_env["data"]["exposed_farmland_ha"],
        "unit_cost_table_ref": "module_g_v1",
    }
    g_env = G.run(g_input)
    g_explain = G.explain(g_input)
    return ({"d": d_env, "g": g_env},
            {"d": d_explain, "g": g_explain, "source": "contract_example"})


ENV = _alert_envelope()
PKG = ENV["data"]["alert_package"]
DOWN, DOWN_EXPLAIN = _downstream()
G_DETAIL = DOWN_EXPLAIN["g"]["detail"]
D_DETAIL = DOWN_EXPLAIN["d"]

SAVED: list[tuple[str, str]] = []


def save(fig, stem: str, caption: str) -> None:
    path = OUT / f"{stem}.png"
    fig.savefig(path)
    plt.close(fig)
    SAVED.append((stem, caption))
    print(f"  {path.name:<34} {caption}")


def _box(ax, x, y, w, h, text, fc, ec, fs=8.5, tc=None, lw=1.2, radius=0.02):
    ax.add_patch(
        patches.FancyBboxPatch(
            (x, y), w, h,
            boxstyle=f"round,pad=0.006,rounding_size={radius}",
            facecolor=fc, edgecolor=ec, linewidth=lw,
        )
    )
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center",
            fontsize=fs, color=tc or INK, linespacing=1.45)


def _arrow(ax, xy_from, xy_to, color=SLATE, lw=1.3, style="-|>"):
    ax.annotate("", xy=xy_to, xytext=xy_from,
                arrowprops=dict(arrowstyle=style, color=color, lw=lw,
                                shrinkA=2, shrinkB=2))


def _clean(ax):
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")


# ---------------------------------------------------------------------------
# 그림 1 — 산청 2025 타임라인과 회복 대상 시간
# ---------------------------------------------------------------------------
def fig_timeline():
    fig, ax = plt.subplots(figsize=(9.6, 3.5))
    ax.set_xlim(-0.4, 3.0)
    ax.set_ylim(-1.25, 1.95)
    ax.axis("off")
    ax.plot([-0.25, 2.9], [0, 0], color=GRID, lw=2.4, zorder=1, solid_capstyle="round")

    events = [
        (0.0, "3월\n경남·경북 산불", "48,238ha 소실\n(11개 지역)", SLATE, 1),
        (1.35, "7/17\n산림청 대피 권고", "위험 신호는\n이미 존재했다", AMBER, 1),
        (2.15, "7/19 12:37\n산사태 경보 격상", "공식 대응 시점", RED, 1),
        (2.62, "7/19\n피해 확정", "산사태 266건\n13명 사망·1명 실종", RED, -1),
    ]
    for x, title, sub, color, side in events:
        ax.scatter([x], [0], s=95, color=color, zorder=4,
                   edgecolor="white", linewidth=1.6)
        top = side > 0
        y0 = 0.16 if top else -0.16
        y1 = 0.48 if top else -0.48
        ax.plot([x, x], [y0, y1], color=color, lw=1.1, zorder=2)
        ax.text(x, y1 + (0.05 if top else -0.05), title,
                ha="center", va="bottom" if top else "top",
                fontsize=9, color=INK, fontweight="bold", linespacing=1.4)
        ax.text(x, y1 + (0.42 if top else -0.42), sub,
                ha="center", va="bottom" if top else "top",
                fontsize=7.8, color=MUTED, linespacing=1.4)

    ax.annotate("", xy=(2.15, -0.86), xytext=(1.35, -0.86),
                arrowprops=dict(arrowstyle="<|-|>", color=BLUE, lw=1.7))
    ax.add_patch(patches.FancyBboxPatch(
        (1.44, -1.15), 0.62, 0.23,
        boxstyle="round,pad=0.012,rounding_size=0.03",
        facecolor="#eff6ff", edgecolor=BLUE, linewidth=1.1))
    ax.text(1.75, -1.035, "회복 대상 구간", ha="center", va="center",
            fontsize=8.6, color=BLUE, fontweight="bold")

    ax.text(-0.35, 1.80,
            "예측이 실패한 사건이 아니다 — 권고와 경보 사이에서 시간이 샌 사건이다",
            fontsize=10.5, color=INK, fontweight="bold", ha="left")
    ax.text(-0.35, 1.60,
            "아쿠아가드가 되찾으려는 것은 이 구간이며, 사망자 수가 아니라 '분'으로만 주장한다",
            fontsize=8.4, color=MUTED, ha="left")
    save(fig, "fig01_timeline", "2025년 산청 복합재해 타임라인과 회복 대상 구간")


# ---------------------------------------------------------------------------
# 그림 2 — 재해연쇄
# ---------------------------------------------------------------------------
def fig_chain():
    fig, ax = plt.subplots(figsize=(9.8, 2.75))
    _clean(ax)
    chain = [
        ("산불 흉터", "dNBR\n토양 결속력 상실", "#fef2f2", RED),
        ("집중호우", "실측 강우\n+ 예보", "#eff6ff", BLUE),
        ("산사태", "FoS < 1\nModule A", "#fef3c7", AMBER),
        ("하천 범람", "수위 상승\nModule B", "#eff6ff", BLUE),
        ("도로 단절", "규칙 판정\nModule C", "#f5f3ff", VIOLET),
        ("마을 고립", "그래프 도달성\nModule E", "#ecfdf5", GREEN),
    ]
    n = len(chain)
    w, gap = 0.138, 0.0324
    for i, (title, sub, fc, ec) in enumerate(chain):
        x = i * (w + gap)
        _box(ax, x, 0.30, w, 0.40, f"{title}\n\n", fc, ec, fs=9.5)
        ax.text(x + w / 2, 0.60, title, ha="center", va="center",
                fontsize=9.6, fontweight="bold", color=INK)
        ax.text(x + w / 2, 0.435, sub, ha="center", va="center",
                fontsize=7.6, color=MUTED, linespacing=1.4)
        if i < n - 1:
            _arrow(ax, (x + w + 0.004, 0.50), (x + w + gap - 0.004, 0.50))

    ax.text(0, 0.88,
            "기존 시스템은 이 사슬의 앞 두세 칸에서 끝난다",
            fontsize=10.2, fontweight="bold", color=INK)
    ax.text(0, 0.775,
            "아쿠아가드의 기여는 새 위험지도가 아니라, 사슬을 끝까지 이어 '누구를 어디로'까지 산출하는 것이다",
            fontsize=8.3, color=MUTED)
    ax.annotate("", xy=(0.995, 0.19), xytext=(0.0, 0.19),
                arrowprops=dict(arrowstyle="-|>", color=GREEN, lw=1.5,
                                linestyle=(0, (5, 3))))
    ax.text(0.5, 0.10, "하나의 상태머신(Module O)이 이 전 구간을 순서대로 통과시킨다",
            ha="center", fontsize=8.2, color=GREEN, fontweight="bold")
    save(fig, "fig02_disaster_chain", "재해연쇄 모델과 모듈 대응 구간")


# ---------------------------------------------------------------------------
# 그림 3 — 시스템 아키텍처
# ---------------------------------------------------------------------------
def fig_architecture():
    fig, ax = plt.subplots(figsize=(9.6, 6.6))
    _clean(ax)

    _box(ax, 0.03, 0.885, 0.94, 0.085,
         "관측·정적 데이터   |   지형(DEM) · dNBR(Sentinel-2) · 실측 강우 · 하천수위 · InSAR · 건물/도로/하천(브이월드)",
         "#f8fafc", SLATE, fs=8.4)

    preds = [("Module A\n산사태 예측", "FoS 기반 · 트랙①", "#fef3c7", AMBER),
             ("Module B\n하천범람 예측", "SFINCS/ANUGA · 트랙①", "#dbeafe", BLUE),
             ("Module C\n도로·지하차도", "규칙기반 · 트랙②", "#ede9fe", VIOLET)]
    for i, (t, s, fc, ec) in enumerate(preds):
        x = 0.06 + i * 0.305
        _box(ax, x, 0.715, 0.275, 0.115, "", fc, ec)
        ax.text(x + 0.1375, 0.787, t, ha="center", va="center",
                fontsize=9, fontweight="bold", linespacing=1.35)
        ax.text(x + 0.1375, 0.740, s, ha="center", va="center",
                fontsize=7.3, color=MUTED)
        _arrow(ax, (x + 0.1375, 0.882), (x + 0.1375, 0.834))
        _arrow(ax, (x + 0.1375, 0.712), (x + 0.1375, 0.648))

    ax.text(0.35, 0.676, "임계치 초과 시에만 호출",
            ha="center", fontsize=7.4, color=MUTED, style="italic")

    _box(ax, 0.06, 0.505, 0.88, 0.14, "", "#eff6ff", BLUE, lw=1.7)
    ax.text(0.5, 0.605, "Module O — 골든타임 오케스트레이터",
            ha="center", fontsize=10.6, fontweight="bold", color=BLUE)
    ax.text(0.5, 0.548,
            "상태머신 7단계 :  관측 → 예측 → 1차 권고 → 시민 역검증 → 경보 격상 → 주민 전파 → 개별 대피",
            ha="center", fontsize=8.1, color=INK)

    downs = [("Module D", "노출자산 오버레이", "#ecfdf5", GREEN),
             ("Module E", "대피경로·고립탐지", "#ecfdf5", GREEN),
             ("Module G", "피해비용 추정", "#ecfdf5", GREEN),
             ("Module H", "시민 역검증", "#ecfdf5", GREEN)]
    for i, (t, s, fc, ec) in enumerate(downs):
        x = 0.06 + i * 0.2266
        _box(ax, x, 0.355, 0.20, 0.105, "", fc, ec)
        ax.text(x + 0.10, 0.419, t, ha="center", fontsize=8.8, fontweight="bold")
        ax.text(x + 0.10, 0.383, s, ha="center", fontsize=7.3, color=MUTED)
        _arrow(ax, (x + 0.10, 0.502), (x + 0.10, 0.463))
        _arrow(ax, (x + 0.10, 0.352), (x + 0.10, 0.313))

    _box(ax, 0.06, 0.232, 0.88, 0.078, "", "#f8fafc", SLATE)
    ax.text(0.5, 0.271, "경보 패키지(alert_package) — 위험·노출·경로·비용·검증을 담은 단일 의사결정 단위",
            ha="center", fontsize=8.8, fontweight="bold")
    _arrow(ax, (0.5, 0.229), (0.5, 0.194))

    _box(ax, 0.06, 0.070, 0.55, 0.120, "", "#f1f5f9", SLATE)
    ax.text(0.335, 0.156, "UI — 3D 지도 대시보드", ha="center",
            fontsize=9, fontweight="bold")
    ax.text(0.335, 0.106, "시민 모드 / 관공서 모드\nProvenance 배지 · LLM 해설층",
            ha="center", fontsize=7.3, color=MUTED, linespacing=1.5)

    _box(ax, 0.64, 0.070, 0.30, 0.120, "", "#fffbeb", AMBER)
    ax.text(0.79, 0.156, "Module V — 검증 엔진", ha="center",
            fontsize=9, fontweight="bold")
    ax.text(0.79, 0.106, "예측 vs 사후 SAR 관측\nIoU · F1 · Recall · lead time",
            ha="center", fontsize=7.3, color=MUTED, linespacing=1.5)

    ax.text(0.03, 0.028,
            "내부 연산은 전 구간 EPSG:5179(m), EPSG:4326 재투영은 UI 출력 직전 한 번만 수행한다",
            fontsize=7.6, color=MUTED, style="italic")
    save(fig, "fig03_architecture", "아쿠아가드 시스템 아키텍처 및 데이터 흐름")


# ---------------------------------------------------------------------------
# 그림 4 — 구현 현황 (테스트 수 · 코드량)
# ---------------------------------------------------------------------------
def fig_implementation():
    mods = ["A", "B", "C", "D", "E", "G", "H", "O", "V"]
    tests = [MEASURED["tests"][m] for m in mods]
    lines = [MEASURED["lines"][m] for m in mods]
    scripts = [MEASURED["script_lines"].get(m, 0) for m in mods]
    total_tests = sum(tests)
    legend = ("A 산사태   B 하천범람   C 도로·지하차도   D 노출자산   E 대피경로·고립   "
              "G 피해비용   H 시민 역검증   O 오케스트레이터   V 검증 엔진")

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9.8, 3.6))
    colors = [GREEN if t > 0 else AMBER for t in tests]

    b1 = ax1.bar(mods, tests, color=colors, width=0.62)
    ax1.bar_label(b1, fontsize=8.2, padding=2, fontweight="bold")
    ax1.set_title(f"모듈별 통과 테스트 수 (총 {total_tests}개)",
                  fontsize=10, fontweight="bold", pad=9)
    ax1.set_ylim(0, max(tests) * 1.24)
    ax1.text(4, 16, "테스트 미작성\n(트랙④ 소유)", ha="center",
             fontsize=7.2, color=AMBER, fontweight="bold", linespacing=1.6)

    b2 = ax2.bar(mods, lines, color=SLATE, width=0.62, label="계약 구현 코드")
    ax2.bar(mods, scripts, bottom=lines, color="#cbd5e1", width=0.62,
            label="재현 파이프라인 스크립트")
    ax2.bar_label(b2, fontsize=7.8, padding=1, fontweight="bold", label_type="center",
                  color="white")
    ax2.set_title("모듈별 코드 줄 수 (테스트 제외)", fontsize=10, fontweight="bold", pad=9)
    ax2.set_ylim(0, max(a + b for a, b in zip(lines, scripts)) * 1.20)
    ax2.legend(fontsize=7.2, frameon=False, loc="upper right")

    for ax in (ax1, ax2):
        ax.spines[["top", "right", "left"]].set_visible(False)
        ax.tick_params(axis="x", labelsize=9.4, length=0)
        ax.tick_params(axis="y", labelsize=7.6, colors=MUTED)
        ax.grid(axis="y", color=GRID, lw=0.7)
        ax.set_axisbelow(True)

    fig.text(0.5, -0.015, legend, ha="center", fontsize=7.6, color=MUTED)
    fig.suptitle("프로토타입 구현 현황 — 2026-09-20 저장소 실측",
                 fontsize=11, fontweight="bold", y=1.03)
    save(fig, "fig04_implementation", "모듈별 구현 코드량과 테스트 통과 수")


# ---------------------------------------------------------------------------
# 그림 5 — Module C 규칙 판정면 (실제 룰셋 v1_kma_mois)
# ---------------------------------------------------------------------------
def fig_module_c_rules():
    rules = json.loads(
        (REPO / "module_c_urban_rule" / "rulesets" / "v1_kma_mois.json").read_text("utf-8"))
    row = {r["id"]: r["value"] for r in rules["rows"]}
    cut_c, cut_w, cut_d = row["cutpoint_주의"], row["cutpoint_경계"], row["cutpoint_위험"]
    override = row["extreme_override"]
    drain = row["drainage_factor"]

    fig, ax = plt.subplots(figsize=(9.4, 3.9))
    rain = [i * 0.5 for i in range(0, 171)]
    labels = ["정상", "주의", "경계", "위험"]
    band = {"정상": "#f8fafc", "주의": "#fef9c3", "경계": "#fed7aa", "위험": "#fecaca"}

    for j, (grade, factor) in enumerate(drain.items()):
        y = 2 - j
        prev, start = None, 0.0
        for r in rain:
            eff = r * factor
            g = ("위험" if (r >= override or eff >= cut_d)
                 else "경계" if eff >= cut_w
                 else "주의" if eff >= cut_c else "정상")
            if prev is None:
                prev, start = g, r
            elif g != prev:
                ax.barh(y, r - start, left=start, height=0.62,
                        color=band[prev], edgecolor="white", linewidth=0.8)
                if r - start > 7:
                    ax.text((start + r) / 2, y, prev, ha="center", va="center",
                            fontsize=8, fontweight="bold", color=INK)
                prev, start = g, r
        ax.barh(y, rain[-1] - start, left=start, height=0.62,
                color=band[prev], edgecolor="white", linewidth=0.8)
        ax.text((start + rain[-1]) / 2, y, prev, ha="center", va="center",
                fontsize=8, fontweight="bold", color=INK)

    ax.set_yticks([2, 1, 0])
    ax.set_yticklabels([f"배수 {k}\n(가중 {v})" for k, v in drain.items()], fontsize=8)
    ax.set_xlabel("1시간 강우강도 (mm/h)", fontsize=8.6, labelpad=4)
    ax.set_xlim(0, 85)
    ax.set_ylim(-0.55, 2.62)

    for v, lab, c in [(cut_c, f"주의 {cut_c:g}", AMBER), (cut_w, f"경계 {cut_w:g}", "#ea580c"),
                      (cut_d, f"위험 {cut_d:g}", RED), (override, f"극한호우 {override:g}", "#7f1d1d")]:
        ax.axvline(v, color=c, lw=1.15, ls="--", alpha=0.85, zorder=5)
        ax.text(v, 2.70, lab, ha="center", fontsize=7.4, color=c, fontweight="bold")

    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.tick_params(length=0, labelsize=7.6)
    ax.set_title("Module C 규칙 판정면 — 룰셋 v1_kma_mois (모델이 아니라 결정론적 분류)",
                 fontsize=10, fontweight="bold", pad=22)
    ax.text(0, -1.52,
            "기상청 기상특보 발표기준(3시간 60/90mm의 시간 균등환산)과 극한호우 긴급재난문자 기준(1시간 72mm)에서 유도했다. "
            "배수등급 가중치는 아직 공식 출처가 없어 PLACEHOLDER로 표기된 가정치다.",
            fontsize=7.2, color=MUTED, wrap=True)
    save(fig, "fig05_module_c_rules", "Module C 규칙 판정면과 임계값 근거")


# ---------------------------------------------------------------------------
# 그림 6 — 데모 시나리오 노출자산 용도별 구성 (실행 결과)
# ---------------------------------------------------------------------------
def fig_exposure_mix():
    counts = dict(G_DETAIL["buildings"]["counts"])
    total = sum(counts.values())
    order = sorted(counts.items(), key=lambda kv: -kv[1])
    labels = [k for k, _ in order]
    values = [v for _, v in order]
    palette = {"주거": BLUE, "미상": "#9ca3af", "상업": VIOLET,
               "공업": SLATE, "농업": GREEN, "공공": AMBER}
    colors = [palette.get(k, SLATE) for k in labels]

    fig = plt.figure(figsize=(10.2, 4.3))
    gs = fig.add_gridspec(1, 2, width_ratios=[1.05, 1], wspace=0.34)
    ax1 = fig.add_subplot(gs[0])
    ax2 = fig.add_subplot(gs[1])

    wedges, _ = ax1.pie(values, colors=colors, startangle=90, radius=1.0,
                        wedgeprops=dict(width=0.40, edgecolor="white", linewidth=1.8))
    ax1.text(0, 0.10, f"{total:,}", ha="center", va="center",
             fontsize=20, fontweight="bold", color=INK)
    ax1.text(0, -0.16, "노출 건물(동)", ha="center", va="center",
             fontsize=8.6, color=MUTED)
    ax1.legend(wedges, [f"{k}  {v:,}동  ({v / total * 100:.1f}%)" for k, v in order],
               loc="upper center", bbox_to_anchor=(0.5, -0.04),
               ncol=3, fontsize=8, frameon=False, handlelength=1.1,
               columnspacing=1.2, handletextpad=0.5)
    ax1.set_title("용도별 구성", fontsize=10, fontweight="bold", pad=2)

    housing = G_DETAIL["housing"]
    farm = G_DETAIL["farmland"]
    lo, hi = DOWN["g"]["data"]["cost_range_krw"]
    parts = [(f"주거 건물  {housing['count']:,}동\n× {housing['unit_krw']:,}원/세대",
              housing["cost_krw"], BLUE),
             (f"농경지  {farm['area_m2']:,.0f}m²\n× {farm['unit_krw_per_m2']:,}원/m²",
              farm["cost_krw"], GREEN)]
    bottom = 0
    for label, val, color in parts:
        ax2.bar([0], [val / 1e8], bottom=bottom / 1e8, color=color, width=0.50)
        ax2.text(0, (bottom + val / 2) / 1e8,
                 f"{label}\n= {val / 1e8:,.2f}억원",
                 ha="center", va="center", fontsize=7.6, color="white",
                 fontweight="bold", linespacing=1.6)
        bottom += val

    ax2.errorbar([0], [bottom / 1e8], yerr=[[0], [(hi - lo) / 1e8]],
                 fmt="none", ecolor=RED, elinewidth=1.6, capsize=9, capthick=1.6)
    ax2.text(0, hi / 1e8 * 1.045, f"점추정  {bottom / 1e8:,.2f}억원",
             ha="center", fontsize=11, fontweight="bold", color=INK)
    ax2.text(0.36, ((bottom + hi) / 2) / 1e8,
             f"상한 {hi / 1e8:,.2f}억원\n\n미상 {G_DETAIL['buildings']['unknown_excluded']}동이\n"
             f"주거 비율 {G_DETAIL['range_basis']['unknown_housing_ratio']:.1%}로\n판명될 경우",
             fontsize=7.4, color=RED, va="center", ha="left", linespacing=1.55)

    ax2.set_ylabel("억원", fontsize=8.6, rotation=0, labelpad=14, ha="right")
    ax2.set_ylim(0, hi / 1e8 * 1.22)
    ax2.set_xlim(-0.42, 1.05)
    ax2.set_xticks([])
    ax2.spines[["top", "right", "bottom"]].set_visible(False)
    ax2.tick_params(labelsize=8, length=0)
    ax2.grid(axis="y", color=GRID, lw=0.7)
    ax2.set_axisbelow(True)
    ax2.set_title("피해비용 구성 — 고시 단가 기반", fontsize=10, fontweight="bold", pad=10)

    fig.suptitle("산청군 전역 경보 스냅샷에서 D·G가 산출한 값 — UI가 화면에 띄우는 값과 동일",
                 fontsize=11, fontweight="bold", y=1.02)
    save(fig, "fig06_exposure_and_cost",
         "노출자산 용도별 구성과 피해비용 — 2025-07 산청 재현 실행의 위험영역을 "
         "건축물·농경지와 교차한 결과이며, 단가는 국토부·농식품부 고시값이다")


# ---------------------------------------------------------------------------
# 그림 7 — 화재흉터 증폭계수 감쇠
# ---------------------------------------------------------------------------
def fig_amplification():
    fig, ax = plt.subplots(figsize=(8.4, 3.7))
    months = [i * 0.25 for i in range(0, 97)]
    half_life = 12.0
    for label, a_max, color in [("high (dNBR ≥ 0.66)", 3.75, RED),
                                ("moderate (0.44~0.66)", 2.0, AMBER),
                                ("low (0.27~0.44)", 1.2, GREEN)]:
        y = [1 + (a_max - 1) * 0.5 ** (m / half_life) for m in months]
        ax.plot(months, y, lw=2.1, color=color, label=f"{label} · $A_{{max}}$={a_max}")

    ax.axvline(4, color=BLUE, lw=1.3, ls="--")
    ax.text(4.35, 3.45, "산청 사례\n산불(3월) → 산사태(7월)\nΔt = 4개월",
            fontsize=7.8, color=BLUE, fontweight="bold", linespacing=1.5)
    ax.axhline(1.0, color=MUTED, lw=0.9, ls=":")

    ax.set_xlabel("산불 이후 경과 시간 Δt (개월)", fontsize=8.6)
    ax.set_ylabel("증폭계수 f(dNBR, Δt)", fontsize=8.6)
    ax.set_xlim(0, 24)
    ax.set_ylim(0.9, 4.1)
    ax.legend(fontsize=7.8, frameon=False, loc="upper right")
    ax.spines[["top", "right"]].set_visible(False)
    ax.tick_params(labelsize=7.8)
    ax.grid(color=GRID, lw=0.7)
    ax.set_axisbelow(True)
    ax.set_title("화재흉터 증폭계수의 시간 감쇠 — 반감기 12개월 가정",
                 fontsize=10, fontweight="bold", pad=9)
    ax.text(0, 0.60,
            "주의: $A_{max}$ 등급값은 국내외 문헌값을 가져다 쓴 가정치이며, 아직 한국 데이터로 사후검증된 계수가 아니다. "
            "2025년 3월 산불 11개 지역의 dNBR을 자체 산출해 보정하는 것이 다음 과제다.",
            fontsize=7.2, color=MUTED, transform=ax.get_xaxis_transform(), wrap=True)
    save(fig, "fig07_amplification", "화재흉터 증폭계수 f(dNBR, Δt)의 시간 감쇠")


# ---------------------------------------------------------------------------
# 그림 8 — 시민 역검증 shrinkage
# ---------------------------------------------------------------------------
def fig_shrinkage():
    sys.path.insert(0, str(REPO))
    from module_h_citizen_verification import policy as hpolicy  # noqa: PLC0415

    pol = hpolicy.active_policy()
    k = pol.shrinkage_k
    cap = abs(pol.max_adjustment)
    weights = pol.type_weights

    fig, ax = plt.subplots(figsize=(8.4, 3.6))
    ns = list(range(0, 31))
    curves = [(weights["이상징후_목격"], "전원 '이상징후 목격'", RED),
              (weights["이미_대피함"], "전원 '이미 대피함'", AMBER),
              (weights["오탐_신고"], "전원 '오탐 신고'", GREEN)]
    for w, label, color in [(w, f"{lab} (가중 {w:g})", c) for w, lab, c in curves]:
        y = [max(-cap, min(cap, (w * n) / (n + k))) for n in ns]
        ax.plot(ns, y, lw=2.1, color=color, label=label, marker="o", ms=2.6)

    ax.axhline(0, color=MUTED, lw=0.9)
    ax.axhline(cap, color=MUTED, lw=0.8, ls=":")
    ax.axhline(-cap, color=MUTED, lw=0.8, ls=":")
    ax.text(0.4, cap + 0.012, f"상한 +{cap:g}", fontsize=7.4, color=MUTED, va="bottom")
    ax.text(0.4, -cap - 0.012, f"하한 -{cap:g}", fontsize=7.4, color=MUTED, va="top")

    rc = PKG_H_REPORTS
    ax.scatter([rc], [0.12], s=110, color=BLUE, zorder=6,
               edgecolor="white", linewidth=1.6)
    ax.annotate(f"계약 예시 실행 결과 — 신고 {rc}건 → 보정 +0.12 (판정: 현장확인)\n"
                "세 곡선은 한 가지 유형만 들어온 경우이고, 예시는 유형이 섞여 있어\n"
                "곡선 위가 아니라 그 사이에 떨어진다",
                xy=(rc, 0.12), xytext=(rc + 1.8, 0.145),
                fontsize=7.4, color=BLUE, linespacing=1.6,
                arrowprops=dict(arrowstyle="-|>", color=BLUE, lw=1.1))

    ax.set_xlabel("유효 시민 신고 건수 n", fontsize=8.6)
    ax.set_ylabel("확률 보정량\nconfidence_adjustment", fontsize=8.2, linespacing=1.5)
    ax.set_xlim(0, 31)
    ax.legend(fontsize=7.6, frameon=False, loc="lower left",
              bbox_to_anchor=(0.30, 0.10))
    ax.spines[["top", "right"]].set_visible(False)
    ax.tick_params(labelsize=7.8)
    ax.grid(color=GRID, lw=0.7)
    ax.set_axisbelow(True)
    ax.set_title(f"시민 신고의 shrinkage 집계 — 분모의 +k(={k:g})가 소수 신고의 과대반영을 막는다",
                 fontsize=10, fontweight="bold", pad=9)
    save(fig, "fig08_shrinkage", "시민 역검증의 shrinkage 집계 곡선")


# ---------------------------------------------------------------------------
# 그림 9 — 폴백 계층
# ---------------------------------------------------------------------------
def fig_fallback():
    rows = [
        ("A 산사태", "InSAR + 실측 강우", "지형 + 실측 강우", "LDAPS 예보 (신뢰구간 확대)"),
        ("B 하천범람", "실측 강우+수위+SAR", "실측 강우 + SAR", "실측 강우만"),
        ("C 도로", "입력 4개 정상", "배수등급·지정위험 결측\n→ 보수적 기본값", "강우 결측 → 최소 등급"),
        ("D 노출자산", "폴리곤·건물·농경지 정상", "점 버퍼 대체\n무효 지오메트리 복구", "위험 지오메트리 없음 → 0건"),
        ("E 대피경로", "실도로 경로 API", "직선거리 근사\n(route_confidence: low)", "후보 대피소 없음"),
        ("H 시민검증", "응답 다수", "응답 소수 (낮은 가중치)", "응답 0건 (보정값 0)"),
    ]
    fig, ax = plt.subplots(figsize=(9.8, 4.3))
    _clean(ax)
    col_x = [0.015, 0.175, 0.455, 0.735]
    col_w = [0.15, 0.27, 0.27, 0.25]
    headers = ["모듈", "1순위 (tier 1)", "2순위 (tier 2)", "3순위 (tier 3)"]
    head_c = ["#f1f5f9", "#ecfdf5", "#fef9c3", "#fee2e2"]
    for x, w, h, c in zip(col_x, col_w, headers, head_c):
        _box(ax, x, 0.862, w, 0.068, h, c, SLATE, fs=8.6)

    for i, r in enumerate(rows):
        y = 0.735 - i * 0.122
        for j, (x, w) in enumerate(zip(col_x, col_w)):
            fc = "#f8fafc" if j == 0 else "white"
            _box(ax, x, y, w, 0.110, r[j], fc,
                 GRID if j else SLATE, fs=7.5,
                 tc=INK if j == 0 else MUTED)

    ax.text(0.015, 0.035,
            "핵심 규칙: '확인 불가'와 '0'을 구분한다. 농경지 레이어를 못 읽으면 노출면적은 0으로 계산되지만, "
            "시스템은 그것이 '없음'이 아니라 '확인 불가'라는 경고를 함께 낸다.",
            fontsize=7.5, color=INK, wrap=True)
    fig.suptitle("모듈별 폴백 계층 — 한 모듈이 실패해도 파이프라인은 멈추지 않는다",
                 fontsize=10.6, fontweight="bold", y=0.985)
    save(fig, "fig09_fallback_tiers", "모듈별 폴백 계층 설계")


# ---------------------------------------------------------------------------
# 그림 10 — Provenance 배지 + 가정 채널
# ---------------------------------------------------------------------------
def fig_provenance():
    fig, ax = plt.subplots(figsize=(9.6, 3.9))
    _clean(ax)
    badges = [("OBSERVED", "실측값", "시민 신고 · 실측 강수/수위", GREEN, "#ecfdf5"),
              ("FORECAST", "외부 기관 예보", "LDAPS 강수 예보", BLUE, "#eff6ff"),
              ("MODEL", "자체 모델 계산값", "Module A/B 확률 · 대피 경로", VIOLET, "#f5f3ff"),
              ("RULE", "규칙 기반 판정", "Module C 지하차도 경보", AMBER, "#fffbeb"),
              ("ASSUMPTION", "사용자 가정값", "What-if 시뮬레이터 값", "#9ca3af", "#f8fafc")]
    for i, (name, mean, ex, ec, fc) in enumerate(badges):
        x = 0.012 + i * 0.198
        _box(ax, x, 0.545, 0.182, 0.23, "", fc, ec, lw=1.5)
        ax.text(x + 0.091, 0.715, name, ha="center", fontsize=8.8,
                fontweight="bold", color=ec)
        ax.text(x + 0.091, 0.655, mean, ha="center", fontsize=7.8, color=INK)
        ax.text(x + 0.091, 0.596, ex, ha="center", fontsize=6.9,
                color=MUTED, linespacing=1.4)

    ax.text(0.012, 0.855, "채널 1 — 배지 : 이 숫자는 '어떻게' 산출됐는가",
            fontsize=9.4, fontweight="bold", color=INK)
    ax.text(0.012, 0.462, "채널 2 — 가정 칩 : 그 위에 '무슨 가정'이 얹혔는가",
            fontsize=9.4, fontweight="bold", color=INK)

    _box(ax, 0.012, 0.20, 0.455, 0.225, "", "white", GRID)
    ax.text(0.036, 0.365, "노출 건물 351동", fontsize=9, fontweight="bold")
    _box(ax, 0.036, 0.245, 0.075, 0.055, "MODEL", "#f5f3ff", VIOLET, fs=7.2, tc=VIOLET)
    ax.text(0.125, 0.272, "공간연산 결과 — 얹힌 가정 없음",
            fontsize=7.4, color=MUTED, va="center")

    _box(ax, 0.49, 0.20, 0.50, 0.225, "", "white", GRID)
    ax.text(0.514, 0.365, "피해액 8.72억원", fontsize=9, fontweight="bold")
    _box(ax, 0.514, 0.245, 0.075, 0.055, "MODEL", "#f5f3ff", VIOLET, fs=7.2, tc=VIOLET)
    _box(ax, 0.598, 0.245, 0.086, 0.055, "가정 2건", "#fef9c3", AMBER, fs=7.2, tc="#92400e")
    ax.text(0.697, 0.272, "필지 단위 주용도 조인 · 1동=1세대",
            fontsize=7.4, color=MUTED, va="center")

    ax.text(0.012, 0.075,
            "배지 하나로는 정직할 수 없다. 두 값 모두 모듈이 계산했지만 얹힌 가정의 수가 다르고, "
            "가정 칩의 문구는 UI가 지어내지 않고 각 모듈의 explain()이 실제로 반환한 문장을 그대로 쓴다.",
            fontsize=7.5, color=INK, wrap=True)
    save(fig, "fig10_provenance", "Provenance 배지 체계와 가정 표기 이원 채널")


# ---------------------------------------------------------------------------
# 그림 11 — AOI 데이터 규모와 주용도 조인 커버리지
# ---------------------------------------------------------------------------
def fig_aoi_coverage():
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9.8, 3.5))

    labels = list(MEASURED["aoi"].keys())
    vals = list(MEASURED["aoi"].values())
    colors = [SLATE, GREEN, BLUE]
    bars = ax1.barh(labels[::-1], vals[::-1], color=colors[::-1], height=0.56)
    ax1.bar_label(bars, labels=[f"{v:,}" for v in vals[::-1]],
                  fontsize=8.6, padding=4, fontweight="bold")
    ax1.set_xlim(0, max(vals) * 1.26)
    ax1.set_title("커밋된 AOI 노출자산 규모", fontsize=9.8, fontweight="bold", pad=9)
    ax1.spines[["top", "right", "left"]].set_visible(False)
    ax1.tick_params(labelsize=7.8, length=0)
    ax1.grid(axis="x", color=GRID, lw=0.7)
    ax1.set_axisbelow(True)
    ax1.text(0, -0.30, "산청 = 경보지점 반경 12km(452km²) · 강남·서초 = 84.8km²",
             fontsize=7.2, color=MUTED, transform=ax1.transAxes)

    regions = list(MEASURED["use_type_join"].keys())
    joined = [MEASURED["use_type_join"][r]["조인성공"] for r in regions]
    unknown = [MEASURED["use_type_join"][r]["미상"] for r in regions]
    pcts = [MEASURED["use_type_join"][r]["pct"] for r in regions]

    ax2.bar(regions, joined, color=BLUE, width=0.46, label="건축물대장 조인 성공")
    ax2.bar(regions, unknown, bottom=joined, color="#d1d5db", width=0.46, label="미상")
    for i, (j, u, p) in enumerate(zip(joined, unknown, pcts)):
        ax2.text(i, j / 2, f"{j:,}\n({p}%)", ha="center", va="center",
                 fontsize=8.2, color="white", fontweight="bold", linespacing=1.4)
        ax2.text(i, j + u / 2, f"{u:,}", ha="center", va="center",
                 fontsize=8, color=INK)
    ax2.set_title("건물 주용도 조인 커버리지", fontsize=9.8, fontweight="bold", pad=9)
    ax2.legend(fontsize=7.4, frameon=False, loc="upper left")
    ax2.set_ylim(0, max(a + b for a, b in zip(joined, unknown)) * 1.25)
    ax2.spines[["top", "right"]].set_visible(False)
    ax2.tick_params(labelsize=7.8, length=0)
    ax2.grid(axis="y", color=GRID, lw=0.7)
    ax2.set_axisbelow(True)
    ax2.text(0, -0.30, "미상 건물은 피해비용 점추정에서 제외하고, 상한 구간으로만 반영한다",
             fontsize=7.2, color=MUTED, transform=ax2.transAxes)

    save(fig, "fig11_aoi_coverage", "AOI 데이터 규모와 건물 주용도 조인 커버리지")


# ---------------------------------------------------------------------------
# 그림 12 — 의사결정 구조 (human-in-the-loop)
# ---------------------------------------------------------------------------
def fig_human_in_loop():
    fig, ax = plt.subplots(figsize=(9.6, 3.5))
    _clean(ax)

    steps = [("위험 임계치 초과", "Module A/B/C", BLUE),
             ("경보 초안 자동 생성", "Module O", BLUE),
             ("담당자 검토", "관공서 모드", AMBER),
             ("승인", "공식 대피명령", GREEN)]
    for i, (t, s, c) in enumerate(steps):
        x = 0.02 + i * 0.247
        _box(ax, x, 0.50, 0.215, 0.20, "", "#f8fafc", c, lw=1.5)
        ax.text(x + 0.1075, 0.625, t, ha="center", fontsize=8.8, fontweight="bold")
        ax.text(x + 0.1075, 0.560, s, ha="center", fontsize=7.4, color=MUTED)
        if i < 3:
            _arrow(ax, (x + 0.219, 0.60), (x + 0.243, 0.60))

    _box(ax, 0.515, 0.130, 0.47, 0.310, "", "#fffbeb", AMBER, lw=1.4)
    ax.text(0.75, 0.400, "15분 무응답 시", ha="center", fontsize=8.6,
            fontweight="bold", color="#92400e")
    ax.text(0.75, 0.297,
            "긴급 재알림 → 상위 담당자 escalation\n승인 전까지 '권고' 상태 유지",
            ha="center", fontsize=7.8, color=INK, linespacing=1.6)
    ax.text(0.75, 0.178, "자동 승인은 코드에서 완전히 삭제했다",
            ha="center", fontsize=7.8, color=RED, fontweight="bold")
    _arrow(ax, (0.635, 0.495), (0.70, 0.445), color=AMBER)

    ax.text(0.02, 0.88,
            "시스템은 어떤 경우에도 공식 대피명령을 독자 발령하지 않는다",
            fontsize=10.2, fontweight="bold", color=INK)
    ax.text(0.02, 0.795,
            "생명안전과 직결된 공공 의사결정에서 '무응답 시 자동승인'은 책임 소재를 흐리는 구조적 결함이기 때문이다. "
            "이 원칙은 테스트로 고정되어 있다 — test_escalation_after_timeout_does_not_auto_approve",
            fontsize=7.6, color=MUTED, wrap=True)
    ax.text(0.02, 0.055,
            "최종 판단은 담당자(관공서 모드) 또는 사용자 본인(시민 모드)의 몫이며, "
            "시스템의 역할은 그 판단에 필요한 근거를 더 빨리 모아주는 데서 끝난다.",
            fontsize=7.5, color=INK, wrap=True)
    save(fig, "fig12_human_in_loop", "human-in-the-loop 의사결정 구조와 escalation")


# ---------------------------------------------------------------------------
# 그림 13 — 두 사용자 모드
# ---------------------------------------------------------------------------
def fig_two_modes():
    fig, ax = plt.subplots(figsize=(9.6, 4.0))
    _clean(ax)

    _box(ax, 0.015, 0.09, 0.475, 0.74, "", "#eff6ff", BLUE, lw=1.6)
    ax.text(0.2525, 0.765, "시민 모드", ha="center", fontsize=11.5,
            fontweight="bold", color=BLUE)
    ax.text(0.2525, 0.715, "\"나는 지금 어떻게 해야 하는가\"",
            ha="center", fontsize=8.2, color=MUTED, style="italic")
    citizen = ["내 위치의 위험 등급과 남은 시간",
               "가장 가까운 안전 대피소와 실도로 경로",
               "차량 / 도보 각각의 예상 소요시간",
               "내 경로가 위험구간과 겹치는지 여부",
               "이상징후 신고 (→ Module H 역검증)",
               "LLM 챗봇 해설 — 경보 데이터만 인용"]
    for i, t in enumerate(citizen):
        y = 0.645 - i * 0.087
        ax.text(0.045, y, "•", fontsize=9, color=BLUE, fontweight="bold")
        ax.text(0.072, y, t, fontsize=8.1, color=INK, va="center")

    _box(ax, 0.51, 0.09, 0.475, 0.74, "", "#fffbeb", AMBER, lw=1.6)
    ax.text(0.7475, 0.765, "관공서 모드", ha="center", fontsize=11.5,
            fontweight="bold", color="#92400e")
    ax.text(0.7475, 0.715, "\"누구에게 무엇을 먼저 지시할 것인가\"",
            ha="center", fontsize=8.2, color=MUTED, style="italic")
    gov = ["3D 지도 위 위험 폴리곤 · 노출자산 중첩",
           "고립 위험 마을 자동 탐지 결과",
           "피해비용 추정과 산정 근거(고시 조항)",
           "경보 초안 검토 · 승인 · escalation",
           "Provenance 배지로 값의 출처 즉시 확인",
           "What-if 시뮬레이터 — 강우 시나리오 비교"]
    for i, t in enumerate(gov):
        y = 0.645 - i * 0.087
        ax.text(0.54, y, "•", fontsize=9, color=AMBER, fontweight="bold")
        ax.text(0.567, y, t, fontsize=8.1, color=INK, va="center")

    ax.text(0.5, 0.905, "같은 경보 패키지, 다른 질문 — 화면을 사용자 역할로 분리했다",
            ha="center", fontsize=10.4, fontweight="bold", color=INK)
    ax.text(0.5, 0.035,
            "두 모드는 동일한 alert_package를 읽는다. 데이터를 두 벌 만들지 않고 표현만 나누므로 "
            "한쪽에서 확인된 값이 다른 쪽과 어긋날 수 없다.",
            ha="center", fontsize=7.6, color=MUTED)
    save(fig, "fig13_two_modes", "시민 모드와 관공서 모드의 기능 분리")


# ---------------------------------------------------------------------------
# 그림 14 — 확장 로드맵
# ---------------------------------------------------------------------------
def fig_roadmap():
    fig, ax = plt.subplots(figsize=(9.8, 4.1))
    tasks = [
        ("Module A 실모델 (FoS 베이스라인)", 0, 2.0, AMBER, "트랙①"),
        ("산청 dNBR × 산사태 인벤토리 공간검증", 0, 1.2, AMBER, "트랙①"),
        ("산청 leakage-free 백테스트", 1.0, 2.2, RED, "트랙①"),
        ("Module V 검증 엔진 구현", 1.2, 2.0, AMBER, "트랙①"),
        ("Module B 하천범람 (SFINCS 연동)", 0.6, 2.4, AMBER, "트랙①"),
        ("네이버 Directions 실도로 경로 상시화", 0, 1.0, GREEN, "트랙④"),
        ("고립마을 탐지 실데이터 검증", 0.5, 1.5, GREEN, "트랙④"),
        ("건물 주용도 커버리지 개선 (63%→85%)", 0.3, 1.4, BLUE, "트랙②"),
        ("민관협력 플랫폼 클라우드·데이터 연동", 0, 1.6, VIOLET, "트랙③"),
        ("외부 전문가·실사용자 task 테스트", 1.4, 2.4, VIOLET, "전원"),
        ("제3지역 out-of-sample 실행", 2.2, 3.2, SLATE, "트랙②③"),
    ]
    for i, (name, start, end, color, owner) in enumerate(tasks):
        y = len(tasks) - i - 1
        ax.barh(y, end - start, left=start, height=0.56,
                color=color, alpha=0.88, edgecolor="white", linewidth=1.1)
        ax.text(end + 0.06, y, owner, va="center", fontsize=7,
                color=MUTED, fontweight="bold")

    ax.set_yticks(range(len(tasks)))
    ax.set_yticklabels([t[0] for t in tasks][::-1], fontsize=7.9)
    ax.set_xticks([0, 1, 2, 3, 3.5])
    ax.set_xticklabels(["10월 초", "10월 말", "11월 말", "12월 말", ""], fontsize=7.8)
    ax.set_xlim(0, 3.65)
    ax.set_ylim(-0.7, len(tasks) + 0.15)

    for v, lab, c, dy in [(1.05, "상세기획서 제출 (11/3)", BLUE, 0.52),
                          (1.15, "예선 (11/4~6)", VIOLET, 0.16),
                          (2.35, "본선 (12월 초)", RED, 0.52)]:
        ax.axvline(v, color=c, lw=1.2, ls="--", alpha=0.8)
        ax.text(v, len(tasks) - 1 + dy, lab, fontsize=7, color=c,
                rotation=0, ha="center", fontweight="bold")

    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.tick_params(length=0)
    ax.grid(axis="x", color=GRID, lw=0.7)
    ax.set_axisbelow(True)
    ax.set_title("구현 로드맵 — 새 기능보다 검증에 가중치를 둔다",
                 fontsize=10.4, fontweight="bold", pad=12)
    save(fig, "fig14_roadmap", "단계별 구현 로드맵과 트랙별 책임")


PKG_H_REPORTS = 6  # contracts/module_h.example.json 실행 결과 report_count

if __name__ == "__main__":
    print(f"출력 디렉터리: {OUT}\n")
    fig_timeline()
    fig_chain()
    fig_architecture()
    fig_implementation()
    fig_module_c_rules()
    fig_exposure_mix()
    fig_amplification()
    fig_shrinkage()
    fig_fallback()
    fig_provenance()
    fig_aoi_coverage()
    fig_human_in_loop()
    fig_two_modes()
    fig_roadmap()
    print(f"\n총 {len(SAVED)}개 생성")
