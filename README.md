# youtube-specialist

Turn any YouTube channel into a Claude Code skill that answers from that channel's actual video transcripts, quoting with `[mm:ss]` links instead of guessing from general knowledge.

## Quick start

```bash
git clone git@github.com:KennySoh/youtube-specialist.git
cd youtube-specialist
./yt setup                                                    # once: .venv + dependencies
./yt add "https://www.youtube.com/@SomeChannel" "Some Channel"   # fetch every transcript
```

Then open Claude Code in this repo and say:

> create the some-channel skill from templates/SKILL.md

Claude reads the transcripts, fills in the template (persona, coverage, the creator's vocabulary) and saves it as `.claude/skills/some-channel/SKILL.md`. Now ask away:

```
/some-channel what do you recommend for ...?
```

## Commands

```bash
./yt add <channel_url> "<Name>" [slug]   # new channel (slug defaults to the name, lowercased)
./yt update                              # pull new videos for every channel
./yt update <slug>                       # just one channel
./yt list                                # channels, transcript counts, missing counts
```

Re-running is always safe: videos that already have a transcript are skipped, and ones that failed before are retried.

## What's where

```
yt                          # the only command you need
templates/SKILL.md          # starting point for each /<slug> skill
scripts/                    # the Python steps ./yt runs (list → fetch → fix dates → index)
youtuber/<slug>/            # created by ./yt add — not committed
  channel_url, channel_name # remembered so `./yt update` needs no arguments
  transcripts/              # one .md per video + INDEX.md
  data/                     # index.json, missing.log (videos with no transcript yet)
.claude/skills/<slug>/      # your generated skills — not committed
```

Channel data and generated skills are git-ignored: the transcripts are the creators' content, so each user builds their own locally.

## Transcript format

```markdown
---
title: Some Video Title
video_id: abc123XYZ_0
url: https://www.youtube.com/watch?v=abc123XYZ_0
channel: Some Channel
published_at: '2026-05-02'
transcript_source: auto
---

# Some Video Title

[00:00] Hey everyone, ...
[00:32] ...
```

Captions are grouped into ~30-second `[mm:ss]` blocks so the skill can cite a working `&t=<seconds>s` link.

## Gotchas

- **Missing transcripts.** Some videos have no captions, and YouTube rate-limits large fetches. Failures land in `data/missing.log`; run `./yt update <slug>` again later.
- **Unknown dates.** For some channels YouTube's listing doesn't return upload dates, so files are named `0000-00-00-…`. Tell the skill to treat those videos as undated.
- **Noisy captions.** Auto-generated captions mangle names and numbers; skills quote them as-is rather than rewriting.
