#!/usr/bin/env python3
"""One-off: move Knowledge Acquisition's files out of the old locations (see docs/software-architecture.md).

    python3 scripts/migrate-storage.py            # dry run: prints every move, changes nothing
    python3 scripts/migrate-storage.py --apply    # does the moves

  raw/books/, raw/youtube/                          → knowledge-acquisition/raw/
  knowledge-library/youtube/.guard.json, .lock      → knowledge-acquisition/state/youtube/
  knowledge-library/youtube/<slug>/channel_url, channel_name, videos.json, status.json
                                                    → knowledge-acquisition/state/youtube/<slug>/
  knowledge-library/books/books.txt                 → knowledge-acquisition/state/books/
  knowledge-library/books/<slug>/ocr.pdf            → knowledge-acquisition/state/books/<slug>/

Everything else in knowledge-library/ stays. Moves are renames on the same disk: nothing is copied or
deleted, file dates are kept (videos.json's date decides when a channel is listed again). It stops
before moving anything if a ./scripts/yt.sh run is going, a destination already exists, or the
destination is on another disk.
"""
from __future__ import annotations

import fcntl
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
LIB = REPO / "knowledge-library"
ACQ = REPO / "knowledge-acquisition"
YT_STATE_FILES = ("channel_url", "channel_name", "videos.json", "status.json")


def plan() -> list[tuple[Path, Path]]:
    moves = []
    for source in ("books", "youtube"):
        old = REPO / "raw" / source
        if old.is_dir():
            new = ACQ / "raw" / source
            if new.is_dir() and not any(new.iterdir()):  # an empty folder made by yt.sh/books.sh: move into it
                moves += [(p, new / p.name) for p in sorted(old.iterdir())]
            else:
                moves.append((old, new))
    for name in (".guard.json", ".lock"):
        if (LIB / "youtube" / name).exists():
            moves.append((LIB / "youtube" / name, ACQ / "state" / "youtube" / name))
    for collection in sorted(p for p in (LIB / "youtube").glob("*") if p.is_dir()):
        for name in YT_STATE_FILES:
            if (collection / name).exists():
                moves.append((collection / name, ACQ / "state" / "youtube" / collection.name / name))
    if (LIB / "books" / "books.txt").exists():
        moves.append((LIB / "books" / "books.txt", ACQ / "state" / "books" / "books.txt"))
    for ocr in sorted((LIB / "books").glob("*/ocr.pdf")):
        moves.append((ocr, ACQ / "state" / "books" / ocr.parent.name / "ocr.pdf"))
    return moves


def size(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())


def human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def problems(moves: list[tuple[Path, Path]]) -> list[str]:
    found = []
    lock = LIB / "youtube" / ".lock"
    if lock.exists():
        with open(lock) as f:
            try:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                found.append("a ./scripts/yt.sh run is going (lock held); wait for it to finish")
    for old, new in moves:
        if new.exists():
            found.append(f"already exists: {new.relative_to(REPO)}")
    ACQ.mkdir(exist_ok=True)
    if moves and os.stat(REPO / moves[0][0].relative_to(REPO).parts[0]).st_dev != os.stat(ACQ).st_dev:
        found.append("knowledge-acquisition/ is on another disk; these would be copies, not renames")
    return found


def main() -> int:
    apply = "--apply" in sys.argv[1:]
    moves = plan()
    if not moves:
        print("Nothing to move: already migrated.")
        return 0

    print(("Plan" if apply else "Dry run, nothing changes") + f": {len(moves)} moves\n")
    for old, new in moves:
        kind = "dir " if old.is_dir() else "file"
        print(f"  {kind} {human(size(old)):>8}  {old.relative_to(REPO)}  →  {new.relative_to(REPO)}")
    stays = sorted({p.relative_to(LIB).parts[0] + "/" + p.relative_to(LIB).parts[1] for p in LIB.glob("*/*")
                    if p.is_dir()})
    print(f"\nStays in knowledge-library/: transcripts/, missing.log, chapters/, notes.md in {len(stays)} collections")

    if found := problems(moves):
        print("\nNot safe to move:")
        for problem in found:
            print(f"  ✗ {problem}")
        return 1
    if not apply:
        print("\nNothing changed. Run again with --apply to move.")
        return 0

    for old, new in moves:
        new.parent.mkdir(parents=True, exist_ok=True)
        os.rename(old, new)  # same disk: instant, keeps dates
    raw = REPO / "raw"
    for d in (raw / "books", raw / "youtube", raw):
        if d.is_dir() and not any(d.iterdir()):
            d.rmdir()
    print(f"\nDone: {len(moves)} moved." + ("" if not raw.exists() else f" {raw.name}/ still has other files; left as is."))
    return 0


if __name__ == "__main__":
    sys.exit(main())
