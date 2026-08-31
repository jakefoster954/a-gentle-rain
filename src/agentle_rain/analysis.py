"""Estimate a tile set's win probability by Monte-Carlo simulation.

:func:`estimate_win_probability` plays many random shuffles with the
:class:`~agentle_rain.agents.HeuristicAgent` (a strong online policy that never
sees the future draw order) and reports its win rate with a confidence interval.
This works for any deck size, including the full 28-tile game.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass

from .agents import HeuristicAgent, play_game
from .engine import Game
from .model import Color, Tile


@dataclass
class WinProbabilityResult:
    """Outcome of :func:`estimate_win_probability`."""

    probability: float
    ci_low: float
    ci_high: float
    samples: int
    wins: int
    elapsed: float

    def __str__(self) -> str:
        return (
            f"P(win) \u2248 {self.probability:.1%} "
            f"[95% CI {self.ci_low:.1%}\u2013{self.ci_high:.1%}] "
            f"over {self.samples} shuffles ({self.elapsed:.1f}s)"
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
    base_seed: int = 0,
    max_samples: int = 200_000,
) -> WinProbabilityResult:
    """Estimate the heuristic's win rate over random shuffles within ``time_budget``.

    Always returns a number: it keeps simulating games until the time budget or
    ``max_samples`` is reached, then reports the win rate and a 95% confidence
    interval.
    """
    start = time.perf_counter()
    agent = HeuristicAgent()
    wins = 0
    n = 0
    batch = 16  # amortise the clock check across a batch of games
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
        ci_low=low,
        ci_high=high,
        samples=n,
        wins=wins,
        elapsed=elapsed,
    )
