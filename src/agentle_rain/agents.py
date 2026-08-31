"""Simple automated players, useful for headless simulation and testing.

These agents make no attempt to play optimally; they exist so that whole games
can be run programmatically (for example, to answer statistical questions about
win rates). Swap in your own policy by subclassing :class:`Agent`.
"""

from __future__ import annotations

import random

from .engine import Game
from .model import Placement


class Agent:
    """Base class: decide a placement and a bloom colour for a game position."""

    def choose_placement(self, game: Game, placements: list[Placement]) -> Placement:
        raise NotImplementedError

    def choose_bloom_color(self, game: Game, candidates: set[int]) -> int:
        raise NotImplementedError


class RandomAgent(Agent):
    """Places tiles and blooms uniformly at random among legal options."""

    def __init__(self, seed: int | None = None, rng: random.Random | None = None) -> None:
        self._rng = rng if rng is not None else random.Random(seed)

    def choose_placement(self, game: Game, placements: list[Placement]) -> Placement:
        return self._rng.choice(placements)

    def choose_bloom_color(self, game: Game, candidates: set[int]) -> int:
        return self._rng.choice(sorted(candidates))


class GreedyAgent(RandomAgent):
    """Prefers placements that immediately bloom a new colour."""

    def choose_placement(self, game: Game, placements: list[Placement]) -> Placement:
        best = None
        best_gain = -1
        available = game.available_colors()
        for placement in placements:
            gain = _bloom_potential(game, placement, available)
            if gain > best_gain:
                best, best_gain = placement, gain
        return best if best is not None else super().choose_placement(game, placements)


def _bloom_potential(game: Game, placement: Placement, available: set[int]) -> int:
    """Count how many fresh colours a placement could bloom (a cheap heuristic)."""
    assert game.current_tile is not None
    from .board import Board  # local import to avoid cycles at module load
    from .model import PlacedTile

    coord = (placement.row, placement.col)
    # Work on a shallow copy of the board so we do not mutate real game state.
    scratch = Board()
    for existing_coord, placed in game.board:
        scratch.place(existing_coord, placed)
    scratch.place(coord, PlacedTile(game.current_tile, placement.orientation))

    gained: set[int] = set()
    for top_left in scratch.surrounding_hole_top_lefts(coord):
        if top_left in game.holes or not scratch.is_block_complete(top_left):
            continue
        gained |= scratch.hole_candidate_colors(top_left) & available
    return len(gained)


def play_game(game: Game, agent: Agent) -> Game:
    """Play ``game`` to completion using ``agent`` and return it."""
    while not game.is_over:
        game.draw()
        if game.is_over:
            break
        placements = game.legal_placements()
        if not placements:
            game.discard()
            continue
        game.place(agent.choose_placement(game, placements))
        while game.pending_blooms:
            bloom = game.pending_blooms[0]
            options = bloom.candidate_colors & game.available_colors()
            game.resolve_bloom(bloom.hole, agent.choose_bloom_color(game, set(options)))
    return game
