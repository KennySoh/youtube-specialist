# youtube-specialist

Turn sources into Claude Code skills that answer from the source itself, with citations:

| Pipeline | Source → files | Marker | Skills |
|---|---|---|---|
| `./yt` | YouTube channel → `library/<slug>/transcripts/*.md` + `INDEX.md` | `[mm:ss]` | one persona per channel (`.claude/skills/<slug>/`) |
| `./books` | PDF → `knowledge/<slug>/chapters/*.md`, then `/extract-book` → `notes.md` | `<!-- p.N -->` | role skills (`role-skills/`, linked into `~/.claude/skills/`) |

The two tools share no code, only this convention: one Markdown file per source with location
markers, an index or notes file, and skills that grep the files and cite the marker. Details:
[docs/youtube.md](docs/youtube.md), [docs/books.md](docs/books.md).

# YouTube

## Setup

**Local** (Python 3.10+; uses `uv` if `python3-venv` isn't installed):

```bash
./yt setup
```

**Or Docker:**

```bash
docker compose build
alias yt='docker compose run --rm yt'   # run from this folder; use `yt …` wherever this guide says `./yt …`
```

Optional: `cp .env.example .env` to change the daily limit or the pause between videos.

## Use

```bash
./yt add "https://www.youtube.com/@SomeChannel" "Some Channel"   # add a channel, start fetching
./yt add "https://youtu.be/<id>"                                 # same, found from one of its videos
./yt grab "https://youtu.be/<id>" <topic>                        # just one video, into a topic
./yt update [slug]                                               # new videos + missing transcripts
./yt list                                                        # progress and today's budget (no network)
```

Then, in Claude Code: *"create the some-channel skill from templates/channel-skill.md"*, and ask `/some-channel …`.

Transcripts land in `library/<slug>/transcripts/`. That folder, and your skills, are git-ignored.

## Daily runs

About 50 videos a day get fetched, so a big channel takes several days. It's safe to re-run at any
time: anything already fetched is skipped. To run it daily with cron (`crontab -e`):

```
0 3 * * * cd /path/to/youtube-specialist && ./yt update >> fetch.log 2>&1
```

(With Docker: `docker compose run --rm yt update`.)

## If YouTube blocks you

A 429 stops every request for 24 h. `./yt list` shows when the block ends. Wait it out: don't
delete `library/.guard.json` or retry by hand.

# Books

PDFs stay outside the repo, in `BOOKS_DIR` (default `~/books`; set it in `.env`). Needs Docker.

```bash
./books                    # convert every book in knowledge/books.txt (skips converted ones)
./books the-mom-test       # one book; add --force to re-convert
```

Add a book: append `<slug> <path relative to BOOKS_DIR>` to `knowledge/books.txt`, run `./books <slug>`,
then `/extract-book <slug>` in Claude Code. `knowledge/` and `role-skills/` are git-ignored.

The role skills (product-manager, ux-designer, software-architect, software-engineer) are used from
other projects, so they're symlinked into `~/.claude/skills/` and read `knowledge/` by absolute path:

```bash
for r in role-skills/*; do ln -sfn "$PWD/$r" ~/.claude/skills/; done
```

# Development

```bash
.venv/bin/python -m pytest tests   # never contacts YouTube
```

Code: `ytspec/youtube.py` (requests), `guard.py` (rate limits), `library.py` (disk),
`transcript.py` (the file format the skills read), `__main__.py` (commands). Books: `pdf2md/pdf2md.py`. If channel listing breaks, update yt-dlp with
`.venv/bin/pip install -U yt-dlp yt-dlp-ejs` and copy the new versions into `requirements.txt`.
