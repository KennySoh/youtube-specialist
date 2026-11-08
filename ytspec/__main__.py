"""The ./yt commands. The only module that uses both youtube.py (requests) and library.py (disk)."""
from __future__ import annotations

import argparse
import fcntl
import sys

from slugify import slugify

from . import guard, youtube
from .library import ROOT, Collection, Video, find_channel, gave_up

LIST_EVERY_HOURS = 24      # a channel is listed at most once a day
MAX_FAILED_IN_A_ROW = 3    # unexplained failures in a row end the run
SKILL_HINT = 'Next: ask Claude to "create the {} skill" from templates/SKILL.md'


def fetch_transcripts(c: Collection, first: Video | None = None, only: bool = False) -> None:
    """Fetch every video in the collection that has no transcript yet. first: fetch it before the rest
    (added to videos.json if it isn't there). only: fetch just first."""
    videos = c.videos()
    if first and first.id not in {v.id for v in videos}:
        videos.append(first)  # newer than the last listing; the next listing fills in its date
        c.save_videos(videos)
    done, statuses = c.transcript_files(), c.statuses()
    todo = [v for v in videos if v.id not in done and not gave_up(statuses.get(v.id))]
    if first:
        if first.id in done:
            print(f"{first.id} already has a transcript")
        elif gave_up(s := statuses.get(first.id)):
            print(f"{first.id} was tried before: {s['status']} ({s['error']})")
        todo.sort(key=lambda v: v.id != first.id)
        if only:
            todo = [v for v in todo if v.id == first.id]
    print(f"{len(done)} done, {len(todo)} to fetch")

    failed_in_a_row = 0
    for video in todo:
        try:
            captions, segments = youtube.fetch_captions(video.id)
        except youtube.NoTranscript as e:
            statuses[video.id] = {"status": e.status, "attempts": statuses.get(video.id, {}).get("attempts", 0) + 1,
                                  "error": e.error}
            c.save_statuses(statuses)
            print(f"{e.status:12s} {video.id}  {e.error}", flush=True)
            failed_in_a_row = failed_in_a_row + 1 if e.status == "failed" else 0
            if failed_in_a_row >= MAX_FAILED_IN_A_ROW:
                raise guard.Stop(f"{MAX_FAILED_IN_A_ROW} failures in a row; stopping before YouTube gets annoyed")
            continue
        c.write_transcript(video, captions, segments)
        if statuses.pop(video.id, None):
            c.save_statuses(statuses)
        failed_in_a_row = 0
        print(f"{captions:12s} {video.id}  {video.title[:60]}", flush=True)


def update(c: Collection, first: Video | None = None, only: bool = False) -> None:
    """List the channel's new videos (channel collections), then fetch the missing transcripts."""
    print(f"→ {c.channel_name} ({c.slug})")
    try:
        if c.channel_url and not only:
            if c.listed_within(LIST_EVERY_HOURS):
                print(f"video list is under {LIST_EVERY_HOURS}h old; not listing again")
            else:
                listed = youtube.list_channel(c.channel_url)
                for v in listed:
                    v.channel = v.channel or c.channel_name
                old = c.videos()
                ids = {v.id for v in listed}
                c.save_videos(listed + [v for v in old if v.id not in ids])  # a cut-short listing loses nothing
                print(f"found {len(listed)} videos ({len(ids - {v.id for v in old})} new)")
        fetch_transcripts(c, first, only)
    finally:
        c.date_transcripts(c.videos())
        c.write_index()
        c.write_missing()


def add(args) -> None:
    if youtube.VIDEO_URL.search(args.url):
        video = youtube.lookup_video(args.url)
        if c := find_channel(video):
            print(f'"{video.title}" is from {c.channel_name}, which you already have ({c.slug}).')
            update(c, first=video)
            return
        name = args.name or video.channel
        c = Collection.create(args.slug or slugify(name), video.channel_url, name)
        print(f'"{video.title}" is from {name}: adding the channel as {c.slug}.')
        update(c, first=video)
    else:
        if not args.name:
            raise SystemExit('Usage: ./yt add <channel_url> "<Name>" [slug]   or   ./yt add <video_url>')
        c = Collection.create(args.slug or slugify(args.name), args.url, args.name)
        update(c)
    print(f"\n{SKILL_HINT.format(c.slug)}")


def grab(args) -> None:
    slug = slugify(args.topic)
    if Collection(slug).channel_url:
        raise SystemExit(f"{slug} is a channel collection; use ./yt add for channels.")
    video = youtube.lookup_video(args.url)
    c = Collection.create(slug)
    print(f'→ "{video.title}" ({video.channel}) into {c.slug}')
    update(c, first=video, only=True)


def update_command(args) -> None:
    if args.slug:
        c = Collection(args.slug)
        if not c.channel_url:
            raise SystemExit(f"Unknown channel '{args.slug}' — see ./yt list")
        update(c)
    else:
        for c in Collection.channels():
            update(c)


def list_command(_args) -> None:
    s = guard.state()
    print(f"today: {guard.used_today(s)}/{guard.DAILY_LIMIT} requests")
    print(guard.stop_reason() or "ok to fetch")
    if s.get("reason"):
        print(f"  last block: {s['reason']} on {s['target']} at {s['at']}: {s['error']}")
    for c in Collection.all():
        ids = {v.id for v in c.videos()}
        done = c.transcript_files().keys() & ids
        counts = {"done": len(done)}
        for vid, status in c.statuses().items():
            if vid in ids and vid not in done:
                counts[status["status"]] = counts.get(status["status"], 0) + 1
        counts["to fetch"] = len(ids) - sum(counts.values())
        print(f"{c.slug:14s} " + "  ".join(f"{k} {v}" for k, v in counts.items()))


def lock():
    """Only one run may talk to YouTube at a time, across terminals and cron."""
    ROOT.mkdir(exist_ok=True)
    f = open(ROOT / ".lock", "w")
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit("Another ./yt run is already fetching; not starting a second one.")
    return f


def main() -> None:
    p = argparse.ArgumentParser(prog="./yt", description="Turn YouTube channels into transcript collections.")
    sub = p.add_subparsers(dest="command", required=True, metavar="command")
    a = sub.add_parser("add", help="add a channel (by its URL, or any of its videos) and fetch everything")
    a.add_argument("url", help="channel URL, or a video URL (that video is fetched first)")
    a.add_argument("name", nargs="?", help="display name (needed for a channel URL)")
    a.add_argument("slug", nargs="?", help="folder name (default: the name, lowercased)")
    a.set_defaults(run=add)
    g = sub.add_parser("grab", help="just one video, into a topic collection")
    g.add_argument("url")
    g.add_argument("topic")
    g.set_defaults(run=grab)
    u = sub.add_parser("update", help="new videos and missing transcripts, for one channel or all")
    u.add_argument("slug", nargs="?")
    u.set_defaults(run=update_command)
    sub.add_parser("list", help="progress per collection and the guard state (no network)").set_defaults(run=list_command)
    args = p.parse_args()

    held = lock() if args.command != "list" else None  # noqa: F841  the lock lasts as long as the process
    try:
        args.run(args)
    except guard.Stop as stop:
        print(f"⏸ {stop}. Progress is saved; run ./yt update again later.")
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":
    main()
