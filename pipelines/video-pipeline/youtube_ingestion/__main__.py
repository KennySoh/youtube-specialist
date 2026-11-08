"""The ./yt commands. The only module that uses both acquire.py (requests) and store.py (disk)."""
from __future__ import annotations

import argparse
import fcntl
import itertools
import re
import sys
import urllib.parse
import webbrowser
from pathlib import Path

from slugify import slugify

from . import acquire, request_guard, store
from .store import Collection, find_channel, gave_up, record_failure
from .process import Video

LIST_EVERY_HOURS = 24      # a channel is listed at most once a day
MAX_FAILED_IN_A_ROW = 3    # unexplained failures in a row end the run
SKILL_HINT = 'Next: ask Claude to "create the {0} expert from experts/_template/" (experts/{0}/expert.md + .claude/skills/{0}/SKILL.md)'


def to_fetch(c: Collection, first: Video | None = None, only: bool = False) -> list[Video]:
    """Videos in the collection without a transcript that are worth a request. first: put it first
    (added to videos.json if it isn't there). only: just first."""
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
    print(f"{c.slug}: {len(done)} done, {len(todo)} to fetch")
    return todo


def fetch(queue: list[tuple[Collection, Video]]) -> None:
    """Get each video's captions in order (a raw/ snapshot first, else YouTube), keeping every
    collection's status.json up to date."""
    statuses = {c.slug: c.statuses() for c, _ in queue}
    failed_in_a_row = 0
    for c, video in queue:
        if raw := c.load_raw(video.id):  # fetched before but never processed: no request needed
            captions, segments, fetched_at = raw
            source = "  (from raw/)"
        else:
            try:
                captions, segments = acquire.fetch_captions(video.id)
            except acquire.NoTranscript as e:
                record_failure(statuses[c.slug], video.id, e.status, e.error)
                c.save_statuses(statuses[c.slug])
                print(f"{e.status:12s} {c.slug}/{video.id}  {e.error}", flush=True)
                failed_in_a_row = failed_in_a_row + 1 if e.status == "failed" else 0
                if failed_in_a_row >= MAX_FAILED_IN_A_ROW:
                    raise request_guard.Stop(f"{MAX_FAILED_IN_A_ROW} failures in a row; stopping before YouTube gets annoyed")
                continue
            fetched_at = c.save_raw(video, captions, segments)  # keep the raw captions before processing
            source = ""
        c.write_transcript(video, captions, segments, fetched_at)
        if statuses[c.slug].pop(video.id, None):
            c.save_statuses(statuses[c.slug])
        failed_in_a_row = 0
        print(f"{captions:12s} {c.slug}/{video.id}  {video.title[:60]}{source}", flush=True)


def round_robin(lists: list[list]) -> list:
    """[[a1, a2, a3], [b1]] → [a1, b1, a2, a3], so one big channel can't use up the whole day."""
    return [x for group in itertools.zip_longest(*lists) for x in group if x is not None]


def list_if_due(c: Collection) -> None:
    """Refresh videos.json from the channel page, at most once a day."""
    if not c.channel_url:
        return
    if c.listed_within(LIST_EVERY_HOURS):
        print(f"{c.slug}: video list is under {LIST_EVERY_HOURS}h old; not listing again")
        return
    listed = acquire.list_channel(c.channel_url)  # on a 429: partial list, saved below, then Stop
    for v in listed:
        v.channel = v.channel or c.channel_name
    old = c.videos()
    ids = {v.id for v in listed}
    c.save_videos(listed + [v for v in old if v.id not in ids])  # a cut-short listing loses nothing
    print(f"{c.slug}: found {len(listed)} videos ({len(ids - {v.id for v in old})} new)")


def finish(c: Collection) -> None:
    """What the skills read: dated file names, INDEX.md, missing.log. No network."""
    c.date_transcripts(c.videos())
    c.write_index()
    c.write_missing()


def update(c: Collection, first: Video | None = None, only: bool = False) -> None:
    """List the channel's new videos (channel collections), then fetch the missing transcripts."""
    update_many([c], first, only)


def update_many(collections: list[Collection], first: Video | None = None, only: bool = False) -> None:
    """List every channel that's due, then fetch their missing transcripts in turn (round-robin)."""
    try:
        if not only:
            for c in collections:
                list_if_due(c)
        fetch(round_robin([[(c, v) for v in to_fetch(c, first, only)] for c in collections]))
    finally:
        for c in collections:
            finish(c)


def add(args) -> None:
    if acquire.VIDEO_URL.search(args.url):
        video = acquire.lookup_video(args.url)
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
    video = acquire.lookup_video(args.url)
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
        update_many(Collection.channels())


def list_command(_args) -> None:
    s = request_guard.state()
    print(f"today: {request_guard.used_today(s)}/{request_guard.DAILY_LIMIT} requests")
    print(request_guard.stop_reason() or "ok to fetch")
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


def todo_command(args) -> None:
    """Videos only you can get now (gave up after retries) first, then the ones not fetched yet."""
    rows = []
    for c in [Collection(args.slug)] if args.slug else Collection.all():
        done, statuses = c.transcript_files(), c.statuses()
        for v in c.videos():
            s = statuses.get(v.id)
            if v.id in done or (s and s["status"] in ("no_captions", "unavailable")):  # nothing to open
                continue
            rows.append((not gave_up(s), c, v, f"{s['status']} ×{s.get('attempts', 1)}" if s else "not fetched"))
    rows.sort(key=lambda r: r[0])
    for _, c, v, status in rows[:args.n]:
        print(f"{status:12s} {c.slug}/{v.id}  {v.url or f'https://youtu.be/{v.id}'}  {v.title[:50]}")
    if len(rows) > args.n:
        print(f"… {len(rows) - args.n} more (-n {len(rows)} for all)")
    for _, _, v, _ in rows[:args.open]:
        webbrowser.open_new_tab(v.url or f"https://youtu.be/{v.id}")  # just opens a tab; no request from here
    if rows:
        print("\nOpen the transcript panel, click the Save transcript bookmark, then: ./yt import")


def import_command(args) -> None:
    """Saved *.transcript.json files → transcripts; the files move to raw/youtube/<slug>/<id>.browser.json."""
    folder = Path(args.dir).expanduser()
    files = sorted(folder.glob("*.transcript.json"))
    if not files:
        print(f"No *.transcript.json in {folder}")
        return
    owners = {v.id: (c, v) for c in Collection.all() for v in c.videos()}
    touched: dict[str, Collection] = {}
    for path in files:
        try:
            data, segments = acquire.read_capture(path)
        except acquire.BadCapture as err:
            print(f"✗ {path.name}: {err}")
            continue
        vid = data["video_id"]
        if vid not in owners:
            print(f"✗ {path.name}: {vid} isn't in any collection; add it first (./yt grab <url> <topic>)")
            continue
        c, video = owners[vid]
        if vid in c.transcript_files():
            print(f"- {c.slug}/{vid} already has a transcript; leaving {path.name}")
            continue
        video.title = video.title or data.get("title", "")
        c.write_transcript(video, "browser", segments, str(data.get("captured_at", ""))[:10] or None)
        statuses = c.statuses()
        if statuses.pop(vid, None) is not None:
            c.save_statuses(statuses)
        c.keep_capture(path, vid)
        touched[c.slug] = c
        print(f"browser      {c.slug}/{vid}  {video.title[:50]}  ({len(segments)} segments)")
    for c in touched.values():
        finish(c)


def reprocess_command(args) -> None:
    """Rebuild transcripts from raw/ only (fetched captions, then bookmarklet captures). No network."""
    if args.slug and not Collection(args.slug).dir.exists():
        raise acquire.UserError(f"Unknown collection '{args.slug}' — see ./yt list")
    for c in [Collection(args.slug)] if args.slug else Collection.all():
        rebuilt = 0
        for video in c.videos():
            if raw := c.load_raw(video.id):
                captions, segments, fetched_at = raw
            elif c.capture_path(video.id).exists():
                try:
                    data, segments = acquire.read_capture(c.capture_path(video.id))
                except acquire.BadCapture as err:
                    print(f"✗ {c.slug}/{video.id}: {err}")
                    continue
                captions, fetched_at = "browser", str(data.get("captured_at", ""))[:10] or None
            else:
                continue
            c.write_transcript(video, captions, segments, fetched_at)
            rebuilt += 1
        finish(c)
        print(f"{c.slug}: rebuilt {rebuilt} transcripts from raw/")


def bookmarklet_command(_args) -> None:
    src = re.sub(r"/\*.*?\*/\s*", "", (Path(__file__).parent / "save_transcript.js").read_text(), flags=re.S)
    print("Make a bookmark named 'Save transcript' with this as its URL:\n")
    print("javascript:" + urllib.parse.quote(src, safe=""))


def lock():
    """Only one run may talk to YouTube at a time, across terminals and cron."""
    store.ROOT.mkdir(exist_ok=True)
    f = open(store.ROOT / ".lock", "w")
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
    t = sub.add_parser("todo", help="videos still missing, the ones only you can get first (no network)")
    t.add_argument("slug", nargs="?")
    t.add_argument("-n", type=int, default=20, help="how many to show (default 20)")
    t.add_argument("--open", type=int, default=0, metavar="N", help="open the first N in your browser")
    t.set_defaults(run=todo_command)
    i = sub.add_parser("import", help="turn transcripts saved with the bookmarklet into .md files (no network)")
    i.add_argument("dir", nargs="?", default="~/Downloads")
    i.set_defaults(run=import_command)
    r = sub.add_parser("reprocess", help="rebuild transcripts from raw/ only (no network)")
    r.add_argument("slug", nargs="?")
    r.set_defaults(run=reprocess_command)
    sub.add_parser("bookmarklet", help="print the 'Save transcript' bookmarklet").set_defaults(run=bookmarklet_command)
    args = p.parse_args()

    held = lock() if args.command not in ("list", "todo", "bookmarklet") else None  # noqa: F841  the lock lasts as long as the process
    try:
        args.run(args)
    except acquire.UserError as err:
        sys.exit(str(err))
    except request_guard.Stop as stop:
        print(f"⏸ {stop}. Progress is saved; run ./yt update again later.")
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":
    main()
