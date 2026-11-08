# YouTube pipeline

Code: `pipelines/video-pipeline/youtube_ingestion/`. Runs in Docker through `./scripts/yt.sh`.

## Commands

```bash
./scripts/yt.sh setup                                   # build the image
./scripts/yt.sh add <channel_url> "<Name>" [slug]       # add a channel collection, list its videos, fetch transcripts
./scripts/yt.sh add <video_url>                         # same; the channel is found from one of its videos
./scripts/yt.sh grab <video_url> <topic>                # one video into a hand-picked topic collection
./scripts/yt.sh update [slug]                           # list new videos + fetch missing transcripts (all channels or one)
./scripts/yt.sh list                                    # progress per collection and the guard state (no network)
./scripts/yt.sh todo [slug] [-n N] [--open N]           # missing videos, the ones that failed 3 times first (no network)
./scripts/yt.sh reprocess [slug]                        # rebuild transcripts from raw/ only (no network)
./scripts/yt.sh bookmarklet                             # print the "Save transcript" bookmarklet
./scripts/yt.sh import [dir]                            # bookmarklet files → transcripts (default ~/Downloads, no network)
```

`./scripts/yt.sh update` with no slug takes the channels in turn, so one big channel can't use up the day's budget.
A channel is listed at most once a day. After `./scripts/yt.sh add`, ask Claude Code to *"create the <slug>
expert from experts/_template/"*.

## Rate limits (the guard)

Settings in `.env` (see `.env.example`): `YT_DAILY_LIMIT` (default 50), `YT_GAP_MIN` / `YT_GAP_MAX`
(seconds between caption requests, default 60–120).

- **Budget:** at most `YT_DAILY_LIMIT` admitted operations a day: one per video, channel listing or
  video lookup. A listing is many HTTP requests underneath; yt-dlp paces those itself.
- **Pace:** a random pause between caption requests, kept across runs.
- **Block:** the first 429 or bot check stops every request for 24 h (longer if YouTube sends Retry-After).
- **Stop:** when the budget is used or a block starts, the run ends cleanly; progress is saved.
- 3 unexplained failures in a row also end the run.

State is in `knowledge-library/youtube/.guard.json`, shared by every run (cron, terminals). Only one
run at a time (`.lock`).

## Files

```
raw/youtube/<slug>/<video_id>.json           captions as fetched (reused instead of fetching again)
raw/youtube/<slug>/<video_id>.browser.json   a bookmarklet capture after import
knowledge-library/youtube/.guard.json        guard state
knowledge-library/youtube/<slug>/
  channel_url, channel_name                  channel collections only
  videos.json                                every video we know of
  status.json                                {video_id: {status, attempts, error}}
  missing.log                                id <tab> status <tab> title (read by the experts)
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
   `missing.log`, and moves the files to `raw/youtube/<slug>/`.

Only videos already in a collection are imported.

## Troubleshooting

- **Blocked:** `./scripts/yt.sh list` shows until when. Wait it out; don't delete `.guard.json` or retry by hand.
- **"Another ./scripts/yt.sh run is already fetching":** a run (maybe cron) is still going; wait for it.
- **Channel listing breaks:** raise `yt-dlp` and `yt-dlp-ejs` in `pipelines/video-pipeline/requirements.txt`,
  then `./scripts/yt.sh setup`.
- **No captions:** a video marked `no_captions` or `unavailable` is never asked for again; `failed` is
  retried up to 3 times, then listed first by `./scripts/yt.sh todo` for the bookmarklet.

## Tests

`./scripts/test.sh`: 39 tests, no network. They cover the formats above, the guard (budget, block,
restart, day boundary, Retry-After), the lock, raw reuse and the bookmarklet import.
