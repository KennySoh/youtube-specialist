# youtube-specialist

Turn a YouTube channel into a Claude Code skill that answers from the channel's own transcripts, with `[mm:ss]` links.

## Setup

**Local** (Python 3.10+):

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

Then, in Claude Code: *"create the some-channel skill from templates/SKILL.md"*, and ask `/some-channel …`.

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

## Development

```bash
.venv/bin/python -m pytest tests   # never contacts YouTube
```

Code: `ytspec/youtube.py` (requests), `guard.py` (rate limits), `library.py` (disk),
`__main__.py` (commands). If channel listing breaks, update yt-dlp with
`.venv/bin/pip install -U yt-dlp yt-dlp-ejs` and copy the new versions into `requirements.txt`.
