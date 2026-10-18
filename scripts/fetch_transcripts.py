#!/usr/bin/env python3
"""Fetch transcripts for every video in <data>/index.json and write one .md per video.

Source priority:
  1. youtube-transcript-api (manual captions, en)
  2. youtube-transcript-api (auto captions, en)
  3. yt-dlp --write-auto-sub fallback (vtt → text)

Output: <out>/<YYYY-MM-DD>-<slug>-<video_id>.md with YAML frontmatter
and inline [mm:ss] timestamps every ~30s.

Pass --channel-dir youtuber/<slug> to scope all paths, or set --index/--out/--tmp/--missing-log individually.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import yaml
from slugify import slugify
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    NoTranscriptFound,
    TranscriptsDisabled,
    VideoUnavailable,
)

LOG = logging.getLogger("fetch")

TIMESTAMP_INTERVAL_SECONDS = 30


@dataclass
class Segment:
    start: float
    text: str


def fmt_ts(seconds: float) -> str:
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def collapse_to_intervals(segments: list[Segment], interval: int = TIMESTAMP_INTERVAL_SECONDS) -> list[tuple[float, str]]:
    """Group raw caption lines into timestamp buckets so the .md isn't a wall of 1-line-per-second."""
    if not segments:
        return []
    buckets: list[list[Segment]] = []
    current: list[Segment] = []
    bucket_start = segments[0].start
    for seg in segments:
        if seg.start - bucket_start >= interval and current:
            buckets.append(current)
            current = []
            bucket_start = seg.start
        current.append(seg)
    if current:
        buckets.append(current)

    out = []
    for group in buckets:
        text = " ".join(s.text.strip() for s in group if s.text.strip())
        text = re.sub(r"\s+", " ", text)
        if text:
            out.append((group[0].start, text))
    return out


def try_transcript_api(video_id: str) -> tuple[list[Segment], str] | None:
    api = YouTubeTranscriptApi()
    try:
        listing = api.list(video_id)
    except (TranscriptsDisabled, VideoUnavailable, NoTranscriptFound) as e:
        LOG.debug("list failed for %s: %s", video_id, e)
        return None
    except Exception as e:  # noqa: BLE001
        LOG.debug("list error %s: %s", video_id, e)
        return None

    # Prefer manual English over auto-generated
    candidates: list[tuple[str, object]] = []
    for tr in listing:
        if tr.language_code.startswith("en") and not tr.is_generated:
            candidates.append(("manual", tr))
    for tr in listing:
        if tr.language_code.startswith("en") and tr.is_generated:
            candidates.append(("auto", tr))
    # Last resort: any language, translated to en if possible
    for tr in listing:
        if tr.is_translatable:
            candidates.append(("translated", tr))

    for source, tr in candidates:
        try:
            if source == "translated" and not tr.language_code.startswith("en"):
                fetched = tr.translate("en").fetch()
            else:
                fetched = tr.fetch()
            segs = [Segment(start=float(s.start), text=s.text) for s in fetched]
            if segs:
                return segs, source
        except Exception as e:  # noqa: BLE001
            LOG.debug("fetch failed (%s) for %s: %s", source, video_id, e)
            continue
    return None


VTT_TS = re.compile(r"^(\d\d):(\d\d):(\d\d)\.(\d{3})")


def parse_vtt(path: Path) -> list[Segment]:
    segments: list[Segment] = []
    current_start: float | None = None
    current_lines: list[str] = []
    seen: set[str] = set()
    for raw in path.read_text(errors="replace").splitlines():
        line = raw.strip()
        if "-->" in line:
            m = VTT_TS.match(line)
            if m:
                h, mm, ss, ms = map(int, m.groups())
                if current_start is not None and current_lines:
                    text = " ".join(current_lines).strip()
                    text = re.sub(r"<[^>]+>", "", text)
                    if text and text not in seen:
                        segments.append(Segment(start=current_start, text=text))
                        seen.add(text)
                current_start = h * 3600 + mm * 60 + ss + ms / 1000
                current_lines = []
            continue
        if line and current_start is not None and not line.startswith("WEBVTT") and not line.startswith("Kind:") and not line.startswith("Language:"):
            current_lines.append(line)
    if current_start is not None and current_lines:
        text = " ".join(current_lines).strip()
        text = re.sub(r"<[^>]+>", "", text)
        if text and text not in seen:
            segments.append(Segment(start=current_start, text=text))
    return segments


def try_ytdlp_subs(video_id: str, tmpdir: Path) -> tuple[list[Segment], str] | None:
    tmpdir.mkdir(parents=True, exist_ok=True)
    out_template = str(tmpdir / f"{video_id}.%(ext)s")
    cmd = [
        "yt-dlp",
        "--skip-download",
        "--write-auto-sub",
        "--write-sub",
        "--sub-lang", "en.*,en",
        "--sub-format", "vtt",
        "--no-warnings",
        "-o", out_template,
        f"https://www.youtube.com/watch?v={video_id}",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    vtts = sorted(tmpdir.glob(f"{video_id}*.vtt"))
    if not vtts:
        LOG.debug("yt-dlp no subs for %s: %s", video_id, proc.stderr.strip().splitlines()[-1] if proc.stderr else "")
        return None
    segs = parse_vtt(vtts[0])
    for v in vtts:
        v.unlink(missing_ok=True)
    if segs:
        return segs, "yt-dlp"
    return None


def render_markdown(video: dict, segments: list[Segment], source: str) -> str:
    pub = video.get("upload_date") or ""
    pub_iso = ""
    if pub and len(pub) == 8:
        pub_iso = f"{pub[0:4]}-{pub[4:6]}-{pub[6:8]}"

    fm = {
        "title": video.get("title") or "",
        "video_id": video["id"],
        "url": video.get("url") or f"https://youtu.be/{video['id']}",
        "channel": video.get("channel") or "",
        "published_at": pub_iso,
        "duration_seconds": video.get("duration"),
        "view_count": video.get("view_count"),
        "tags": [],
        "transcript_source": source,
        "fetched_at": dt.date.today().isoformat(),
    }
    body_lines = [
        "---",
        yaml.safe_dump(fm, sort_keys=False, allow_unicode=True).strip(),
        "---",
        "",
        f"# {fm['title']}",
        "",
    ]
    for ts, text in collapse_to_intervals(segments):
        body_lines.append(f"[{fmt_ts(ts)}] {text}")
    return "\n".join(body_lines) + "\n"


def output_path(video: dict, out_dir: Path) -> Path:
    pub = video.get("upload_date") or "00000000"
    pub_iso = f"{pub[0:4]}-{pub[4:6]}-{pub[6:8]}" if len(pub) == 8 else "0000-00-00"
    slug = slugify(video.get("title") or "untitled")[:60] or "untitled"
    return out_dir / f"{pub_iso}-{slug}-{video['id']}.md"


def fetch_one(video: dict, out_dir: Path, tmpdir: Path) -> tuple[str, str]:
    vid = video["id"]
    target = output_path(video, out_dir)
    if target.exists():
        return "skip", str(target)

    result = try_transcript_api(vid)
    if not result:
        result = try_ytdlp_subs(vid, tmpdir)
    if not result:
        return "missing", vid

    segments, source = result
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_markdown(video, segments, source))
    return source, str(target)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--channel-dir", type=Path, default=None, help="youtuber/<slug> root; derives --index/--out/--tmp/--missing-log")
    p.add_argument("--index", type=Path, default=None)
    p.add_argument("--out", type=Path, default=None)
    p.add_argument("--tmp", type=Path, default=None)
    p.add_argument("--missing-log", type=Path, default=None)
    p.add_argument("--sleep", type=float, default=0.5, help="seconds between requests")
    p.add_argument("--limit", type=int, default=0, help="0 = all")
    p.add_argument("--refresh", action="store_true", help="re-fetch even if .md exists")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args()

    if args.channel_dir is not None:
        args.index = args.index or args.channel_dir / "data/index.json"
        args.out = args.out or args.channel_dir / "transcripts"
        args.tmp = args.tmp or args.channel_dir / "data/_tmp_subs"
        args.missing_log = args.missing_log or args.channel_dir / "data/missing.log"
    if args.index is None or args.out is None or args.tmp is None or args.missing_log is None:
        raise SystemExit("Must pass --channel-dir youtuber/<slug> (or all of --index/--out/--tmp/--missing-log explicitly)")

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(message)s")

    videos = json.loads(args.index.read_text())
    if args.limit:
        videos = videos[: args.limit]

    args.out.mkdir(parents=True, exist_ok=True)
    args.missing_log.parent.mkdir(parents=True, exist_ok=True)

    counts = {"manual": 0, "auto": 0, "translated": 0, "yt-dlp": 0, "skip": 0, "missing": 0}
    missing_ids: list[str] = []

    for i, video in enumerate(videos, 1):
        target = output_path(video, args.out)
        if target.exists() and not args.refresh:
            counts["skip"] += 1
            print(f"[{i:3d}/{len(videos)}] skip   {video['id']}  {video.get('title','')[:60]}")
            continue
        if args.refresh and target.exists():
            target.unlink()

        try:
            status, _ = fetch_one(video, args.out, args.tmp)
        except Exception as e:  # noqa: BLE001
            LOG.warning("error %s: %s", video["id"], e)
            status = "missing"

        counts[status] = counts.get(status, 0) + 1
        if status == "missing":
            missing_ids.append(f"{video['id']}\t{video.get('title','')}")
        print(f"[{i:3d}/{len(videos)}] {status:6s} {video['id']}  {video.get('title','')[:60]}")
        time.sleep(args.sleep)

    if missing_ids:
        args.missing_log.write_text("\n".join(missing_ids) + "\n")

    print("\nSummary:")
    for k, v in counts.items():
        print(f"  {k:10s} {v}")
    print(f"\n→ transcripts in {args.out}")
    if missing_ids:
        print(f"→ missing logged in {args.missing_log}")


if __name__ == "__main__":
    main()
