#!/usr/bin/env python3
"""One-shot: backfill published_at/channel into existing transcript frontmatter
and rename files to the correct date-prefixed slug. Idempotent."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import yaml
from slugify import slugify


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--index", type=Path, required=True, help="youtuber/<slug>/data/index.json")
    p.add_argument("--transcripts", type=Path, required=True, help="youtuber/<slug>/transcripts")
    args = p.parse_args()

    videos = {v["id"]: v for v in json.loads(args.index.read_text())}
    by_id_to_path = {}
    for md in args.transcripts.glob("*.md"):
        if md.name == "INDEX.md":
            continue
        m = re.search(r"-([A-Za-z0-9_-]{11})\.md$", md.name)
        if m:
            by_id_to_path[m.group(1)] = md

    renamed = 0
    patched = 0
    for vid, video in videos.items():
        md_path = by_id_to_path.get(vid)
        if not md_path:
            continue

        text = md_path.read_text()
        if not text.startswith("---\n"):
            continue
        _, fm_text, body = text.split("---\n", 2)
        fm = yaml.safe_load(fm_text) or {}

        pub = video.get("upload_date") or ""
        pub_iso = f"{pub[0:4]}-{pub[4:6]}-{pub[6:8]}" if len(pub) == 8 else fm.get("published_at") or ""
        changed = False
        if pub_iso and fm.get("published_at") != pub_iso:
            fm["published_at"] = pub_iso
            changed = True
        if video.get("channel") and fm.get("channel") != video["channel"]:
            fm["channel"] = video["channel"]
            changed = True
        if video.get("view_count") and fm.get("view_count") != video["view_count"]:
            fm["view_count"] = video["view_count"]
            changed = True

        if changed:
            new_text = "---\n" + yaml.safe_dump(fm, sort_keys=False, allow_unicode=True) + "---\n" + body
            md_path.write_text(new_text)
            patched += 1

        slug = slugify(fm.get("title") or "untitled")[:60] or "untitled"
        target_name = f"{pub_iso or '0000-00-00'}-{slug}-{vid}.md"
        target = args.transcripts / target_name
        if target != md_path and not target.exists():
            md_path.rename(target)
            renamed += 1

    print(f"patched {patched} frontmatters, renamed {renamed} files")


if __name__ == "__main__":
    main()
