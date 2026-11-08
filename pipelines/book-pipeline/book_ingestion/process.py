"""PROCESS: a PDF → page texts and chapter ranges. No writing to the library.

Chapters come from the PDF outline, else from bold `#` headings, else 25-page parts.
Scanned PDFs are OCR'd first.
"""
import re
import subprocess
from pathlib import Path

import pymupdf
import pymupdf4llm

pymupdf.TOOLS.mupdf_display_errors(False)  # malformed PDFs spam harmless warnings
# ignore_graphics below: otherwise text in shaded boxes (tips, sidebars) is dropped

MAX_PAGES = 60   # outline sections longer than this are split into sub-sections
CHUNK = 25       # pages per part when there is no outline or headings
MIN_CHARS = 100  # average chars/page below this means the PDF is a scan
Section = tuple[str, int, int]  # (title, first page, end page exclusive), 0-based


def process(pdf: Path, ocr_cache: Path) -> tuple[list[str], list[Section]]:
    """(page texts as Markdown, chapter sections)."""
    doc = pymupdf.open(pdf)
    scanned = chars_per_page(doc) < MIN_CHARS
    if scanned:
        doc = pymupdf.open(ocr(pdf, ocr_cache))
        if chars_per_page(doc) < MIN_CHARS:
            print(f"  ! {pdf.name}: still little text after OCR, check the output")

    pages = [c["text"] for c in pymupdf4llm.to_markdown(doc, page_chunks=True, show_progress=False, ignore_graphics=True)]
    if scanned:  # OCR text comes out as code blocks with blank lines between lines
        pages = [re.sub(r"\n\n(?=\S)", "\n", re.sub(r"^```\n?", "", t, flags=re.M)) for t in pages]
    return pages, outline_sections(doc) or heading_sections(pages) or chunk_sections(len(pages))


def chars_per_page(doc) -> float:
    pages = range(0, doc.page_count, max(1, doc.page_count // 20))
    return sum(len(doc[i].get_text()) for i in pages) / len(pages)


def ocr(pdf: Path, out: Path) -> Path:
    if not out.exists():
        print("  scanned PDF, running OCR (takes a while)...")
        tmp = out.with_suffix(".tmp.pdf")
        subprocess.run(["ocrmypdf", "-q", "--skip-text", str(pdf), str(tmp)], check=True)
        tmp.rename(out)
    return out


def outline_sections(doc) -> list[tuple[str, int, int]]:
    """(title, start, end) page ranges from the PDF outline; end is exclusive."""
    toc = [(lvl, title.strip(), page - 1) for lvl, title, page in doc.get_toc() if page >= 1]
    tops = [i for i, entry in enumerate(toc) if entry[0] == 1]
    out = []
    for n, i in enumerate(tops):
        j = tops[n + 1] if n + 1 < len(tops) else len(toc)
        title, start = toc[i][1], toc[i][2]
        end = toc[j][2] if j < len(toc) else doc.page_count
        kids = [e for e in toc[i + 1:j] if e[0] == 2]
        if end - start > MAX_PAGES and kids:  # long part: split into its chapters
            out.append((title, start, kids[0][2]))
            for k, (_, kid_title, kid_start) in enumerate(kids):
                out.append((kid_title, kid_start, kids[k + 1][2] if k + 1 < len(kids) else end))
        else:
            out.append((title, start, end))
    if out and out[0][1] > 0:
        out.insert(0, ("Front matter", 0, out[0][1]))
    return [s for s in out if s[2] > s[1]]


def heading_sections(pages: list[str]) -> list[tuple[str, int, int]]:
    """Split on bold `#` headings; also use `##` if `#` alone leaves sections too long."""
    best = []
    for depth in (1, 2):
        sections = _split_on_headings(pages, depth) or best
        if sections and max(e - s for _, s, e in sections) <= MAX_PAGES:
            return sections
        best = sections
    return best


def _split_on_headings(pages: list[str], depth: int) -> list[tuple[str, int, int]]:
    # real headings are bold; code comments like "# config" are not
    pattern = re.compile(r"#{1,%d} \*\*" % depth)
    starts = []
    for i, text in enumerate(pages):
        heading = next((l for l in text.splitlines() if pattern.match(l)), None)
        if heading:
            starts.append((" ".join(re.sub(r"[#*_]", " ", heading).split()), i))
    if len(starts) < 3:
        return []
    if starts[0][1] > 0:
        starts.insert(0, ("Front matter", 0))
    ends = [s for _, s in starts[1:]] + [len(pages)]
    return [(t, s, e) for (t, s), e in zip(starts, ends)]


def chunk_sections(n_pages: int) -> list[tuple[str, int, int]]:
    return [(f"Part {i // CHUNK + 1}", i, min(i + CHUNK, n_pages)) for i in range(0, n_pages, CHUNK)]
