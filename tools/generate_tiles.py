"""Generate the bundled ``tiles.json`` for *A Gentle Rain*.

The real game ships 28 lake tiles printed with 8 flower colours. Until the exact
per-tile artwork is transcribed, this script produces a *valid, playable and
reproducible* placeholder set so the engine and UI are fully functional. The
output file is plain JSON and intended to be hand-edited once the true tile
layouts are known.

Usage::

    python tools/generate_tiles.py            # regenerate the data file
    python tools/generate_tiles.py --stats    # also simulate to report win rate
"""

from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from agentle_rain.data_loader import write_tiles_file  # noqa: E402

# The eight lily/flower colours. Hex values are only used for the UI.
COLORS = [
    {"name": "red", "hex": "#e23b3b"},
    {"name": "pink", "hex": "#f06fae"},
    {"name": "yellow", "hex": "#f2c53d"},
    {"name": "orange", "hex": "#ef8a3b"},
    {"name": "purple", "hex": "#7b3fa0"},
    {"name": "blue", "hex": "#3f6fd0"},
    {"name": "white", "hex": "#e8e8ee"},
    {"name": "green", "hex": "#5fa64f"},
]

NUM_TILES = 28
NUM_EDGES = 4
SEED = 20240531

DATA_FILE = Path(__file__).resolve().parent.parent / "src" / "agentle_rain" / "data" / "tiles.json"


def generate_tiles(seed: int = SEED) -> list[dict]:
    """Create 28 tiles whose edge colours are drawn from a balanced multiset.

    Every colour appears the same number of times across all edges, which keeps
    matching frequent enough for the game to be enjoyable.
    """
    rng = random.Random(seed)
    num_colors = len(COLORS)
    total_edges = NUM_TILES * NUM_EDGES
    pool = [i % num_colors for i in range(total_edges)]
    rng.shuffle(pool)

    tiles = []
    for tile_id in range(NUM_TILES):
        edges = pool[tile_id * NUM_EDGES : (tile_id + 1) * NUM_EDGES]
        tiles.append({"id": tile_id, "edges": edges})
    return tiles


def write_data(tiles: list[dict]) -> None:
    edges = [t["edges"] for t in tiles]
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    write_tiles_file(DATA_FILE, COLORS, edges)
    print(f"Wrote {len(tiles)} tiles to {DATA_FILE}")


def report_stats(games: int = 2000) -> None:
    """Simulate games with the greedy agent and print summary statistics."""
    # Imported here so the script can regenerate data before the engine loads it.
    sys.path.insert(0, str(DATA_FILE.resolve().parent.parent.parent))
    from agentle_rain.agents import GreedyAgent, play_game
    from agentle_rain.engine import Game

    wins = 0
    total_score = 0
    total_blooms = 0
    for i in range(games):
        game = Game(seed=i, data_path=str(DATA_FILE))
        play_game(game, GreedyAgent(seed=i))
        wins += game.is_won
        total_score += game.score
        total_blooms += game.blooms_placed
    print(f"Simulated {games} games (greedy agent):")
    print(f"  win rate      : {wins / games:.1%}")
    print(f"  avg score     : {total_score / games:.2f}")
    print(f"  avg blooms/8  : {total_blooms / games:.2f}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=SEED, help="RNG seed for tile edges")
    parser.add_argument("--stats", action="store_true", help="simulate games after writing")
    args = parser.parse_args()

    write_data(generate_tiles(args.seed))
    if args.stats:
        report_stats()


if __name__ == "__main__":
    main()
