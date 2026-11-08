# Book pipeline

Code: `pipelines/book-pipeline/book_ingestion/`. Runs in its own Docker image (PyMuPDF + Tesseract)
through `./scripts/books.sh`.

```
raw/books/*.pdf ──./scripts/books.sh──► knowledge-library/books/<slug>/chapters/ ──/extract-book──► notes.md ──► role experts
```

## Adding a book

1. Put the PDF under `raw/books/` (or point `BOOKS_DIR` in `.env` at another folder).
2. Add a line to `knowledge-library/books/books.txt`: `<slug> <path relative to raw/books>`.
3. `./scripts/books.sh <slug>` converts it (`./scripts/books.sh` alone converts every book not converted yet; `--force` redoes it).
4. In Claude Code: `/extract-book <slug>` writes `notes.md`.

Open book work (books still to extract, role refinements) is tracked in `knowledge-library/books/plan.md`.

## Conversion

- Text comes from the PDF; a scanned PDF (little text per page) is OCR'd first, cached as `<slug>/ocr.pdf`.
- Chapters come from the PDF outline, else from bold `#` headings, else 25-page parts. Outline parts
  longer than 60 pages are split into their chapters.
- Output: `chapters/NN-title.md`, starting with `<!-- <title> | <pdf name> | PDF pages A-B -->` and with
  `<!-- p.N -->` before every page. **N is the PDF page**, not the number printed in the book.
- `--force` rewrites `chapters/` only. `notes.md` and `ocr.pdf` are never touched.
- `chapters/` is copyrighted text: keep it local (the whole library is git-ignored).

## notes.md

Written by `/extract-book` from `chapters/`, read first by the role experts.

1. **Overview**: thesis, mental model, chapter → topic map, missing pages.
2. **Concepts**, one section each: **Claim** (with page), **Why**, **When / when not**, **How to apply**,
   **Anti-pattern**, **Review question + evidence**, **Related**. Mark your own interpretation or
   example with *(interpretation)*.
3. **Checklist**: review questions the experts ask.

Split it into `notes/<topic>.md` only past ~500 lines.

Example concept:

> **Deep modules** (p. NN)
> - **Claim:** a good module hides a lot of complexity behind a simple interface.
> - **Why:** many tiny classes add interfaces that callers have to learn.
> - **When not:** a small module with a clear, stable job is fine.
> - **Anti-pattern:** layers that only pass calls through.
> - **Review:** does the API hide real detail, or just forward calls? Evidence: interface size, number
>   of calls a use case needs, implementation details that leak out.

## Citation rules

1. **Only cite what's in `chapters/`.** Never invent pages or quotes; say which pages are missing.
   Cite as *(Book p.N)* with the PDF page from the markers.
2. **Keep the reasoning, not just the rule**: the why, trade-offs and exceptions; paraphrase instead of
   copying long passages.
3. **Judgment, not dogma**: when books conflict, explain the context, then record the decision and any
   open questions.
4. **Experts stay short**: read `notes.md` first, then grep `chapters/` for exact detail.

## Role experts

| Expert | Books |
|---|---|
| product-manager | The Mom Test, Inspired |
| ux-designer | About Face, Don't Make Me Think |
| software-architect | Learning DDD, DDD (Evans), Clean Architecture, Fundamentals of SA, Philosophy of SD, PoEAA |
| software-engineer | Philosophy of SD, Pragmatic Programmer, Refactoring, Clean Code |

They're used from other projects, so their skills are linked into `~/.claude/skills/` and use absolute paths:

```bash
for r in product-manager ux-designer software-architect software-engineer; do
  ln -sfn "$PWD/.claude/skills/$r" ~/.claude/skills/$r
done
```

## Tests

`./scripts/test.sh` includes the book store tests: `books.txt` parsing, the chapter format and page
markers, and that `notes.md` survives a re-conversion. (PDF processing itself is checked by converting
a book and comparing the output.)
