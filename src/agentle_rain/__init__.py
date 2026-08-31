"""A Gentle Rain: a tile-laying game engine, agents and UI.

Typical use::

    from agentle_rain import Game

    game = Game(seed=42)
    while not game.is_over:
        tile = game.draw()
        if game.is_over:
            break
        moves = game.legal_placements()
        if moves:
            game.place(moves[0])
            for bloom in game.pending_blooms:
                colour = sorted(bloom.candidate_colors & game.available_colors())[0]
                game.resolve_bloom(bloom.hole, colour)
        else:
            game.discard()
    print(game.score)
"""

from __future__ import annotations

from .analysis import WinProbabilityResult, estimate_win_probability
from .board import Board, Coord
from .engine import Game, GameState, InvalidAction, PendingBloom
from .geometry import Direction
from .model import Color, PlacedTile, Placement, Tile
from .solver import optimal_online_winprob
from .tilesets import make_colors, make_tiles, random_tileset

__all__ = [
    "Game",
    "GameState",
    "PendingBloom",
    "InvalidAction",
    "Board",
    "Coord",
    "Direction",
    "Color",
    "Tile",
    "PlacedTile",
    "Placement",
    "make_colors",
    "make_tiles",
    "random_tileset",
    "estimate_win_probability",
    "WinProbabilityResult",
    "optimal_online_winprob",
]
