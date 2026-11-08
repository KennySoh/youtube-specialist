# My AI Brain

Your knowledge. Your experts. Your personal AI.

1. **Collect knowledge**: books and YouTube (notes and documents later) become a searchable library.
2. **Personalize**: choose the sources, topics and perspectives that matter to you.
3. **Create AI experts**: specialists that answer only from the sources you chose, with citations.
   Claude Code today; ChatGPT or a local model later.

## Layout

| Folder | Domain | Responsibility |
|---|---|---|
| `raw/` | Raw sources | Original files you import (book PDFs in `raw/books/`) |
| `pipelines/` | Knowledge acquisition | Collect and process sources: `video-pipeline/`, `book-pipeline/` |
| `knowledge-library/` | Knowledge library | Searchable Markdown: `youtube/`, `books/`, `notes/` (later) |
| `experts/` | AI experts | `experts/<name>/expert.md`: who the expert is, which sources it may use, how it answers |
| `.claude/skills/` | Claude integration | `SKILL.md` per expert: when Claude uses it, then "read expert.md" |
| `scripts/` | Commands | `scripts/yt`, `scripts/books`; `./yt` and `./books` at the root are symlinks to them |

`raw/`, `knowledge-library/`, `experts/` and `.claude/skills/` are git-ignored: the repo ships only
the tools. `templates/` has a starting `expert.md` and `SKILL.md`.

Every source follows one convention, so any expert can cite it: one Markdown file per source with
location markers, an index or notes file, and experts that grep the files and cite the marker.

| Source | Pipeline | Library files | Marker |
|---|---|---|---|
| YouTube channel | `./yt` | `knowledge-library/youtube/<slug>/transcripts/*.md` + `INDEX.md`, `missing.log` | `[mm:ss]` |
| Book (PDF) | `./books`, then `/extract-book` | `knowledge-library/books/<slug>/chapters/*.md` + `notes.md` | `<!-- p.N -->` |

Details: [docs/youtube.md](docs/youtube.md), [docs/books.md](docs/books.md).

## Setup

```bash
./yt setup                      # Python 3.10+ venv (uses uv if python3-venv is missing)
cp .env.example .env            # optional: daily limit, pauses, BOOKS_DIR
```

Or with Docker: `docker compose build`, then `docker compose run --rm yt <command>`.
`./books` always runs in Docker (it needs Tesseract for scanned PDFs).

# YouTube

```bash
./yt add "https://www.youtube.com/@SomeChannel" "Some Channel"   # add a channel, start fetching
./yt add "https://youtu.be/<id>"                                 # same, found from one of its videos
./yt grab "https://youtu.be/<id>" <topic>                        # just one video, into a topic
./yt update [slug]                                               # new videos + missing transcripts
./yt list                                                        # progress and today's budget (no network)
./yt todo [slug] [--open N]                                      # what's still missing, hardest first (no network)
./yt import [dir]                                                # bookmarklet captures → transcripts (no network)
```

`./yt update` with no slug takes the channels in turn, so one big channel can't use up the day's budget.
Then, in Claude Code: *"create the some-channel expert from templates/"*, and ask `/some-channel …`.

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
   updates `INDEX.md` and `missing.log`, and moves the files to `knowledge-library/youtube/_imported/`.

Only videos already in a collection are imported. With Docker, run `import` locally or mount the folder.

# Books

```bash
./books                    # convert every book in knowledge-library/books/books.txt (skips converted ones)
./books the-mom-test       # one book; add --force to re-convert
```

Add a book: put the PDF under `raw/books/` (or set `BOOKS_DIR`), append `<slug> <path relative to it>`
to `knowledge-library/books/books.txt`, run `./books <slug>`, then `/extract-book <slug>` in Claude Code.

The role experts (product-manager, ux-designer, software-architect, software-engineer) are used from
other projects, so their skills are symlinked into `~/.claude/skills/` and use absolute paths:

```bash
for r in product-manager ux-designer software-architect software-engineer; do
  ln -sfn "$PWD/.claude/skills/$r" ~/.claude/skills/$r
done
```

# Development

```bash
cd pipelines/video-pipeline && ../../.venv/bin/python -m pytest tests   # never contacts YouTube
```

- `pipelines/video-pipeline/youtube_ingestion/`: `youtube_client.py` (every request), `request_guard.py`
  (rate limits), `knowledge_library.py` (disk), `transcript.py` (the file format experts read),
  `browser.py` (bookmarklet imports), `__main__.py` (commands).
- `pipelines/book-pipeline/book_ingestion/pdf_to_markdown.py`: PDF → chapters with page markers.

If channel listing breaks, update yt-dlp with `.venv/bin/pip install -U yt-dlp yt-dlp-ejs` and copy
the new versions into `pipelines/video-pipeline/requirements.txt`.
