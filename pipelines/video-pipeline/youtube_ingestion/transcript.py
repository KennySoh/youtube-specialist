"""The transcript file format the skills depend on: file name, frontmatter and [mm:ss] paragraphs.

<YYYY-MM-DD>-<title-slug>-<video_id>.md   (0000-00-00 until the upload date is known)
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import re
from dataclasses import dataclass
from pathlib import Path

import yaml
from slugify import slugify

PARAGRAPH_SECONDS = 30  # one [mm:ss] paragraph per ~30 s of captions
FILE_ID = re.compile(r"-([A-Za-z0-9_-]{11})\.md$")


@dataclass
class Video:
    id: str
    title: str = ""
    url: str = ""
    channel: str | None = None
    channel_url: str | None = None
    upload_date: str | None = None  # YYYYMMDD
    duration: int | None = None
    view_count: int | None = None

    @classmethod
    def from_dict(cls, d: dict) -> Video:
        names = {f.name for f in dataclasses.fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in names})

    @property
    def published(self) -> str:
        """YYYY-MM-DD, or '' if YouTube didn't say."""
        d = self.upload_date or ""
        return f"{d[0:4]}-{d[4:6]}-{d[6:8]}" if len(d) == 8 else ""


@dataclass
class Segment:
    start: float
    text: str
    duration: float = 0.0


def timestamp(seconds: float) -> str:
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def paragraphs(segments: list[Segment]) -> list[tuple[float, str]]:
    """Join caption lines into ~30 s paragraphs, so a transcript isn't one line per second."""
    groups: list[list[Segment]] = []
    for seg in segments:
        if not groups or seg.start - groups[-1][0].start >= PARAGRAPH_SECONDS:
            groups.append([])
        groups[-1].append(seg)
    out = []
    for group in groups:
        text = re.sub(r"\s+", " ", " ".join(s.text.strip() for s in group)).strip()
        if text:
            out.append((group[0].start, text))
    return out


def file_name(published: str, title: str, video_id: str) -> str:
    slug = slugify(title or "untitled")[:60] or "untitled"
    return f"{published or '0000-00-00'}-{slug}-{video_id}.md"


def join(frontmatter: dict, body: str) -> str:
    return "---\n" + yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True) + "---\n" + body


def render(video: Video, captions: str, segments: list[Segment]) -> str:
    """captions: 'manual' or 'auto'."""
    frontmatter = {
        "title": video.title,
        "video_id": video.id,
        "url": video.url or f"https://youtu.be/{video.id}",
        "channel": video.channel or "",
        "published_at": video.published,
        "duration_seconds": video.duration,
        "transcript_source": captions,
        "fetched_at": dt.date.today().isoformat(),
    }
    lines = ["", f"# {video.title}", ""] + [f"[{timestamp(start)}] {text}" for start, text in paragraphs(segments)]
    return join(frontmatter, "\n".join(lines) + "\n")


def read(path: Path) -> tuple[dict, str]:
    """(frontmatter, body)."""
    _, frontmatter, body = path.read_text().split("---\n", 2)
    return yaml.safe_load(frontmatter) or {}, body
