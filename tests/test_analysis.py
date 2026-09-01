"""Tests for Monte-Carlo win-probability estimation and the heuristic agent."""

from __future__ import annotations

import pytest

from agentle_rain import Game, make_colors, make_tiles
from agentle_rain.agents import HeuristicAgent, play_game
from agentle_rain.analysis import estimate_win_probability, wilson_interval
from agentle_rain.data_loader import load_colors_and_tiles


@pytest.mark.parametrize(
    ("wins", "n"),
    [(0, 0), (0, 100), (100, 100), (50, 100)],
)
def test_wilson_interval_bounds(wins, n):
    low, high = wilson_interval(wins, n)
    assert 0.0 <= low <= high <= 1.0
    if n:
        p = wins / n
        assert low - 1e-9 <= p <= high + 1e-9  # tolerance for float rounding at p in {0, 1}


def test_estimate_returns_a_number_for_full_set():
    colors, tiles = load_colors_and_tiles()
    result = estimate_win_probability(colors, tiles, time_budget=2.0)
    assert result.ci_low <= result.probability <= result.ci_high + 1e-9
    assert 0.0 <= result.ci_low <= result.ci_high <= 1.0
    assert result.samples > 0
    assert 0 <= result.average_score <= result.highest_score


def test_estimate_works_for_small_deck():
    # Four identical single-colour tiles: the heuristic can always build a 2x2.
    result = estimate_win_probability(
        make_colors(1), make_tiles([[0, 0, 0, 0]] * 4), time_budget=1.0
    )
    assert result.probability == 1.0


def test_heuristic_agent_plays_full_game():
    colors, tiles = load_colors_and_tiles()
    game = Game(colors=colors, tiles=tiles, seed=0)
    play_game(game, HeuristicAgent())
    assert game.is_over
