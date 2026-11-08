"""Track B: transcripts you open yourself in your own browser. No requests to YouTube.

The bookmarklet (tools/save_transcript.js) saves the open transcript panel as
<video_id>.transcript.json: {video_id, title, channel, url, captured_at, segments: [{t, text}], panel_text}.
`./yt import` turns those files into the usual transcripts, with transcript_source: browser.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .transcript import Segment

TIME = re.compile(r"^(?:(\d+):)?(\d{1,2}):(\d{2})$")
# Lines in the panel that aren't caption text: spoken-out times ("1 minute, 5 seconds"), chapter headings.
SPOKEN_TIME = re.compile(r"^\d+ (?:hours?|minutes?|seconds?)(?:, \d+ (?:hours?|minutes?|seconds?))*$")
CHAPTER = re.compile(r"^Chapter \d+")


class BadCapture(Exception):
    """A saved file we can't turn into a transcript."""


def seconds(t: str) -> float:
    """'1:23' → 83, '1:02:03' → 3723."""
    if not (m := TIME.match(t.strip())):
        raise BadCapture(f"not a timestamp: {t!r}")
    h, m_, s = m.groups()
    return int(h or 0) * 3600 + int(m_) * 60 + int(s)


def parse_panel_text(text: str) -> list[Segment]:
    """The panel's visible text: a timestamp line, then the caption on the next real line."""
    segments, start = [], None
    for line in (ln.strip() for ln in text.splitlines()):
        if not line or SPOKEN_TIME.match(line) or CHAPTER.match(line):
            continue
        if TIME.match(line):
            start = seconds(line)
        elif start is not None:
            segments.append(Segment(start, line))
            start = None
    return segments


def read_capture(path: Path) -> tuple[dict, list[Segment]]:
    """(the file's fields, segments). Raises BadCapture."""
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as err:
        raise BadCapture(f"unreadable: {err}") from err
    if not re.fullmatch(r"[A-Za-z0-9_-]{11}", str(data.get("video_id", ""))):
        raise BadCapture("no video_id")
    segments = [Segment(seconds(s["t"]), s["text"].strip()) for s in data.get("segments") or [] if s.get("text", "").strip()]
    if not segments:
        segments = parse_panel_text(data.get("panel_text") or "")
    if not segments:
        raise BadCapture("0 segments (was the transcript panel open?)")
    segments.sort(key=lambda s: s.start)
    return data, segments
