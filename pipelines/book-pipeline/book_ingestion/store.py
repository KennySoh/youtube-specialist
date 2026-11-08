"""STORE: where books come from and where their chapters go.

knowledge-library/books/books.txt     "<slug> <pdf path relative to BOOKS_DIR>"
knowledge-library/books/<slug>/chapters/NN-title.md   a `<!-- p.N -->` marker before every page (N = PDF page)
knowledge-library/books/<slug>/ocr.pdf                OCR cache for scanned PDFs
"""
import os
import re
import shutil
from pathlib import Path

# BOOKS_LIBRARY overrides it (tests); otherwise <repo>/knowledge-library/books.
KNOWLEDGE = Path(os.environ.get("BOOKS_LIBRARY") or Path(__file__).resolve().parents[3] / "knowledge-library" / "books")
BOOKS = Path(os.environ.get("BOOKS_DIR", "/books"))  # raw/books, mounted read-only in Docker


def read_books() -> dict[str, Path]:
    books = {}
    for line in (KNOWLEDGE / "books.txt").read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            slug, path = line.split(maxsplit=1)
            books[slug] = BOOKS / path
    return books


def book_dir(slug: str) -> Path:
    return KNOWLEDGE / slug


def has_chapters(slug: str) -> bool:
    return (book_dir(slug) / "chapters").exists()


def write_chapters(slug: str, pdf: Path, pages: list[str], sections: list[tuple[str, int, int]]) -> None:
    chapters = book_dir(slug) / "chapters"
    shutil.rmtree(chapters, ignore_errors=True)
    chapters.mkdir(parents=True)
    for n, (title, s, e) in enumerate(sections):
        body = "\n\n".join(f"<!-- p.{i + 1} -->\n{pages[i]}" for i in range(s, e))
        header = f"<!-- {title} | {pdf.name} | PDF pages {s + 1}-{e} -->\n\n"
        (chapters / f"{n:02d}-{slugify(title)}.md").write_text(header + body, encoding="utf-8")


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:50] or "section"
