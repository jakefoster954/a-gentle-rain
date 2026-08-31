"""Exact optimal-online win-probability analysis for *A Gentle Rain*.

The player never sees the future draw order, but (with perfect memory) always
knows which tiles remain in the deck. Because the deck is a uniform random
shuffle, the next draw is uniform over the remaining tiles, so the game is a
finite Markov decision process whose belief state is::

    (board, remaining tiles, colours bloomed, tile in hand)

:func:`optimal_online_winprob` returns the exact value of that MDP — the best
achievable probability of blooming every colour — by memoised expectimax. It is
only tractable for small decks; :mod:`agentle_rain.analysis` falls back to
Monte-Carlo estimation for large ones.
"""

from __future__ import annotations

import time
from collections import Counter

from .model import Color, Tile

# Oriented edges are a 4-tuple in (N, E, S, W) order.
Edges = tuple[int, int, int, int]
Cell = tuple[int, int]

_DELTAS = ((-1, 0), (0, 1), (1, 0), (0, -1))  # N, E, S, W
_OPPOSITE = (2, 3, 0, 1)


class _BudgetExceeded(Exception):
    """Raised internally to abort the search when a time/node budget is hit."""


def _oriented(base: Edges, orientation: int) -> Edges:
    return tuple(base[(d - orientation) % 4] for d in range(4))  # type: ignore[return-value]


def _canonical(board: dict[Cell, Edges]) -> frozenset:
    """Translation-invariant key for a board (positions shifted to the origin)."""
    if not board:
        return frozenset()
    min_r = min(r for r, _ in board)
    min_c = min(c for _, c in board)
    return frozenset(((r - min_r, c - min_c), edges) for (r, c), edges in board.items())


def _legal_placements(board: dict[Cell, Edges], base: Edges) -> list[tuple[Cell, Edges]]:
    """All (cell, oriented-edges) placements of ``base`` that match every neighbour."""
    if not board:
        return [((0, 0), _oriented(base, 0))]  # first tile: origin, orientation fixed by symmetry
    frontier: set[Cell] = set()
    for r, c in board:
        for dr, dc in _DELTAS:
            cell = (r + dr, c + dc)
            if cell not in board:
                frontier.add(cell)
    out: list[tuple[Cell, Edges]] = []
    for cell in frontier:
        r, c = cell
        for orientation in range(4):
            edges = _oriented(base, orientation)
            touches = False
            ok = True
            for d, (dr, dc) in enumerate(_DELTAS):
                neighbour = board.get((r + dr, c + dc))
                if neighbour is None:
                    continue
                touches = True
                if edges[d] != neighbour[_OPPOSITE[d]]:
                    ok = False
                    break
            if touches and ok:
                out.append((cell, edges))
    return out


def _completed_holes(board: dict[Cell, Edges], cell: Cell) -> list[frozenset[int]]:
    """Candidate colour sets for every 2x2 hole completed by placing ``cell``."""
    r, c = cell
    holes: list[frozenset[int]] = []
    for br, bc in ((r - 1, c - 1), (r - 1, c), (r, c - 1), (r, c)):
        tl = board.get((br, bc))
        tr = board.get((br, bc + 1))
        bl = board.get((br + 1, bc))
        brc = board.get((br + 1, bc + 1))
        if tl and tr and bl and brc:
            holes.append(frozenset((tl[1], tl[2], tr[2], bl[1])))
    return holes


def optimal_online_winprob(
    colors: list[Color],
    tiles: list[Tile],
    time_budget: float = 30.0,
    node_budget: int | None = None,
) -> float | None:
    """Return the exact optimal online win probability, or ``None`` if the budget is hit.

    ``None`` means the deck is too large to solve exactly within the given
    time/node budget; use Monte-Carlo estimation instead.
    """
    num_colors = len(colors)
    target = frozenset(range(num_colors))
    bases: list[Edges] = [tuple(t.edges) for t in tiles]  # type: ignore[misc]

    # Cheap exact answer: a colour that never appears on any edge can never bloom.
    present = {e for base in bases for e in base}
    if not target <= present:
        return 0.0

    start = time.perf_counter()
    nodes = 0
    memo_chance: dict[tuple, float] = {}
    memo_decision: dict[tuple, float] = {}

    def tick() -> None:
        nonlocal nodes
        nodes += 1
        if node_budget is not None and nodes > node_budget:
            raise _BudgetExceeded
        if (nodes & 2047) == 0 and time.perf_counter() - start > time_budget:
            raise _BudgetExceeded

    def chance(
        board_key: frozenset, board: dict[Cell, Edges], remaining: tuple, bloomed: frozenset
    ) -> float:
        if len(bloomed) == num_colors:
            return 1.0
        if not remaining:
            return 0.0
        key = (board_key, remaining, bloomed)
        cached = memo_chance.get(key)
        if cached is not None:
            return cached
        tick()
        n = len(remaining)
        value = 0.0
        for base, count in Counter(remaining).items():
            rest = list(remaining)
            rest.remove(base)
            value += (count / n) * decision(board_key, board, tuple(rest), bloomed, base)
        memo_chance[key] = value
        return value

    def decision(
        board_key: frozenset,
        board: dict[Cell, Edges],
        remaining: tuple,
        bloomed: frozenset,
        held: Edges,
    ) -> float:
        key = (board_key, remaining, bloomed, held)
        cached = memo_decision.get(key)
        if cached is not None:
            return cached
        tick()
        placements = _legal_placements(board, held)
        if not placements:
            value = chance(board_key, board, remaining, bloomed)  # forced discard
            memo_decision[key] = value
            return value
        best = 0.0
        for cell, edges in placements:
            new_board = dict(board)
            new_board[cell] = edges
            holes = _completed_holes(new_board, cell)
            value = resolve(new_board, holes, remaining, bloomed)
            if value > best:
                best = value
            if best >= 1.0:
                break
        memo_decision[key] = best
        return best

    def resolve(
        board: dict[Cell, Edges], holes: list[frozenset[int]], remaining: tuple, bloomed: frozenset
    ) -> float:
        # A completed hole must bloom an available surrounding colour (player picks which).
        def rec(idx: int, bloomed: frozenset) -> float:
            if len(bloomed) == num_colors:
                return 1.0
            if idx == len(holes):
                return chance(_canonical(board), board, remaining, bloomed)
            available = holes[idx] - bloomed
            if not available:
                return rec(idx + 1, bloomed)
            best = 0.0
            for colour in available:
                value = rec(idx + 1, bloomed | {colour})
                if value > best:
                    best = value
                if best >= 1.0:
                    break
            return best

        return rec(0, bloomed)

    try:
        return chance(frozenset(), {}, tuple(sorted(bases)), frozenset())
    except _BudgetExceeded:
        return None
