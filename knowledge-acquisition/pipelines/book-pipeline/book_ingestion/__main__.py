"""./scripts/books.sh [slug ...] [--force]: convert the books in knowledge-acquisition/state/books/books.txt.

books.txt paths are relative to BOOKS_DIR (knowledge-acquisition/raw/books by default; mounted read-only at /books).
Books have no ACQUIRE step yet: you put the PDFs in knowledge-acquisition/raw/books/ yourself.
"""
import argparse
import sys
import time
from pathlib import Path

from . import store
from .process import process


def convert(slug: str, pdf: Path, force: bool) -> None:
    if store.has_chapters(slug) and not force:
        print(f"- {slug}  (exists, skipping; use --force)")
        return
    start = time.time()
    store.book_dir(slug).mkdir(parents=True, exist_ok=True)
    pages, sections = process(pdf, store.ocr_cache(slug))
    store.write_chapters(slug, pdf, pages, sections)
    print(f"✓ {slug}  {len(sections)} chapters, {len(pages)} pages  ({time.time() - start:.0f}s)")


def main() -> int:
    ap = argparse.ArgumentParser(prog="./scripts/books.sh", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("slugs", nargs="*", help="books to convert (default: all in books.txt)")
    ap.add_argument("--force", action="store_true", help="re-convert existing books")
    args = ap.parse_args()

    books = store.read_books()
    unknown = [s for s in args.slugs if s not in books]
    if unknown:
        print(f"✗ not in knowledge-acquisition/state/books/books.txt: {', '.join(unknown)}", file=sys.stderr)
        return 1

    failed = 0
    for slug in args.slugs or books:
        if not books[slug].exists():
            print(f"✗ {slug}  no PDF at {books[slug]} (is BOOKS_DIR set?)", file=sys.stderr)
            failed += 1
            continue
        try:
            convert(slug, books[slug], args.force)
        except Exception as e:  # keep going on broken PDFs
            print(f"✗ {slug}  failed: {e}", file=sys.stderr)
            failed += 1
    return 1 if failed else 0


sys.exit(main())
