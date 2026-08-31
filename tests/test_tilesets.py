"""Tests for programmatic tile-set construction, the data writer and the editor helpers."""

from __future__ import annotations

import pytest

from agentle_rain import Game, make_colors, make_tiles, random_tileset
from agentle_rain.agents import GreedyAgent, play_game
from agentle_rain.data_loader import load_colors_and_tiles, read_raw, write_tiles_file
from agentle_rain.ui.editor import _initial_data, _normalize_hex


def test_make_tiles_requires_four_edges():
    with pytest.raises(ValueError):
        make_tiles([[0, 1, 2]])


def test_make_colors_from_count_and_specs():
    assert len(make_colors(6)) == 6
    colors = make_colors([("teal", "#00a0a0"), ("gold", "#ffcc00")])
    assert [c.name for c in colors] == ["teal", "gold"]
    assert [c.id for c in colors] == [0, 1]


def test_random_tileset_shapes_and_playable():
    colors, tiles = random_tileset(num_tiles=20, num_colors=6, rng=1)
    assert len(colors) == 6
    assert len(tiles) == 20
    assert all(len(t.edges) == 4 for t in tiles)
    game = Game(colors=colors, tiles=tiles, seed=0)
    play_game(game, GreedyAgent(seed=0))
    assert game.is_over


def test_game_from_memory_bypasses_file_and_counts():
    tiles = make_tiles([[0, 0, 0, 0], [1, 1, 1, 1], [2, 2, 2, 2]])
    game = Game(colors=make_colors(3), tiles=tiles, seed=0)
    assert game.num_colors == 3
    assert game.deck_remaining == 2  # 3 tiles, one placed at start


def test_game_requires_both_colors_and_tiles():
    with pytest.raises(ValueError):
        Game(colors=make_colors(3))


def test_game_rejects_duplicate_tile_ids():
    from agentle_rain.model import Tile

    dupes = [Tile(id=0, edges=(0, 0, 0, 0)), Tile(id=0, edges=(1, 1, 1, 1))]
    with pytest.raises(ValueError):
        Game(colors=make_colors(2), tiles=dupes)


def test_write_and_read_roundtrip(tmp_path):
    colors = [{"name": "red", "hex": "#ff0000"}, {"name": "blue", "hex": "#0000ff"}]
    tiles = [[0, 1, 0, 1], [1, 1, 0, 0]]
    path = tmp_path / "tiles.json"
    write_tiles_file(path, colors, tiles)
    text = path.read_text()
    assert '{"id": 0, "edges": [0, 1, 0, 1]}' in text  # compact, one line per tile
    back_colors, back_tiles = read_raw(path)
    assert back_colors == colors
    assert back_tiles == tiles


def test_loader_accepts_any_counts(tmp_path):
    # A trimmed-down set (as produced by deleting tiles in the editor) still loads
    # and runs without raising.
    colors = [{"name": f"c{i}", "hex": "#000000"} for i in range(8)]
    tiles = [[0, 1, 2, 3], [3, 2, 1, 0]]
    path = tmp_path / "tiles.json"
    write_tiles_file(path, colors, tiles)
    loaded_colors, loaded_tiles = load_colors_and_tiles(path)
    assert len(loaded_colors) == 8
    assert len(loaded_tiles) == 2
    game = Game(data_path=str(path), seed=0)
    play_game(game, GreedyAgent(seed=0))
    assert game.is_over


def test_loader_still_rejects_malformed(tmp_path):
    path = tmp_path / "bad.json"
    # A tile edge referencing a colour that does not exist.
    write_tiles_file(path, [{"name": "red", "hex": "#ff0000"}], [[0, 0, 5, 0]])
    with pytest.raises(ValueError):
        load_colors_and_tiles(path)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("#3f6fd0", "#3f6fd0"),
        ("3f6fd0", "#3f6fd0"),
        ("f60", "#ff6600"),
        ("#ABCDEF", "#abcdef"),
        ("nope", None),
        ("#12", None),
    ],
)
def test_normalize_hex(value, expected):
    assert _normalize_hex(value) == expected


def test_editor_seeds_defaults_for_missing_file(tmp_path):
    colors, tiles, message = _initial_data(tmp_path / "does_not_exist.json")
    assert len(colors) == 8  # default palette
    assert tiles == [[0, 0, 0, 0]]  # one blank tile
    assert "New file" in message


def test_editor_loads_existing_file(tmp_path):
    path = tmp_path / "tiles.json"
    write_tiles_file(path, [{"name": "red", "hex": "#ff0000"}], [[0, 0, 0, 0], [0, 0, 0, 0]])
    colors, tiles, message = _initial_data(path)
    assert len(colors) == 1
    assert len(tiles) == 2
    assert "Loaded" in message


def test_cli_missing_play_file_exits_gracefully(monkeypatch, capsys):
    import sys

    from agentle_rain.__main__ import main

    monkeypatch.setattr(sys, "argv", ["agentle-rain", "--path", "/no/such/agr_file.json"])
    with pytest.raises(SystemExit) as excinfo:
        main()
    assert excinfo.value.code == 2
    assert "no such tile file" in capsys.readouterr().err
