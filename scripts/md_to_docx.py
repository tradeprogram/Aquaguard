"""마크다운 인수인계 문서 → Word(.docx).

저장소의 .md를 원본으로 두고 배포본을 만들기 위한 것이다 — 내용을 따로 옮겨 적으면
두 벌이 어긋나므로, 항상 .md에서 생성한다.

지원하는 문법은 작업 지시서 문서가 실제로 쓰는 것만이다:
  # ## ###  제목 · **굵게** · `코드` · 표 · ``` 코드블록 · > 인용 · - 목록 · --- 구분선

    python scripts/md_to_docx.py 작업 지시서 [출력.docx]
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

BODY_FONT = "맑은 고딕"
CODE_FONT = "D2Coding"  # 없으면 Word가 대체 폰트를 쓴다 — Consolas로 폴백
INK = RGBColor(0x11, 0x18, 0x27)
MUTED = RGBColor(0x5B, 0x65, 0x73)
ACCENT = RGBColor(0x1D, 0x4E, 0xD8)
DANGER = RGBColor(0xB9, 0x1C, 0x1C)

INLINE = re.compile(r"(\*\*.+?\*\*|`[^`]+`)")


def _set_font(run, name: str) -> None:
    run.font.name = name
    run._element.rPr.rFonts.set(qn("w:eastAsia"), name)


def _shade(cell, hex_color: str) -> None:
    el = OxmlElement("w:shd")
    el.set(qn("w:val"), "clear")
    el.set(qn("w:fill"), hex_color)
    cell._tc.get_or_add_tcPr().append(el)


def _left_bar(par, hex_color: str) -> None:
    pPr = par._p.get_or_add_pPr()
    bdr = OxmlElement("w:pBdr")
    left = OxmlElement("w:left")
    left.set(qn("w:val"), "single")
    left.set(qn("w:sz"), "18")
    left.set(qn("w:space"), "10")
    left.set(qn("w:color"), hex_color)
    bdr.append(left)
    pPr.append(bdr)


CODE_SPAN = re.compile(r"(`[^`]+`)")


def _emit(par, text: str, *, size: float, color, bold: bool) -> None:
    """`코드`만 해석해 run을 만든다. 굵게 여부는 호출부가 정한다.

    굵게 안에 코드가 들어가는 경우(**... `x` ...**)가 흔해서, 코드 해석을 이 함수로
    빼고 write_inline이 굵게 구간에도 같은 함수를 태운다 — 안 그러면 백틱이 그대로 남는다.
    """
    for piece in CODE_SPAN.split(text):
        if not piece:
            continue
        run = par.add_run(piece[1:-1] if piece.startswith("`") else piece)
        if piece.startswith("`"):
            _set_font(run, CODE_FONT)
            run.font.size = Pt(size - 0.7)
            run.font.color.rgb = RGBColor(0x9A, 0x34, 0x12)
        else:
            _set_font(run, BODY_FONT)
            run.font.size = Pt(size)
            run.font.color.rgb = color
        run.font.bold = bold


def write_inline(par, text: str, *, size=10.5, color=INK, bold=False) -> None:
    """**굵게**와 `코드`를 해석한다(중첩 포함). 나머지는 그대로 둔다."""
    for piece in INLINE.split(text):
        if not piece:
            continue
        if piece.startswith("**") and piece.endswith("**"):
            _emit(par, piece[2:-2], size=size, color=color, bold=True)
        else:
            _emit(par, piece, size=size, color=color, bold=bold)


def build(md_path: Path, out_path: Path) -> None:
    lines = md_path.read_text(encoding="utf-8").splitlines()

    doc = Document()
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Cm(21.0), Cm(29.7)
    sec.left_margin = sec.right_margin = Cm(2.0)
    sec.top_margin = sec.bottom_margin = Cm(1.9)

    normal = doc.styles["Normal"]
    normal.font.name = BODY_FONT
    normal.font.size = Pt(10.5)
    normal.font.color.rgb = INK
    normal.element.rPr.rFonts.set(qn("w:eastAsia"), BODY_FONT)
    normal.paragraph_format.line_spacing = 1.45
    normal.paragraph_format.space_after = Pt(6)

    for name, size, color, before, after in [
        ("Heading 1", 15, ACCENT, 20, 8),
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

    i = 0
    n = len(lines)
    while i < n:
        raw = lines[i]
        line = raw.rstrip()

        # 코드블록
        if line.startswith("```"):
            i += 1
            body: list[str] = []
            while i < n and not lines[i].startswith("```"):
                body.append(lines[i])
                i += 1
            i += 1
            par = doc.add_paragraph()
            par.paragraph_format.left_indent = Cm(0.5)
            par.paragraph_format.line_spacing = 1.25
            par.paragraph_format.space_before = Pt(5)
            par.paragraph_format.space_after = Pt(9)
            _shade_paragraph(par, "F5F7FA")
            run = par.add_run("\n".join(body))
            _set_font(run, CODE_FONT)
            run.font.size = Pt(8.8)
            run.font.color.rgb = RGBColor(0x1F, 0x29, 0x37)
            continue

        # 표
        if line.startswith("|") and i + 1 < n and re.match(r"^\|[\s:|-]+\|$", lines[i + 1].strip()):
            header = [c.strip() for c in line.strip().strip("|").split("|")]
            i += 2
            rows: list[list[str]] = []
            while i < n and lines[i].strip().startswith("|"):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            _add_table(doc, header, rows)
            continue

        # 구분선
        if line.strip() in ("---", "***", "___"):
            par = doc.add_paragraph()
            par.paragraph_format.space_before = Pt(4)
            par.paragraph_format.space_after = Pt(4)
            pPr = par._p.get_or_add_pPr()
            bdr = OxmlElement("w:pBdr")
            bottom = OxmlElement("w:bottom")
            bottom.set(qn("w:val"), "single")
            bottom.set(qn("w:sz"), "6")
            bottom.set(qn("w:space"), "1")
            bottom.set(qn("w:color"), "D5DBE3")
            bdr.append(bottom)
            pPr.append(bdr)
            i += 1
            continue

        # 제목
        m = re.match(r"^(#{1,3})\s+(.*)$", line)
        if m:
            level = len(m.group(1))
            heading = doc.add_heading("", level=level)
            write_inline(heading, m.group(2), size=[15, 12.5, 11][level - 1],
                         color=ACCENT if level == 1 else INK, bold=True)
            i += 1
            continue

        # 인용
        if line.startswith(">"):
            block: list[str] = []
            while i < n and lines[i].startswith(">"):
                block.append(lines[i].lstrip(">").strip())
                i += 1
            par = doc.add_paragraph()
            par.paragraph_format.left_indent = Cm(0.5)
            par.paragraph_format.space_before = Pt(5)
            par.paragraph_format.space_after = Pt(9)
            par.paragraph_format.line_spacing = 1.4
            _left_bar(par, "D97706")
            write_inline(par, " ".join(x for x in block if x), size=9.9, color=MUTED)
            continue

        # 목록
        if re.match(r"^[-*]\s+", line):
            # 목록 항목도 다음 줄로 이어질 수 있다(소프트 줄바꿈). 들여쓴 후속 줄을 흡수한다.
            item = [re.sub(r"^[-*]\s+", "", line)]
            i += 1
            while i < n and lines[i].startswith("  ") and lines[i].strip() \
                    and not re.match(r"^\s*[-*]\s+", lines[i]):
                item.append(lines[i].strip())
                i += 1
            par = doc.add_paragraph(style="List Bullet")
            par.paragraph_format.space_after = Pt(3)
            par.paragraph_format.line_spacing = 1.4
            write_inline(par, " ".join(item), size=10.3)
            continue

        if not line.strip():
            i += 1
            continue

        # 마크다운의 소프트 줄바꿈 — 빈 줄이 나올 때까지가 한 문단이다. 줄 단위로
        # 끊어 렌더링하면 **굵게**가 줄을 넘어갈 때 별표가 그대로 남는다.
        block = []
        while i < n and lines[i].strip() and not _is_block_start(lines[i]):
            block.append(lines[i].strip())
            i += 1
        par = doc.add_paragraph()
        write_inline(par, " ".join(block))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(out_path)


def _is_block_start(line: str) -> bool:
    """이 줄부터 새 블록이 시작되는가 — 문단 누적을 여기서 끊는다."""
    stripped = line.strip()
    return bool(
        line.startswith("```")
        or line.startswith("|")
        or line.startswith(">")
        or re.match(r"^#{1,6}\s", line)
        or re.match(r"^[-*]\s+", line)
        or stripped in ("---", "***", "___")
    )


def _shade_paragraph(par, hex_color: str) -> None:
    pPr = par._p.get_or_add_pPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:fill"), hex_color)
    pPr.append(shd)


def _add_table(doc, header: list[str], rows: list[list[str]]) -> None:
    cols = len(header)
    table = doc.add_table(rows=1, cols=cols)
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    for idx, text in enumerate(header):
        cell = table.rows[0].cells[idx]
        cell.text = ""
        par = cell.paragraphs[0]
        par.alignment = WD_ALIGN_PARAGRAPH.CENTER
        par.paragraph_format.space_after = Pt(2)
        par.paragraph_format.line_spacing = 1.15
        write_inline(par, text, size=9.2, bold=True)
        _shade(cell, "EEF2F7")
    for row in rows:
        cells = table.add_row().cells
        for idx in range(cols):
            cells[idx].text = ""
            par = cells[idx].paragraphs[0]
            par.paragraph_format.space_after = Pt(2)
            par.paragraph_format.line_spacing = 1.2
            write_inline(par, row[idx] if idx < len(row) else "", size=9.2)
    doc.add_paragraph().paragraph_format.space_after = Pt(5)


if __name__ == "__main__":
    src = Path(sys.argv[1]).resolve()
    dst = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else src.with_suffix(".docx")
    build(src, dst)
    print(f"저장: {dst}")
