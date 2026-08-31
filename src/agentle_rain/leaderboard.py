"""Persistent, tileset-specific leaderboards.

Each tile set has its own leaderboard, identified by a content hash of its
colours and tiles, stored as JSON under the user's home directory. Entries are
ordered by score (descending) then time (ascending), so a higher score wins and,
on a tie, the faster game ranks higher.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from .model import Color, Tile

LEADERBOARD_DIR = Path.home() / ".agentle_rain" / "leaderboards"


@dataclass(frozen=True)
class Entry:
    """A single leaderboard result."""

    name: str
    score: int
    time: float  # seconds elapsed from first draw to game end
    won: bool
    date: str  # ISO-8601 UTC timestamp


def tileset_id(colors: list[Color], tiles: list[Tile]) -> str:
    """Stable identifier for a tile set, derived from its colours and tiles."""
    payload = {
        "colors": [[c.name, c.hex] for c in colors],
        "tiles": [list(t.edges) for t in tiles],
    }
    blob = json.dumps(payload, separators=(",", ":"), sort_keys=False)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:16]


def sort_entries(entries: list[Entry]) -> list[Entry]:
    """Order by score (high first), then time (low first)."""
    return sorted(entries, key=lambda e: (-e.score, e.time))


def _path(tid: str, directory: Path) -> Path:
    return directory / f"{tid}.json"


def load(tid: str, directory: Path | None = None) -> list[Entry]:
    """Return the sorted entries for a tile set (empty if none recorded yet)."""
    directory = directory or LEADERBOARD_DIR
    path = _path(tid, directory)
    if not path.exists():
        return []
    raw = json.loads(path.read_text())
    return sort_entries([Entry(**item) for item in raw.get("entries", [])])


def save(tid: str, entries: list[Entry], directory: Path | None = None) -> None:
    directory = directory or LEADERBOARD_DIR
    path = _path(tid, directory)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"entries": [asdict(e) for e in sort_entries(entries)]}
    path.write_text(json.dumps(payload, indent=2) + "\n")


def add(tid: str, entry: Entry, directory: Path | None = None) -> list[Entry]:
    """Append ``entry``, persist, and return the updated sorted entries."""
    directory = directory or LEADERBOARD_DIR
    entries = load(tid, directory)
    entries.append(entry)
    entries = sort_entries(entries)
    save(tid, entries, directory)
    return entries


def make_entry(name: str, score: int, time: float, won: bool) -> Entry:
    """Build an :class:`Entry` with a UTC timestamp and rounded time."""
    return Entry(
        name=name.strip(),
        score=score,
        time=round(time, 1),
        won=won,
        date=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
