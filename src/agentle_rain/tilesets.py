"""Programmatic construction of colour palettes and tile sets.

These helpers let agents and experiments build tile sets in memory, without
touching the JSON data file — useful for statistical studies that run many
generated decks. Everything here returns plain :class:`~agentle_rain.model.Color`
and :class:`~agentle_rain.model.Tile` objects that can be passed straight to
:class:`~agentle_rain.engine.Game`::

    from agentle_rain import Game
    from agentle_rain.tilesets import random_tileset

    colors, tiles = random_tileset(num_tiles=28, num_colors=8, rng=42)
    game = Game(colors=colors, tiles=tiles, seed=0)
"""

from __future__ import annotations

import random
from collections.abc import Iterable, Sequence

from .model import Color, Tile

# A neutral 8-colour palette; only the ``hex`` values matter to the UI.
DEFAULT_PALETTE: list[tuple[str, str]] = [
    ("red", "#e23b3b"),
    ("pink", "#f06fae"),
    ("yellow", "#f2c53d"),
    ("orange", "#ef8a3b"),
    ("purple", "#7b3fa0"),
    ("blue", "#3f6fd0"),
    ("white", "#e8e8ee"),
    ("green", "#5fa64f"),
]


def make_colors(specs: Iterable[tuple[str, str]] | int) -> list[Color]:
    """Build a colour list from ``(name, hex)`` pairs, or the first ``n`` defaults.

    ``make_colors(6)`` returns the first six colours of :data:`DEFAULT_PALETTE`;
    ``make_colors([("teal", "#00a0a0")])`` builds from explicit specs.
    """
    if isinstance(specs, int):
        specs = DEFAULT_PALETTE[:specs]
    return [Color(id=i, name=name, hex=hex_) for i, (name, hex_) in enumerate(specs)]


def make_tiles(edges_iterable: Iterable[Sequence[int]]) -> list[Tile]:
    """Build a tile list from an iterable of 4-element ``(N, E, S, W)`` edge sequences."""
    tiles = []
    for i, edges in enumerate(edges_iterable):
        edges = tuple(edges)
        if len(edges) != 4:
            raise ValueError(f"tile {i} must have 4 edges, got {len(edges)}")
        tiles.append(Tile(id=i, edges=edges))
    return tiles


def _as_rng(rng: random.Random | int | None) -> random.Random:
    return rng if isinstance(rng, random.Random) else random.Random(rng)


def random_tileset(
    num_tiles: int = 28,
    num_colors: int = 8,
    rng: random.Random | int | None = None,
    balanced: bool = True,
    colors: list[Color] | None = None,
) -> tuple[list[Color], list[Tile]]:
    """Generate a random ``(colors, tiles)`` pair for experiments.

    With ``balanced=True`` every colour appears the same number of times across
    all edges, which keeps matches frequent; otherwise each edge is independent
    and uniform. Pass ``colors`` to reuse a specific palette.
    """
    r = _as_rng(rng)
    palette = colors if colors is not None else make_colors(num_colors)
    n = len(palette)
    total_edges = num_tiles * 4
    if balanced:
        pool = [i % n for i in range(total_edges)]
        r.shuffle(pool)
    else:
        pool = [r.randrange(n) for _ in range(total_edges)]
    edges_iter = (pool[i * 4 : i * 4 + 4] for i in range(num_tiles))
    return palette, make_tiles(edges_iter)
