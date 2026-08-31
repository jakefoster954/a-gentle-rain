"""Tests for win-probability analysis (exact solver + Monte-Carlo estimate)."""

from __future__ import annotations

import pytest

from agentle_rain import Game, make_colors, make_tiles
from agentle_rain.agents import HeuristicAgent, play_game
from agentle_rain.analysis import estimate_win_probability, wilson_interval
from agentle_rain.data_loader import load_colors_and_tiles
from agentle_rain.solver import optimal_online_winprob


# -------------------------------------------------------------------- solver
def test_exact_trivial_win():
    # Four identical single-colour tiles can always be arranged into a 2x2.
    p = optimal_online_winprob(make_colors(1), make_tiles([[0, 0, 0, 0]] * 4))
    assert p == 1.0


def test_exact_cannot_form_hole():
    # Fewer than four tiles cannot complete a 2x2, so no colour ever blooms.
    assert optimal_online_winprob(make_colors(1), make_tiles([[0, 0, 0, 0]] * 3)) == 0.0
    assert optimal_online_winprob(make_colors(1), make_tiles([[0, 0, 0, 0]] * 2)) == 0.0


def test_exact_missing_colour_is_zero():
    # Colour 1 never appears on an edge, so it can never bloom.
    assert optimal_online_winprob(make_colors(2), make_tiles([[0, 0, 0, 0]] * 4)) == 0.0


def test_exact_probability_between_zero_and_one():
    p = optimal_online_winprob(make_colors(1), make_tiles([[0, 0, 0, 0]] * 5))
    assert 0.0 <= p <= 1.0


def test_exact_returns_none_when_budget_exhausted():
    # A tiny node budget forces an early abort -> None (unknown), never a crash.
    colors, tiles = load_colors_and_tiles()
    assert optimal_online_winprob(colors, tiles, node_budget=1) is None


# ------------------------------------------------------------------ wilson
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


# ----------------------------------------------------------------- estimate
def test_estimate_uses_exact_for_small_decks():
    result = estimate_win_probability(make_colors(1), make_tiles([[0, 0, 0, 0]] * 4))
    assert result.method == "exact"
    assert result.probability == 1.0


def test_estimate_montecarlo_for_full_set_returns_number():
    colors, tiles = load_colors_and_tiles()
    result = estimate_win_probability(colors, tiles, time_budget=2.0, exact_max_tiles=0)
    assert result.method == "montecarlo"
    assert 0.0 <= result.ci_low <= result.probability <= result.ci_high <= 1.0
    assert result.samples > 0


def test_heuristic_agent_plays_full_game():
    colors, tiles = load_colors_and_tiles()
    game = Game(colors=colors, tiles=tiles, seed=0)
    play_game(game, HeuristicAgent())
    assert game.is_over
