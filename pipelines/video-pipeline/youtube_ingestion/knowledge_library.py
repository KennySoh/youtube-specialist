"""Everything on disk. No network.

knowledge-library/youtube/<slug>/           one collection
  channel_url, channel_name   channel collections only (no channel_url = topic collection)
  videos.json             every video we know of
  status.json             why a video has no transcript: no_captions, unavailable or failed
  missing.log             the same, one line per video, for the skills
  transcripts/*.md        one transcript per video, plus INDEX.md
"""
from __future__ import annotations

import dataclasses
import json
import os
import time
from pathlib import Path

import yaml

from . import transcript
from .transcript import Segment, Video

# YT_LIBRARY overrides it (Docker, tests); otherwise <repo>/knowledge-library/youtube, wherever ./yt is run from.
ROOT = Path(os.environ.get("YT_LIBRARY") or Path(__file__).resolve().parents[3] / "knowledge-library" / "youtube")
MAX_ATTEMPTS = 3        # a failed video is tried again on the next runs, this many times in all


def write_atomic(path: Path, text: str) -> None:
    """Temp file + rename, so a crash never leaves half a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(text)
    os.replace(tmp, path)


def save_json(path: Path, data) -> None:
    write_atomic(path, json.dumps(data, indent=2, ensure_ascii=False))


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return default


# --- collections ---------------------------------------------------------------------------------

class Collection:
    def __init__(self, slug: str):
        self.slug = slug
        self.dir = ROOT / slug
        self.transcripts = self.dir / "transcripts"

    @staticmethod
    def all() -> list[Collection]:
        return [Collection(p.parent.name) for p in sorted(ROOT.glob("*/videos.json"))]

    @staticmethod
    def channels() -> list[Collection]:
        return [Collection(p.parent.name) for p in sorted(ROOT.glob("*/channel_url"))]

    @staticmethod
    def create(slug: str, channel_url: str | None = None, channel_name: str | None = None) -> Collection:
        c = Collection(slug)
        c.transcripts.mkdir(parents=True, exist_ok=True)
        if channel_url:
            (c.dir / "channel_url").write_text(channel_url.removesuffix("/").removesuffix("/videos") + "/videos\n")
            (c.dir / "channel_name").write_text(f"{channel_name}\n")
        if not (c.dir / "videos.json").exists():
            c.save_videos([])
        return c

    def _read(self, name: str) -> str | None:
        path = self.dir / name
        return path.read_text().strip() if path.exists() else None

    @property
    def channel_url(self) -> str | None:
        return self._read("channel_url")

    @property
    def channel_name(self) -> str:
        return self._read("channel_name") or self.slug

    def videos(self) -> list[Video]:
        return [Video.from_dict(d) for d in load_json(self.dir / "videos.json", [])]

    def save_videos(self, videos: list[Video]) -> None:
        save_json(self.dir / "videos.json", [dataclasses.asdict(v) for v in videos])

    def listed_within(self, hours: float) -> bool:
        path = self.dir / "videos.json"
        return path.exists() and time.time() - path.stat().st_mtime < hours * 3600

    def statuses(self) -> dict[str, dict]:
        return load_json(self.dir / "status.json", {})

    def save_statuses(self, statuses: dict[str, dict]) -> None:
        save_json(self.dir / "status.json", statuses)

    def transcript_files(self) -> dict[str, Path]:
        """video id → transcript file."""
        return {m.group(1): f for f in self.transcripts.glob("*.md") if (m := transcript.FILE_ID.search(f.name))}

    def write_transcript(self, video: Video, captions: str, segments: list[Segment]) -> None:
        write_atomic(self.transcripts / transcript.file_name(video.published, video.title, video.id),
                     transcript.render(video, captions, segments))

    def date_transcripts(self, videos: list[Video]) -> None:
        """A listing can learn a video's date after its transcript was saved as 0000-00-00-…: fix those."""
        dates = {v.id: v.published for v in videos if v.published}
        for vid, path in self.transcript_files().items():
            if not path.name.startswith("0000-00-00-") or vid not in dates:
                continue
            frontmatter, body = transcript.read(path)
            frontmatter["published_at"] = dates[vid]
            write_atomic(path.parent / transcript.file_name(dates[vid], frontmatter.get("title"), vid),
                         transcript.join(frontmatter, body))
            path.unlink()

    def write_index(self) -> None:
        """transcripts/INDEX.md: one row per transcript, newest first."""
        rows = []
        for path in sorted(self.transcript_files().values()):
            try:
                fm, body = transcript.read(path)
            except (ValueError, yaml.YAMLError):
                print(f"⚠ skipping {path.name}: unreadable frontmatter")
                continue
            words = sum(len(line.split()) for line in body.splitlines() if line.startswith("["))
            rows.append((fm.get("published_at") or "", fm.get("title") or path.stem, path.name,
                         fm.get("transcript_source") or "", words, fm.get("url") or "", fm.get("channel") or ""))
        rows.sort(key=lambda r: r[0], reverse=True)
        channel = next((r[6] for r in rows if r[6]), "")
        lines = [f"# {channel or 'Channel'} — Transcript Index", "",
                 f"_{len(rows)} videos · auto-generated by `./yt`_", "",
                 "| Date | Title | Source | Words | Link |", "|------|-------|--------|------:|------|"]
        for date, title, name, source, words, url, _ in rows:
            title = str(title).replace("|", "\\|")
            lines.append(f"| {date} | [{title}]({name}) | {source} | {words} | [yt]({url}) |")
        write_atomic(self.transcripts / "INDEX.md", "\n".join(lines) + "\n")

    def write_missing(self) -> None:
        """missing.log: every video without a transcript, and why."""
        done, statuses = self.transcript_files(), self.statuses()
        write_atomic(self.dir / "missing.log", "".join(
            f"{v.id}\t{statuses.get(v.id, {}).get('status', 'not fetched yet')}\t{v.title}\n"
            for v in self.videos() if v.id not in done))


def record_failure(statuses: dict[str, dict], video_id: str, status: str, error: str) -> None:
    """Note why a video has no transcript; attempts counts every try so far."""
    attempts = statuses.get(video_id, {}).get("attempts", 0) + 1
    statuses[video_id] = {"status": status, "attempts": attempts, "error": error}


def gave_up(status: dict | None) -> bool:
    """True if a video must not be asked for again."""
    return bool(status) and (status["status"] != "failed" or status.get("attempts", 0) >= MAX_ATTEMPTS)


def find_channel(video: Video) -> Collection | None:
    """The channel collection this video belongs to, if we have it."""
    channels = Collection.channels()
    for c in channels:
        if any(v.id == video.id for v in c.videos()):
            return c
    for c in channels:
        # Channels added by /channel/UC… URL can't be matched to an @handle, so fall back to the name.
        if (c.channel_url or "").removesuffix("/videos").lower() == (video.channel_url or "").lower() \
                or c.channel_name.casefold() == (video.channel or "").casefold():
            return c
    return None
