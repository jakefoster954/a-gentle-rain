"""The game engine for *A Gentle Rain*.

:class:`Game` is the single entry point for both the UI and any automated
simulation. It exposes the full game state and a small, explicit set of actions
(:meth:`draw`, :meth:`place`, :meth:`discard`, :meth:`resolve_bloom`) plus rich
inspection helpers so an agent can reason about the position.

Rules implemented
-----------------
* Shuffle 28 tiles; flip one face up to start.
* Each turn: draw the top tile and place it adjacent to the tableau so every
  touching flower half matches its neighbour (tiles may be rotated). A tile with
  no legal placement is discarded.
* Completing a 2x2 block opens a circular hole; a lily blooms there in one of the
  four surrounding flower colours, provided that colour's token is still free.
* Win by blooming all 8 lily colours before the draw stack runs out.
* Score: 8 + leftover tiles if all 8 bloom; otherwise the number of blooms made.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from enum import Enum, auto

from .board import Board, Coord
from .data_loader import load_colors_and_tiles
from .geometry import Direction
from .model import Color, PlacedTile, Placement, Tile


class GameState(Enum):
    """The action the engine is currently waiting for."""

    DRAW = auto()  # ready to draw the next tile
    PLACE = auto()  # a tile is in hand, awaiting placement or discard
    BLOOM = auto()  # placement opened holes that need resolving
    WON = auto()
    LOST = auto()


@dataclass(frozen=True)
class PendingBloom:
    """A completed 2x2 hole awaiting a token, with its still-available colours."""

    hole: Coord
    candidate_colors: frozenset[int]


class Game:
    """A single game of *A Gentle Rain*.

    Parameters
    ----------
    seed:
        Optional seed for the internal RNG (mutually exclusive with ``rng``).
    rng:
        Optional pre-seeded ``random.Random`` for full control over shuffling.
    data_path:
        Optional path to an alternative tile-definition JSON file.
    colors, tiles:
        Optional in-memory palette and tile list. Provide both to build a game
        without any JSON file (ideal for simulations that generate their own tile
        sets). These take precedence over ``data_path`` and are not restricted to
        the 8-colour / 28-tile retail configuration.
    """

    def __init__(
        self,
        seed: int | None = None,
        rng: random.Random | None = None,
        data_path: str | None = None,
        *,
        colors: list[Color] | None = None,
        tiles: list[Tile] | None = None,
    ) -> None:
        if colors is not None or tiles is not None:
            if colors is None or tiles is None:
                raise ValueError("provide both 'colors' and 'tiles', or neither")
            self.colors = list(colors)
            self._tiles = list(tiles)
        else:
            self.colors, self._tiles = load_colors_and_tiles(data_path)
        if len({t.id for t in self._tiles}) != len(self._tiles):
            raise ValueError("tiles must have unique ids")
        self._tiles_by_id = {t.id: t for t in self._tiles}
        self._rng = rng if rng is not None else random.Random(seed)

        self.board = Board()
        self.deck: list[int] = []
        self.discarded: list[int] = []
        self.current_tile: Tile | None = None
        self.state = GameState.DRAW

        # hole coord -> colour id (or None if it bloomed empty)
        self.holes: dict[Coord, int | None] = {}
        # colour id -> hole coord where its token was placed
        self.tokens: dict[int, Coord] = {}
        self._pending: list[PendingBloom] = []

        self._start()

    # ------------------------------------------------------------------ setup
    def _start(self) -> None:
        self.deck = [t.id for t in self._tiles]
        self._rng.shuffle(self.deck)
        first_id = self.deck.pop()
        self.board.place((0, 0), PlacedTile(self._tiles_by_id[first_id], 0))
        self.state = GameState.DRAW

    # ---------------------------------------------------------------- queries
    @property
    def num_colors(self) -> int:
        return len(self.colors)

    @property
    def deck_remaining(self) -> int:
        return len(self.deck)

    @property
    def tiles(self) -> list[Tile]:
        """The full tile set that defines this game (independent of shuffle)."""
        return list(self._tiles)

    def remaining_tiles(self) -> list[Tile]:
        """Tiles still in the deck (the set a perfect-memory player knows remain)."""
        return [self._tiles_by_id[i] for i in self.deck]

    def available_colors(self) -> set[int]:
        """Colour ids whose lily token has not yet been placed."""
        return {c.id for c in self.colors} - set(self.tokens)

    @property
    def pending_blooms(self) -> list[PendingBloom]:
        return list(self._pending)

    @property
    def blooms_placed(self) -> int:
        return len(self.tokens)

    @property
    def is_won(self) -> bool:
        return self.state is GameState.WON

    @property
    def is_over(self) -> bool:
        return self.state in (GameState.WON, GameState.LOST)

    @property
    def score(self) -> int:
        """Final score. Only meaningful once :attr:`is_over` is true."""
        if len(self.tokens) == self.num_colors:
            return self.num_colors + self.deck_remaining
        return len(self.tokens)

    def _is_legal(self, coord: Coord, tile: Tile, orientation: int) -> bool:
        if coord in self.board:
            return False
        touches = False
        for direction in Direction:
            neighbour = self.board.neighbour(coord, direction)
            if neighbour is None:
                continue
            touches = True
            if tile.edge_color(direction, orientation) != neighbour.edge_color(direction.opposite):
                return False
        return touches

    def legal_placements(self, tile: Tile | None = None) -> list[Placement]:
        """All legal placements for ``tile`` (defaults to the tile in hand)."""
        tile = tile or self.current_tile
        if tile is None:
            return []
        placements: list[Placement] = []
        for coord in self.board.empty_frontier():
            for orientation in range(4):
                if self._is_legal(coord, tile, orientation):
                    placements.append(Placement(coord[0], coord[1], orientation))
        return placements

    def has_legal_placement(self, tile: Tile | None = None) -> bool:
        return bool(self.legal_placements(tile))

    # ----------------------------------------------------------------- actions
    def draw(self) -> Tile | None:
        """Draw the top tile. Ends the game as a loss if the deck is empty."""
        if self.state is not GameState.DRAW:
            raise InvalidAction(f"cannot draw while in state {self.state.name}")
        if not self.deck:
            self.state = GameState.LOST
            return None
        self.current_tile = self._tiles_by_id[self.deck.pop()]
        self.state = GameState.PLACE
        return self.current_tile

    def place(self, placement: Placement) -> list[PendingBloom]:
        """Place the current tile, returning any holes that need resolving."""
        if self.state is not GameState.PLACE:
            raise InvalidAction(f"cannot place while in state {self.state.name}")
        tile = self.current_tile
        assert tile is not None
        coord = (placement.row, placement.col)
        if not self._is_legal(coord, tile, placement.orientation):
            raise InvalidAction(f"illegal placement {placement}")

        self.board.place(coord, PlacedTile(tile, placement.orientation))
        self.current_tile = None
        self._detect_blooms(coord)
        self._advance_after_placement()
        return list(self._pending)

    def discard(self) -> None:
        """Discard the current tile. Only allowed when it has no legal placement."""
        if self.state is not GameState.PLACE:
            raise InvalidAction(f"cannot discard while in state {self.state.name}")
        if self.has_legal_placement():
            raise InvalidAction("cannot discard a tile that can be legally placed")
        assert self.current_tile is not None
        self.discarded.append(self.current_tile.id)
        self.current_tile = None
        self.state = GameState.DRAW

    def resolve_bloom(self, hole: Coord, color_id: int) -> None:
        """Place a lily token of ``color_id`` in the pending ``hole``."""
        if self.state is not GameState.BLOOM:
            raise InvalidAction(f"no blooms to resolve in state {self.state.name}")
        bloom = next((b for b in self._pending if b.hole == hole), None)
        if bloom is None:
            raise InvalidAction(f"{hole} is not a pending bloom")
        if color_id not in bloom.candidate_colors:
            raise InvalidAction(f"colour {color_id} does not surround hole {hole}")
        if color_id in self.tokens:
            raise InvalidAction(f"colour {color_id} has already bloomed")

        self.tokens[color_id] = hole
        self.holes[hole] = color_id
        self._pending = [b for b in self._pending if b.hole != hole]
        self._prune_pending()
        if not self._pending:
            self._finish_bloom_phase()

    # --------------------------------------------------------------- internals
    def _detect_blooms(self, coord: Coord) -> None:
        for top_left in self.board.surrounding_hole_top_lefts(coord):
            if top_left in self.holes:
                continue
            if not self.board.is_block_complete(top_left):
                continue
            candidates = self.board.hole_candidate_colors(top_left)
            available = candidates & self.available_colors()
            if available:
                self._pending.append(PendingBloom(top_left, frozenset(candidates)))
            else:
                # The hole opens but no matching token is free: it stays empty.
                self.holes[top_left] = None

    def _prune_pending(self) -> None:
        """Drop pending holes whose colours are no longer available (bloom empty)."""
        available = self.available_colors()
        still_pending: list[PendingBloom] = []
        for bloom in self._pending:
            if bloom.candidate_colors & available:
                still_pending.append(bloom)
            else:
                self.holes[bloom.hole] = None
        self._pending = still_pending

    def _advance_after_placement(self) -> None:
        self._prune_pending()
        if self._pending:
            self.state = GameState.BLOOM
        else:
            self._finish_bloom_phase()

    def _finish_bloom_phase(self) -> None:
        if len(self.tokens) == self.num_colors:
            self.state = GameState.WON
        elif not self.deck:
            self.state = GameState.LOST
        else:
            self.state = GameState.DRAW

    # ------------------------------------------------------------- inspection
    def color(self, color_id: int) -> Color:
        return self.colors[color_id]

    def state_dict(self) -> dict:
        """A JSON-serialisable snapshot of the full game state."""
        return {
            "state": self.state.name,
            "deck_remaining": self.deck_remaining,
            "discarded": list(self.discarded),
            "current_tile": (
                None
                if self.current_tile is None
                else {"id": self.current_tile.id, "edges": list(self.current_tile.edges)}
            ),
            "board": [
                {
                    "row": r,
                    "col": c,
                    "tile_id": placed.tile.id,
                    "orientation": placed.orientation,
                    "edges": list(placed.edges),
                }
                for (r, c), placed in self.board
            ],
            "holes": {f"{r},{c}": color for (r, c), color in self.holes.items()},
            "tokens": {self.colors[cid].name: list(coord) for cid, coord in self.tokens.items()},
            "available_colors": sorted(self.available_colors()),
            "pending_blooms": [
                {"hole": list(b.hole), "candidates": sorted(b.candidate_colors)}
                for b in self._pending
            ],
            "blooms_placed": self.blooms_placed,
            "won": self.is_won,
            "over": self.is_over,
            "score": self.score if self.is_over else None,
        }


class InvalidAction(Exception):
    """Raised when an action is attempted that the rules do not permit."""
