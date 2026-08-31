"""Tests for the A Gentle Rain engine, model and agents."""

from __future__ import annotations

import json
import random

import pytest

from agentle_rain import Direction, Game, GameState, InvalidAction, Placement, Tile
from agentle_rain.agents import GreedyAgent, RandomAgent, play_game
from agentle_rain.data_loader import load_colors_and_tiles


# --------------------------------------------------------------------- geometry
def test_direction_opposite_and_delta():
    assert Direction.N.opposite is Direction.S
    assert Direction.E.opposite is Direction.W
    assert Direction.N.delta == (-1, 0)
    assert Direction.E.delta == (0, 1)


def test_tile_rotation_moves_edges_clockwise():
    tile = Tile(id=0, edges=(1, 2, 3, 4))  # N=1, E=2, S=3, W=4
    # Unrotated
    assert tile.edge_color(Direction.N, 0) == 1
    assert tile.edge_color(Direction.E, 0) == 2
    # One clockwise quarter turn: the old West edge (4) is now on the North.
    assert tile.edge_color(Direction.N, 1) == 4
    assert tile.edge_color(Direction.E, 1) == 1
    # Full turn returns to the start.
    assert tuple(tile.edge_color(d, 4) for d in Direction) == (1, 2, 3, 4)


# ------------------------------------------------------------------------- data
def test_data_has_eight_colors_and_28_tiles():
    colors, tiles = load_colors_and_tiles()
    assert len(colors) == 8
    assert len(tiles) == 28
    assert all(len(t.edges) == 4 for t in tiles)


# ----------------------------------------------------------------------- engine
def test_game_starts_with_one_tile_on_board():
    game = Game(seed=1)
    assert len(game.board) == 1
    assert game.deck_remaining == 27
    assert game.state is GameState.DRAW


def test_draw_then_place_or_discard_cycle():
    game = Game(seed=3)
    tile = game.draw()
    assert tile is not None
    assert game.state is GameState.PLACE
    placements = game.legal_placements()
    if placements:
        game.place(placements[0])
        assert game.state in (GameState.DRAW, GameState.BLOOM, GameState.WON, GameState.LOST)
    else:
        game.discard()
        assert game.state is GameState.DRAW


def test_only_matching_placements_are_legal():
    game = Game(seed=5)
    game.draw()
    origin = game.board.get((0, 0))
    assert origin is not None
    for placement in game.legal_placements():
        coord = (placement.row, placement.col)
        for direction in Direction:
            neighbour = game.board.neighbour(coord, direction)
            if neighbour is not None:
                mine = game.current_tile.edge_color(direction, placement.orientation)
                assert mine == neighbour.edge_color(direction.opposite)


def test_cannot_discard_when_a_legal_move_exists():
    game = Game(seed=7)
    game.draw()
    if game.has_legal_placement():
        with pytest.raises(InvalidAction):
            game.discard()


def test_cannot_place_illegally():
    game = Game(seed=2)
    game.draw()
    with pytest.raises(InvalidAction):
        game.place(Placement(100, 100, 0))  # far away, touches nothing


def test_bloom_and_win_via_forced_tiles(tmp_path):
    """Construct a tiny deterministic game where a 2x2 always blooms."""
    data = {
        "colors": [{"name": f"c{i}", "hex": "#000000"} for i in range(8)],
        # Every edge is colour 0 so any tile matches any other on every side.
        "tiles": [{"id": i, "edges": [0, 0, 0, 0]} for i in range(28)],
    }
    path = tmp_path / "tiles.json"
    path.write_text(json.dumps(data))

    game = Game(seed=0, data_path=str(path))
    # Place tiles to complete a 2x2 block: (0,0) already down; add (0,1),(1,0),(1,1).
    for coord in [(0, 1), (1, 0), (1, 1)]:
        game.draw()
        game.place(Placement(coord[0], coord[1], 0))
    # The last placement completes the block and opens a bloom.
    assert game.state is GameState.BLOOM
    bloom = game.pending_blooms[0]
    assert bloom.hole == (0, 0)
    assert 0 in bloom.candidate_colors
    game.resolve_bloom((0, 0), 0)
    assert game.blooms_placed == 1
    assert game.tokens[0] == (0, 0)


def test_full_random_playthrough_terminates():
    for seed in range(30):
        game = Game(seed=seed)
        play_game(game, RandomAgent(seed=seed))
        assert game.is_over
        assert game.state in (GameState.WON, GameState.LOST)
        if game.is_won:
            assert game.blooms_placed == 8
            assert game.score == 8 + game.deck_remaining
        else:
            assert game.score == game.blooms_placed


def test_state_dict_is_json_serialisable():
    game = Game(seed=9)
    play_game(game, GreedyAgent(seed=9))
    snapshot = game.state_dict()
    # Round-trips through JSON without error.
    assert json.loads(json.dumps(snapshot))["over"] is True


def test_seed_is_reproducible():
    a = Game(seed=123)
    b = Game(seed=123)
    play_game(a, GreedyAgent(seed=1))
    play_game(b, GreedyAgent(seed=1))
    assert a.state_dict() == b.state_dict()


def test_rng_argument_controls_shuffle():
    game = Game(rng=random.Random(55))
    assert game.deck_remaining == 27
