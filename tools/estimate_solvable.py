"""Estimate the optimal online win probability of a tile set.

Examples::

    python tools/estimate_solvable.py                       # bundled tiles.json
    python tools/estimate_solvable.py --path experiments/small.json --time-budget 30
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from agentle_rain.analysis import estimate_win_probability  # noqa: E402
from agentle_rain.data_loader import load_colors_and_tiles  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", type=Path, default=None, help="tiles.json (default: bundled set)")
    parser.add_argument("--time-budget", type=float, default=60.0, help="seconds to spend")
    parser.add_argument(
        "--exact-max-tiles",
        type=int,
        default=12,
        help="attempt an exact solve at or below this tile count",
    )
    parser.add_argument("--base-seed", type=int, default=0, help="first shuffle seed")
    args = parser.parse_args()

    colors, tiles = load_colors_and_tiles(args.path)
    print(f"Tile set: {len(colors)} colours, {len(tiles)} tiles")
    result = estimate_win_probability(
        colors,
        tiles,
        time_budget=args.time_budget,
        exact_max_tiles=args.exact_max_tiles,
        base_seed=args.base_seed,
    )
    print(result)


if __name__ == "__main__":
    main()
