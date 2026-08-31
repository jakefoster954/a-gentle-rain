# A Gentle Rain

A Python simulation and playable UI of the peaceful tile-laying game
**[A Gentle Rain](https://boardgamegeek.com/blog/1/blogpost/122010/game-overview-a-gentle-rain-or-every-flower-blooms)**.

The project is split so that the **engine is a clean, importable API** — ideal for
running large numbers of simulations to answer statistical questions (e.g. *"what
is the fewest tiles you can win with?"*) — with a **pygame UI** on top for playing
by hand.

## The game

* Shuffle the **28 lake tiles**; flip one face up to start.
* Each turn, **draw** the top tile and **place** it next to the tableau so every
  touching flower half **matches its neighbour** (tiles may be rotated). A tile
  that cannot legally connect anywhere is **discarded**.
* Completing a **2×2 block** opens a circular hole in its centre. A **lily blooms**
  there in one of the **8 flower colours** surrounding the hole — provided that
  colour's token has not already been used.
* **Win** by blooming all **8 lily colours** before the draw stack runs out.
* **Score:** `8 + leftover tiles` if you bloom all eight; otherwise the number of
  blooms you managed.

## Setup

Requires Python 3.10–3.13 (pygame does not yet ship wheels for 3.14).

```bash
python3.12 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

## Play

```bash
python -m agentle_rain            # or: agentle-rain
python -m agentle_rain --seed 42  # a repeatable shuffle
```

**Controls:** `Space` draw · `R` rotate · left-click a green highlight to place ·
`D` discard (when nothing fits) · click a colour swatch to bloom a hole · `N` new
game · `Esc` quit.

## Programmatic API

The engine has no UI dependencies and exposes the full state for automation:

```python
from agentle_rain import Game

game = Game(seed=42)
while not game.is_over:
    game.draw()
    if game.is_over:
        break
    moves = game.legal_placements()
    if not moves:
        game.discard()
        continue
    game.place(moves[0])
    for bloom in game.pending_blooms:
        colour = sorted(bloom.candidate_colors & game.available_colors())[0]
        game.resolve_bloom(bloom.hole, colour)

print("won" if game.is_won else "lost", "score", game.score)
print(game.state_dict())  # JSON-serialisable snapshot of everything
```

Key methods on `Game`: `draw()`, `legal_placements()`, `place(Placement)`,
`discard()`, `pending_blooms`, `resolve_bloom(hole, color_id)`,
`available_colors()`, `state_dict()`, plus `is_over`, `is_won` and `score`.

Ready-made players live in `agentle_rain.agents` (`RandomAgent`, `GreedyAgent`,
`play_game`) — a good starting point for your statistical experiments.

## Project layout

```
src/agentle_rain/
  geometry.py      # directions and grid maths
  model.py         # Color, Tile, PlacedTile, Placement
  board.py         # sparse grid + hole detection
  engine.py        # Game: the state machine and public API
  agents.py        # simple automated players for headless simulation
  data/tiles.json  # the 8 colours and 28 tiles (editable)
  ui/pygame_ui.py  # the interactive UI
tools/generate_tiles.py   # regenerate / verify the tile set
tests/                     # pytest suite
```

## Tile data — please note

The exact per-tile artwork of the real 28 tiles could not be reliably transcribed
from photographs. `src/agentle_rain/data/tiles.json` currently holds a **valid,
balanced, playable placeholder set** (8 colours, 28 tiles, each edge is a colour
id for the N/E/S/W side). It is plain JSON and **designed to be corrected by hand**
once the true layouts are known — no code changes are required. Regenerate or
sanity-check it with:

```bash
python tools/generate_tiles.py --stats
```

## Development

```bash
ruff check .        # lint
ruff format .       # format
pytest              # run the test suite
```
