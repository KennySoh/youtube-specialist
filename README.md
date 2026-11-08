# My AI Brain

Your knowledge. Your experts. Your personal AI.

1. **Collect knowledge**: books and YouTube (notes and documents later) become a searchable library.
2. **Personalize**: choose the sources, topics and perspectives that matter to you.
3. **Create AI experts**: specialists that answer only from the sources you chose, with citations.
   Claude Code today; ChatGPT or a local model later.

## Layout

| Folder | Domain | Responsibility |
|---|---|---|
| `raw/` | Raw sources | Originals: book PDFs in `raw/books/`, captions as fetched in `raw/youtube/<slug>/<id>.json` |
| `pipelines/` | Knowledge acquisition | Collect and process sources: `video-pipeline/`, `book-pipeline/` |
| `knowledge-library/` | Knowledge library | Searchable Markdown: `youtube/`, `books/`, `notes/` (later) |
| `experts/` | AI experts | `experts/<name>/expert.md`: who the expert is, which sources it may use, how it answers |
| `.claude/skills/` | Claude integration | `SKILL.md` per expert: when Claude uses it, then "read expert.md" |
| `scripts/` | Commands | `yt.sh`, `books.sh`, `test.sh`; `./yt` and `./books` at the root are symlinks |

`raw/`, `knowledge-library/`, `experts/` and `.claude/skills/` are git-ignored: the repo ships only
the tools, plus `experts/_template/` (a starting `expert.md` and `SKILL.md`).

Every source follows one convention, so any expert can cite it: one Markdown file per source with
location markers, an index or notes file, and experts that grep the files and cite the marker.

| Source | Pipeline | Library files | Marker |
|---|---|---|---|
| YouTube channel | `./yt` | `knowledge-library/youtube/<slug>/transcripts/*.md` + `INDEX.md`, `missing.log` | `[mm:ss]` |
| Book (PDF) | `./books`, then `/extract-book` | `knowledge-library/books/<slug>/chapters/*.md` + `notes.md` | `<!-- p.N -->` |


## Setup

Everything runs in Docker; nothing to install but Docker itself.

```bash
./yt setup                      # build the YouTube image (later runs rebuild it when the code changes)
cp .env.example .env            # optional: daily limit, pauses, BOOKS_DIR
```

`./books` builds its own image on first use (it needs Tesseract for scanned PDFs).

## Conventions (experts depend on these; don't change them)

- Transcript files: `<YYYY-MM-DD>-<title-slug>-<video_id>.md` (`0000-00-00` until the date is known),
  frontmatter `title`, `video_id`, `url`, `channel`, `published_at`, `duration_seconds`,
  `transcript_source` (`manual`, `auto` or `browser`), `fetched_at`; body in ~30 s `[mm:ss]` paragraphs.
- `INDEX.md` and `missing.log` (`id <tab> status <tab> title`) per collection.
- Book chapters: `chapters/NN-title.md` with `<!-- p.N -->` before every page (N = PDF page).
- The commands, and the guard: never a request while blocked or over budget.

Words used in the code: a **collection** is one folder in `knowledge-library/youtube/` (a **channel
collection** has a `channel_url`, a **topic collection** doesn't); **captions** are what YouTube has
(`manual` or `auto`); a **transcript** is our `.md`; a **status** says why a video has none
(`no_captions`, `unavailable`, `failed`, retried up to 3 times); the **guard** is the daily **budget**,
the **pace** (60–120 s between caption requests) and the 24 h **block** after a 429 or bot check.

# YouTube

```bash
./yt add "https://www.youtube.com/@SomeChannel" "Some Channel"   # add a channel, start fetching
./yt add "https://youtu.be/<id>"                                 # same, found from one of its videos
./yt grab "https://youtu.be/<id>" <topic>                        # just one video, into a topic
./yt update [slug]                                               # new videos + missing transcripts
./yt list                                                        # progress and today's budget (no network)
./yt todo [slug] [--open N]                                      # what's still missing, hardest first (no network)
./yt import [dir]                                                # bookmarklet captures → transcripts (no network)
./yt reprocess [slug]                                            # rebuild transcripts from raw/ (no network)
```

`./yt update` with no slug takes the channels in turn, so one big channel can't use up the day's budget.
Every fetch keeps the captions in `raw/youtube/<slug>/<id>.json`; a video with a raw snapshot is
built from it instead of asking YouTube again, and `./yt reprocess` rebuilds transcripts from `raw/` alone.
Then, in Claude Code: *"create the some-channel expert from experts/_template/"*, and ask `/some-channel …`.

## Daily runs

About 50 videos a day get fetched, so a big channel takes several days. It's safe to re-run at any
time: anything already fetched is skipped. To run it daily with cron (`crontab -e`):

```
0 3 * * * cd /path/to/this/repo && ./yt update >> fetch.log 2>&1
```

## If YouTube blocks you

A 429 stops every request for 24 h. `./yt list` shows when the block ends. Wait it out: don't
delete `knowledge-library/youtube/.guard.json` or retry by hand.

## Videos the tool can't get (one click each)

1. `./yt bookmarklet` prints a `javascript:` URL: save it as a bookmark called *Save transcript*.
2. `./yt todo --open 5` opens the next 5 missing videos in your browser.
3. On each: open the transcript panel (*Show transcript*, or *In this video › Timeline*), then click the bookmark.
   It saves `<id>.transcript.json` to your Downloads. It reads only what's on screen and sends nothing.
4. `./yt import` (default `~/Downloads`) writes the transcripts (`transcript_source: browser`),
   updates `INDEX.md` and `missing.log`, and moves the files to `raw/youtube/<slug>/<id>.browser.json`.

Only videos already in a collection are imported. `~/Downloads` is mounted into the container;
inside Docker `--open` can't start your browser, so it just lists the links.

# Books

```bash
./books                    # convert every book in knowledge-library/books/books.txt (skips converted ones)
./books the-mom-test       # one book; add --force to re-convert
```

Add a book: put the PDF under `raw/books/` (or set `BOOKS_DIR`), append `<slug> <path relative to it>`
to `knowledge-library/books/books.txt`, run `./books <slug>`, then `/extract-book <slug>` in Claude Code.
`./books --force` rewrites `chapters/` only; `notes.md` is never touched. Open book work is tracked in
`knowledge-library/books/plan.md`.

## Book notes (`notes.md`)

Written by `/extract-book` from `chapters/`, read first by the role experts.

1. **Overview**: thesis, mental model, chapter → topic map, missing pages.
2. **Concepts**, one section each: **Claim** (with page), **Why**, **When / when not**, **How to apply**,
   **Anti-pattern**, **Review question + evidence**, **Related**. Mark your own interpretation or
   example with *(interpretation)*.
3. **Checklist**: review questions the experts ask.

Split into `notes/<topic>.md` only past ~500 lines. Rules:

1. **Only cite what's in `chapters/`.** Never invent pages or quotes; say which pages are missing.
   `p.N` is the PDF page from the `<!-- p.N -->` markers, not the number printed in the book.
2. **Keep the reasoning, not just the rule**: the why, trade-offs and exceptions; paraphrase.
3. **Judgment, not dogma**: when books conflict, explain the context and record the decision.
4. **Experts stay short**: read `notes.md` first, then grep `chapters/` for exact detail.

The role experts (product-manager, ux-designer, software-architect, software-engineer) are used from
other projects, so their skills are symlinked into `~/.claude/skills/` and use absolute paths:

```bash
for r in product-manager ux-designer software-architect software-engineer; do
  ln -sfn "$PWD/.claude/skills/$r" ~/.claude/skills/$r
done
```

# Development

```bash
./scripts/test.sh     # both pipelines' tests in Docker: no network, no real data mounted
```

Every pipeline has the same steps: **acquire** (get the source) → **process** (turn it into
Markdown) → **store** (write `raw/` and `knowledge-library/`); `__main__.py` runs them in order.

- `pipelines/video-pipeline/youtube_ingestion/`: `acquire.py` (every YouTube request, plus bookmarklet
  captures), `request_guard.py` (rate limits), `process.py` (captions → transcript Markdown, shared types),
  `store.py` (all disk I/O), `__main__.py` (commands).
- `pipelines/book-pipeline/book_ingestion/`: `process.py` (PDF → pages and chapters, OCR), `store.py`
  (`books.txt`, chapter files), `__main__.py`. No acquire step: you put the PDFs in `raw/books/`.

If channel listing breaks, raise the `yt-dlp` and `yt-dlp-ejs` versions in
`pipelines/video-pipeline/requirements.txt`, then `./yt setup`.
