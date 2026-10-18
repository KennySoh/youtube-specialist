#!/usr/bin/env python3
"""Enumerate every video on a YouTube channel into <out>/index.json + <out>/index.csv.

Usage: list_videos.py <channel_url> [--out youtuber/<slug>/data/]
"""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path


def fetch_videos(channel_url: str) -> list[dict]:
    cmd = [
        "yt-dlp",
        "--flat-playlist",
        "--no-warnings",
        "--print-json",
        "--ignore-errors",
        "--extractor-args", "youtubetab:approximate_date",
        channel_url,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0 and not proc.stdout.strip():
        sys.stderr.write(proc.stderr)
        raise SystemExit(f"yt-dlp failed (exit {proc.returncode})")

    videos = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if entry.get("_type") not in (None, "url", "video"):
            continue
        vid = entry.get("id")
        if not vid:
            continue
        videos.append(
            {
                "id": vid,
                "title": entry.get("title") or "",
                "url": entry.get("webpage_url") or f"https://youtu.be/{vid}",
                "duration": entry.get("duration"),
                "view_count": entry.get("view_count"),
                "upload_date": entry.get("upload_date"),
                "channel": entry.get("channel") or entry.get("uploader"),
                "channel_url": entry.get("channel_url"),
            }
        )
    return videos


def write_outputs(videos: list[dict], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "index.json").write_text(json.dumps(videos, indent=2, ensure_ascii=False))
    with (out_dir / "index.csv").open("w", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=["id", "title", "url", "duration", "view_count", "upload_date", "channel"],
        )
        writer.writeheader()
        for v in videos:
            writer.writerow({k: v.get(k) for k in writer.fieldnames})


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("channel_url")
    p.add_argument("--out", default=None, type=Path, help="output dir (default: youtuber/<slug>/data, derived from --channel-name)")
    p.add_argument("--channel-name", default=None, help="override channel name (flat-playlist often omits it)")
    args = p.parse_args()

    if args.out is None:
        if not args.channel_name:
            raise SystemExit("Must pass --out or --channel-name so an output directory can be determined")
        from slugify import slugify
        args.out = Path("youtuber") / slugify(args.channel_name) / "data"

    videos = fetch_videos(args.channel_url)
    if args.channel_name:
        for v in videos:
            v["channel"] = v.get("channel") or args.channel_name
    write_outputs(videos, args.out)
    print(f"Found {len(videos)} videos → {args.out}/index.json")


if __name__ == "__main__":
    main()
