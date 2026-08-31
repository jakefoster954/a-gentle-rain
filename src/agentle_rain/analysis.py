"""Estimate the optimal online win probability of a tile set.

The headline function is :func:`estimate_win_probability`. For small decks it
returns the *exact* optimal online win probability (via
:func:`agentle_rain.solver.optimal_online_winprob`); for realistic decks (~28
tiles) exact solving is infeasible, so it returns a Monte-Carlo estimate: the win
rate of a strong online heuristic over many random shuffles, with a confidence
interval. That win rate is a lower bound on the true optimum — the best online
play can only do at least as well as the heuristic.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass

from .agents import HeuristicAgent, play_game
from .engine import Game
from .model import Color, Tile
from .solver import optimal_online_winprob


@dataclass
class WinProbabilityResult:
    """Outcome of :func:`estimate_win_probability`."""

    probability: float
    method: str  # "exact" or "montecarlo"
    ci_low: float
    ci_high: float
    samples: int
    wins: int
    elapsed: float
    note: str

    def __str__(self) -> str:
        pct = f"{self.probability:.1%}"
        if self.method == "exact":
            return f"P(win) = {pct} (exact optimal online, {self.elapsed:.2f}s)"
        return (
            f"P(win) \u2248 {pct} [95% CI {self.ci_low:.1%}\u2013{self.ci_high:.1%}], "
            f"heuristic lower bound over {self.samples} shuffles ({self.elapsed:.1f}s)"
        )


def wilson_interval(wins: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95%-by-default Wilson score confidence interval for a binomial proportion."""
    if n == 0:
        return (0.0, 1.0)
    p = wins / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = (z / denom) * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (max(0.0, centre - half), min(1.0, centre + half))


def estimate_win_probability(
    colors: list[Color],
    tiles: list[Tile],
    *,
    time_budget: float = 60.0,
    exact_max_tiles: int = 12,
    exact_time_fraction: float = 0.5,
    base_seed: int = 0,
    max_samples: int = 200_000,
) -> WinProbabilityResult:
    """Estimate the optimal online win probability within ``time_budget`` seconds.

    Small decks (``len(tiles) <= exact_max_tiles``) are solved exactly if that
    fits in ``exact_time_fraction`` of the budget; otherwise a Monte-Carlo
    heuristic estimate is returned. Either way a number is always produced.
    """
    start = time.perf_counter()

    if len(tiles) <= exact_max_tiles:
        exact = optimal_online_winprob(colors, tiles, time_budget=time_budget * exact_time_fraction)
        if exact is not None:
            elapsed = time.perf_counter() - start
            return WinProbabilityResult(
                probability=exact,
                method="exact",
                ci_low=exact,
                ci_high=exact,
                samples=0,
                wins=0,
                elapsed=elapsed,
                note="exact optimal online win probability",
            )

    agent = HeuristicAgent()
    wins = 0
    n = 0
    # Amortise the clock check across a batch of games.
    batch = 32
    while n < max_samples and (time.perf_counter() - start) < time_budget:
        for _ in range(batch):
            game = Game(colors=colors, tiles=tiles, seed=base_seed + n)
            play_game(game, agent)
            wins += int(game.is_won)
            n += 1
    elapsed = time.perf_counter() - start
    low, high = wilson_interval(wins, n)
    return WinProbabilityResult(
        probability=wins / n if n else 0.0,
        method="montecarlo",
        ci_low=low,
        ci_high=high,
        samples=n,
        wins=wins,
        elapsed=elapsed,
        note="lower bound on optimal online win probability (heuristic policy)",
    )
