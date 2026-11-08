"""Every request to YouTube, and nothing else. Each one asks the guard first.

- list_channel:   a channel's videos (yt-dlp; it never fetches captions, see README "Lessons learned")
- lookup_video:   a video URL → title and channel (oEmbed, a small JSON lookup)
- fetch_captions: a video's English captions (youtube-transcript-api; never a machine translation)
"""
from __future__ import annotations

import html
import json
import re
import subprocess

import requests

from . import request_guard
from .transcript import Segment, Video

VIDEO_URL = re.compile(r"(?:[?&]v=|youtu\.be/|/shorts/|/live/|/embed/)([A-Za-z0-9_-]{11})")
LANGUAGES = ["en", "en-US", "en-GB"]


class UserError(Exception):
    """A problem the user can fix (bad link, unknown video). The CLI prints it and exits."""


class NoTranscript(Exception):
    """A video we can't get captions for. status: no_captions, unavailable or failed (worth a retry)."""

    def __init__(self, status: str, error: str):
        super().__init__(error)
        self.status, self.error = status, error


def retry_after(response) -> float | None:
    value = str(response.headers.get("Retry-After", ""))
    return float(value) if value.isdigit() else None


def block_reason(text: str) -> str | None:
    """'429' or 'bot_check' if a yt-dlp error means YouTube is limiting us."""
    s = text.lower()
    if any(m in s for m in ("http error 429", "too many requests", "http error 402", "payment required")):  # yt-dlp FAQ: 402 = same IP limit
        return "429"
    if "sign in to confirm" in s or "captcha" in s:
        return "bot_check"
    return None


def last_error(stderr: str) -> str:
    """yt-dlp's last ERROR line, with URL query strings (signatures, tokens) stripped."""
    lines = [ln for ln in stderr.splitlines() if ln.startswith("ERROR")] or stderr.splitlines() or [""]
    return re.sub(r"(https?://[^\s?]+)\?\S*", r"\1?…", lines[-1])[:300]


def list_channel(channel_url: str) -> list[Video]:
    """Every video yt-dlp can see. If YouTube cuts it short with a 429, the guard is blocked
    (so the next request stops) but the videos found so far are still returned."""
    request_guard.allow()
    proc = subprocess.run(["yt-dlp", "--flat-playlist", "--print-json", "--ignore-errors", "--sleep-requests", "5",
                           "--extractor-args", "youtubetab:approximate_date", channel_url],
                          capture_output=True, text=True, check=False)
    videos = []
    for line in proc.stdout.splitlines():
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if entry.get("_type") in (None, "url", "video") and entry.get("id"):
            videos.append(Video(
                id=entry["id"],
                title=entry.get("title") or "",
                url=entry.get("webpage_url") or f"https://youtu.be/{entry['id']}",
                channel=entry.get("channel") or entry.get("uploader"),
                channel_url=entry.get("channel_url"),
                upload_date=entry.get("upload_date"),
                duration=entry.get("duration"),
                view_count=entry.get("view_count"),
            ))
    if reason := block_reason(proc.stderr):
        print(f"yt-dlp: {last_error(proc.stderr)}")
        # Don't raise: the caller saves this partial listing first; the next request_guard.allow() raises the Stop.
        request_guard.block(reason, channel_url, last_error(proc.stderr))
    elif not videos:
        raise UserError(f"yt-dlp found no videos: {last_error(proc.stderr)}")
    return videos


def lookup_video(url: str) -> Video:
    """Title and channel of a watch?v=, youtu.be/, shorts/ or live/ link."""
    if not (m := VIDEO_URL.search(url)):
        raise UserError(f"Not a YouTube video link: {url}")
    video_id = m.group(1)
    watch_url = f"https://www.youtube.com/watch?v={video_id}"
    request_guard.allow()
    try:
        r = requests.get("https://www.youtube.com/oembed", params={"url": watch_url, "format": "json"}, timeout=20)
    except requests.RequestException as err:
        raise UserError(f"Couldn't reach YouTube: {err}")
    if r.status_code == 429:
        raise request_guard.block("429", video_id, "oEmbed HTTP 429", retry_after(r))
    if r.status_code == 401:
        raise UserError(f"{video_id}: the owner disabled embedding, so its channel can't be looked up. "
                         'Use the channel URL instead: ./yt add <channel_url> "<Name>"')
    if r.status_code != 200:
        raise UserError(f"{video_id}: video not found, private or removed (HTTP {r.status_code})")
    info = r.json()
    return Video(id=video_id, title=info.get("title", ""), url=watch_url,
                 channel=info["author_name"], channel_url=info["author_url"].removesuffix("/"))


def fetch_captions(video_id: str) -> tuple[str, list[Segment]]:
    """('manual' or 'auto', segments). Raises NoTranscript, or request_guard.Stop if YouTube is limiting us."""
    from youtube_transcript_api import YouTubeTranscriptApi
    from youtube_transcript_api import _errors as e

    request_guard.allow(paced=True)
    seen_retry_after: list[float] = []

    def remember_retry_after(response, *_args, **_kwargs):  # the library raises IpBlocked and drops the response
        if response.status_code == 429 and (seconds := retry_after(response)):
            seen_retry_after.append(seconds)

    session = requests.Session()
    session.hooks["response"].append(remember_retry_after)
    try:
        t = YouTubeTranscriptApi(http_client=session).fetch(video_id, languages=LANGUAGES)
    except e.IpBlocked as err:  # HTTP 429 or a captcha page
        raise request_guard.block("429", video_id, type(err).__name__, max(seen_retry_after, default=None))
    except (e.RequestBlocked, e.FailedToCreateConsentCookie) as err:
        raise request_guard.block("bot_check", video_id, type(err).__name__)
    except (e.TranscriptsDisabled, e.NoTranscriptFound) as err:
        raise NoTranscript("no_captions", type(err).__name__)
    except (e.VideoUnavailable, e.InvalidVideoId, e.AgeRestricted, e.VideoUnplayable) as err:
        raise NoTranscript("unavailable", type(err).__name__)
    except Exception as err:  # noqa: BLE001  network, 5xx, YouTube page changes
        raise NoTranscript("failed", f"{type(err).__name__}: {err}"[:300])

    segments = [Segment(s.start, html.unescape(s.text), s.duration) for s in t.snippets]
    if not "".join(s.text for s in segments).strip():  # never save an empty or error page as a transcript
        raise NoTranscript("failed", f"captions came back empty ({len(segments)} segments)")
    return ("auto" if t.is_generated else "manual"), segments
