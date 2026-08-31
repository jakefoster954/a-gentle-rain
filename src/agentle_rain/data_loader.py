"""Loading of the colour palette and the 28 lake tiles from bundled JSON data."""

from __future__ import annotations

import json
from importlib import resources
from pathlib import Path

from .model import Color, Tile

_DATA_PACKAGE = "agentle_rain.data"
_DEFAULT_FILE = "tiles.json"


def _parse(raw: dict) -> tuple[list[Color], list[Tile]]:
    colors = [
        Color(id=i, name=entry["name"], hex=entry["hex"]) for i, entry in enumerate(raw["colors"])
    ]
    tiles = [Tile(id=entry["id"], edges=tuple(entry["edges"])) for entry in raw["tiles"]]
    _validate(colors, tiles)
    return colors, tiles


def _validate(colors: list[Color], tiles: list[Tile]) -> None:
    if len(colors) != 8:
        raise ValueError(f"expected 8 colours, found {len(colors)}")
    if len(tiles) != 28:
        raise ValueError(f"expected 28 tiles, found {len(tiles)}")
    color_ids = {c.id for c in colors}
    for tile in tiles:
        if len(tile.edges) != 4:
            raise ValueError(f"tile {tile.id} must have 4 edges, has {len(tile.edges)}")
        for edge in tile.edges:
            if edge not in color_ids:
                raise ValueError(f"tile {tile.id} references unknown colour {edge}")


def load_colors_and_tiles(path: str | Path | None = None) -> tuple[list[Color], list[Tile]]:
    """Load the palette and tiles.

    With no ``path`` the data bundled inside the package is used; otherwise the
    JSON file at ``path`` is read. This makes it trivial to swap in a corrected
    tile set later.
    """
    if path is None:
        raw = json.loads(resources.files(_DATA_PACKAGE).joinpath(_DEFAULT_FILE).read_text())
    else:
        raw = json.loads(Path(path).read_text())
    return _parse(raw)
