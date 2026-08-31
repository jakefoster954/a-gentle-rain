"""Simple automated players, useful for headless simulation and testing.

These agents make no attempt to play optimally; they exist so that whole games
can be run programmatically (for example, to answer statistical questions about
win rates). Swap in your own policy by subclassing :class:`Agent`.
"""

from __future__ import annotations

import random
from collections import Counter

from .board import Board
from .engine import Game
from .geometry import Direction
from .model import PlacedTile, Placement


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


class HeuristicAgent(RandomAgent):
    """A stronger online policy for estimating the optimal online win rate.

    Placement preference (lexicographic): bloom the most *new* colours, then set
    up the most near-complete holes, then keep the tableau dense. Blooms grab the
    scarcest still-available colour (the hardest to obtain from the tiles left),
    using only the remaining *set* of tiles — never the hidden draw order.
    """

    def choose_placement(self, game: Game, placements: list[Placement]) -> Placement:
        available = game.available_colors()
        best: Placement | None = None
        best_score: tuple[int, int, int] | None = None
        for placement in placements:
            score = _score_placement(game, placement, available)
            if best_score is None or score > best_score:
                best, best_score = placement, score
        return best if best is not None else super().choose_placement(game, placements)

    def choose_bloom_color(self, game: Game, candidates: set[int]) -> int:
        scarcity = _remaining_color_counts(game)
        return min(candidates, key=lambda c: (scarcity.get(c, 0), c))


def _score_placement(game: Game, placement: Placement, available: set[int]) -> tuple[int, int, int]:
    assert game.current_tile is not None
    coord = (placement.row, placement.col)
    scratch = Board()
    for existing_coord, placed in game.board:
        scratch.place(existing_coord, placed)
    scratch.place(coord, PlacedTile(game.current_tile, placement.orientation))

    new_blooms: set[int] = set()
    near_complete = 0
    for top_left in scratch.surrounding_hole_top_lefts(coord):
        cells = [(top_left[0] + dr, top_left[1] + dc) for dr in (0, 1) for dc in (0, 1)]
        filled = sum(1 for cell in cells if cell in scratch)
        if filled == 4 and top_left not in game.holes:
            new_blooms |= scratch.hole_candidate_colors(top_left) & available
        elif filled == 3:
            near_complete += 1
    adjacency = sum(1 for d in Direction if scratch.neighbour(coord, d) is not None)
    return (len(new_blooms), near_complete, adjacency)


def _remaining_color_counts(game: Game) -> Counter[int]:
    counts: Counter[int] = Counter()
    for tile in game.remaining_tiles():
        counts.update(tile.edges)
    return counts


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
