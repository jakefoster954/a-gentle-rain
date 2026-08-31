"""Directions and grid geometry helpers.

The board is an infinite square grid addressed by ``(row, col)`` where ``row``
increases downwards and ``col`` increases to the right.
"""

from __future__ import annotations

from enum import IntEnum


class Direction(IntEnum):
    """The four edges of a tile, ordered clockwise starting at the top.

    The integer values double as indices into a tile's ``edges`` tuple.
    """

    N = 0
    E = 1
    S = 2
    W = 3

    @property
    def delta(self) -> tuple[int, int]:
        """Return the ``(drow, dcol)`` step towards the neighbour in this direction."""
        return _DELTAS[self]

    @property
    def opposite(self) -> Direction:
        """Return the facing edge on the adjacent tile (N<->S, E<->W)."""
        return Direction((self + 2) % 4)


_DELTAS: dict[Direction, tuple[int, int]] = {
    Direction.N: (-1, 0),
    Direction.E: (0, 1),
    Direction.S: (1, 0),
    Direction.W: (0, -1),
}
