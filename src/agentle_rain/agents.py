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
    """A strong online policy for estimating the online win rate.

    The guiding principle (applied to both placing and blooming) is *most
    constrained first*: prioritise the colours you currently have the fewest ways
    to bloom. A colour's number of "sources" is counted structurally from the
    board and the remaining tiles, so nothing is tied to a particular tile set.

    Placement is scored (lexicographically, higher is better) by:

    1. ``immediate`` — new needed colours bloomed now, weighted by criticality
       (a colour with fewer other sources is worth more).
    2. ``-dead`` — avoid creating an adjacent empty cell that no remaining tile
       can ever fill (a permanent gap).
    3. ``setup`` — L-shapes (2x2s one tile short) that a remaining tile can
       actually complete and whose colour is still needed, criticality-weighted,
       so the agent cultivates holes for under-served colours.
    4. ``variety`` — the number of *distinct* still-needed colours set up.
    5. ``frontier`` — prefer exposing edge colours still plentiful in the deck.
    6. ``adjacency`` — a compactness tie-break.

    Blooms spend the most constrained available colour: the one with the fewest
    other sources (other open holes / completable L-shapes), tie-broken by the
    scarcer remaining supply. Everything uses only the remaining *set* of tiles.
    """

    def choose_placement(self, game: Game, placements: list[Placement]) -> Placement:
        tile = game.current_tile
        assert tile is not None
        available = game.available_colors()
        remaining = game.remaining_tiles()
        deck = _deck_orientations(remaining)
        supply: Counter[int] = Counter()
        for t in remaining:
            supply.update(t.edges)
        cache: dict[frozenset, bool] = {}

        scratch = Board()
        for coord, placed in game.board:
            scratch.place(coord, placed)
        # How many ways each colour can currently be bloomed elsewhere (before this move).
        sources = _completable_l_sources(scratch, deck, cache)

        best: Placement | None = None
        best_score: tuple | None = None
        for placement in placements:
            coord = (placement.row, placement.col)
            scratch._tiles[coord] = PlacedTile(tile, placement.orientation)
            score = _evaluate(scratch, game, coord, available, deck, supply, sources, cache)
            del scratch._tiles[coord]
            if best_score is None or score > best_score:
                best, best_score = placement, score
        return best if best is not None else super().choose_placement(game, placements)

    def choose_bloom_color(self, game: Game, candidates: set[int]) -> int:
        deck = _deck_orientations(game.remaining_tiles())
        sources = _completable_l_sources(game.board, deck, {})
        supply = _remaining_color_counts(game)
        others = game.pending_blooms[1:]  # other holes still awaiting a token

        def constraint(color: int) -> tuple[int, int, int]:
            elsewhere = sources.get(color, 0) + sum(
                1 for b in others if color in b.candidate_colors
            )
            return (elsewhere, supply.get(color, 0), color)

        return min(candidates, key=constraint)


def _deck_orientations(tiles: list) -> list:
    """Every oriented (N, E, S, W) edge-tuple the given tiles could present."""
    return [tuple(t.edge_color(d, o) for d in Direction) for t in tiles for o in range(4)]


def _criticality(color_id: int, sources: Counter[int]) -> float:
    """A colour with fewer other ways to bloom it is more urgent."""
    return 1.0 / (1.0 + sources.get(color_id, 0))


def _fill_constraints(board: Board, cell: tuple[int, int]) -> dict[int, int]:
    """Edge colours a tile must show to legally fill ``cell`` (by direction index)."""
    constraints: dict[int, int] = {}
    for d in Direction:
        neighbour = board.neighbour(cell, d)
        if neighbour is not None:
            constraints[d.value] = neighbour.edge_color(d.opposite)
    return constraints


def _can_fill(constraints: dict[int, int], deck: list, cache: dict) -> bool:
    """True if any remaining tile (some rotation) satisfies ``constraints``."""
    if not constraints:
        return True
    key = frozenset(constraints.items())
    cached = cache.get(key)
    if cached is not None:
        return cached
    result = any(all(tup[d] == col for d, col in constraints.items()) for tup in deck)
    cache[key] = result
    return result


def _known_hole_colors(board: Board, top_left: tuple[int, int]) -> set[int]:
    """Colours of a 2x2 hole that are already fixed by the tiles present."""
    r, c = top_left
    tl = board.get((r, c))
    tr = board.get((r, c + 1))
    bl = board.get((r + 1, c))
    colors: set[int] = set()
    if tl is not None:
        colors.add(tl.edge_color(Direction.E))
        colors.add(tl.edge_color(Direction.S))
    if tr is not None:
        colors.add(tr.edge_color(Direction.S))
    if bl is not None:
        colors.add(bl.edge_color(Direction.E))
    return colors


def _completable_l_sources(board: Board, deck: list, cache: dict) -> Counter[int]:
    """Per colour, how many open 3-of-4 'L's a remaining tile could complete for it."""
    sources: Counter[int] = Counter()
    seen: set[tuple[int, int]] = set()
    for coord, _ in board:
        for top_left in board.surrounding_hole_top_lefts(coord):
            if top_left in seen:
                continue
            seen.add(top_left)
            cells = [(top_left[0] + dr, top_left[1] + dc) for dr in (0, 1) for dc in (0, 1)]
            present = [cell for cell in cells if cell in board]
            if len(present) != 3:
                continue
            empty = next(cell for cell in cells if cell not in board)
            if _can_fill(_fill_constraints(board, empty), deck, cache):
                for colour in _known_hole_colors(board, top_left):
                    sources[colour] += 1
    return sources


def _evaluate(
    board: Board,
    game: Game,
    coord: tuple[int, int],
    available: set[int],
    deck: list,
    supply: Counter[int],
    sources: Counter[int],
    cache: dict,
) -> tuple:
    immediate = 0.0
    got: set[int] = set()
    setup_value = 0.0
    variety: set[int] = set()
    for top_left in board.surrounding_hole_top_lefts(coord):
        cells = [(top_left[0] + dr, top_left[1] + dc) for dr in (0, 1) for dc in (0, 1)]
        present = [cell for cell in cells if cell in board]
        if len(present) == 4 and top_left not in game.holes:
            for color in board.hole_candidate_colors(top_left) & available:
                if color not in got:
                    got.add(color)
                    immediate += _criticality(color, sources)
        elif len(present) == 3:
            empty = next(cell for cell in cells if cell not in board)
            if _can_fill(_fill_constraints(board, empty), deck, cache):
                needed = _known_hole_colors(board, top_left) & available
                if needed:
                    setup_value += max(_criticality(c, sources) for c in needed)
                    variety |= needed

    dead = 0
    frontier = 0
    placed = board.get(coord)
    assert placed is not None
    for d in Direction:
        dr, dc = d.delta
        neighbour_cell = (coord[0] + dr, coord[1] + dc)
        if neighbour_cell in board:
            continue
        frontier += supply.get(placed.edge_color(d), 0)
        constraints = _fill_constraints(board, neighbour_cell)
        if constraints and not _can_fill(constraints, deck, cache):
            dead += 1

    adjacency = sum(1 for d in Direction if board.neighbour(coord, d) is not None)
    return (immediate, -dead, setup_value, len(variety), frontier, adjacency)


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
