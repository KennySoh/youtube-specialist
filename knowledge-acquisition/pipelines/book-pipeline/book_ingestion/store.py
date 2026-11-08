"""STORE: where books come from and where their chapters go.

Knowledge Acquisition's own files (never read by the experts):
knowledge-acquisition/raw/books/                    the PDFs (BOOKS_DIR, mounted read-only at /books)
knowledge-acquisition/state/books/books.txt         "<slug> <pdf path relative to BOOKS_DIR>"
knowledge-acquisition/state/books/<slug>/ocr.pdf    OCR cache for scanned PDFs

What it publishes to the Knowledge Library:
knowledge-library/books/<slug>/chapters/NN-title.md   a `<!-- p.N -->` marker before every page (N = PDF page)
(notes.md next to chapters/ is written by /extract-book, never by this pipeline)
"""
import os
import re
import shutil
from pathlib import Path

# BOOKS_LIBRARY and BOOKS_STATE override these (tests); otherwise they're found from this file.
# knowledge-acquisition/, wherever this file sits under it (in the YouTube image the env vars are used instead)
_ACQUISITION = next((p for p in Path(__file__).resolve().parents if p.name == "knowledge-acquisition"),
                    Path(__file__).resolve().parent)
KNOWLEDGE = Path(os.environ.get("BOOKS_LIBRARY") or _ACQUISITION.parent / "knowledge-library" / "books")  # published
STATE = Path(os.environ.get("BOOKS_STATE") or _ACQUISITION / "state" / "books")  # books.txt, OCR caches
BOOKS = Path(os.environ.get("BOOKS_DIR", "/books"))  # knowledge-acquisition/raw/books, mounted read-only in Docker


def read_books() -> dict[str, Path]:
    books = {}
    for line in (STATE / "books.txt").read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            slug, path = line.split(maxsplit=1)
            books[slug] = BOOKS / path
    return books


def book_dir(slug: str) -> Path:
    return KNOWLEDGE / slug


def ocr_cache(slug: str) -> Path:
    """Where a scanned book's OCR'd PDF is kept, so OCR runs only once."""
    return STATE / slug / "ocr.pdf"


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
