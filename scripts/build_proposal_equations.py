"""제안서 본문에 넣을 산식을 이미지로 렌더링한다.

matplotlib mathtext를 쓴다. 주의할 점 두 가지:
  - TeX 조각은 반드시 raw string이어야 한다. 일반 문자열에서 '\beta'는 백스페이스
    문자로 해석된다.
  - mathtext는 LaTeX의 부분집합이다. '\dfrac'과 '\begin{cases}'를 모르므로
    각각 '\frac'과 여러 줄 분해로 대체한다.

한글은 $...$ 밖에 두면 본문 폰트(Malgun Gothic)로, 수식은 $...$ 안에서 cm 폰트로
렌더링되므로 한 줄에 섞어 쓸 수 있다.

    python scripts/build_proposal_equations.py [출력디렉터리]
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["mathtext.fontset"] = "cm"
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["savefig.bbox"] = "tight"
plt.rcParams["savefig.facecolor"] = "white"

REPO = Path(__file__).resolve().parent.parent
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else REPO / "docs" / "proposal_figures"
OUT.mkdir(parents=True, exist_ok=True)

INK = "#111827"
MUTED = "#6b7280"

# (파일명, [줄...]) — 줄은 (텍스트, 글자크기) 또는 텍스트
EQUATIONS: list[tuple[str, list]] = [
    ("eq1_amplification", [
        r"$f(\mathrm{dNBR},\ \Delta t)\ =\ 1\ +\ \left[\,A_{max}(c)-1\,\right]\cdot 2^{\,-\Delta t/\tau}$",
        (r"$c$ : dNBR 등급    $A_{max}$ : 등급별 최대 증폭    $\tau$ : 반감기(12개월 가정)", 10),
    ]),
    ("eq2_infinite_slope", [
        r"$FoS\ =\ \frac{c' + \left(\gamma z \cos^{2}\beta - u\right)\tan\phi'}"
        r"{\gamma z \sin\beta \cos\beta}$",
        (r"$c'$ : 점착력    $\phi'$ : 내부마찰각    $\gamma$ : 단위중량    "
         r"$z$ : 토층두께    $\beta$ : 사면경사    $u$ : 간극수압", 10),
    ]),
    ("eq3_rule_level", [
        (r"유효 강우강도    $R_{eff}\ =\ R_{1h}\cdot w(d)$", 15),
        (r"위험    $R_{1h} \geq 72$   또는   $R_{eff} \geq 50$", 13),
        (r"경계    $R_{eff} \geq 30$", 13),
        (r"주의    $R_{eff} \geq 20$   또는   (지정위험 지하차도 $\wedge\ R_{1h} > 0$)", 13),
        (r"정상    그 외", 13),
        (r"$R_{1h}$ : 1시간 강우강도(mm/h)    $w(d)$ : 배수등급 가중(low 1.3 / medium 1.0 / high 0.85)", 10),
    ]),
    ("eq4_exposure", [
        r"$P=\bigcup_{i} P_i$",
        r"$E_B=\left\{\,b\in B\ :\ \mathrm{geom}(b)\cap P \neq \varnothing\,\right\}"
        r"\qquad A_F=\sum_{f\in F}\mathrm{area}\!\left(f\cap P\right)$",
        (r"$P_i$ : 모듈 A·B·C가 낸 위험 폴리곤    $B$ : 건물 집합    $F$ : 농경지 필지 집합", 10),
    ]),
    ("eq5_damage_cost", [
        r"$C\ =\ n_{h}\cdot u_{h}\ +\ A_F\cdot u_{c}$",
        r"$C_{hi}\ =\ \max\!\left[\ C\,(1+\rho),\quad C + n_{u}\cdot q\cdot u_{h}\ \right]$",
        (r"$n_h$ : 주거 판정 건물 수    $u_h$ : 주택 침수 단가    $A_F$ : 노출 농경지 면적    "
         r"$u_c$ : 대파대 단가", 10),
        (r"$n_u$ : 용도 미상 건물 수    $q$ : 미상의 주거 추정비율    $\rho$ : 최소 상단폭(0.3)", 10),
    ]),
    ("eq6_shrinkage", [
        r"$\delta\ =\ \mathrm{clip}\!\left(\ \frac{\sum_{i=1}^{n} w(t_i)\cdot v_i}{n+k},"
        r"\quad -\delta_{max},\ \ +\delta_{max}\ \right)$",
        (r"$w(t_i)$ : 신고 유형별 가중    $v_i$ : 유효 신고 여부    "
         r"$k$ : shrinkage 상수(9)    $\delta_{max}$ : 보정 상한(0.3)", 10),
    ]),
    ("eq7_golden_time", [
        r"$\mathrm{hazard\ lead}\ =\ T_{event}-T_{agent}$",
        r"$\mathrm{decision\ latency\ recovered}\ =\ T_{official}-T_{agent}$",
        (r"$T_{agent}$ : 모델이 처음 임계치를 넘은 시각    $T_{event}$ : 최초 피해 발생 시각    "
         r"$T_{official}$ : 실제 공식 경보 시각", 10),
    ]),
]


def render(stem: str, lines: list) -> None:
    norm = [(ln, 15) if isinstance(ln, str) else ln for ln in lines]
    heights = [0.10 + fs * 0.020 for _, fs in norm]
    total = sum(heights) + 0.16

    fig = plt.figure(figsize=(7.6, total))
    y = 1.0
    for (text, fs), h in zip(norm, heights):
        frac = h / total
        y -= frac
        color = INK if fs >= 13 else MUTED
        fig.text(0.5, y + frac / 2, text, ha="center", va="center",
                 fontsize=fs, color=color)
    path = OUT / f"{stem}.png"
    fig.savefig(path, dpi=220)
    plt.close(fig)
    print(f"  {path.name}")


if __name__ == "__main__":
    print(f"출력 디렉터리: {OUT}\n")
    for stem, lines in EQUATIONS:
        render(stem, lines)
    print(f"\n총 {len(EQUATIONS)}개 생성")
