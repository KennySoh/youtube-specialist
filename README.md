# My AI Brain

**Your knowledge. Your experts. Your personal AI.**

Turn YouTube videos and books into a personal, searchable knowledge library. Create AI experts that
answer from your chosen sources, with citations.

### How it works

1. **Collect knowledge**: import YouTube transcripts and books.
2. **Personalize**: organize and select the knowledge that matters to you.
3. **Create AI experts**: source-grounded specialists in Claude Code today, other AI models later.

**Architecture:** Acquire → Raw → Process → Store → Knowledge Library → AI Experts

## Project structure

```text
my-ai-brain/
├── raw/                    # Original PDFs and YouTube captions
│   ├── books/
│   └── youtube/
│
├── pipelines/              # Acquire, process and store knowledge
│   ├── video-pipeline/
│   │   └── youtube_ingestion/
│   └── book-pipeline/
│       └── book_ingestion/
│
├── knowledge-library/      # Processed, searchable Markdown
│   ├── youtube/
│   ├── books/
│   └── notes/
│
├── experts/                # Expert definitions and source rules
├── .claude/skills/         # Claude Code integration
├── scripts/                # CLI commands and tests (./yt and ./books are shortcuts)
├── docs/
└── compose.yaml
```

Each pipeline uses simple `acquire.py`, `process.py` and `store.py` modules where needed. YouTube is
acquired automatically; books are added by hand.

## Quick start

Requires Docker.

```bash
./yt setup
cp .env.example .env       # optional configuration
```

### YouTube

```bash
./yt add "https://youtube.com/@channel" "Channel Name"
./yt grab "https://youtu.be/VIDEO_ID" business
./yt update                # fetch new and missing videos
./yt list                  # progress and request budget
./yt todo                  # videos still missing
./yt reprocess             # rebuild Markdown from saved raw captions
```

Transcripts are saved in `knowledge-library/youtube/` with `[mm:ss]` timestamps.

YouTube requests are rate-limited (about 50 a day). A 429 triggers a 24-hour block. Captions already
saved in `raw/` are reused instead of fetched again.

For videos the tool can't get, use `./yt bookmarklet` and `./yt import`.

### Books

Place PDFs in `raw/books/` and register them in `knowledge-library/books/books.txt`.

```bash
./books                    # convert all registered books
./books the-mom-test       # convert one book
./books the-mom-test --force
```

Books become Markdown chapters with `<!-- p.N -->` PDF page markers.

In Claude Code, `/extract-book <slug>` writes a structured `notes.md`: concepts, reasoning, trade-offs
and page references.

## AI experts

Expert definitions live in `experts/<name>/expert.md`, with Claude Code entry points in `.claude/skills/`.

Examples:
- **Creator experts:** Noah Kagan, Alex Teo, David Heacock.
- **Role experts:** Product Manager, UX Designer, Software Architect, Software Engineer.

Each expert searches its selected sources and answers with citations. If the sources don't support an
answer, it says so.

Create a new expert from `experts/_template/`.

## Automation and development

Run YouTube updates daily:

```cron
0 3 * * * cd /path/to/my-ai-brain && ./yt update >> fetch.log 2>&1
```

Run the offline tests:

```bash
./scripts/test.sh
```

Original books, transcripts, knowledge and personal experts are kept locally and git-ignored. Back
them up separately.

## Documentation

- [Software architecture](docs/software-architecture.md): responsibilities, domain model, data flows, design decisions.
- [YouTube pipeline](docs/youtube.md): commands, rate limits, file formats, bookmarklet, troubleshooting.
- [Book pipeline](docs/books.md): PDF conversion, notes format, citation rules.

**Design principle:** keep source pipelines independent, preserve original material, and let AI
experts use the knowledge without depending on how it was acquired.
