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
python -m agentle_rain --path my.json  # play a custom tile set
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

Passing `seed=N` (or `rng=random.Random(...)`) makes the whole shuffle and
playthrough **reproducible**, so two games with the same seed and moves are
identical — handy for statistical runs and regression tests.

Ready-made players live in `agentle_rain.agents` (`RandomAgent`, `GreedyAgent`,
`play_game`) — a good starting point for your statistical experiments.

### Building tile sets in code

Agents and experiments can generate tile sets entirely in memory — no file
required — and hand them straight to `Game`:

```python
from agentle_rain import Game, make_colors, make_tiles, random_tileset

# A random, balanced deck for a statistical run:
colors, tiles = random_tileset(num_tiles=28, num_colors=8, rng=42)
game = Game(colors=colors, tiles=tiles, seed=0)

# Or build specific tiles by their (N, E, S, W) edge colour ids:
tiles = make_tiles([[0, 1, 2, 3], [3, 3, 0, 1]])
game = Game(colors=make_colors(4), tiles=tiles, seed=0)
```

In-memory games are **not** restricted to the 8-colour / 28-tile retail setup, so
you can freely vary deck size and palette when exploring questions like the
fewest tiles needed to win.

### Win-probability analysis

`estimate_win_probability` answers "how often can this tile set be won, playing
optimally online (never seeing the future draw order)?"

```python
from agentle_rain import estimate_win_probability
from agentle_rain.data_loader import load_colors_and_tiles

colors, tiles = load_colors_and_tiles()
print(estimate_win_probability(colors, tiles, time_budget=60))
```

- **Small decks** (≈ ≤12 tiles): returns the **exact** optimal online win
  probability via memoised expectimax over the belief state
  `(board, remaining tiles, bloomed colours, tile in hand)`.
- **Large decks** (e.g. the retail 28): exact solving is infeasible, so it
  returns a **Monte-Carlo estimate** — the win rate of a strong online heuristic
  over many random shuffles, with a 95% confidence interval. That figure is a
  **lower bound** on the true optimum (optimal play can only do at least as well).
- It always returns a number within `time_budget` seconds.

From the command line:

```bash
python tools/estimate_solvable.py --time-budget 60
python tools/estimate_solvable.py --path experiments/small.json --time-budget 30
```

## Editing the tiles

The tile data lives in `src/agentle_rain/data/tiles.json`, in a compact,
hand-editable format (one colour and one tile per line). You can edit it directly,
or use the **tile editor**:

```bash
python -m agentle_rain --edit                 # edits the bundled tiles.json
python -m agentle_rain --edit --path my.json  # edit a separate file instead
```

The editor lets you define the colours (add/remove/rename/set hex), paint each
tile's four edges by clicking them, and add/remove tiles — then save (`S`). A
status line shows the set is playable and whether it matches the retail 8/28.

To **start a new experiment set**, point `--edit` at a file that doesn't exist
yet: the editor opens with the default palette and one blank tile, and creates
the file (and any parent folders) when you save:

```bash
python -m agentle_rain --edit --path experiments/new.json
```

`--path` is relative to your current directory. The repo's `experiments/` folder
is git-ignored, so it's the recommended place for scratch tile sets — keeping
them there (or anywhere outside the repo) avoids cluttering the project or
committing them by accident.

The game and engine accept **any number of colours and tiles** (minimum one
tile), so trimmed or custom sets load and play fine; only the structure is
validated (four edges per tile, each referencing an existing colour). Play a
saved custom file with `python -m agentle_rain --path my.json` (or
`Game(data_path="my.json")`); playing a missing file prints a friendly error
telling you to create it with `--edit`.

## Project layout

```
src/agentle_rain/
  geometry.py      # directions and grid maths
  model.py         # Color, Tile, PlacedTile, Placement
  board.py         # sparse grid + hole detection
  engine.py        # Game: the state machine and public API
  agents.py        # simple automated players for headless simulation
  tilesets.py      # build colours/tiles in code (make_tiles, random_tileset, ...)
  solver.py        # exact optimal-online win probability (small decks)
  analysis.py      # estimate_win_probability (exact + Monte-Carlo)
  data/tiles.json  # the 8 colours and 28 tiles (compact, editable)
  ui/pygame_ui.py  # the interactive game UI
  ui/editor.py     # the tile editor UI
tools/generate_tiles.py    # regenerate / verify the tile set
tools/estimate_solvable.py # estimate a set's win probability
tests/                     # pytest suite
```

## Tile data — please note

The exact per-tile artwork of the real 28 tiles could not be reliably transcribed
from photographs. `src/agentle_rain/data/tiles.json` currently holds a **valid,
balanced, playable placeholder set** (8 colours, 28 tiles, each edge is a colour
id for the N/E/S/W side). It is plain JSON and **designed to be corrected** once
the true layouts are known — either by hand, with the tile editor
(`python -m agentle_rain --edit`), or programmatically — no code changes required.
Regenerate or sanity-check the placeholder with:

```bash
python tools/generate_tiles.py --stats
```

## Development

```bash
ruff check .        # lint
ruff format .       # format
pytest              # run the test suite
```
