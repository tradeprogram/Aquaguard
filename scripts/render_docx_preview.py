"""docx를 PDF로 변환하고 페이지를 PNG로 렌더링해 눈으로 검수할 수 있게 한다.

이 환경에는 LibreOffice가 없고 Microsoft Word가 있으므로 Word COM을 쓴다.

    python scripts/render_docx_preview.py docs/아쿠아가드_제안서.docx [출력디렉터리]
"""

from __future__ import annotations

import sys
from pathlib import Path

import pymupdf
import win32com.client

WD_FORMAT_PDF = 17


def to_pdf(docx_path: Path) -> Path:
    pdf_path = docx_path.with_suffix(".pdf")
    word = win32com.client.Dispatch("Word.Application")
    word.Visible = False
    try:
        doc = word.Documents.Open(str(docx_path), ReadOnly=True)
        try:
            doc.SaveAs(str(pdf_path), FileFormat=WD_FORMAT_PDF)
        finally:
            doc.Close(SaveChanges=False)
    finally:
        word.Quit()
    return pdf_path


def rasterize(pdf_path: Path, out_dir: Path, dpi: int = 88) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    for stale in out_dir.glob("page-*.png"):
        stale.unlink()
    doc = pymupdf.open(pdf_path)
    zoom = dpi / 72
    written = []
    width = len(str(len(doc)))
    for i, page in enumerate(doc, start=1):
        pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom))
        path = out_dir / f"page-{i:0{width}d}.png"
        pix.save(path)
        written.append(path)
    return written


if __name__ == "__main__":
    src = Path(sys.argv[1]).resolve()
    out = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else src.parent / "_preview"
    pdf = to_pdf(src)
    pages = rasterize(pdf, out)
    print(f"PDF : {pdf}")
    print(f"페이지 {len(pages)}쪽 → {out}")
