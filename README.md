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
python -m agentle_rain --cheat    # pre-pick the heuristic's move each turn
```

**Controls:** `Space` draw · `R` rotate · **arrows** move the cursor · `Enter`/`Space`
place · `D` discard · `L` leaderboard · `N` new game · `Esc` quit. When a 2×2 completes,
pick the lily colour with the **arrows** (or `1`–`9`) and `Enter`. The mouse works too; the
whole game is keyboard-playable, and the selected cell previews the tile you'll place.

A **timer** runs from your first draw to game end. Each tile set has its own **leaderboard**
(by score, then fastest time): press `L` to view it, and on game over you can enter a name to
save your result (blank = skip). Stored under `~/.agentle_rain/leaderboards/`.

Running with `--cheat` pre-selects the heuristic's suggested placement (and bloom colour) each
turn — press `Enter` to accept or override it as usual; cheat games can't be saved to the
leaderboard.

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
well online (never seeing the future draw order)?"

```python
from agentle_rain import estimate_win_probability
from agentle_rain.data_loader import load_colors_and_tiles

colors, tiles = load_colors_and_tiles()
print(estimate_win_probability(colors, tiles, time_budget=60))
```

It plays many random shuffles with a strong online heuristic (`HeuristicAgent`)
and reports its win rate with a 95% confidence interval, along with the average
and highest score across all runs. This works for any deck
size, including the full retail 28, and always returns a number within
`time_budget` seconds. The heuristic plays *most-constrained colour first*: it
cultivates completable 2x2s for the colours it currently has the fewest ways to
bloom, and at each hole spends the most-constrained available colour — see
[docs/heuristic.md](docs/heuristic.md) for the full explanation.

From the command line:

```bash
python tools/estimate_solvable.py --time-budget 60
python tools/estimate_solvable.py --path experiments/example_deck.json --time-budget 30
```

## Editing the tiles

Tile data lives in `src/agentle_rain/data/tiles.json` (compact JSON: one colour and one
tile per line). Edit it by hand, or use the **tile editor**:

```bash
python -m agentle_rain --edit                 # edit the bundled set
python -m agentle_rain --edit --path my.json  # a separate file (created on save if new)
```

The editor lets you add/remove/rename colours and set their hex, paint each tile's four
edges, and add/remove tiles, then save (`S`). Pointing `--edit` at a non-existent file starts
a fresh set. `--path` is relative to your cwd; the git-ignored `experiments/` folder is the
recommended home for scratch sets.

Any number of colours and tiles is accepted (min one tile); only the structure is validated.
Play a custom file with `python -m agentle_rain --path my.json` (or `Game(data_path=...)`); a
missing file gives a friendly error.

## Project layout

```
src/agentle_rain/
  geometry.py      # directions and grid maths
  model.py         # Color, Tile, PlacedTile, Placement
  board.py         # sparse grid + hole detection
  engine.py        # Game: the state machine and public API
  agents.py        # simple automated players for headless simulation
  tilesets.py      # build colours/tiles in code (make_tiles, random_tileset, ...)
  analysis.py      # estimate_win_probability (Monte-Carlo heuristic)
  leaderboard.py   # persistent, tileset-specific high-score tables
  data/tiles.json  # the 8 colours and 28 tiles (compact, editable)
  ui/pygame_ui.py  # the interactive game UI
  ui/editor.py     # the tile editor UI
tools/generate_tiles.py    # regenerate / verify the tile set
tools/estimate_solvable.py # estimate a set's win probability
tools/diagnose_losses.py   # analyse why the heuristic loses (diagnostic)
tests/                     # pytest suite
```

## Tile data — please note

The real 28 tiles couldn't be reliably transcribed from photos, so
`src/agentle_rain/data/tiles.json` holds a **valid, playable placeholder set** (8 colours,
28 tiles; each edge is a colour id for the N/E/S/W side). Correct it any time — by hand, in
the editor, or programmatically — no code changes needed. Regenerate/sanity-check with
`python tools/generate_tiles.py --stats`.

## Development

```bash
ruff check .        # lint
ruff format .       # format
pytest              # run the test suite
```
