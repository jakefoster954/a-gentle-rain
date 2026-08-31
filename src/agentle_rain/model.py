"""Immutable data model: colours, tiles and placed tiles.

A :class:`Tile` stores the four flower colours printed on its edges in the tile's
own reference frame. Rotating a tile does not mutate it; instead a
:class:`PlacedTile` pairs a tile with an ``orientation`` (0-3 quarter turns
clockwise) and exposes the colour visible on each board-facing edge.
"""

from __future__ import annotations

from dataclasses import dataclass

from .geometry import Direction


@dataclass(frozen=True)
class Color:
    """A flower colour: one of the eight lily varieties."""

    id: int
    name: str
    hex: str


@dataclass(frozen=True)
class Tile:
    """A lake tile with a flower colour on each of its four edges.

    ``edges`` lists the colour id on the (N, E, S, W) edge in the tile's own,
    unrotated frame.
    """

    id: int
    edges: tuple[int, int, int, int]

    def edge_color(self, direction: Direction, orientation: int) -> int:
        """Return the colour id shown on ``direction`` when placed at ``orientation``.

        ``orientation`` is the number of 90-degree clockwise rotations applied.
        """
        return self.edges[(direction - orientation) % 4]


@dataclass(frozen=True)
class PlacedTile:
    """A tile fixed on the board at a particular orientation."""

    tile: Tile
    orientation: int

    def edge_color(self, direction: Direction) -> int:
        """Return the colour id shown on the given board-facing ``direction``."""
        return self.tile.edge_color(direction, self.orientation)

    @property
    def edges(self) -> tuple[int, int, int, int]:
        """The colours currently facing (N, E, S, W) after rotation."""
        return tuple(self.edge_color(d) for d in Direction)  # type: ignore[return-value]


@dataclass(frozen=True)
class Placement:
    """A candidate or committed placement of the current tile."""

    row: int
    col: int
    orientation: int
