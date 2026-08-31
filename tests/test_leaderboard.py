"""Tests for the tileset-specific leaderboard."""

from __future__ import annotations

from agentle_rain import make_colors, make_tiles
from agentle_rain.leaderboard import (
    Entry,
    add,
    load,
    make_entry,
    sort_entries,
    tileset_id,
)


def test_tileset_id_is_stable_and_distinct():
    colors = make_colors(2)
    a = make_tiles([[0, 1, 0, 1], [1, 1, 0, 0]])
    b = make_tiles([[0, 1, 0, 1], [1, 1, 0, 1]])  # one edge differs
    assert tileset_id(colors, a) == tileset_id(colors, a)
    assert tileset_id(colors, a) != tileset_id(colors, b)


def test_sort_by_score_then_time():
    entries = [
        Entry("a", score=5, time=30.0, won=False, date="x"),
        Entry("b", score=8, time=90.0, won=True, date="x"),
        Entry("c", score=8, time=45.0, won=True, date="x"),  # same score, faster
    ]
    ordered = sort_entries(entries)
    assert [e.name for e in ordered] == ["c", "b", "a"]


def test_add_and_load_roundtrip(tmp_path):
    tid = "deck123"
    assert load(tid, directory=tmp_path) == []
    add(tid, make_entry("Alice", 8, 42.3, True), directory=tmp_path)
    add(tid, make_entry("Bob", 8, 30.1, True), directory=tmp_path)
    add(tid, make_entry("Cara", 6, 10.0, False), directory=tmp_path)
    entries = load(tid, directory=tmp_path)
    assert [e.name for e in entries] == ["Bob", "Alice", "Cara"]  # score desc, time asc


def test_make_entry_strips_and_rounds():
    entry = make_entry("  Dana  ", 7, 12.34, False)
    assert entry.name == "Dana"
    assert entry.time == 12.3
    assert entry.date  # a timestamp was recorded


def test_leaderboards_are_per_tileset(tmp_path):
    add("deckA", make_entry("A", 8, 20.0, True), directory=tmp_path)
    assert load("deckB", directory=tmp_path) == []
    assert len(load("deckA", directory=tmp_path)) == 1
