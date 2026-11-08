# YouTube pipeline (ytspec): design notes

## What it does

A personal CLI tool. It downloads the English captions of YouTube videos and saves one Markdown
transcript per video. Claude Code "skills" (prompt files) then grep those transcripts, so they can
answer questions as a given YouTuber and cite `[mm:ss]` timestamps.

- One user, one machine, runs daily from cron. Python 3.10+, about 650 lines, plus Docker.
- **The hard constraint is YouTube rate limiting (HTTP 429).** The real ceiling is ~50
  requests/day. One 429 means waiting 24 h. Most of the design exists to never trigger one.
- **Goal of the code:** simple and readable, with light DDD-style naming. No frameworks and no
  layers for their own sake.

## Commands

```
./yt setup                              create .venv
./yt add <channel_url> "<Name>"         add a channel collection, list its videos, fetch transcripts
./yt add <video_url>                    same, the channel is found from one of its videos
./yt grab <video_url> <topic>           one video into a hand-picked "topic" collection
./yt update [slug]                      list new videos + fetch missing transcripts (all channels or one)
./yt list                               progress + guard state, no network
```

`./yt` is a 14-line bash wrapper. It runs `setup`, loads `.env`, then runs `python -m ytspec`.
Docker: `docker compose run --rm yt <command>`, with `library/` mounted from the host.

## Vocabulary (used in the code)

| Word | Meaning |
|---|---|
| library | `library/`: every collection |
| collection | one folder `library/<slug>/`. A **channel collection** has a `channel_url`; a **topic collection** doesn't |
| video | one entry in `videos.json` |
| captions | what YouTube has: `manual` or `auto` |
| transcript | our `.md` file built from the captions, in ~30 s `[mm:ss]` paragraphs |
| status | why a video has no transcript: `no_captions`, `unavailable`, `failed` (retried up to 3 attempts) |
| guard | the rate-limit rules: daily **budget**, **pace** (random 60–120 s between caption requests), **block** (24 h stop after a 429 or bot check) |
| Stop | the exception meaning "no more requests now, progress saved" |

## Structure

```
yt                    bash wrapper (14 lines)
ytspec/
  __main__.py   175   argparse commands; fetch loop (fetch_transcripts); update = list + fetch + write index; file lock (fcntl)
  youtube.py    137   all network: list_channel (yt-dlp subprocess), lookup_video (oEmbed), fetch_captions (youtube-transcript-api)
  guard.py       73   budget/pace/block; state in library/.guard.json; allow(paced) raises Stop
  transcript.py      Video/Segment dataclasses and the transcript file format (name, frontmatter, [mm:ss] paragraphs)
  library.py         Collection (all disk I/O), INDEX.md, missing.log, status records (record_failure, gave_up)
tests/test_ytspec.py  19 tests, no network (fetch_captions is monkeypatched)
Dockerfile, compose.yaml
templates/channel-skill.md    template for the channel skills
```

Dependency direction: `__main__` → `youtube` → `guard` → `library` → `transcript`. Nothing imports `__main__`.

On disk:

```
library/.guard.json               {"day", "used", "last_paced", "blocked_until", "reason", ...}
library/<slug>/channel_url        channel collections only
library/<slug>/channel_name
library/<slug>/videos.json        list of Video dicts
library/<slug>/status.json        {video_id: {"status", "attempts", "error"}}
library/<slug>/missing.log        id \t status \t title   (read by the skills)
library/<slug>/transcripts/*.md   <YYYY-MM-DD>-<title-slug>-<video_id>.md, plus INDEX.md
```

## Key signatures

```python
# youtube.py
class NoTranscript(Exception): status: str; error: str
def list_channel(channel_url: str) -> list[Video]        # on a 429, records the block but still returns partial results
def lookup_video(url: str) -> Video                      # raises UserError for user-facing errors
def fetch_captions(video_id: str) -> tuple[str, list[Segment]]   # raises NoTranscript or guard.Stop

# guard.py
class Stop(Exception)
def allow(paced: bool = False) -> None                    # call before every request: raises Stop or counts the request (and sleeps if paced)
def block(reason, target, error, retry_after=None) -> Stop   # persists the block, returns the exception to raise
def stop_reason() -> str | None

# transcript.py
@dataclass Video(id, title, url, channel, channel_url, upload_date, duration, view_count)  # .published -> "YYYY-MM-DD"
@dataclass Segment(start, text, duration)
def render(video, captions, segments) -> str;  file_name(published, title, id);  read(path);  join(frontmatter, body)

# library.py
ROOT = $YT_LIBRARY or <repo>/library
def record_failure(statuses, video_id, status, error);  gave_up(status: dict | None) -> bool
def find_channel(video) -> Collection | None
class Collection(slug):
    all(), channels(), create(slug, channel_url=None, channel_name=None)
    channel_url, channel_name, videos(), save_videos(), listed_within(hours)
    statuses(), save_statuses(), transcript_files() -> {id: Path}
    write_transcript(), date_transcripts(videos), write_index(), write_missing()

# __main__.py
def fetch_transcripts(c, first: Video | None = None, only: bool = False)   # the fetch loop + status bookkeeping
def update(c, first=None, only=False)                    # list (if channel and older than 24 h) → fetch → finally: dates, INDEX.md, missing.log
```

## What must not change

The skills depend on these:

- The transcript file name and frontmatter: `title`, `video_id`, `url`, `channel`, `published_at`,
  `duration_seconds`, `transcript_source`, `fetched_at`
- The `[mm:ss]` body, `INDEX.md` and `missing.log`
- The commands
- The guard behaviour: never send a request while blocked or over budget

## Decisions (2026-11-08 refactor)

- Split the transcript format out of `library.py` into `transcript.py`: the format the skills
  depend on lives in one file. Output is byte-identical to before.
- Status records stay plain dicts; `record_failure()` is the one place that writes them.
- `__main__.py` keeps the fetch loop: 175 lines with one job; no service layer.
- `guard.py` reads its JSON on every call on purpose (state shared across processes and cron).
- `ROOT` no longer depends on the working directory (`YT_LIBRARY` or `<repo>/library`).
- `youtube.py` raises `UserError` instead of `SystemExit`; `main()` prints it and exits 1.
- `find_channel` scanning every collection is fine at ~10 collections.
- `list_channel` records a 429 without raising so the partial listing is saved; commented at both ends.
