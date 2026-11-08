# YouTube pipeline

Code: `knowledge-acquisition/pipelines/video-pipeline/youtube_ingestion/`. Runs in Docker through `./scripts/yt.sh`.

Diagram: [video pipeline](diagrams/video-pipeline.mmd).

| Module | Job |
|---|---|
| `__main__.py` | The commands, the run lock, round-robin queue, `finish()` (dates, `INDEX.md`, `missing.log`) |
| `acquire.py` | Channel listing (yt-dlp), video lookup (oEmbed; yt-dlp for videos with embedding disabled), captions (youtube-transcript-api), reading bookmarklet files |
| `request_guard.py` | Budget, pacing and blocks; asked before every request |
| `process.py` | `Video` and `Segment`; captions → transcript Markdown. No disk, no network |
| `store.py` | `Collection`: everything on disk, raw snapshots included. No network |
| `save_transcript.js` | The bookmarklet source |

## Commands

```bash
./scripts/yt.sh setup                                   # build the image
./scripts/yt.sh add <channel_url> "<Name>" [slug]       # add a channel collection, list its videos, fetch transcripts
./scripts/yt.sh add <video_url>                         # same; the channel is found from one of its videos
./scripts/yt.sh grab <video_url> <topic>                # one video into a hand-picked topic collection
./scripts/yt.sh update [slug]                           # list new videos + fetch missing transcripts (all channels or one)
./scripts/yt.sh list                                    # progress per collection and the guard state (no network)
./scripts/yt.sh todo [slug] [-n N] [--open N]           # missing videos, the ones that failed 3 times first (no network)
./scripts/yt.sh reprocess [slug]                        # rebuild transcripts from raw captions only (no network)
./scripts/yt.sh bookmarklet                             # print the "Save transcript" bookmarklet
./scripts/yt.sh import [dir]                            # bookmarklet files → transcripts (default ~/Downloads, no network)
```

`./scripts/yt.sh update` with no slug takes the channels in turn, so one big channel can't use up the day's budget.
A channel is listed at most once a day. After `./scripts/yt.sh add`, ask Claude Code to *"create the <slug>
expert from experts/_template/"*.

`add <video_url>` looks the video up (oEmbed). If you already have its channel (matched by URL or name), it
updates that collection with this video first; otherwise it creates the channel collection. `grab` refuses a
slug that is a channel collection. `grab` skips a video already in the topic without making a request, so re-running a queue is free.

## How captions are fetched

- **Listing** (`yt-dlp --flat-playlist --sleep-requests 5`) only reads the channel's video list, never captions.
- **Captions** come from youtube-transcript-api, English only (`en`, `en-US`, `en-GB`), manual preferred to
  auto-generated, never a machine translation. Captions that come back empty count as `failed`.
- **Raw first:** fetched captions are saved to `knowledge-acquisition/raw/youtube/<slug>/<id>.json` before the
  transcript is written. A video with a valid snapshot is never fetched again; `reprocess` rebuilds every transcript from `raw/`
  (snapshots, then bookmarklet captures).
- Writes are atomic (temp file + rename). A transcript rebuilt under a new title or date replaces the old file.

## Rate limits (the guard)

Settings in `.env` (see `.env.example`): `YT_DAILY_LIMIT` (default 50), `YT_GAP_MIN` / `YT_GAP_MAX`
(seconds between caption requests, default 60–120).

- **Budget:** at most `YT_DAILY_LIMIT` admitted operations a day: one per video, channel listing or
  video lookup. A listing is many HTTP requests underneath; yt-dlp paces those itself.
- **Pace:** a random pause between caption requests, kept across runs.
- **Block:** the first 429 (or 402, which yt-dlp reports for the same IP limit) or bot check stops every
  request for 24 h (longer if YouTube sends Retry-After). A listing cut short this way still saves what it found.
- **Stop:** when the budget is used or a block starts, the run ends cleanly; progress is saved.
- 3 unexplained failures in a row also end the run.

State is in `knowledge-acquisition/state/youtube/.guard.json`, shared by every run (cron, terminals). The day
boundary is the host's local time (`/etc/localtime` is mounted). Only one run at a time (`.lock`): every
command except `list`, `todo` and `bookmarklet` takes it.

## Files

Knowledge Acquisition keeps its own files; it publishes only transcripts and `missing.log` to the library.

```
knowledge-acquisition/raw/youtube/<slug>/
  <video_id>.json                            captions as fetched (reused instead of fetching again)
  <video_id>.browser.json                    a bookmarklet capture after import
knowledge-acquisition/state/youtube/
  .guard.json, .lock                         guard state, run lock
  <slug>/channel_url, channel_name           channel collections only
  <slug>/videos.json                         every video we know of
  <slug>/status.json                         {video_id: {status, attempts, error}}

knowledge-library/youtube/<slug>/            what the experts read
  missing.log                                id <tab> status <tab> title
  transcripts/INDEX.md                       one row per transcript, newest first
  transcripts/<YYYY-MM-DD>-<title-slug>-<video_id>.md
```

**These formats must not change** (the experts depend on them):
- File name `<YYYY-MM-DD>-<title-slug>-<video_id>.md`; `0000-00-00` until the upload date is known,
  then renamed.
- Frontmatter, in this order: `title`, `video_id`, `url`, `channel`, `published_at`, `duration_seconds`,
  `transcript_source` (`manual`, `auto` or `browser`), `fetched_at`.
- Body: `# <title>`, then ~30 s paragraphs, each starting with `[mm:ss]` (`[hh:mm:ss]` past an hour).
- `INDEX.md` and `missing.log` as above.

## Videos the tool can't get (bookmarklet)

1. `./scripts/yt.sh bookmarklet` prints a `javascript:` URL: save it as a bookmark called *Save transcript*.
2. `./scripts/yt.sh todo` lists the missing videos (inside Docker, `--open` can't start a browser; click the links).
3. On each: open the transcript panel (*Show transcript*, or *In this video › Timeline*), click the bookmark.
   It saves `<id>.transcript.json` to Downloads. It only reads what's on screen and sends nothing.
4. `./scripts/yt.sh import` writes the transcripts (`transcript_source: browser`), updates `INDEX.md` and
   `missing.log`, and moves the files to `knowledge-acquisition/raw/youtube/<slug>/`.

Only videos already in a collection are imported.

## Troubleshooting

- **Blocked:** `./scripts/yt.sh list` shows until when. Wait it out; don't delete `.guard.json` or retry by hand.
- **"Another ./scripts/yt.sh run is already fetching":** a run (maybe cron) is still going; wait for it.
- **Channel listing breaks:** raise `yt-dlp` and `yt-dlp-ejs` in `knowledge-acquisition/pipelines/video-pipeline/requirements.txt`,
  then `./scripts/yt.sh setup`.
- **No captions:** a video marked `no_captions` or `unavailable` is never asked for again; `failed` is
  retried up to 3 times, then listed first by `./scripts/yt.sh todo` for the bookmarklet.

## Tests

`./scripts/test.sh`: 43 tests, no network. They cover the formats above, that only transcripts and
`missing.log` reach the library, the guard (budget, block,
restart, day boundary, Retry-After), the lock, raw reuse and the bookmarklet import.
