"""Diagnose why the heuristic loses some games.

Runs many shuffles with the :class:`HeuristicAgent`, finds the ones it loses, and
for each replays the game while instrumenting *why* the missing colour(s) were
never bloomed. It classifies each loss into one of:

* ``bloom-choice`` — a completed 2x2 offered the missing colour but the agent
  bloomed a different colour instead (a resolution mistake).
* ``no-opportunity`` — no completed 2x2 ever had the missing colour available
  (a placement / board-shape problem: we never built a hole around it).
* ``unfinished-setup`` — at the end there was a 3-of-4 "L" whose colours included
  the missing one, i.e. it was set up but never completed (ran out of matching
  tiles / draws).

A human-readable report is written to ``experiments/loss_report.txt`` and an
aggregate summary is printed.

    python tools/diagnose_losses.py --games 3000
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from agentle_rain.agents import HeuristicAgent  # noqa: E402
from agentle_rain.data_loader import load_colors_and_tiles  # noqa: E402
from agentle_rain.engine import Game  # noqa: E402
from agentle_rain.geometry import Direction  # noqa: E402

REPORT_PATH = Path(__file__).resolve().parent.parent / "experiments" / "loss_report.txt"


def _known_hole_colors(board, top_left) -> set[int]:
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


def _unfinished_setup_colors(board) -> set[int]:
    """Colours fixed on any 3-of-4 'L' still open on the final board."""
    seen: set[tuple[int, int]] = set()
    out: set[int] = set()
    for coord, _ in board:
        for top_left in board.surrounding_hole_top_lefts(coord):
            if top_left in seen:
                continue
            seen.add(top_left)
            cells = [(top_left[0] + dr, top_left[1] + dc) for dr in (0, 1) for dc in (0, 1)]
            if sum(1 for cell in cells if cell in board) == 3:
                out |= _known_hole_colors(board, top_left)
    return out


def _play_traced(game: Game, agent: HeuristicAgent) -> dict:
    """Play a game, recording bloom opportunities per colour."""
    chances: Counter[int] = Counter()  # completed holes where colour c was available
    grabbed: Counter[int] = Counter()  # colour c actually bloomed
    hole_sets: list[frozenset[int]] = []  # full candidate set of every completed hole
    discards = 0
    while not game.is_over:
        game.draw()
        if game.is_over:
            break
        placements = game.legal_placements()
        if not placements:
            game.discard()
            discards += 1
            continue
        before = set(game.holes)
        game.place(agent.choose_placement(game, placements))
        completed = (set(game.holes) - before) | {b.hole for b in game.pending_blooms}
        for hole in completed:
            hole_sets.append(frozenset(game.board.hole_candidate_colors(hole)))
        while game.pending_blooms:
            bloom = game.pending_blooms[0]
            available = bloom.candidate_colors & game.available_colors()
            for colour in available:
                chances[colour] += 1
            chosen = agent.choose_bloom_color(game, set(available))
            grabbed[chosen] += 1
            game.resolve_bloom(bloom.hole, chosen)
    return {
        "chances": chances,
        "grabbed": grabbed,
        "discards": discards,
        "unfinished": _unfinished_setup_colors(game.board),
        "hole_sets": hole_sets,
    }


def max_colour_coverage(hole_sets: list[frozenset[int]], num_colors: int) -> int:
    """Largest number of distinct colours coverable by assigning holes to colours.

    A hole can bloom any of its (up to four) surrounding colours; each colour is
    needed once. This is a bipartite matching between colours and completed holes.
    """
    holes_for = {c: [i for i, s in enumerate(hole_sets) if c in s] for c in range(num_colors)}
    match_hole: dict[int, int] = {}

    def assign(colour: int, seen: set[int]) -> bool:
        for hole in holes_for[colour]:
            if hole in seen:
                continue
            seen.add(hole)
            if hole not in match_hole or assign(match_hole[hole], seen):
                match_hole[hole] = colour
                return True
        return False

    return sum(1 for c in range(num_colors) if assign(c, set()))


def classify_loss(game: Game, trace: dict, color_names: list[str]) -> list[dict]:
    """For each missing colour, work out why it never bloomed."""
    missing = sorted(set(range(game.num_colors)) - set(game.tokens))
    results = []
    for c in missing:
        chances = trace["chances"].get(c, 0)
        if chances > 0:
            cause = "bloom-choice"  # we completed holes with c available but chose others
        elif c in trace["unfinished"]:
            cause = "unfinished-setup"
        else:
            cause = "no-opportunity"
        results.append({"colour": color_names[c], "chances": chances, "cause": cause})
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", type=int, default=3000, help="how many seeds to try")
    parser.add_argument("--path", type=Path, default=None, help="tiles.json (default: bundled)")
    args = parser.parse_args()

    colors, tiles = load_colors_and_tiles(args.path)
    names = [c.name for c in colors]
    agent = HeuristicAgent()

    losses: list[str] = []
    cause_counts: Counter[str] = Counter()
    missed_colour_counts: Counter[str] = Counter()
    discards_in_losses: list[int] = []
    coverable_losses = 0
    total_wins = 0

    for seed in range(args.games):
        game = Game(colors=colors, tiles=tiles, seed=seed)
        trace = _play_traced(game, agent)
        if game.is_won:
            total_wins += 1
            continue
        reasons = classify_loss(game, trace, names)
        discards_in_losses.append(trace["discards"])
        coverable = max_colour_coverage(trace["hole_sets"], game.num_colors) == game.num_colors
        coverable_losses += int(coverable)
        parts = []
        for r in reasons:
            cause_counts[r["cause"]] += 1
            missed_colour_counts[r["colour"]] += 1
            parts.append(f"{r['colour']}({r['cause']}, chances={r['chances']})")
        losses.append(
            f"seed {seed:5d}: score {game.score}, blooms {game.blooms_placed}/8, "
            f"discards {trace['discards']}, coverable={coverable}, missing: {', '.join(parts)}"
        )

    games = args.games
    lost = games - total_wins
    lines = [
        "A Gentle Rain — heuristic loss analysis",
        f"games: {games}  wins: {total_wins} ({total_wins / games:.1%})  losses: {lost}",
        "",
        f"losses where a valid holes->8-colour assignment existed (fixable by better "
        f"bloom choice): {coverable_losses}/{lost}",
        "",
        "Loss causes (per missing colour):",
        *[f"  {cause}: {n}" for cause, n in cause_counts.most_common()],
        "",
        "Most-missed colours:",
        *[f"  {name}: {n}" for name, n in missed_colour_counts.most_common()],
        "",
        f"avg discards in lost games: {sum(discards_in_losses) / len(discards_in_losses):.2f}"
        if discards_in_losses
        else "",
        "",
        "Per-loss detail:",
        *losses,
    ]
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n")

    print("\n".join(lines[:14]))
    print(f"\nFull report: {REPORT_PATH}")


if __name__ == "__main__":
    main()
