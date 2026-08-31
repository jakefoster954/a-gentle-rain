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
    # Any number of colours and tiles is allowed; only structural integrity is
    # required so the game runs with custom or partial sets, not just the 8/28
    # retail configuration.
    if not colors:
        raise ValueError("at least one colour is required")
    if not tiles:
        raise ValueError("at least one tile is required")
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


DEFAULT_COMMENT = (
    "Tile set for 'A Gentle Rain'. 'edges' lists the flower colour id on the "
    "(N, E, S, W) edge of each tile. Edit by hand or with the tile editor: "
    "python -m agentle_rain --edit"
)


def default_data_path() -> Path:
    """Filesystem path of the bundled ``tiles.json`` (writable in a dev install)."""
    return Path(str(resources.files(_DATA_PACKAGE).joinpath(_DEFAULT_FILE)))


def read_raw(path: str | Path | None = None) -> tuple[list[dict], list[list[int]]]:
    """Read colours and tile edges without enforcing the 8/28 game constraints.

    Returns ``(colors, tiles)`` where ``colors`` is a list of ``{"name", "hex"}``
    dicts and ``tiles`` is a list of 4-element edge lists. Intended for authoring
    tools such as the tile editor, which may hold work-in-progress data.
    """
    if path is None:
        text = resources.files(_DATA_PACKAGE).joinpath(_DEFAULT_FILE).read_text()
    else:
        text = Path(path).read_text()
    raw = json.loads(text)
    colors = [{"name": c["name"], "hex": c["hex"]} for c in raw.get("colors", [])]
    tiles = [list(t["edges"]) for t in raw.get("tiles", [])]
    return colors, tiles


def write_tiles_file(
    path: str | Path,
    colors: list[dict],
    tiles: list[list[int]],
    comment: str = DEFAULT_COMMENT,
) -> None:
    """Write ``colors`` and ``tiles`` as compact, hand-editable JSON.

    Each colour and each tile is written on its own single line so the file is
    easy to read and edit by hand.
    """
    lines = ["{", f'  "_comment": {json.dumps(comment)},', '  "colors": [']
    for i, c in enumerate(colors):
        tail = "," if i < len(colors) - 1 else ""
        lines.append(
            f'    {{"name": {json.dumps(c["name"])}, "hex": {json.dumps(c["hex"])}}}{tail}'
        )
    lines += ["  ],", '  "tiles": [']
    for i, edges in enumerate(tiles):
        tail = "," if i < len(tiles) - 1 else ""
        joined = ", ".join(str(int(e)) for e in edges)
        lines.append(f'    {{"id": {i}, "edges": [{joined}]}}{tail}')
    lines += ["  ]", "}"]
    Path(path).write_text("\n".join(lines) + "\n")
