"""The guard: rules that keep us under YouTube's rate limit. acquire.py asks before every request.

- budget: at most YT_DAILY_LIMIT requests a day (a video, a channel listing and a video lookup each count as one)
- pace:   a random YT_GAP_MIN–YT_GAP_MAX seconds between caption requests, across runs too
- block:  the first 429 or bot check stops every request for 24 h (longer if YouTube sends Retry-After)

State lives in knowledge-library/youtube/.guard.json, shared by every run (cron, terminals).
"""
from __future__ import annotations

import datetime as dt
import os
import random
import time

from . import store
from .store import load_json, save_json

DAILY_LIMIT = int(os.environ.get("YT_DAILY_LIMIT", 50))
GAP_SECONDS = (float(os.environ.get("YT_GAP_MIN", 60)), float(os.environ.get("YT_GAP_MAX", 120)))
BLOCK_SECONDS = 24 * 3600


class Stop(Exception):
    """No more requests now. Progress is saved; run again later."""


def now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def state_file():
    return store.ROOT / ".guard.json"


def state() -> dict:
    return load_json(state_file(), {})


def used_today(s: dict) -> int:
    return s.get("used", 0) if s.get("day") == dt.date.today().isoformat() else 0


def stop_reason() -> str | None:
    """Why we must not send a request right now, or None."""
    s = state()
    if (until := s.get("blocked_until")) and dt.datetime.fromisoformat(until) > now():
        return f"blocked by YouTube ({s['reason']}) until {dt.datetime.fromisoformat(until).astimezone():%Y-%m-%d %H:%M}"
    if used_today(s) >= DAILY_LIMIT:
        return f"daily budget used ({DAILY_LIMIT} requests); continues tomorrow"
    return None


def allow(paced: bool = False) -> None:
    """Call right before a YouTube request. Raises Stop if we must not make it; otherwise counts it.

    paced: wait out the gap since the last paced request first (caption requests).
    """
    if reason := stop_reason():
        raise Stop(reason)
    s = state()
    if paced and (last := s.get("last_paced")):
        wait = random.uniform(*GAP_SECONDS) - (now() - dt.datetime.fromisoformat(last)).total_seconds()
        if wait > 0:
            time.sleep(wait)
    s.update(day=dt.date.today().isoformat(), used=used_today(s) + 1)
    if paced:
        s["last_paced"] = now().isoformat(timespec="seconds")
    save_json(state_file(), s)


def block(reason: str, target: str, error: str, retry_after: float | None = None) -> Stop:
    """Record that YouTube said slow down. Returns the Stop to raise."""
    until = now() + dt.timedelta(seconds=max(BLOCK_SECONDS, retry_after or 0))
    save_json(state_file(), {**state(), "blocked_until": until.isoformat(timespec="seconds"), "reason": reason,
                      "target": target, "error": error, "at": now().isoformat(timespec="seconds")})
    return Stop(f"⛔ YouTube says slow down ({reason}); no requests until {until.astimezone():%Y-%m-%d %H:%M}")
