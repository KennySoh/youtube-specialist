"""Tests for what must not change (see docs/youtube.md). Nothing here contacts YouTube."""
from __future__ import annotations

import json

import pytest

from youtube_ingestion import __main__ as cli
from youtube_ingestion import knowledge_library, request_guard, transcript, youtube_client
from youtube_ingestion.knowledge_library import Collection
from youtube_ingestion.transcript import Segment, Video


@pytest.fixture(autouse=True)
def tmp_library(tmp_path, monkeypatch):
    """Every test gets an empty library and a fresh guard, with no waiting between requests."""
    monkeypatch.setattr(knowledge_library, "ROOT", tmp_path / "library")
    monkeypatch.setattr(request_guard, "GAP_SECONDS", (0, 0))
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
    assert knowledge_library.gave_up(status) == gave_up


def test_budget():
    for _ in range(request_guard.DAILY_LIMIT):
        request_guard.allow()
    with pytest.raises(request_guard.Stop, match="daily budget"):
        request_guard.allow()


def test_block_stops_every_request():
    request_guard.block("429", "abcdefghijk", "IpBlocked")
    with pytest.raises(request_guard.Stop, match="blocked by YouTube"):
        request_guard.allow()


@pytest.mark.parametrize("stderr, expected", [
    ("ERROR: [youtube] abc: Unable to download webpage: HTTP Error 429: Too Many Requests", "429"),
    ("ERROR: [youtube] abc: HTTP Error 402: Payment Required", "429"),
    ("ERROR: [youtube] abc: Sign in to confirm you're not a bot", "bot_check"),
    ("ERROR: [youtube] abc: HTTP Error 404: Not Found", None),
])
def test_block_reason(stderr, expected):
    assert youtube_client.block_reason(stderr) == expected


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
    monkeypatch.setattr(youtube_client, "fetch_captions", fake_captions({
        "aaaaaaaaaaa": None, "bbbbbbbbbbb": youtube_client.NoTranscript("no_captions", "TranscriptsDisabled")}))
    cli.update(c, only=True)  # only: skip listing (no network)
    assert list(c.transcript_files()) == ["aaaaaaaaaaa"]
    assert c.statuses()["bbbbbbbbbbb"]["status"] == "no_captions"
    assert (c.dir / "missing.log").read_text() == "bbbbbbbbbbb\tno_captions\tnone\n"
    assert "[has captions](0000-00-00-has-captions-aaaaaaaaaaa.md)" in (c.transcripts / "INDEX.md").read_text()


def test_grab_fetches_only_that_video(monkeypatch):
    c = Collection.create("topic")
    c.save_videos([Video(id="otherVideo1", title="pending")])
    monkeypatch.setattr(youtube_client, "fetch_captions", fake_captions({"-wNyEUrxzFU": None}))
    cli.update(c, first=Video(id="-wNyEUrxzFU", title="dash"), only=True)
    assert list(c.transcript_files()) == ["-wNyEUrxzFU"]


def test_failures_in_a_row_stop_the_run(monkeypatch):
    c = Collection.create("ch", "https://www.youtube.com/@ch", "Ch")
    ids = [f"vid{i:08d}" for i in range(5)]
    c.save_videos([Video(id=i) for i in ids])
    monkeypatch.setattr(youtube_client, "fetch_captions", fake_captions({i: youtube_client.NoTranscript("failed", "x") for i in ids}))
    with pytest.raises(request_guard.Stop):
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
    with pytest.raises(youtube_client.UserError, match="Not a YouTube video link"):
        youtube_client.lookup_video("https://example.com/watch")
    assert request_guard.used_today(request_guard.state()) == 0  # rejected before any request was counted


def test_record_failure_counts_attempts():
    statuses: dict = {}
    knowledge_library.record_failure(statuses, "abcdefghijk", "failed", "x")
    knowledge_library.record_failure(statuses, "abcdefghijk", "failed", "y")
    assert statuses["abcdefghijk"] == {"status": "failed", "attempts": 2, "error": "y"}
    knowledge_library.record_failure(statuses, "abcdefghijk", "failed", "z")
    assert knowledge_library.gave_up(statuses["abcdefghijk"])


def test_round_robin_interleaves_channels():
    assert cli.round_robin([["a1", "a2", "a3"], [], ["b1"]]) == ["a1", "b1", "a2", "a3"]


def test_update_many_takes_turns(monkeypatch):
    big, small = Collection.create("big", "u1", "Big"), Collection.create("small", "u2", "Small")
    big.save_videos([Video(id=f"big{i:08d}") for i in range(3)])
    small.save_videos([Video(id="small000000")])
    order = []
    monkeypatch.setattr(cli, "list_if_due", lambda c: None)
    monkeypatch.setattr(youtube_client, "fetch_captions", lambda vid: order.append(vid) or ("auto", [Segment(0, "x")]))
    cli.update_many([big, small])
    assert order[:2] == ["big00000000", "small000000"]


TIMELINE_PANEL = """In this video
Timeline
Chapter 1: Intro
0:00
0 seconds
hello there
1:05
1 minute, 5 seconds
second line
1:02:03
1 hour, 2 minutes, 3 seconds
late one
"""


def test_panel_text_parsing():
    from youtube_ingestion import browser
    segs = browser.parse_panel_text(TIMELINE_PANEL)
    assert [(s.start, s.text) for s in segs] == [(0, "hello there"), (65, "second line"), (3723, "late one")]


def test_import_writes_transcript_and_moves_file(tmp_path):
    c = Collection.create("ch", "https://www.youtube.com/@ch", "Ch")
    c.save_videos([VIDEO])
    knowledge_library.record_failure(st := {}, VIDEO.id, "failed", "x")
    c.save_statuses(st)
    downloads = tmp_path / "dl"
    downloads.mkdir()
    (downloads / f"{VIDEO.id}.transcript.json").write_text(json.dumps(
        {"video_id": VIDEO.id, "segments": [{"t": "0:31", "text": "b"}, {"t": "0:00", "text": "a"}]}))
    (downloads / "zzzzzzzzzzz.transcript.json").write_text(json.dumps({"video_id": "zzzzzzzzzzz", "panel_text": "0:00\nhi"}))
    (downloads / "yyyyyyyyyyy.transcript.json").write_text(json.dumps({"video_id": "yyyyyyyyyyy", "segments": []}))
    cli.import_command(type("Args", (), {"dir": str(downloads)})())
    [path] = c.transcript_files().values()
    fm, body = transcript.read(path)
    assert fm["transcript_source"] == "browser" and fm["published_at"] == "2026-01-02"
    assert "[00:00] a\n[00:31] b" in body
    assert c.statuses() == {}
    assert (knowledge_library.ROOT / "_imported" / f"{VIDEO.id}.transcript.json").exists()
    assert sorted(p.name for p in downloads.iterdir()) == ["yyyyyyyyyyy.transcript.json", "zzzzzzzzzzz.transcript.json"]
    assert path.name in (c.transcripts / "INDEX.md").read_text()


def test_todo_lists_given_up_videos_first(capsys):
    c = Collection.create("ch", "https://www.youtube.com/@ch", "Ch")
    c.save_videos([Video(id="new00000000", title="new"), Video(id="hard0000000", title="hard"),
                   Video(id="none0000000", title="no captions")])
    st: dict = {}
    for _ in range(3):
        knowledge_library.record_failure(st, "hard0000000", "failed", "x")
    knowledge_library.record_failure(st, "none0000000", "no_captions", "x")
    c.save_statuses(st)
    cli.todo_command(type("Args", (), {"slug": None, "n": 20, "open": 0})())
    lines = [ln for ln in capsys.readouterr().out.splitlines() if "ch/" in ln]
    assert ["hard0000000" in lines[0], "new00000000" in lines[1], len(lines)] == [True, True, 2]
