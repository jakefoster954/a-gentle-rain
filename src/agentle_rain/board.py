"""The board: a sparse grid of placed tiles plus hole/lily bookkeeping."""

from __future__ import annotations

from collections.abc import Iterator

from .geometry import Direction
from .model import PlacedTile

Coord = tuple[int, int]


class Board:
    """A sparse square grid of :class:`PlacedTile` objects.

    Coordinates are ``(row, col)`` and unbounded in every direction. A "hole" is
    the circular gap at the centre of a completed 2x2 block of tiles; it is
    identified by the coordinate of its top-left tile.
    """

    def __init__(self) -> None:
        self._tiles: dict[Coord, PlacedTile] = {}

    def __contains__(self, coord: object) -> bool:
        return coord in self._tiles

    def __iter__(self) -> Iterator[tuple[Coord, PlacedTile]]:
        return iter(self._tiles.items())

    def __len__(self) -> int:
        return len(self._tiles)

    @property
    def is_empty(self) -> bool:
        return not self._tiles

    def get(self, coord: Coord) -> PlacedTile | None:
        return self._tiles.get(coord)

    def place(self, coord: Coord, placed: PlacedTile) -> None:
        if coord in self._tiles:
            raise ValueError(f"cell {coord} is already occupied")
        self._tiles[coord] = placed

    def neighbour(self, coord: Coord, direction: Direction) -> PlacedTile | None:
        dr, dc = direction.delta
        return self._tiles.get((coord[0] + dr, coord[1] + dc))

    def occupied_coords(self) -> list[Coord]:
        return list(self._tiles)

    def empty_frontier(self) -> set[Coord]:
        """Empty cells that are orthogonally adjacent to at least one tile."""
        frontier: set[Coord] = set()
        for row, col in self._tiles:
            for direction in Direction:
                dr, dc = direction.delta
                candidate = (row + dr, col + dc)
                if candidate not in self._tiles:
                    frontier.add(candidate)
        return frontier

    def bounds(self) -> tuple[int, int, int, int]:
        """Return ``(min_row, min_col, max_row, max_col)`` of placed tiles."""
        if not self._tiles:
            return (0, 0, 0, 0)
        rows = [r for r, _ in self._tiles]
        cols = [c for _, c in self._tiles]
        return (min(rows), min(cols), max(rows), max(cols))

    def is_block_complete(self, top_left: Coord) -> bool:
        """True if the 2x2 block whose top-left cell is ``top_left`` is fully placed."""
        r, c = top_left
        return all((r + dr, c + dc) in self._tiles for dr in (0, 1) for dc in (0, 1))

    def hole_candidate_colors(self, top_left: Coord) -> set[int]:
        """Colours of the four flowers surrounding a completed 2x2 hole.

        The hole sits at the shared corner of the four tiles; the surrounding
        flowers are the inner edges pointing at that corner.
        """
        r, c = top_left
        tl = self._tiles[(r, c)]
        tr = self._tiles[(r, c + 1)]
        bl = self._tiles[(r + 1, c)]
        return {
            tl.edge_color(Direction.E),  # top flower
            tl.edge_color(Direction.S),  # left flower
            tr.edge_color(Direction.S),  # right flower
            bl.edge_color(Direction.E),  # bottom flower
        }

    def surrounding_hole_top_lefts(self, coord: Coord) -> list[Coord]:
        """Top-left coords of the four 2x2 blocks that include ``coord``."""
        r, c = coord
        return [(r - 1, c - 1), (r - 1, c), (r, c - 1), (r, c)]
