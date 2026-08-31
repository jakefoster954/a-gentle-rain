"""Clairvoyant ceiling check: is a losing shuffle winnable *with* foresight?

For a fixed draw order (a single seed) this backtracks over placements and bloom
choices to decide whether ANY legal line blooms every colour. The order is fixed,
so it is a bounded search (with a transposition table and a per-seed budget), not
the intractable full-deck problem.

Run it on the seeds the heuristic loses to classify each loss as:

* ``winnable``   — a winning line exists, so a better heuristic could get it.
* ``unwinnable`` — the whole tree was searched and no line wins (100% impossible
  for this seed under the rules).
* ``unknown``    — the budget ran out before deciding.

    python tools/clairvoyant.py --games 3000 --budget 15
"""

from __future__ import annotations

import argparse
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from agentle_rain.agents import HeuristicAgent, play_game  # noqa: E402
from agentle_rain.data_loader import load_colors_and_tiles  # noqa: E402
from agentle_rain.engine import Game  # noqa: E402

Edges = tuple[int, int, int, int]
Cell = tuple[int, int]

_DELTAS = ((-1, 0), (0, 1), (1, 0), (0, -1))  # N, E, S, W
_OPPOSITE = (2, 3, 0, 1)


class _Budget(Exception):
    pass


def _oriented(base: Edges, orientation: int) -> Edges:
    return tuple(base[(d - orientation) % 4] for d in range(4))  # type: ignore[return-value]


def _canonical(board: dict[Cell, Edges]) -> frozenset:
    min_r = min(r for r, _ in board)
    min_c = min(c for _, c in board)
    return frozenset(((r - min_r, c - min_c), e) for (r, c), e in board.items())


def _legal(board: dict[Cell, Edges], base: Edges) -> list[tuple[Cell, Edges]]:
    if not board:
        return [((0, 0), _oriented(base, 0))]
    frontier: set[Cell] = set()
    for r, c in board:
        for dr, dc in _DELTAS:
            cell = (r + dr, c + dc)
            if cell not in board:
                frontier.add(cell)
    out: list[tuple[Cell, Edges]] = []
    for r, c in frontier:
        for orientation in range(4):
            edges = _oriented(base, orientation)
            touches = False
            ok = True
            for i, (dr, dc) in enumerate(_DELTAS):
                nb = board.get((r + dr, c + dc))
                if nb is None:
                    continue
                touches = True
                if edges[i] != nb[_OPPOSITE[i]]:
                    ok = False
                    break
            if touches and ok:
                out.append(((r, c), edges))
    return out


def _holes(board: dict[Cell, Edges], cell: Cell) -> list[frozenset[int]]:
    r, c = cell
    result: list[frozenset[int]] = []
    for br, bc in ((r - 1, c - 1), (r - 1, c), (r, c - 1), (r, c)):
        tl = board.get((br, bc))
        tr = board.get((br, bc + 1))
        bl = board.get((br + 1, bc))
        brc = board.get((br + 1, bc + 1))
        if tl and tr and bl and brc:
            result.append(frozenset((tl[1], tl[2], tr[2], bl[1])))
    return result


def play_order(tiles, seed: int) -> list[Edges]:
    """Reconstruct the exact tile order a Game(seed=...) plays (first tile first)."""
    ids = [t.id for t in tiles]
    random.Random(seed).shuffle(ids)
    by_id = {t.id: tuple(t.edges) for t in tiles}
    return [by_id[i] for i in reversed(ids)]  # game pops from the end; first placed at origin


def winnable(num_colors: int, sequence: list[Edges], time_budget: float) -> bool | None:
    start = time.perf_counter()
    nodes = 0
    losing: set = set()

    def tick() -> None:
        nonlocal nodes
        nodes += 1
        if (nodes & 4095) == 0 and time.perf_counter() - start > time_budget:
            raise _Budget

    def new_blooms(board: dict[Cell, Edges], cell: Cell, bloomed: frozenset) -> int:
        return len({c for hole in _holes(board, cell) for c in hole} - bloomed)

    def resolve(
        board: dict[Cell, Edges], holes: list[frozenset[int]], index: int, bloomed: frozenset
    ) -> bool:
        def rec(i: int, bloomed: frozenset) -> bool:
            if len(bloomed) == num_colors:
                return True
            if i == len(holes):
                return dfs(index + 1, board, bloomed)
            available = holes[i] - bloomed
            if not available:
                return rec(i + 1, bloomed)
            return any(rec(i + 1, bloomed | {c}) for c in available)

        return rec(0, bloomed)

    def dfs(index: int, board: dict[Cell, Edges], bloomed: frozenset) -> bool:
        if len(bloomed) == num_colors:
            return True
        if index >= len(sequence):
            return False
        tick()
        key = (_canonical(board), index, bloomed)
        if key in losing:
            return False
        placements = _legal(board, sequence[index])
        if not placements:
            result = dfs(index + 1, board, bloomed)  # forced discard
        else:
            placements.sort(key=lambda p: -new_blooms({**board, p[0]: p[1]}, p[0], bloomed))
            result = False
            for cell, edges in placements:
                nb = {**board, cell: edges}
                if resolve(nb, _holes(nb, cell), index, bloomed):
                    result = True
                    break
        if not result:
            losing.add(key)
        return result

    try:
        board = {(0, 0): _oriented(sequence[0], 0)}
        return dfs(1, board, frozenset())
    except _Budget:
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", type=int, default=3000, help="seeds to scan for losses")
    parser.add_argument("--budget", type=float, default=15.0, help="seconds per losing seed")
    parser.add_argument("--path", type=Path, default=None, help="tiles.json (default: bundled)")
    args = parser.parse_args()

    colors, tiles = load_colors_and_tiles(args.path)
    agent = HeuristicAgent()

    losing_seeds = []
    for seed in range(args.games):
        game = Game(colors=colors, tiles=tiles, seed=seed)
        play_game(game, agent)
        if not game.is_won:
            losing_seeds.append(seed)

    print(f"heuristic lost {len(losing_seeds)} / {args.games} games; checking with foresight...\n")
    tally = {"winnable": 0, "unwinnable": 0, "unknown": 0}
    for seed in losing_seeds:
        sequence = play_order(tiles, seed)
        t0 = time.perf_counter()
        verdict = winnable(len(colors), sequence, args.budget)
        label = {True: "winnable", False: "unwinnable", None: "unknown"}[verdict]
        tally[label] += 1
        print(f"  seed {seed:5d}: {label:10s} ({time.perf_counter() - t0:4.1f}s)")

    print(
        f"\nCeiling on the {len(losing_seeds)} losses: "
        f"winnable-with-foresight {tally['winnable']}, "
        f"proven-unwinnable {tally['unwinnable']}, unknown {tally['unknown']}"
    )


if __name__ == "__main__":
    main()
