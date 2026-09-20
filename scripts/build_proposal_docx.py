"""공모전 제안서 Word 문서를 생성한다.

그림·수식은 docs/proposal_figures/ 에 있는 이미지를 본문 흐름 안에 끼워 넣는다
(뒤로 몰지 않는다). 본문 수치는 저장소 실측값이며, 각 값의 산출 근거는
scripts/build_proposal_figures.py 의 MEASURED 블록과 실행 결과에 있다.

    python scripts/build_proposal_figures.py
    python scripts/build_proposal_equations.py
    python scripts/build_proposal_docx.py [출력경로.docx]
"""

from __future__ import annotations

import sys
from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

REPO = Path(__file__).resolve().parent.parent
FIG = REPO / "docs" / "proposal_figures"
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else REPO / "docs" / "아쿠아가드_제안서.docx"

BODY_FONT = "맑은 고딕"
INK = RGBColor(0x11, 0x18, 0x27)
MUTED = RGBColor(0x60, 0x6B, 0x7A)
ACCENT = RGBColor(0x1D, 0x4E, 0xD8)

FIG_NO = {"n": 0}
EQ_NO = {"n": 0}
TBL_NO = {"n": 0}


# ---------------------------------------------------------------------------
# 문서 기본 설정
# ---------------------------------------------------------------------------
def build_document() -> Document:
    doc = Document()
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Cm(21.0), Cm(29.7)
    sec.left_margin = sec.right_margin = Cm(2.3)
    sec.top_margin = sec.bottom_margin = Cm(2.2)

    normal = doc.styles["Normal"]
    normal.font.name = BODY_FONT
    normal.font.size = Pt(10.5)
    normal.font.color.rgb = INK
    normal.element.rPr.rFonts.set(qn("w:eastAsia"), BODY_FONT)
    pf = normal.paragraph_format
    pf.line_spacing = 1.58
    pf.space_after = Pt(7)

    for name, size, color, before, after in [
        ("Heading 1", 16, ACCENT, 22, 9),
        ("Heading 2", 12.5, INK, 15, 6),
        ("Heading 3", 11, INK, 11, 4),
    ]:
        st = doc.styles[name]
        st.font.name = BODY_FONT
        st.font.size = Pt(size)
        st.font.bold = True
        st.font.color.rgb = color
        st.element.rPr.rFonts.set(qn("w:eastAsia"), BODY_FONT)
        st.paragraph_format.space_before = Pt(before)
        st.paragraph_format.space_after = Pt(after)
        st.paragraph_format.keep_with_next = True
    return doc


def _shade(cell, hex_color: str) -> None:
    el = OxmlElement("w:shd")
    el.set(qn("w:val"), "clear")
    el.set(qn("w:fill"), hex_color)
    cell._tc.get_or_add_tcPr().append(el)


def _run(p, text, *, bold=False, size=10.5, color=INK, italic=False):
    r = p.add_run(text)
    r.font.name = BODY_FONT
    r.font.size = Pt(size)
    r.font.bold = bold
    r.font.italic = italic
    r.font.color.rgb = color
    r._element.rPr.rFonts.set(qn("w:eastAsia"), BODY_FONT)
    return r


# ---------------------------------------------------------------------------
# 블록 헬퍼
# ---------------------------------------------------------------------------
class Doc:
    def __init__(self, doc: Document):
        self.d = doc

    def h1(self, text):
        self.d.add_heading(text, level=1)

    def h2(self, text):
        self.d.add_heading(text, level=2)

    def h3(self, text):
        self.d.add_heading(text, level=3)

    def p(self, text, *, size=10.5, color=INK, bold=False, align=None, space_after=7):
        par = self.d.add_paragraph()
        par.paragraph_format.space_after = Pt(space_after)
        if align is not None:
            par.alignment = align
        _run(par, text, bold=bold, size=size, color=color)
        return par

    def lead(self, text):
        """장 도입부 — 본문보다 조금 크게, 그 장에서 무엇을 말할지 한 문단."""
        par = self.p(text, size=11, color=INK)
        par.paragraph_format.space_after = Pt(11)
        return par

    def bullets(self, items, *, size=10.5):
        for it in items:
            par = self.d.add_paragraph(style="List Bullet")
            par.paragraph_format.space_after = Pt(3)
            par.paragraph_format.line_spacing = 1.45
            if isinstance(it, tuple):
                _run(par, it[0], bold=True, size=size)
                _run(par, it[1], size=size)
            else:
                _run(par, it, size=size)

    def figure(self, stem, caption, *, width_cm=15.6):
        path = FIG / f"{stem}.png"
        if not path.exists():
            raise FileNotFoundError(f"그림 없음: {path} — build_proposal_figures.py 먼저 실행")
        FIG_NO["n"] += 1
        par = self.d.add_paragraph()
        par.alignment = WD_ALIGN_PARAGRAPH.CENTER
        par.paragraph_format.space_before = Pt(9)
        par.paragraph_format.space_after = Pt(3)
        par.paragraph_format.keep_with_next = True
        par.add_run().add_picture(str(path), width=Cm(width_cm))
        cap = self.d.add_paragraph()
        cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
        cap.paragraph_format.space_after = Pt(13)
        _run(cap, f"[그림 {FIG_NO['n']}] {caption}", size=9, color=MUTED)
        return FIG_NO["n"]

    def equation(self, stem, caption, *, width_cm=13.4):
        path = FIG / f"{stem}.png"
        if not path.exists():
            raise FileNotFoundError(f"수식 없음: {path} — build_proposal_equations.py 먼저 실행")
        EQ_NO["n"] += 1
        par = self.d.add_paragraph()
        par.alignment = WD_ALIGN_PARAGRAPH.CENTER
        par.paragraph_format.space_before = Pt(8)
        par.paragraph_format.space_after = Pt(2)
        par.paragraph_format.keep_with_next = True
        par.add_run().add_picture(str(path), width=Cm(width_cm))
        cap = self.d.add_paragraph()
        cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
        cap.paragraph_format.space_after = Pt(12)
        _run(cap, f"[수식 {EQ_NO['n']}] {caption}", size=9, color=MUTED)
        return EQ_NO["n"]

    def table(self, headers, rows, caption, *, widths=None, font=9.5):
        TBL_NO["n"] += 1
        cap = self.d.add_paragraph()
        cap.paragraph_format.space_before = Pt(8)
        cap.paragraph_format.space_after = Pt(4)
        cap.paragraph_format.keep_with_next = True
        _run(cap, f"[표 {TBL_NO['n']}] {caption}", size=9, color=MUTED, bold=True)

        t = self.d.add_table(rows=1, cols=len(headers))
        t.style = "Table Grid"
        t.alignment = WD_TABLE_ALIGNMENT.CENTER
        for i, h in enumerate(headers):
            c = t.rows[0].cells[i]
            c.text = ""
            par = c.paragraphs[0]
            par.alignment = WD_ALIGN_PARAGRAPH.CENTER
            par.paragraph_format.space_after = Pt(2)
            par.paragraph_format.line_spacing = 1.2
            _run(par, h, bold=True, size=font)
            _shade(c, "EEF2F7")
        for row in rows:
            cells = t.add_row().cells
            for i, v in enumerate(row):
                cells[i].text = ""
                par = cells[i].paragraphs[0]
                par.paragraph_format.space_after = Pt(2)
                par.paragraph_format.line_spacing = 1.25
                _run(par, str(v), size=font)
        if widths:
            for r in t.rows:
                for i, w in enumerate(widths):
                    r.cells[i].width = Cm(w)
        self.d.add_paragraph().paragraph_format.space_after = Pt(7)
        return TBL_NO["n"]

    def note(self, text):
        """주의·한계를 적는 들여쓴 회색 박스형 문단."""
        par = self.d.add_paragraph()
        par.paragraph_format.left_indent = Cm(0.6)
        par.paragraph_format.space_before = Pt(5)
        par.paragraph_format.space_after = Pt(10)
        par.paragraph_format.line_spacing = 1.45
        pPr = par._p.get_or_add_pPr()
        bdr = OxmlElement("w:pBdr")
        left = OxmlElement("w:left")
        left.set(qn("w:val"), "single")
        left.set(qn("w:sz"), "18")
        left.set(qn("w:space"), "10")
        left.set(qn("w:color"), "D97706")
        bdr.append(left)
        pPr.append(bdr)
        _run(par, text, size=9.8, color=MUTED)
        return par

    def page_break(self):
        self.d.add_paragraph().add_run().add_break(WD_BREAK.PAGE)


# ---------------------------------------------------------------------------
# 본문
# ---------------------------------------------------------------------------
def write(D: Doc) -> None:
    d = D.d

    # ---------------- 표지 ----------------
    sp = d.add_paragraph()
    sp.paragraph_format.space_before = Pt(90)
    title = d.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title.paragraph_format.space_after = Pt(6)
    _run(title, "아쿠아가드 (AquaGuard AI)", bold=True, size=26, color=ACCENT)

    sub = d.add_paragraph()
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    sub.paragraph_format.space_after = Pt(30)
    _run(sub, "산불–호우 재해연쇄의 골든타임 회복 시스템", bold=True, size=14)

    pitch = d.add_paragraph()
    pitch.alignment = WD_ALIGN_PARAGRAPH.CENTER
    pitch.paragraph_format.space_after = Pt(42)
    pitch.paragraph_format.line_spacing = 1.75
    _run(pitch,
         "흩어진 위험 신호를 하나의 재해연쇄로 연결해\n"
         "‘어디가 위험한가’를 ‘지금 누구를 어디로 대피시켜야 하는가’로 바꾸고,\n"
         "그 판단이 실제 재난에서 몇 분 빨라지는지를 검증하는 의사결정 시스템",
         size=11.5, color=MUTED)

    D.table(
        ["구분", "내용"],
        [
            ("공모 분야", "디지털 기반 국가 사회현안 해결 서비스 — 아이디어 발굴(프로토타입 개발)"),
            ("공모 주제", "자연 재난 — 산사태 · 극한 호우(국지성 집중호우) · 홍수/침수"),
            ("대상 지역", "경남 산청군(주 사례) · 서울 강남구·서초구(확장성 검증)"),
            ("프로토타입", "Python 3.14 / FastAPI 백엔드 + Next.js·MapLibre 3D 대시보드, AWS 서울 리전 배포"),
            ("구현 현황", "9개 모듈 전부 구현 완료 · 자동화 테스트 491개 통과"),
            ("검증 현황", "산청 2025-07 leakage-free 백테스트 완료 — 음성 결과 포함 전량 공개"),
        ],
        "제안 개요",
        widths=[3.6, 12.0], font=10,
    )
    D.page_break()

    # ---------------- 1. 한 문장 ----------------
    D.h1("1. 제안의 핵심")

    D.lead("아쿠아가드는 새로운 산사태 위험지도가 아닙니다. 이 구분이 이 제안서 전체의 전제입니다.")

    D.p("산불위험·산사태·홍수 예측은 이미 각각 존재하고, 상당한 수준으로 운영되고 있습니다. "
        "산림청 산사태정보시스템은 예보발령·예측정보·실황정보·위기경보·대피소 검색을 제공하며, "
        "강우반영 산사태위험도에는 도로·건물·송전탑뿐 아니라 산불피해지도 이미 반영됩니다. "
        "미국 USGS 역시 화재 후 토석류(post-fire debris flow)의 발생확률과 부피를 burn severity·강우·유역 "
        "특성으로 평가해 운영하고 있습니다.")

    D.p("그러므로 “산불을 고려한 산사태 예측”은 우리의 독창성이 아닙니다. 그렇게 주장하지 않겠습니다.")

    D.p("우리가 채우려는 공백은 다른 곳에 있습니다. 위험도가 임계치를 넘은 그 순간부터 "
        "‘어떤 도로가 끊기고, 어떤 마을이 고립되며, 누구를 어느 대피소로 보내야 하는가’까지를 "
        "하나의 의사결정 패키지로 자동 생성하고, 그 판단이 실제 재난에서 몇 분 빨라질 수 있었는지를 "
        "숫자로 검증하는 시스템은 아직 없습니다.", bold=True)

    D.p("즉 아쿠아가드가 다루는 대상은 재난 자체가 아니라, 위험 신호와 실제 대피 사이에서 "
        "새어나가는 시간입니다.")

    # ---------------- 2. 배경 ----------------
    D.h1("2. 추진 배경 및 필요성")

    D.h2("2.1  2025년 산청 — 실패한 것은 예측이 아니었다")

    D.p("2025년 여름, 한반도는 한 시즌 안에 복합재해를 겪었습니다. 7월 16~20일 집중호우로 전국에서 "
        "37명이 사망하고 12,921명이 대피했으며 피해액은 1조 848억원을 기록했습니다.")

    D.p("가장 심각했던 곳은 경남 산청군입니다. 7월 19일 하루에 산사태 266건이 발생해 "
        "13명이 사망하고 1명이 실종됐습니다. 그런데 이 사건의 경과를 시간 순으로 놓아 보면 "
        "실패한 지점이 예측이 아니었다는 것이 드러납니다.")

    D.bullets([
        ("산림청은 이미 7월 17일에 ", "대피를 권고한 상태였습니다."),
        ("산사태 경보가 실제로 격상된 시각은 ", "7월 19일 12시 37분이었습니다."),
    ])

    D.p("위험 신호는 이미 존재했고, 그 신호가 판단·전파 단계를 지나는 동안 여러 시간이 새어나갔습니다. "
        "더 정확한 모델을 하나 더 만드는 것으로는 이 구간이 줄어들지 않습니다.", bold=True)

    D.figure("fig01_timeline", "2025년 산청 복합재해 타임라인과 회복 대상 구간")

    D.note("이 제안서는 “이 시스템이 있었다면 몇 명을 살릴 수 있었다”는 식의 주장을 하지 않습니다. "
           "그것은 대피 순응률·이동시간·현장 접근성을 모두 검증해야 성립하는 인과 주장이기 때문입니다. "
           "우리가 증명하려는 것은 “공식 경보보다 N분 빠른 실행 가능한 신호를 냈고, 그 시점에는 "
           "아직 안전한 경로가 남아 있었다”까지입니다.")

    D.h2("2.2  산불 흉터가 만든 취약 사면 — 그리고 우리가 확인하지 못한 것")

    D.p("산청군은 이 산사태 4개월 전인 2025년 3월, 경남·경북 11개 지역 48,238ha를 태운 대형 산불의 "
        "피해지였습니다. 산불로 훼손된 사면은 두 가지를 동시에 잃습니다. 나무 뿌리가 흙을 붙잡아 주던 "
        "결속력과, 토양이 빗물을 흡수하던 능력입니다. 국내 실측에서 화재 2년 후까지도 토양유출량이 "
        "일반 산림 대비 3~4배 높게 유지되고, 화재 6개월 후 강우 침투속도가 2배 이상 빨라진다는 결과가 "
        "보고돼 있습니다.")

    D.p("그러나 이 물리가 산청의 7월 산사태에 실제로 작동했는지는 별개의 질문이고, 저희는 그것을 "
        "직접 검정했습니다. 결과는 불지지였습니다.", bold=True)

    D.p("흉터와 산사태 발생 기록의 공간 중첩을 모형을 거치지 않고 관측 대 관측으로 본 결과, "
        "산사태 가중 평균 산불노출은 5.885%로 전체 급사면 기저 7.190%보다 오히려 낮았습니다"
        "(농축배수 0.82배). 읍면·리 단위 상관도 모두 유의하지 않았습니다(Spearman p = 0.47~0.58).")

    D.p("원인은 참값에 있습니다. 단성면은 산사태 99건으로 가장 많은데 흉터는 3.6%뿐이고, 금서면은 "
        "흉터 4.8%인데 산사태가 0건입니다. 피해기록이 급사면이 아니라 거주지 분포를 따라가고 있습니다. "
        "즉 이 참값은 산불–산사태 가설을 검정할 검정력 자체가 없습니다 — 물리를 반증한 것이 아니라, "
        "검정하지 못한 것입니다.")

    D.p("그래서 이 제안서는 산청을 ‘산불 증폭 사례’가 아니라 의사결정 지연 사례로 다룹니다. "
        "산불 기여의 근거는 관측 상관이 아니라 모형 내부의 절제 실험(§5.1)에서 가져옵니다. "
        "발생부(source area) 좌표를 확보하면 같은 스크립트로 즉시 재검정되며, 산림청·국립산림과학원에 "
        "공식 요청서를 제출해 둔 상태입니다.")

    D.h2("2.3  재해연쇄를 끝까지 추적하는 시스템이 없다")

    D.p("문제는 이 연결이 산사태에서 끝나지 않는다는 데 있습니다. 산사태는 하류 하천의 유사량을 늘려 "
        "범람 위험을 높이고, 범람과 토사는 도로를 끊으며, 도로가 끊기면 마을이 고립됩니다. "
        "고립은 대피가 불가능해지는 지점이고, 재난 대응에서 가장 늦게 발견되는 상태입니다.")

    D.figure("fig02_disaster_chain", "재해연쇄 모델과 모듈 대응 구간")

    D.p("현재 운영 중인 시스템들은 이 사슬의 앞 두세 칸을 각각 잘 담당합니다. 그러나 사슬 전체를 "
        "하나의 상태로 이어 마지막 칸인 ‘고립’까지 계산하는 시스템은 확인되지 않습니다. "
        "아쿠아가드의 기여는 새로운 칸을 만드는 것이 아니라 칸들을 이어붙이는 데 있습니다.")

    # ---------------- 3. 독창성 ----------------
    D.h1("3. 아이디어의 독창성")

    D.lead("기능 하나하나가 세계 최초여서 강한 제안이 아닙니다. 여러 기존 기술을 행정 의사결정 "
           "흐름으로 연결하는 방식이 강점입니다. 그래서 먼저 우리가 주장하지 않는 것부터 적습니다.")

    D.h2("3.1  우리가 독창성으로 주장하지 않는 것")

    D.table(
        ["요소", "판정", "근거"],
        [
            ("강우 기반 산사태 위험", "이미 존재", "산림청이 실시간·예측 위험정보를 운영 중"),
            ("산불 피해지 반영 산사태 위험", "이미 존재", "산림청 강우반영 위험도에 산불피해지 반영이 명시됨"),
            ("화재 후 토석류 확률·부피", "이미 존재", "USGS post-fire debris flow 평가체계 운영"),
            ("토석류 downstream runout", "연구·운영 시작", "USGS가 별도 데이터셋으로 제공"),
            ("실시간 침수 GIS", "이미 존재", "동일 공모전 2023년 수상작에 선례 존재"),
            ("대피소 검색", "이미 존재", "산림청 시스템이 위치기반 대피소 검색 제공"),
        ],
        "선행 기술 인정 — 이 항목들은 우리의 차별점이 아니다",
        widths=[5.6, 2.8, 7.2],
    )

    D.h2("3.2  실제 차별점 세 가지")

    D.p("반대로 다음 세 가지는 조합 자체가 새롭거나, 기존 시스템이 명시적으로 다루지 않는 영역입니다.")

    D.h3("① 재해연쇄를 하나의 상태머신으로 연결")
    D.p("산불 흉터 → 산사태 → 하천 범람 → 도로 단절 → 마을 고립이라는 인과 사슬을 개별 모듈로 "
        "나누되, 하나의 오케스트레이터가 순서대로 통과시킵니다. 개별 요소는 기존 기술이지만 "
        "통합 워크플로 자체가 차별점입니다.")

    D.h3("② 도로 위험 제거 후의 대피소 연결성 판정")
    D.p("실제 도로망 그래프에서 위험 폴리곤과 겹치는 링크를 제거한 뒤, 어느 대피소로도 경로가 "
        "남지 않는 건물 군집을 그래프 알고리즘으로 찾아냅니다. 이것은 위험도 표시가 아니라 "
        "대피 가능성 판정이며, 상용 GIS 시각화 도구가 기본 제공하지 않는 계산입니다.")

    D.h3("③ 행정 의사결정 지연 시간의 정량화")
    D.p("모델이 처음 임계치를 넘은 시각과 실제 공식 경보 시각의 차이를 측정 대상 지표로 삼습니다. "
        "단순한 위험도가 아니라 decision latency를 재는 것이며, 이것이 아쿠아가드가 "
        "‘위험지도’가 아니라 ‘의사결정 시스템’인 이유입니다.")

    # ---------------- 4. 구조 ----------------
    D.h1("4. 서비스 구조와 프로토타입 구현")

    D.h2("4.1  전체 아키텍처")

    D.p("시스템은 9개 모듈로 나뉩니다. 예측을 담당하는 앞단(A·B·C), 전체를 순서대로 호출하는 "
        "오케스트레이터(O), 결과를 실제 의사결정 재료로 바꾸는 뒷단(D·E·G·H), 그리고 예측이 맞았는지를 "
        "사후에 채점하는 검증 엔진(V)입니다.")

    D.figure("fig03_architecture", "아쿠아가드 시스템 아키텍처 및 데이터 흐름", width_cm=15.2)

    D.h2("4.2  모듈별 역할과 구현 상태")

    D.p("어디까지가 실제로 동작하고 어디부터가 아직 목업인지를 그대로 적습니다. "
        "이 구분은 시스템이 스스로도 표기합니다 — 서버의 상태 확인 응답이 어느 모듈이 실물이고 "
        "어느 것이 예시값인지를 반환합니다.")

    D.table(
        ["모듈", "역할", "주요 산출", "상태"],
        [
            ("A 산사태", "무한사면 안전율(FoS) 기반 확률 산출", "landslide_prob, hours_to_critical", "구현 완료 (601줄 + 스크립트 1,157줄)"),
            ("B 하천범람", "SFINCS·ANUGA 물리모형 2종 + 계약 래핑", "flood_prob, 침수범위", "구현 완료 (369줄 + 스크립트 1,476줄)"),
            ("C 도로·지하차도", "규칙기반 판정(예측 모델 아님)", "alert_level 4단계", "구현 완료 (598줄)"),
            ("D 노출자산", "위험 폴리곤 ∩ 건축물·농경지 공간연산", "노출 건물, 노출 농경지 면적", "구현 완료 (849줄)"),
            ("E 대피경로·고립", "실도로 경로 + 도로망 그래프 고립 탐지", "경로, 고립 구역", "구현 완료 (524줄)"),
            ("G 피해비용", "국토부·농식품부 고시 단가 기반 산정", "추정 피해액, 범위", "구현 완료 (459줄)"),
            ("H 시민 역검증", "시민 신고를 shrinkage 집계로 신뢰도 보정", "검증 상태, 확률 보정량", "구현 완료 (703줄)"),
            ("O 오케스트레이터", "위 전부를 순서대로 호출해 경보 패키지 생성", "alert_package", "구현 완료 (728줄)"),
            ("V 검증 엔진", "예측 폴리곤 vs 사후 SAR 관측 자동 대조", "IoU, F1, Recall, lead time", "구현 완료 (322줄 + 스크립트 451줄)"),
        ],
        "모듈별 역할과 2026-09-20 기준 구현 상태 — 9개 모듈 전부 구현 완료 (줄 수는 테스트 제외)",
        widths=[2.6, 5.0, 3.9, 4.1], font=9,
    )

    D.figure("fig04_implementation", "모듈별 구현 코드량과 테스트 통과 수")

    D.note("Module E는 구현이 완료됐지만 자동화 테스트가 아직 없습니다(전체 491개 중 0개). "
           "트랙④가 소유한 모듈이며 10월 중 테스트 작성이 예정돼 있습니다. 표에 그대로 적어 둡니다.")

    D.h2("4.3  모듈 간 계약 — 실패를 설계에 포함한다")

    D.p("모든 모듈은 JSON Schema로 입출력이 고정되어 있고, 공통된 응답 봉투를 씁니다. "
        "상태(ok/degraded/error), 몇 순위 데이터로 계산했는지를 나타내는 폴백 등급, 데이터, "
        "사람이 읽을 수 있는 경고 네 가지입니다.")

    D.p("이 구조의 핵심은 모듈이 예외를 바깥으로 던지지 않는다는 데 있습니다. 실패는 예외가 아니라 "
        "‘등급이 내려간 결과 + 경고’로 표현되고, 상위 모듈이 그 등급을 이어받습니다. "
        "재난 상황에서 입력 하나가 결측됐다고 전체 파이프라인이 멈추면 안 되기 때문입니다.", bold=True)

    D.p("각 계약의 예시 파일은 자기 입력으로 자기 출력을 실제로 재현할 수 있는지가 테스트로 "
        "고정되어 있습니다. 문서와 코드가 어긋나는 것을 구조적으로 막기 위한 장치입니다.")

    # ---------------- 5. 산식 ----------------
    D.h1("5. 핵심 산식")

    D.lead("판단의 근거가 되는 계산을 모두 식으로 제시합니다. 각 식에는 그 값이 공식 출처에서 "
           "온 것인지, 유도한 것인지, 아직 가정치인지를 함께 적습니다.")

    D.h2("5.1  화재흉터 증폭계수")

    D.p("산불 피해 사면의 취약성 증가를 시간에 따라 감쇠하는 증폭계수로 표현합니다. "
        "dNBR(정규화 연소비율 차분) 등급이 높을수록 초기 증폭이 크고, 식생이 회복되면서 "
        "시간이 지날수록 1에 수렴합니다.")

    D.equation("eq1_amplification", "화재흉터 증폭계수의 시간 감쇠", width_cm=11.4)

    D.figure("fig07_amplification", "화재흉터 증폭계수 f(dNBR, Δt)의 시간 감쇠", width_cm=13.6)

    D.note("A_max 등급값(low 1.2 / moderate 2.0 / high 3.5~4.0)은 국내외 문헌값을 가져다 쓴 "
           "가정치이며, 아직 한국 데이터로 사후검증된 계수가 아닙니다. 발표에서 이 수치를 "
           "‘검증된 한국형 계수’라고 말하지 않습니다.")

    D.h3("절제 실험 — 산불을 빼면 신호가 죽는가")

    D.p("계수를 문헌에서 가져왔다면 그것이 실제로 기여하는지는 따로 증명해야 합니다. 산불은 이 모형에 "
        "뿌리점착력 약화라는 한 경로로만 들어가므로, 계수 f만 1로 바꾼 반사실(fire_off) 시나리오와 "
        "비교하면 기여도가 순수하게 분리됩니다.")

    D.figure("fig16_ablation", "산불 기여도 분리 실험 — 지반 시나리오 B_weathered", width_cm=15.4)

    D.p("산청 2025-07-19 기준으로 peak 임계초과율이 0.479%에서 0.899%로 1.88배 올랐고, "
        "절대문턱 0.05%에서는 탐지 시각이 8시간 앞당겨졌습니다. 문턱 0.50%는 산불을 빼면 "
        "아예 도달하지 못합니다. 즉 이 사건에서 산불 흉터는 장식이 아니라 신호의 실질적 구성요소입니다.",
        bold=True)

    D.note("이 실험은 방법론 결함도 하나 드러냈습니다. 기존 T_agent 정의(임계초과율이 당일 최대의 "
           "50%에 도달한 시각)는 자기정규화 지표여서, 위험도장을 통째로 몇 배 키우거나 줄여도 시각이 "
           "변하지 않습니다. 실제로 산불을 완전히 제거해도 T_agent가 09:00으로 동일하게 나왔습니다. "
           "이 정의로는 어떤 절제 실험도 효과를 잡을 수 없으며, 시나리오 비교에는 절대문턱만 "
           "유효합니다. 이 사실 자체가 실험의 산출물입니다.")

    D.h2("5.2  무한사면 안전율")

    D.p("산사태 판단의 기본은 물리 모형입니다. 기계학습을 먼저 쓰지 않고 무한사면 안전율(FoS, "
        "TRIGRS의 원리)을 먼저 계산한 뒤, 학습 모델은 그 위에 보정용으로만 얹는 순서를 택했습니다. "
        "근거를 설명할 수 없는 확률값은 재난 의사결정에 쓸 수 없기 때문입니다.")

    D.equation("eq2_infinite_slope", "무한사면 안전율 (Infinite Slope)", width_cm=12.6)

    D.p("안전율이 1보다 작으면 불안정한 상태입니다. 산불 피해 사면에서는 뿌리 점착력 c′가 "
        "감소하고 침투 증가로 간극수압 u가 상승해, 분자가 양쪽에서 동시에 줄어듭니다. "
        "5.1의 증폭계수는 이 물리적 변화를 계수 형태로 근사한 것입니다.")

    D.h2("5.3  도로·지하차도 규칙 판정")

    D.p("Module C는 예측 모델이 아닙니다. 관측된 강우에 공식 기준 임계값을 적용하는 결정론적 "
        "분류입니다. 그래서 화면에서도 다른 모듈과 구분되는 배지를 답니다(10.1 참조).")

    D.equation("eq3_rule_level", "지하차도 경보 등급 판정 규칙", width_cm=13.8)

    D.p("임계값은 기상청 기상특보 발표기준(호우주의보 3시간 60mm, 호우경보 3시간 90mm)을 "
        "시간 균등환산한 값과, 극한호우 긴급재난문자 기준(1시간 72mm)에서 유도했습니다. "
        "원출처를 직접 접속 검증했고 보도 2건으로 교차 확인했습니다.")

    D.figure("fig05_module_c_rules", "Module C 규칙 판정면과 임계값 근거", width_cm=15.0)

    D.note("배수등급 가중치(low 1.3 / medium 1.0 / high 0.85)와 지정위험 가중(1.15)은 아직 공식 출처를 "
           "찾지 못해 정책 파일에 PLACEHOLDER로 표기돼 있습니다. 또한 공식 기준은 3시간·12시간 누적인데 "
           "계약 입력에는 1시간 강우강도만 있어, 시간 균등환산이라는 가정이 남습니다. "
           "그래서 이 행들의 상태는 ‘확인됨(CONFIRMED)’이 아니라 ‘유도됨(DERIVED)’입니다.")

    D.h2("5.4  노출자산 공간연산")

    D.p("위험 폴리곤과 실제 건축물·농경지 레이어를 교차해 노출 자산을 산출합니다. "
        "건물은 개수로, 농경지는 면적으로 집계합니다.")

    D.equation("eq4_exposure", "노출 건물 집합과 노출 농경지 면적", width_cm=13.2)

    D.h2("5.5  피해비용 추정")

    D.p("피해액은 고시 단가를 기준으로 산정하되, 점추정과 상한을 나누어 제시합니다. "
        "용도가 확인되지 않은 건물을 점추정에 넣으면 값이 부풀기 때문에 제외하고, "
        "그 건물들이 모두 주거로 판명될 경우를 상한 구간으로만 반영합니다.")

    D.equation("eq5_damage_cost", "피해비용 점추정과 상한", width_cm=13.4)

    D.table(
        ["항목", "근거 고시", "단가", "상태"],
        [
            ("주택 침수", "국토교통부고시 제2026-90호 (시행 2026-02-19)", "3,500,000원/세대", "CONFIRMED"),
            ("농작물 대파대", "농림축산식품부고시 제2026-78호 (시행 2026-07-30)", "381원/㎡", "CONFIRMED"),
        ],
        "피해비용 단가의 공식 근거 — 원문 PDF를 저장소에 함께 보관",
        widths=[2.8, 7.4, 3.2, 2.2],
    )

    D.p("두 고시 모두 원문 PDF를 저장소에 그대로 두고, 정책 파일의 각 행이 그 파일 경로와 조항을 "
        "직접 참조합니다. 각 고시 제3조의 재검토 기한(3년)도 함께 기록해 두어 단가가 만료되면 "
        "드러나게 했습니다.")

    D.note("이 단가는 복구비 ‘지원’ 단가이므로 실제 경제적 손실의 하한입니다. 또한 점추정에는 "
           "‘주거 건물 1동 = 1세대’라는 가정이 들어갑니다(공동주택 세대수 미반영). "
           "화면에서는 이 가정이 별도 칩으로 표시되며, 건축물대장의 세대수를 확보하면 해소됩니다.")

    D.h2("5.6  시민 신고의 역검증")

    D.p("시민 신고는 유용하지만 소수의 신고가 확률을 크게 흔들면 위험합니다. 그래서 분모에 "
        "상수 k를 더하는 shrinkage 집계를 씁니다. 신고 1~2건으로는 최대 보정이 나오지 않고, "
        "건수가 쌓일수록 보정이 실제 비율에 수렴합니다.")

    D.equation("eq6_shrinkage", "시민 신고의 shrinkage 집계", width_cm=13.0)

    D.p("분모의 +k가 핵심입니다. 신고 한두 건으로는 최대 보정이 나오지 않고, 건수가 쌓일수록 "
        "보정이 실제 비율에 수렴합니다. 이 설계가 없으면 소수의 오신고나 중복 신고가 "
        "위험도를 크게 흔들 수 있습니다.")

    D.figure("fig08_shrinkage", "시민 역검증의 shrinkage 집계 곡선", width_cm=14.4)

    D.h2("5.7  골든타임 지표")

    D.p("이 시스템이 최종적으로 주장하려는 값입니다. 중요한 것은 이를 하나의 숫자로 뭉뚱그리지 "
        "않는 것입니다. ‘재난을 얼마나 먼저 맞혔는가’와 ‘행정 의사결정 시간을 얼마나 되찾았는가’는 "
        "서로 다른 지표이며, 섞어 쓰면 검증 가능성이 사라집니다.")

    D.equation("eq7_golden_time", "골든타임 관련 두 지표의 정의", width_cm=14.2)

    D.p("예를 들어 모델이 08시 10분에 위험을 냈고 피해가 10시 30분, 공식 경보가 12시 37분이었다면 "
        "‘2시간 20분 먼저 재난을 맞혔다’와 ‘4시간 27분의 행정 의사결정 시간을 회복했다’는 "
        "서로 다른 주장입니다. 두 값을 섞어 하나의 헤드라인 숫자로 만들면 검증이 불가능해집니다.")

    # ---------------- 6. 데이터 ----------------
    D.h1("6. 데이터")

    D.h2("6.1  공간 데이터")

    D.table(
        ["데이터", "출처", "용도"],
        [
            ("건물통합정보 (LT_C_SPBD)", "국토교통부 / 브이월드", "건물 footprint, 노출자산"),
            ("표준노드링크 (LT_L_MOCTLINK)", "국가교통정보센터 / 브이월드", "도로망, 고립 탐지"),
            ("하천망 (LT_C_WKMSTRM)", "브이월드", "하천 폴리곤"),
            ("행정경계 3계층", "SGIS 기반 (BND_ADM_DONG_PG)", "시도/시군구/읍면동 검색·경계"),
            ("지진옥외대피소 (2,604곳)", "행정안전부 재난안전데이터공유플랫폼", "대피소 후보"),
            ("팜맵(FarmMap)", "농림수산식품교육문화정보원", "농경지 필지"),
            ("건축물대장 표제부", "국토교통부 (data.go.kr)", "건물 주용도 조인"),
            ("지형 타일", "AWS Terrain Tiles (공개)", "3D 지형"),
            ("위성영상", "Esri World Imagery", "3D 지도 배경"),
        ],
        "사용 중인 공간 데이터와 출처",
        widths=[5.4, 5.8, 4.4],
    )

    D.h2("6.2  AOI 설계 — 경계로 자르지 않은 이유")

    D.p("전국 원본은 용량이 커서 분석 대상 구역(AOI)만 잘라 사용합니다. 그런데 산청 AOI를 "
        "행정경계가 아니라 경보지점 반경으로 자른 데에는 이유가 있습니다.")

    D.p("행정경계로 자르면 경계 근처에서 위험영역이 밖으로 새어 노출자산이 조용히 누락됩니다. "
        "실제로 측정해 보니 생비량면(44km²)으로 잘랐을 때 6km 위험영역의 18%가, 산청군 전체(790km²)로 "
        "넓혀도 12%가 경계 밖이었습니다. 데모 좌표가 군 동쪽 경계에서 5.4km 지점이기 때문입니다. "
        "반경 12km로 자르면 그 누락이 0이 됩니다.")

    D.figure("fig11_aoi_coverage", "AOI 데이터 규모와 건물 주용도 조인 커버리지")

    D.p("건물 주용도는 건축물대장 표제부를 25자리 건물관리번호의 앞 19자리(필지키)로 조인해 채웁니다. "
        "현재 커버리지는 산청 63.1%, 강남·서초 86.2%입니다. 조인되지 않은 건물은 ‘미상’으로 두고 "
        "피해비용 점추정에서 제외합니다 — 추정해서 채우지 않습니다.")

    # ---------------- 7. 실제 산출 ----------------
    D.h1("7. 검증 — 산청 2025 백테스트")

    D.lead("이 장이 이 제안서에서 가장 중요합니다. 결과의 상당수가 음성(negative)이고, 그 이유가 "
           "모형인지 참값인지 분리할 수 없다는 사실까지 포함해 그대로 적습니다. 유리한 숫자만 떼어 "
           "쓰면 아래에 적은 오독 목록에 그대로 걸립니다.")

    D.h2("7.1  설계 — data leakage 금지")

    D.p("시각 t에서 시스템이 보는 데이터는 그 시각 이전에 실제로 이용 가능했던 정보로만 제한했습니다. "
        "7월 19일 이후에 확정된 산사태 위치나 피해지도를 입력에 섞으면 그 순간 백테스트 전체가 "
        "무의미해지기 때문입니다. 위성자료는 Copernicus Data Space와 Microsoft Planetary Computer에서 "
        "직접 받아 처리했습니다.")

    D.h2("7.2  골든타임 — 두 지표를 분리한다")

    D.p("§5.7에서 정의한 두 지표를 실제로 측정했습니다. 결과는 한쪽은 성립하고 한쪽은 성립하지 "
        "않습니다.")

    D.figure("fig15_goldentime", "산청 백테스트 실측 — decision latency와 hazard lead", width_cm=15.2)

    D.table(
        ["지표", "값", "의미", "판정"],
        [
            ("decision latency", "+3.62 h (217분)", "공식 경보 12:37보다 이만큼 빨랐다", "성립"),
            ("hazard lead 상한", "−1.00 h", "최초 신고 08:00보다 1시간 늦었다", "미성립"),
        ],
        "골든타임 두 지표의 실측 결과 (T_agent = 09:00)",
        widths=[3.4, 3.0, 6.6, 2.6],
    )

    D.p("따라서 “붕괴보다 3.6시간 먼저 탐지했다”는 말은 틀립니다. “공식 경보보다 3.6시간 먼저”가 "
        "맞는 표현이며, 이 제안서와 발표에서는 후자만 씁니다.", bold=True)

    D.p("절대문턱을 쓰면 더 이른 신호도 얻을 수 있습니다. 최초 신고를 앞서면서 경보가 안정적인"
        "(지속률 ≥ 0.8) 조합이 7개 있고, 그중 지반 시나리오 B_weathered·문턱 0.10%가 "
        "decision latency 5.62시간 / hazard lead 상한 +1.0시간으로 가장 방어 가능합니다.")

    D.note("실제 붕괴 시각 T_event는 확보하지 못했습니다. 산림청 피해기록 362건에 발생일시 필드가 "
           "없고(리 단위 집계) 발생부 좌표도 없기 때문입니다. 그래서 점추정 대신 최초 신고 08:00을 "
           "상한으로 묶어 보고합니다 — hazard lead의 실제 값은 표기값보다 작거나 같습니다.")

    D.h2("7.3  산사태 예측력 — 현재 참값으로는 검증 불가")

    D.p("1km 격자 838개(급사면 200px 이상), 양성 54개를 대상으로 공간분할 검증을 수행했습니다. "
        "이 모형은 적합할 계수가 없는 물리식이므로 분할은 훈련/시험 분리가 아니라 "
        "‘이 예측력이 특정 읍면 하나가 만든 착시인가’를 보는 점검입니다.")

    D.figure("fig18_landslide_honesty", "산사태 예측력 검증의 음성 결과", width_cm=15.2)

    D.table(
        ["분할", "AUPRC", "비고"],
        [
            ("전체", "0.0606 (기저 0.0644, ROC-AUC 0.469)", "lift 0.94 — 무작위 이하"),
            ("무작위 5-fold", "0.074 ± 0.031", "공간자기상관으로 낙관 편향"),
            ("읍면 leave-one-out", "중앙값 0.072", "lift > 1인 읍면 6/9"),
        ],
        "산사태 예측력 — 공간분할별 AUPRC",
        widths=[3.6, 6.4, 5.6],
    )

    D.p("전역으로는 무기력하고 국지적으로만 약한 신호가 남습니다. 읍면별로는 단성(1.37)·시천(1.33)·"
        "삼장(1.21)에서 lift가 1을 넘고 신안(0.87)·차황(0.89)에서 1 미만입니다.")

    D.p("이 결과를 감추지 않는 이유는 분명합니다. 현재 참값이 발생부가 아니라 피해 집계 마을이라 "
        "모형 성능과 참값 품질을 분리할 수 없습니다. 발생부 좌표가 확보되면 같은 스크립트로 즉시 "
        "재검정되며, 그 전까지는 “산사태 예측이 검증됐다”고 말하지 않습니다.", bold=True)

    D.h2("7.4  물리 위 ML 보정 — 사전등록 기준으로 기각")

    D.p("물리 점수에 지형 변수를 더한 학습 모델이 성능을 올리는지 평가했습니다. 사후에 기준을 바꾸지 "
        "않기 위해 채택 기준을 먼저 등록하고 시작했습니다 — 공간CV AUPRC 중앙값이 물리단독보다 높고 "
        "Wilcoxon p < 0.05일 때만 채택.")

    D.figure("fig19_ml_rejected", "사전등록 기준에 따른 ML 보정 기각", width_cm=14.6)

    D.p("로지스틱 회귀는 중앙값이 0.072에서 0.130으로 거의 두 배가 됐지만 p = 0.074로 기준에 "
        "못 미쳐 기각했고, 물리단독을 유지했습니다. 읍면이 9개뿐이라 검정력이 낮습니다 — 방향은 "
        "긍정적이지만 근거가 부족합니다.")

    D.p("기각한 이유는 통계만이 아닙니다. 참값이 거주지 분포를 따라가므로(§2.2) 여기에 학습을 맞추면 "
        "모형은 산사태가 아니라 ‘사람이 사는 곳’을 학습합니다. 표면 점수는 올라도 산사태 예측력은 "
        "떨어질 수 있어, 학습된 가중치는 배포하지 않았습니다.")

    D.h2("7.5  하천범람 — 제대로 된 물리 참값이 있는 쪽")

    D.p("산사태와 달리 하천범람에는 수위계 실측과 독립 엔진 2종이라는 제대로 된 참값이 있습니다. "
        "SFINCS와 ANUGA를 각각 구축해 서로 대조하고, 경호교 수위계와 Sentinel-1 SAR 관측에 "
        "함께 맞춰 봤습니다.")

    D.figure("fig17_flood_validation", "Module B 하천범람 엔진 교차검증", width_cm=15.2)

    D.table(
        ["지표", "SFINCS", "ANUGA v1", "해석"],
        [
            ("vs SAR IoU", "0.363", "0.359", "초목 계곡에서 SAR이 과소탐지 — 센서 한계"),
            ("vs SAR F1", "0.533", "0.529", "두 엔진이 거의 동일"),
            ("경호교 수위 RMSE", "1.42 m", "2.48 m", "SFINCS가 더 정확"),
            ("엔진 교차 IoU", "0.775", "—", "독립 구현 2종이 서로 일치 — 주검증"),
        ],
        "Module B 하천범람 검증 (관측 침수 5.75km², 공통 50m 격자)",
        widths=[3.6, 2.6, 2.6, 6.8],
    )

    D.p("SAR 대비 IoU가 0.36에 머무는 것은 모형 오차가 아니라 초목이 덮인 계곡에서 SAR이 수면을 "
        "놓치는 센서 한계입니다. 그래서 주검증은 2엔진 교차(0.775)와 수위계(RMSE 1.42m)로 "
        "삼았습니다.")

    D.h2("7.6  검증 엔진은 만능이 아니다")

    D.p("Module V는 같은 코드로 두 재해를 채점합니다. 그 결과 차이 자체가 정보입니다.")

    D.figure("fig20_module_v", "Module V 검증 엔진의 재해별 결과 차이", width_cm=14.4)

    D.p("하천범람은 IoU 0.32 · F1 0.485 · lead time 217분으로 의미 있는 값이 나오지만, 같은 엔진을 "
        "산사태에 돌리면 IoU 0.0038로 사실상 신호가 없습니다. 강우 후 토양수분과 식생 위상이 섞여 "
        "SAR 변화의 잡음이 크기 때문입니다. 화면에도 두 값을 나란히 띄워 이 차이를 숨기지 않습니다.")

    D.h2("7.7  발표 전 점검 — 하면 안 되는 말")

    D.table(
        ["하면 안 되는 말", "왜 틀렸나", "맞는 말"],
        [
            ("붕괴보다 3.6시간 먼저 탐지", "3.6h는 공식 경보 대비. 붕괴 대비는 −1h", "공식 경보보다 3.6시간 먼저"),
            ("AUC 0.91", "UI 목업값이었다", "ROC-AUC 0.469 — 현 참값으로는 검증 불가"),
            ("산불–산사태 연관 입증", "ρ≈0, 농축 0.82배", "현 참값으로는 확인 불가. 물리 근거는 문헌과 절제 실험"),
            ("ML로 성능 개선", "p = 0.074로 기각", "평가했으나 기준 미달로 기각, 물리단독 유지"),
            ("미보정 파라미터 없음", "Rsat·Wmax·시그모이드 k 전부 미보정", "발생부 좌표 확보 시 보정 예정"),
        ],
        "검증 결과의 오독을 막기 위한 대조표",
        widths=[4.2, 5.4, 6.0],
    )

    D.note("UI의 모델 성능 패널은 2026-09-20에 목업값을 실제값으로 교체했습니다 — 산사태 ROC-AUC "
           "0.91 → 0.469, precision 0.86 → 0.068. 목업 숫자를 그대로 두고 발표하면 성능 조작이 "
           "되기 때문입니다. 두 패널 모두 지표 위에 참값 한계 배너를 상시 노출합니다.")

    D.h1("8. 하위 모듈의 산출 — 위험영역이 주어졌을 때")

    D.lead("위 검증은 예측 앞단(A·B)의 이야기입니다. 위험영역이 정해진 다음 단계 — 노출자산·피해비용·"
           "대피경로 — 는 별도로 검증됩니다. 이 값들은 공간연산과 고시 단가의 결과라 모형 정확도와 "
           "독립입니다.")

    D.figure("fig06_exposure_and_cost",
             "노출자산 용도별 구성과 피해비용 — 위험영역을 명시적으로 주었을 때의 산출")

    D.table(
        ["산출 항목", "값", "산출 모듈"],
        [
            ("노출 건물", "351동 (주거 202 · 미상 88 · 상업 24 · 공업 23 · 농업 10 · 공공 4)", "Module D"),
            ("노출 농경지", "43.4 ha", "Module D"),
            ("피해비용 점추정", "872,354,000원", "Module G"),
            ("피해비용 상한", "1,134,060,200원", "Module G"),
            ("지하차도 경보", "위험 (강우 45mm/h · 배수 low · 지정위험)", "Module C"),
        ],
        "위험영역이 주어졌을 때 하위 모듈의 산출 (커밋된 실데이터로 실제 실행)",
        widths=[3.4, 8.4, 3.8],
    )

    D.note("이 표의 입력 위험영역은 contracts/module_a.example.json이 문서화한 폴리곤(데모 AOI 내 "
           "2km×2km)입니다. 실모델 A가 이 영역을 산출했다는 뜻이 아닙니다 — 현재 데모 입력에는 "
           "부지 토양이 주입되지 않아 Module A가 tier 2 폴백으로 내려가고, 운영 임계 0.7을 넘지 "
           "못합니다. 하위 모듈의 산출 능력과 예측 앞단의 성능을 분리해서 읽어 주십시오.")

    # ---------------- 8. 사용자 ----------------
    D.h1("9. 사용자와 활용 시나리오")

    D.p("같은 경보 패키지를 읽지만 사용자가 던지는 질문이 다르기 때문에 화면을 두 모드로 나눴습니다. "
        "데이터를 두 벌 만들지 않고 표현만 나누므로, 한쪽에서 확인된 값이 다른 쪽과 어긋날 수 없습니다.")

    D.figure("fig13_two_modes", "시민 모드와 관공서 모드의 기능 분리", width_cm=15.2)

    D.h2("9.1  활용 시나리오 — 산청 재연")

    D.bullets([
        ("① 관측 — ", "산불 흉터(dNBR)와 누적 강우가 입력되고, Module A가 안전율 임계를 넘는 시각을 포착합니다."),
        ("② 노출 판정 — ", "위험 폴리곤과 건축물·농경지를 교차해 몇 동·몇 ha가 걸리는지 즉시 산출합니다."),
        ("③ 경로 판정 — ", "위험구간과 겹치는 도로 링크를 제거한 뒤 대피소 도달 가능성을 다시 계산합니다."),
        ("④ 고립 탐지 — ", "어느 대피소로도 경로가 남지 않는 건물 군집이 ‘고립 위험’으로 표시됩니다."),
        ("⑤ 경보 초안 — ", "담당자 화면에 근거가 붙은 경보 초안이 생성되고, 승인 전까지는 권고 상태입니다."),
        ("⑥ 시간 비교 — ", "실제 공식 경보 시각과 대조해 되찾은 시간을 분 단위로 표시합니다."),
    ])

    # ---------------- 9. 신뢰성 ----------------
    D.h1("10. 신뢰성 설계")

    D.lead("재난 시스템에서 가장 위험한 것은 모델의 낮은 정확도가 아니라, 결과를 실제보다 확실한 것처럼 "
           "포장하는 것입니다. 이 프로젝트가 가장 공들인 부분이 여기입니다.")

    D.h2("10.1  Provenance 배지 — 모든 숫자에 출처를 붙인다")

    D.p("화면의 모든 값에는 그 값이 어떻게 산출됐는지를 나타내는 배지가 반드시 붙습니다. "
        "실측(OBSERVED), 외부 예보(FORECAST), 자체 모델(MODEL), 규칙 판정(RULE), 사용자 가정(ASSUMPTION) "
        "다섯 가지입니다.")

    D.p("RULE은 나중에 추가한 다섯 번째입니다. Module C는 학습·추론한 값이 아니라 관측 강우에 "
        "고시 임계값을 적용한 결정론적 분류이므로, MODEL 배지를 달면 그 표기 자체가 부정확해지기 "
        "때문입니다.")

    D.p("다만 배지 하나로는 정직할 수 없는 값이 있습니다. ‘노출 건물 351동’은 공간연산 결과지만, "
        "‘피해액 8.72억원’은 그 위에 필지 단위 주용도 조인과 1동=1세대 가정이 얹힌 값입니다. "
        "그래서 배지는 ‘어떻게 산출됐는가’, 별도 칩은 ‘무슨 가정이 얹혔는가’로 채널을 나눴습니다.")

    D.figure("fig10_provenance", "Provenance 배지 체계와 가정 표기 이원 채널", width_cm=15.2)

    D.p("가정 칩의 문구는 화면이 지어내지 않습니다. 각 모듈이 설명 함수로 실제 반환한 문장을 "
        "그대로 표시합니다. 화면이 문구를 만들면 모듈의 실제 가정과 어긋날 수 있기 때문입니다.")

    D.h2("10.2  폴백 계층 — 최상급 데이터가 없어도 멈추지 않는다")

    D.figure("fig09_fallback_tiers", "모듈별 폴백 계층 설계", width_cm=15.2)

    D.p("가장 중요한 규칙은 ‘확인 불가’와 ‘0’을 구분하는 것입니다. 농경지 레이어를 읽지 못하면 "
        "노출 면적은 0으로 계산되지만, 시스템은 그것이 ‘없음’이 아니라 ‘확인 불가’라는 경고를 "
        "함께 냅니다. 이 둘을 같게 표시하면 담당자가 안전하다고 오판할 수 있습니다.", bold=True)

    D.h2("10.3  자동화의 범위를 의도적으로 제한했다")

    D.p("개발 초기에는 담당자가 일정 시간 응답하지 않으면 시스템이 자동으로 경보를 승인하는 "
        "로직이 있었습니다. 이를 완전히 삭제했습니다.")

    D.p("생명안전과 직결된 공공 의사결정에서 ‘무응답 시 자동승인’은 책임 소재를 불분명하게 만드는 "
        "구조적 결함이기 때문입니다. 법적·행정적으로도 실현 가능성을 떨어뜨립니다.")

    D.figure("fig12_human_in_loop", "human-in-the-loop 의사결정 구조와 escalation", width_cm=15.2)

    D.p("시스템은 어떤 경우에도 공식 대피명령을 독자 발령하지 않습니다. 최종 판단은 "
        "담당자(관공서 모드) 또는 사용자 본인(시민 모드)의 몫이며, 이 원칙은 코드 레벨 테스트로 "
        "고정되어 있습니다.", bold=True)

    D.h2("10.4  검증을 별도 모듈로 분리했다")

    D.p("Module V는 사후 관측 데이터(Sentinel-1 SAR, 실측 인벤토리)와 사전 예측 폴리곤을 자동 대조해 "
        "IoU·Precision·Recall·F1·lead time을 계산합니다. 핵심 설계 규칙은 데이터 누출(data leakage) "
        "금지입니다 — 사건 이후에 취득한 데이터를 예측 입력에 절대 섞지 않습니다.")

    D.p("검증을 예측 모듈 안에 두지 않고 분리한 이유는 단순합니다. 같은 모듈이 예측하고 채점하면 "
        "채점이 느슨해지기 때문입니다.")

    D.h2("10.5  정책값의 근거 수준 표기")

    D.p("모든 정책값은 근거 수준을 상태로 명시합니다. 이렇게 하면 “이 숫자 어디서 왔나요”라는 "
        "질문에 파일 한 줄로 답할 수 있고, 아직 근거가 없는 값이 조용히 섞여 들어가지 못합니다.")

    D.table(
        ["상태", "의미"],
        [
            ("CONFIRMED", "공식 문서(고시 등)로 확인. 출처 URL·조항·시행일 기록"),
            ("DERIVED", "공식 기준에서 유도 (예: 3시간 기준 → 1시간 환산)"),
            ("TEAM_DECISION", "팀이 명시적으로 결정. 공식 출처 없음"),
            ("ASSUMPTION", "가정. 무엇을 가정했는지 문장으로 기록"),
            ("PLACEHOLDER", "아직 근거 미확보. 교체 대상임을 명시"),
        ],
        "정책값 근거 수준 분류",
        widths=[3.6, 12.0],
    )

    # ---------------- 10. 확장성 ----------------
    D.h1("11. 확장성")

    D.h2("11.1  지역 확장")

    D.p("데이터 스택과 모듈 계약이 지역에 무관하게 설계되어 있어, 다른 지자체의 공간 데이터와 "
        "강수·지형 데이터만 연결하면 같은 파이프라인이 그대로 돕니다. 강남·서초 AOI가 그 증거입니다 — "
        "산간지역인 산청과 성격이 완전히 다른 고밀도 도시인데 코드 변경 없이 같은 파이프라인이 "
        "건물 41,814동을 처리했습니다.")

    D.h2("11.2  재해 유형 확장")

    D.p("Module C처럼 모델이 아닌 규칙기반 경보를 파이프라인에 낮은 비용으로 추가할 수 있는 "
        "구조입니다. 폭염·대설·가뭄 등 다른 재난에도 같은 골든타임 회복 프레임워크를 적용할 수 있고, "
        "필요한 것은 새 모듈 하나와 그 모듈의 계약 파일뿐입니다.")

    D.h2("11.3  모듈 교체")

    D.p("모든 모듈이 단일 진입점만 노출하므로, Module B를 SFINCS에서 다른 수리모형으로 바꿔도 "
        "나머지 코드는 수정할 필요가 없습니다. 실제로 트랙②·④는 트랙①의 실모델을 기다리지 않고 "
        "계약 예시 파일을 목업 삼아 개발을 끝냈습니다 — 계약 분리가 실제로 작동한다는 증거입니다.")

    # ---------------- 11. 추진 ----------------
    D.h1("12. 추진 체계와 일정")

    D.h2("12.1  역할 분담")

    D.table(
        ["트랙", "담당", "소유 모듈", "핵심 산출물"],
        [
            ("① 예측모델·위성·검증", "트랙①", "A, B, V", "산사태·홍수 폴리곤, Sentinel-1 검증, dNBR 증폭계수"),
            ("② 대응로직·데이터통합", "트랙②", "C, D, G, H", "도로침수 규칙엔진, 노출자산, 피해비용, 시민 역검증"),
            ("③ 오케스트레이션·UI·3D", "트랙③", "O, UI", "상태머신·경보 전파, 3D 대시보드, 통합·데모 총괄"),
            ("④ 대피경로·고립분석", "동현", "E", "대피소 도달가능성, 도로망 그래프 기반 고립 탐지"),
        ],
        "트랙별 역할 분담",
        widths=[4.0, 1.9, 2.4, 7.3],
    )

    D.p("트랙 간 결합은 계약 파일뿐입니다. 담당자가 바뀌어도 계약만 유지되면 재구성됩니다.")

    D.h2("12.2  일정")

    D.p("남은 기간의 배분 원칙은 분명합니다. 새 기능 추가보다 검증에 무게를 둡니다. "
        "현재 프로젝트는 “무엇을 더 넣어야 하는가”보다 “이미 넣은 것 중 무엇을 실제라고 증명할 것인가”의 "
        "단계에 있기 때문입니다.")

    D.figure("fig14_roadmap", "단계별 구현 로드맵과 트랙별 책임", width_cm=15.4)

    D.h2("12.3  가장 중요한 단일 과제")

    D.p("산청 2025 사건을 당시 데이터만으로 다시 돌리는 leakage-free 백테스트입니다. "
        "시각 t에서 시스템이 보는 데이터는 반드시 그 시각 이전에 실제로 이용 가능했던 정보로 "
        "제한해야 합니다. 7월 19일 이후에 확정된 산사태 위치를 입력에 섞으면 그 순간 "
        "백테스트 전체가 무의미해집니다.")

    D.bullets([
        ("공간 중첩 검증 — ", "3월 burn scar와 7월 산사태 인벤토리가 실제로 같은 사면·소유역에서 겹치는가"),
        ("입력 시점 제한 — ", "그 시각까지의 실측 강우와 당시 발행된 예보만 사용"),
        ("세 시각 확정 — ", "모델 임계 초과 시각, 최초 피해 시각, 공식 경보 시각을 원자료로 확보"),
        ("불확실성 — ", "임계값을 바꾸면 lead time과 오경보율이 어떻게 달라지는지 함께 제시"),
    ])

    D.note("산청 사건의 정확한 기준시각은 원자료 확보가 필요합니다. 경보 격상 시각(12시 37분)은 "
           "복수 보도에서 확인되지만, 최초 피해 시각은 산청군·산림청·재난문자 기록 등 1차 행정기록으로 "
           "확정해야 합니다. 근거를 대지 못하는 시각으로 ‘몇 시간을 벌었다’고 주장하면 "
           "백테스트 전체의 신뢰도가 흔들리기 때문입니다.")

    # ---------------- 12. 기대효과 ----------------
    D.h1("13. 기대효과")

    D.h2("13.1  행정 현장")

    D.p("담당자가 여러 시스템을 오가며 수작업으로 맞춰 보던 정보 — 위험 범위, 그 안의 자산, "
        "대피소까지의 경로, 끊긴 도로, 예상 피해 규모 — 가 하나의 화면에서 근거와 함께 제시됩니다. "
        "판단 자체를 대신하는 것이 아니라, 판단에 필요한 재료를 모으는 시간을 줄이는 것이 목표입니다.")

    D.h2("13.2  시민")

    D.p("‘우리 지역이 위험합니다’가 아니라 ‘당신의 위치에서 가장 가까운 안전 대피소는 여기이고, "
        "차량 기준 몇 분이며, 그 경로가 위험구간과 겹치는지 여부는 이렇습니다’까지 제시합니다. "
        "위험 정보와 행동 사이의 거리를 좁히는 것이 목적입니다.")

    D.h2("13.3  재난 데이터 인프라")

    D.p("모든 값에 출처와 가정을 붙이고 모든 정책값에 근거 수준을 명시하는 방식 자체가 "
        "재난 의사결정 시스템의 참고 사례가 될 수 있습니다. 재난 분야에서 "
        "‘이 숫자가 어디서 왔는지 알 수 없는 화면’은 쓰이지 않거나, 더 나쁘게는 잘못 쓰입니다.")

    D.h2("13.4  솔직한 한계")

    D.p("마지막으로 현재 상태를 있는 그대로 적습니다. 이 제안서가 화면의 모든 숫자에 출처를 붙이는 "
        "것을 원칙으로 삼고 있으므로, 제안서 자체도 같은 기준을 따릅니다.")

    D.table(
        ["항목", "현재 상태", "영향"],
        [
            ("산사태 예측력", "ROC-AUC 0.469, lift 0.94", "현 참값으로는 검증 불가. 발생부 좌표 확보가 선결"),
            ("발생부 좌표", "미확보 (산림청 요청 중)", "예측력·공간중첩·ML·계수 보정이 모두 여기서 막힘"),
            ("T_event 실제 붕괴시각", "미확보", "hazard lead를 점추정 못 하고 상한으로만 보고"),
            ("A_max·Rsat·Wmax·k", "전부 미보정", "문헌값·임의값. 한국 데이터 보정 전"),
            ("데모 부지 토양", "미주입", "Module A가 tier 2 폴백 → 데모가 운영 임계 0.7 미달"),
            ("주용도 커버리지", "산청 63.1% / 강남·서초 86.2%", "미매칭분은 피해비용 점추정에서 제외"),
            ("Module E 테스트", "미작성 (491개 중 0개)", "다른 모듈과 달리 자동 검증이 없음"),
            ("오경보율(FAR)", "산정 불가", "단일 이벤트라 계산 불가 — 다중 이벤트 확보 필요"),
        ],
        "현재 해소되지 않은 한계와 그 영향",
        widths=[3.4, 4.6, 7.6],
    )

    D.p("한 가지가 눈에 띌 것입니다. 여덟 개 중 다섯 개가 같은 원인 하나로 수렴합니다 — "
        "참값이 발생부(source area)가 아니라 피해 집계 마을이라는 점입니다. 이것이 풀리면 "
        "예측력 검증·공간중첩·ML 보정·시그모이드 보정이 같은 스크립트로 즉시 재검정됩니다. "
        "그래서 저희의 다음 단일 최우선 과제는 새 기능이 아니라 이 데이터의 확보입니다.", bold=True)

    D.p("이 한계들은 감추는 것이 아니라 해소 일정과 함께 관리되고 있습니다. 시스템은 이 상태를 "
        "스스로 표기합니다 — 어느 모듈이 실물이고 어느 것이 예시값인지가 서버 응답에 그대로 실리고, "
        "UI의 성능 패널에는 참값 한계 배너가 상시 노출됩니다.")

    # ---------------- 붙임 ----------------
    D.page_break()
    D.h1("붙임 1. 그림 목록")
    for i, cap in enumerate(FIGURE_CAPTIONS, start=1):
        par = d.add_paragraph()
        par.paragraph_format.space_after = Pt(3)
        par.paragraph_format.line_spacing = 1.4
        _run(par, f"[그림 {i}] ", bold=True, size=10)
        _run(par, cap, size=10)

    D.h1("붙임 2. 수식 목록")
    for i, cap in enumerate(EQUATION_CAPTIONS, start=1):
        par = d.add_paragraph()
        par.paragraph_format.space_after = Pt(3)
        par.paragraph_format.line_spacing = 1.4
        _run(par, f"[수식 {i}] ", bold=True, size=10)
        _run(par, cap, size=10)

    D.h1("붙임 3. 재현 방법")
    D.p("제안서 본문의 수치는 다음으로 재현됩니다. 그림과 수식 이미지도 저장소의 스크립트가 "
        "실행 결과에서 직접 생성한 것이며, 별도로 그린 것이 아닙니다. 7장의 검증 그림은 "
        "backtest_sancheong/outputs/ 의 산출 JSON을 그대로 읽습니다 — 스크립트 안에 숫자를 "
        "옮겨 적지 않았습니다.", size=10)

    code = d.add_paragraph()
    code.paragraph_format.left_indent = Cm(0.6)
    code.paragraph_format.line_spacing = 1.35
    code.paragraph_format.space_after = Pt(10)
    r = code.add_run(
        "pip install -r requirements.txt\n"
        "python -m pytest -q                            # 491개 통과\n"
        "python scripts/build_proposal_figures.py       # 그림 14개\n"
        "python scripts/build_validation_figures.py     # 검증 그림 6개\n"
        "python scripts/build_proposal_equations.py     # 수식 7개\n"
        "python scripts/build_proposal_docx.py          # 이 문서\n"
        "\n"
        "# 7장 백테스트 재실행 (원시 래스터가 로컬에 있어야 한다)\n"
        "python backtest_sancheong/scripts/39_backtest_ablation.py\n"
        "python backtest_sancheong/scripts/40_fire_landslide_overlap.py\n"
        "python backtest_sancheong/scripts/42_backtest_eval_split.py"
    )
    r.font.name = "Consolas"
    r.font.size = Pt(9)
    r.font.color.rgb = MUTED


FIGURE_CAPTIONS = [
    "2025년 산청 복합재해 타임라인과 회복 대상 구간",
    "재해연쇄 모델과 모듈 대응 구간",
    "아쿠아가드 시스템 아키텍처 및 데이터 흐름",
    "모듈별 구현 코드량과 테스트 통과 수",
    "화재흉터 증폭계수 f(dNBR, Δt)의 시간 감쇠",
    "산불 기여도 분리 실험 (ablation)",
    "Module C 규칙 판정면과 임계값 근거",
    "시민 역검증의 shrinkage 집계 곡선",
    "AOI 데이터 규모와 건물 주용도 조인 커버리지",
    "산청 백테스트 실측 — decision latency와 hazard lead",
    "산사태 예측력 검증의 음성 결과",
    "사전등록 기준에 따른 ML 보정 기각",
    "Module B 하천범람 엔진 교차검증",
    "Module V 검증 엔진의 재해별 결과 차이",
    "노출자산 용도별 구성과 피해비용 (위험영역이 주어졌을 때)",
    "시민 모드와 관공서 모드의 기능 분리",
    "Provenance 배지 체계와 가정 표기 이원 채널",
    "모듈별 폴백 계층 설계",
    "human-in-the-loop 의사결정 구조와 escalation",
    "단계별 구현 로드맵과 트랙별 책임",
]

EQUATION_CAPTIONS = [
    "화재흉터 증폭계수의 시간 감쇠",
    "무한사면 안전율 (Infinite Slope)",
    "지하차도 경보 등급 판정 규칙",
    "노출 건물 집합과 노출 농경지 면적",
    "피해비용 점추정과 상한",
    "시민 신고의 shrinkage 집계",
    "골든타임 관련 두 지표의 정의",
]


if __name__ == "__main__":
    doc = build_document()
    write(Doc(doc))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    doc.save(OUT)
    print(f"저장: {OUT}")
    print(f"  그림 {FIG_NO['n']}개 · 수식 {EQ_NO['n']}개 · 표 {TBL_NO['n']}개")
