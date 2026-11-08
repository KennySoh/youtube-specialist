# Software architecture: My AI Brain

## 1. System overview

My AI Brain turns sources (YouTube channels and books today) into a local library of Markdown files
with location markers, and defines AI experts that answer only from sources they're allowed to use,
citing where each claim comes from.

Principles:
- **Local-first.** Sources, knowledge and experts live on your disk, in plain files.
- **Preserve originals.** What was acquired is kept in `raw/`, so processing can be redone offline.
- **Independent pipelines.** Each source type has its own small pipeline; they share conventions, not code.
- **Experts don't know about pipelines.** An expert reads the library; it never depends on how the
  files were made.
- **Small and plain.** Plain functions, small dataclasses, files on disk. No services, databases or frameworks.

## 2. System architecture

```
External sources ──► Acquire ──► raw/ ──► Process ──► Store ──► knowledge-library/ ──► experts/ ──► AI integrations
(YouTube, PDFs)      (network,           (pure, no            (disk)                  (rules,       (Claude Code today)
                      rate-limited)       network)                                     sources)
```

YouTube's rate limit is the hard constraint: about 50 admitted requests a day, and one 429 means
waiting 24 hours. Much of the YouTube design exists to never trigger one.

## 3. Modules and responsibilities

| Area | Where | Responsibility |
|---|---|---|
| Knowledge acquisition | `pipelines/*/…/acquire.py`, `request_guard.py` | Get sources: list channels, look up videos, fetch captions, read bookmarklet captures. Every YouTube request asks the guard first. Books have no acquire step: you add PDFs by hand. |
| Knowledge processing | `pipelines/*/…/process.py` | Turn raw material into citation-ready Markdown: captions → `[mm:ss]` paragraphs; PDF → chapters with `<!-- p.N -->`, OCR for scans. No network, no disk. |
| Knowledge library | `pipelines/*/…/store.py`, `knowledge-library/`, `raw/` | Persist raw snapshots and processed Markdown, indexes (`INDEX.md`, `missing.log`), status and metadata. |
| AI experts | `experts/<name>/expert.md` | Who the expert is, which sources it may use (`sources:` in frontmatter), how it answers and cites, what it does when the sources are silent. |
| AI integrations | `.claude/skills/<name>/SKILL.md` | Thin adapter: when Claude should use the expert, then "read `expert.md`". Other models would get their own adapter. |

`__main__.py` in each pipeline is the CLI and runs the steps in order. There is no other orchestration layer.

## 4. Domain model

| Concept | Meaning | In the code / on disk |
|---|---|---|
| Source | Something knowledge comes from: a YouTube video or a book | `Video` (`process.py`); a line in `books.txt` |
| Collection | A group of videos: a **channel collection** (has a `channel_url`) or a **topic collection** (hand-picked) | `Collection` (`store.py`); `knowledge-library/youtube/<slug>/` |
| Captions | What YouTube has for a video: `manual` or `auto` (or `browser`, saved by hand) | `Segment` list; `raw/youtube/<slug>/<id>.json` |
| Transcript | Our Markdown for one video, in ~30 s `[mm:ss]` paragraphs | `transcripts/<date>-<title>-<id>.md` |
| Status | Why a video has no transcript: `no_captions`, `unavailable`, `failed` (retried up to 3 times) | `status.json`, `missing.log` |
| Guard | The rate-limit rules: daily budget, pacing, 24 h block | `request_guard.py`; `.guard.json` |
| Book | One PDF, converted to chapters, distilled into notes | `knowledge-library/books/<slug>/chapters/`, `notes.md` |
| Expert | A specialist bound to chosen sources and answering rules | `experts/<name>/expert.md` |
| Citation | A pointer back to the exact place in a source | `[mm:ss](url&t=Ns)` for videos, `(Book p.N)` for books |

## 5. Data flows

**YouTube ingestion** (`./scripts/yt.sh update`)
1. Take the run lock (one ingestion run at a time).
2. For each channel due for a listing (at most once a day), list its videos and merge them into `videos.json`.
3. Queue the videos without a transcript, channels taken in turn (round-robin).
4. For each video: use `raw/youtube/<slug>/<id>.json` if it exists; otherwise ask the guard, fetch the
   captions and save them to `raw/` first.
5. Process into a transcript and store it; record failures in `status.json`.
6. Always finish with dated file names, `INDEX.md` and `missing.log`, even after a Stop.

**Book ingestion** (`./scripts/books.sh <slug>`)
1. Read `books.txt` → PDF in `raw/books/`.
2. Process: extract text (OCR if scanned), find chapters (outline → bold headings → 25-page parts).
3. Store: rewrite `chapters/` only. `notes.md` is never touched.
4. In Claude Code, `/extract-book <slug>` reads the chapters and writes `notes.md`.

**Expert question answering** (Claude Code)
1. A question matches a skill's description, or the user calls `/<expert>`.
2. The skill reads `experts/<name>/expert.md`.
3. The expert greps its sources (`INDEX.md`, transcripts, `notes.md`, then `chapters/` for detail).
4. It answers with citations, or says the sources don't cover it.

## 6. Folder structure

| Folder | Responsibility |
|---|---|
| `raw/` | Original material: `books/` PDFs, `youtube/` caption snapshots and bookmarklet captures |
| `pipelines/video-pipeline/` | `youtube_ingestion` package, its tests and Docker image |
| `pipelines/book-pipeline/` | `book_ingestion` package, its tests and Docker image (Tesseract for OCR) |
| `knowledge-library/` | Processed Markdown and per-source metadata; `.guard.json` and `.lock` for YouTube |
| `experts/` | Expert definitions; `_template/` for new ones |
| `.claude/skills/` | Claude Code entry points; role skills are also linked into `~/.claude/skills/` |
| `scripts/` | `yt.sh`, `books.sh`, `test.sh`: every command |
| `docs/` | This file and the two pipeline docs |

Git holds only the tools and `experts/_template/`; `raw/`, `knowledge-library/`, `experts/` and
`.claude/skills/` stay local.

## 7. Design decisions

- **Local-first, plain files.** Everything is greppable Markdown and JSON; no database or search index.
- **Markdown with location markers** is the one convention every source follows, so any expert can cite
  any source the same way.
- **Source-grounded answers.** Experts cite or decline; they never fill gaps from model memory unless asked.
- **Independent pipelines.** Different dependencies (yt-dlp vs. PyMuPDF + Tesseract), different failure
  modes, separate Docker images. Shared conventions, no shared code.
- **Raw before processed.** Captions cost scarce requests, so they're saved before processing and reused.
- **The guard is separate and conservative.** Budget, pacing and blocks are persisted on disk and shared
  by every run; an admitted operation can be many HTTP requests (a yt-dlp listing).
- **Experts are tool-agnostic.** `expert.md` holds the content; `SKILL.md` is a three-line Claude adapter.
  Claude Code today, other models later through their own adapters.
- **Docker only.** No local Python environment to maintain; tests run in the image with no network.
- **Not yet:** article pipeline, semantic search, web UI. Add them when there's a real need.
