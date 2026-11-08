"""Tests for what must not change (see docs/youtube.md). Nothing here contacts YouTube."""
from __future__ import annotations

import json

import pytest

from ytspec import __main__ as cli
from ytspec import guard, library, transcript, youtube
from ytspec.library import Collection
from ytspec.transcript import Segment, Video


@pytest.fixture(autouse=True)
def tmp_library(tmp_path, monkeypatch):
    """Every test gets an empty library and a fresh guard, with no waiting between requests."""
    monkeypatch.setattr(library, "ROOT", tmp_path / "library")
    monkeypatch.setattr(guard, "GAP_SECONDS", (0, 0))
    return tmp_path


VIDEO = Video(id="abcdefghijk", title="Hello: World!", url="https://www.youtube.com/watch?v=abcdefghijk",
              channel="Ch", upload_date="20260102", duration=4010)


def test_transcript_format():
    segments = [Segment(i * 7.5, f"line {i}", 7) for i in range(12)] + [Segment(4000, "late")]
    text = transcript.render(VIDEO, "auto", segments)
    head, body = text.split("---\n")[1:]
    assert list(transcript.yaml.safe_load(head)) == ["title", "video_id", "url", "channel", "published_at",
                                                  "duration_seconds", "transcript_source", "fetched_at"]
    assert body.splitlines()[3:] == [
        "[00:00] line 0 line 1 line 2 line 3",
        "[00:30] line 4 line 5 line 6 line 7",
        "[01:00] line 8 line 9 line 10 line 11",
        "[01:06:40] late",
    ]
    assert transcript.file_name(VIDEO.published, VIDEO.title, VIDEO.id) == "2026-01-02-hello-world-abcdefghijk.md"
    assert transcript.file_name("", "", "-wNyEUrxzFU") == "0000-00-00-untitled--wNyEUrxzFU.md"


@pytest.mark.parametrize("status, gave_up", [
    (None, False),
    ({"status": "failed", "attempts": 2}, False),
    ({"status": "failed", "attempts": 3}, True),
    ({"status": "no_captions", "attempts": 1}, True),
    ({"status": "unavailable", "attempts": 1}, True),
])
def test_gave_up(status, gave_up):
    assert library.gave_up(status) == gave_up


def test_budget():
    for _ in range(guard.DAILY_LIMIT):
        guard.allow()
    with pytest.raises(guard.Stop, match="daily budget"):
        guard.allow()


def test_block_stops_every_request():
    guard.block("429", "abcdefghijk", "IpBlocked")
    with pytest.raises(guard.Stop, match="blocked by YouTube"):
        guard.allow()


@pytest.mark.parametrize("stderr, expected", [
    ("ERROR: [youtube] abc: Unable to download webpage: HTTP Error 429: Too Many Requests", "429"),
    ("ERROR: [youtube] abc: HTTP Error 402: Payment Required", "429"),
    ("ERROR: [youtube] abc: Sign in to confirm you're not a bot", "bot_check"),
    ("ERROR: [youtube] abc: HTTP Error 404: Not Found", None),
])
def test_block_reason(stderr, expected):
    assert youtube.block_reason(stderr) == expected


def fake_captions(results: dict):
    def fetch(video_id):
        result = results[video_id]
        if isinstance(result, Exception):
            raise result
        return "manual", [Segment(0, f"words of {video_id}")]
    return fetch


def test_fetch_records_status_and_missing_log(monkeypatch):
    c = Collection.create("ch", "https://www.youtube.com/@ch", "Ch")
    c.save_videos([Video(id="aaaaaaaaaaa", title="has captions"), Video(id="bbbbbbbbbbb", title="none")])
    monkeypatch.setattr(youtube, "fetch_captions", fake_captions({
        "aaaaaaaaaaa": None, "bbbbbbbbbbb": youtube.NoTranscript("no_captions", "TranscriptsDisabled")}))
    cli.update(c, only=True)  # only: skip listing (no network)
    assert list(c.transcript_files()) == ["aaaaaaaaaaa"]
    assert c.statuses()["bbbbbbbbbbb"]["status"] == "no_captions"
    assert (c.dir / "missing.log").read_text() == "bbbbbbbbbbb\tno_captions\tnone\n"
    assert "[has captions](0000-00-00-has-captions-aaaaaaaaaaa.md)" in (c.transcripts / "INDEX.md").read_text()


def test_grab_fetches_only_that_video(monkeypatch):
    c = Collection.create("topic")
    c.save_videos([Video(id="otherVideo1", title="pending")])
    monkeypatch.setattr(youtube, "fetch_captions", fake_captions({"-wNyEUrxzFU": None}))
    cli.update(c, first=Video(id="-wNyEUrxzFU", title="dash"), only=True)
    assert list(c.transcript_files()) == ["-wNyEUrxzFU"]


def test_failures_in_a_row_stop_the_run(monkeypatch):
    c = Collection.create("ch", "https://www.youtube.com/@ch", "Ch")
    ids = [f"vid{i:08d}" for i in range(5)]
    c.save_videos([Video(id=i) for i in ids])
    monkeypatch.setattr(youtube, "fetch_captions", fake_captions({i: youtube.NoTranscript("failed", "x") for i in ids}))
    with pytest.raises(guard.Stop):
        cli.update(c, only=True)
    assert len(c.statuses()) == cli.MAX_FAILED_IN_A_ROW


def test_listing_learns_a_date():
    c = Collection.create("ch", "https://www.youtube.com/@ch", "Ch")
    undated = Video(id=VIDEO.id, title=VIDEO.title)
    c.write_transcript(undated, "auto", [Segment(0, "hi")])
    c.date_transcripts([VIDEO])
    [path] = c.transcript_files().values()
    assert path.name == "2026-01-02-hello-world-abcdefghijk.md"
    assert transcript.read(path)[0]["published_at"] == "2026-01-02"


def test_videos_json_keeps_its_keys():
    c = Collection.create("ch", "https://www.youtube.com/@ch/videos", "Ch")
    c.save_videos([VIDEO])
    assert set(json.loads((c.dir / "videos.json").read_text())[0]) == {
        "id", "title", "url", "channel", "channel_url", "upload_date", "duration", "view_count"}
    assert c.channel_url == "https://www.youtube.com/@ch/videos"


def test_bad_video_link_is_a_user_error():
    with pytest.raises(youtube.UserError, match="Not a YouTube video link"):
        youtube.lookup_video("https://example.com/watch")
    assert guard.used_today(guard.state()) == 0  # rejected before any request was counted


def test_record_failure_counts_attempts():
    statuses: dict = {}
    library.record_failure(statuses, "abcdefghijk", "failed", "x")
    library.record_failure(statuses, "abcdefghijk", "failed", "y")
    assert statuses["abcdefghijk"] == {"status": "failed", "attempts": 2, "error": "y"}
    library.record_failure(statuses, "abcdefghijk", "failed", "z")
    assert library.gave_up(statuses["abcdefghijk"])
