"""A pygame UI for playing *A Gentle Rain*.

Controls
--------
* **Space** / click *Draw*  : draw the next tile
* **R** / click *Rotate*    : rotate the tile in hand
* **Left click** a highlight : place the tile there
* **D** / click *Discard*   : discard a tile that cannot be placed
* Click a colour swatch      : choose the lily colour for a blooming hole
* **N** / click *New Game*   : start a fresh game
* **Esc**                    : quit

Run with ``python -m agentle_rain`` or the ``agentle-rain`` command.
"""

from __future__ import annotations

import pygame

from ..engine import Game, GameState
from ..geometry import Direction
from ..model import Placement

# Layout -----------------------------------------------------------------------
WINDOW_W, WINDOW_H = 1100, 760
SIDEBAR_W = 300
BOARD_W = WINDOW_W - SIDEBAR_W
MIN_CELL, MAX_CELL = 26, 96

BG = (24, 28, 36)
BOARD_BG = (18, 22, 28)
TILE_FILL = (44, 54, 64)
TILE_EDGE = (70, 84, 96)
HOLE_EMPTY = (12, 14, 18)
TEXT = (226, 230, 236)
MUTED = (140, 150, 162)
HIGHLIGHT = (90, 200, 140)
PENDING = (240, 200, 90)
BUTTON = (54, 64, 78)
BUTTON_HOVER = (74, 88, 106)


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


class Button:
    """A clickable rectangular button with a keyboard hint."""

    def __init__(self, label: str, key: str, action: str) -> None:
        self.label = label
        self.key = key
        self.action = action
        self.rect = pygame.Rect(0, 0, 0, 0)
        self.enabled = True

    def draw(self, surface: pygame.Surface, font: pygame.font.Font, mouse: tuple[int, int]) -> None:
        hovered = self.enabled and self.rect.collidepoint(mouse)
        color = BUTTON_HOVER if hovered else BUTTON
        if not self.enabled:
            color = (38, 44, 52)
        pygame.draw.rect(surface, color, self.rect, border_radius=8)
        label = f"{self.label}  ({self.key})"
        text = font.render(label, True, TEXT if self.enabled else MUTED)
        surface.blit(text, text.get_rect(center=self.rect.center))


class GameUI:
    """Interactive pygame front-end wrapping a :class:`Game`."""

    def __init__(self, seed: int | None = None) -> None:
        pygame.init()
        pygame.display.set_caption("A Gentle Rain")
        self.screen = pygame.display.set_mode((WINDOW_W, WINDOW_H))
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("helvetica,arial", 18)
        self.small = pygame.font.SysFont("helvetica,arial", 15)
        self.big = pygame.font.SysFont("helvetica,arial", 26, bold=True)

        self._seed = seed
        self.game = Game(seed=seed)
        self.orientation = 0
        self.message = ""
        self._legal_cache: list[Placement] = []

        self.buttons = {
            "draw": Button("Draw tile", "Space", "draw"),
            "rotate": Button("Rotate", "R", "rotate"),
            "discard": Button("Discard", "D", "discard"),
            "new": Button("New Game", "N", "new"),
        }
        self._swatch_rects: list[tuple[pygame.Rect, int]] = []

    # ------------------------------------------------------------------- loop
    def run(self) -> None:
        running = True
        while running:
            mouse = pygame.mouse.get_pos()
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    running = self._on_key(event.key)
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    self._on_click(mouse)
            self._draw(mouse)
            pygame.display.flip()
            self.clock.tick(60)
        pygame.quit()

    # ---------------------------------------------------------------- actions
    def _new_game(self) -> None:
        self.game = Game(seed=self._seed)
        self.orientation = 0
        self.message = ""

    def _do_draw(self) -> None:
        if self.game.state is not GameState.DRAW:
            return
        self.game.draw()
        self.orientation = 0
        if self.game.state is GameState.PLACE and not self.game.has_legal_placement():
            self.message = "No legal placement — discard this tile."
        else:
            self.message = ""

    def _do_discard(self) -> None:
        if self.game.state is GameState.PLACE and not self.game.has_legal_placement():
            self.game.discard()
            self.message = "Tile discarded."

    def _rotate(self) -> None:
        if self.game.state is GameState.PLACE:
            self.orientation = (self.orientation + 1) % 4

    def _try_place(self, cell: tuple[int, int]) -> None:
        if self.game.state is not GameState.PLACE or self.game.current_tile is None:
            return
        placement = Placement(cell[0], cell[1], self.orientation)
        if placement in self._legal_cache:
            self.game.place(placement)
            self.message = ""

    def _pick_color(self, color_id: int) -> None:
        if self.game.state is not GameState.BLOOM:
            return
        bloom = self.game.pending_blooms[0]
        options = bloom.candidate_colors & self.game.available_colors()
        if color_id in options:
            self.game.resolve_bloom(bloom.hole, color_id)

    def _on_key(self, key: int) -> bool:
        if key == pygame.K_ESCAPE:
            return False
        if key == pygame.K_SPACE:
            self._do_draw()
        elif key == pygame.K_r:
            self._rotate()
        elif key == pygame.K_d:
            self._do_discard()
        elif key == pygame.K_n:
            self._new_game()
        return True

    def _on_click(self, mouse: tuple[int, int]) -> None:
        for name, button in self.buttons.items():
            if button.enabled and button.rect.collidepoint(mouse):
                {
                    "draw": self._do_draw,
                    "rotate": self._rotate,
                    "discard": self._do_discard,
                    "new": self._new_game,
                }[name]()
                return
        for rect, color_id in self._swatch_rects:
            if rect.collidepoint(mouse):
                self._pick_color(color_id)
                return
        if mouse[0] < BOARD_W:
            cell = self._pixel_to_cell(mouse)
            if cell is not None:
                self._try_place(cell)

    # -------------------------------------------------------------- geometry
    def _view(self) -> tuple[float, int, int, int, int]:
        """Return ``(cell, origin_x, origin_y, min_row, min_col)`` for the board."""
        min_row, min_col, max_row, max_col = self.game.board.bounds()
        # One cell of padding all round so the placement frontier is visible.
        cols = (max_col - min_col + 1) + 2
        rows = (max_row - min_row + 1) + 2
        cell = min(BOARD_W / cols, WINDOW_H / rows)
        cell = max(MIN_CELL, min(MAX_CELL, cell))
        used_w = cols * cell
        used_h = rows * cell
        origin_x = (BOARD_W - used_w) / 2
        origin_y = (WINDOW_H - used_h) / 2
        return cell, int(origin_x), int(origin_y), min_row, min_col

    def _cell_rect(self, row: int, col: int) -> pygame.Rect:
        cell, ox, oy, min_row, min_col = self._view()
        x = ox + (col - min_col + 1) * cell
        y = oy + (row - min_row + 1) * cell
        return pygame.Rect(int(x), int(y), int(cell), int(cell))

    def _pixel_to_cell(self, pos: tuple[int, int]) -> tuple[int, int] | None:
        cell, ox, oy, min_row, min_col = self._view()
        col = int((pos[0] - ox) // cell) + min_col - 1
        row = int((pos[1] - oy) // cell) + min_row - 1
        return (row, col)

    # ---------------------------------------------------------------- drawing
    def _draw(self, mouse: tuple[int, int]) -> None:
        self.screen.fill(BG)
        pygame.draw.rect(self.screen, BOARD_BG, (0, 0, BOARD_W, WINDOW_H))
        self._legal_cache = (
            self.game.legal_placements() if self.game.state is GameState.PLACE else []
        )
        self._draw_legal_cells()
        self._draw_tiles()
        self._draw_holes()
        self._draw_sidebar(mouse)

    def _color_rgb(self, color_id: int) -> tuple[int, int, int]:
        return hex_to_rgb(self.game.colors[color_id].hex)

    def _draw_legal_cells(self) -> None:
        for placement in self._legal_cache:
            if placement.orientation != self.orientation:
                continue
            rect = self._cell_rect(placement.row, placement.col)
            surf = pygame.Surface(rect.size, pygame.SRCALPHA)
            surf.fill((*HIGHLIGHT, 55))
            self.screen.blit(surf, rect.topleft)
            pygame.draw.rect(self.screen, HIGHLIGHT, rect, width=2, border_radius=6)

    def _draw_tiles(self) -> None:
        cell = self._view()[0]
        flower_r = max(4, int(cell * 0.16))
        for (row, col), placed in self.game.board:
            rect = self._cell_rect(row, col)
            pygame.draw.rect(self.screen, TILE_FILL, rect, border_radius=6)
            pygame.draw.rect(self.screen, TILE_EDGE, rect, width=1, border_radius=6)
            centers = {
                Direction.N: (rect.centerx, rect.top),
                Direction.E: (rect.right, rect.centery),
                Direction.S: (rect.centerx, rect.bottom),
                Direction.W: (rect.left, rect.centery),
            }
            for direction, center in centers.items():
                color = self._color_rgb(placed.edge_color(direction))
                pygame.draw.circle(self.screen, color, center, flower_r)
                pygame.draw.circle(self.screen, BOARD_BG, center, flower_r, width=1)

    def _draw_holes(self) -> None:
        cell = self._view()[0]
        radius = max(6, int(cell * 0.24))
        pending = {b.hole for b in self.game.pending_blooms}
        for (row, col), color in self.game.holes.items():
            rect = self._cell_rect(row, col)
            center = (rect.right, rect.bottom)
            if color is None:
                pygame.draw.circle(self.screen, HOLE_EMPTY, center, radius)
                pygame.draw.circle(self.screen, TILE_EDGE, center, radius, width=2)
            else:
                pygame.draw.circle(self.screen, self._color_rgb(color), center, radius)
                pygame.draw.circle(self.screen, TEXT, center, radius, width=2)
        for row, col in pending:
            rect = self._cell_rect(row, col)
            center = (rect.right, rect.bottom)
            pygame.draw.circle(self.screen, HOLE_EMPTY, center, radius)
            pygame.draw.circle(self.screen, PENDING, center, radius, width=3)

    # ---------------------------------------------------------------- sidebar
    def _draw_sidebar(self, mouse: tuple[int, int]) -> None:
        x = BOARD_W + 20
        y = 20
        self.screen.blit(self.big.render("A Gentle Rain", True, TEXT), (x, y))
        y += 44

        rows = [
            f"State: {self.game.state.name.title()}",
            f"Tiles left: {self.game.deck_remaining}",
            f"Blooms: {self.game.blooms_placed} / {self.game.num_colors}",
            f"Discarded: {len(self.game.discarded)}",
        ]
        for line in rows:
            self.screen.blit(self.font.render(line, True, TEXT), (x, y))
            y += 26
        y += 6

        y = self._draw_available(x, y)
        y = self._draw_hand(x, y)
        y = self._draw_bloom_picker(x, y)
        y = self._draw_result(x, y)

        self._layout_buttons(x)
        for button in self.buttons.values():
            button.draw(self.screen, self.small, mouse)

        if self.message:
            self.screen.blit(self.small.render(self.message, True, PENDING), (x, WINDOW_H - 120))

    def _draw_available(self, x: int, y: int) -> int:
        self.screen.blit(self.small.render("Lily colours (dim = bloomed)", True, MUTED), (x, y))
        y += 22
        available = self.game.available_colors()
        for i, color in enumerate(self.game.colors):
            cx = x + (i % 4) * 62
            cy = y + (i // 4) * 46
            rgb = hex_to_rgb(color.hex)
            if i not in available:
                rgb = tuple(c // 3 for c in rgb)  # type: ignore[assignment]
            pygame.draw.circle(self.screen, rgb, (cx + 12, cy + 12), 12)
            pygame.draw.circle(self.screen, MUTED, (cx + 12, cy + 12), 12, width=1)
            self.screen.blit(self.small.render(color.name[:6], True, MUTED), (cx, cy + 24))
        return y + 2 * 46 + 6

    def _draw_hand(self, x: int, y: int) -> int:
        self.screen.blit(self.small.render("Tile in hand", True, MUTED), (x, y))
        y += 22
        size = 96
        rect = pygame.Rect(x, y, size, size)
        if self.game.current_tile is None:
            pygame.draw.rect(self.screen, TILE_FILL, rect, border_radius=8)
            self.screen.blit(self.small.render("—", True, MUTED), rect.center)
            return y + size + 12
        pygame.draw.rect(self.screen, TILE_FILL, rect, border_radius=8)
        pygame.draw.rect(self.screen, TILE_EDGE, rect, width=1, border_radius=8)
        centers = {
            Direction.N: (rect.centerx, rect.top),
            Direction.E: (rect.right, rect.centery),
            Direction.S: (rect.centerx, rect.bottom),
            Direction.W: (rect.left, rect.centery),
        }
        for direction, center in centers.items():
            color_id = self.game.current_tile.edge_color(direction, self.orientation)
            pygame.draw.circle(self.screen, self._color_rgb(color_id), center, 14)
            pygame.draw.circle(self.screen, BOARD_BG, center, 14, width=1)
        return y + size + 12

    def _draw_bloom_picker(self, x: int, y: int) -> int:
        self._swatch_rects = []
        if self.game.state is not GameState.BLOOM or not self.game.pending_blooms:
            return y
        bloom = self.game.pending_blooms[0]
        options = sorted(bloom.candidate_colors & self.game.available_colors())
        self.screen.blit(self.font.render("Choose a lily colour:", True, PENDING), (x, y))
        y += 30
        for i, color_id in enumerate(options):
            rect = pygame.Rect(x + i * 52, y, 44, 44)
            pygame.draw.rect(self.screen, self._color_rgb(color_id), rect, border_radius=8)
            pygame.draw.rect(self.screen, TEXT, rect, width=2, border_radius=8)
            self._swatch_rects.append((rect, color_id))
        return y + 60

    def _draw_result(self, x: int, y: int) -> int:
        if not self.game.is_over:
            return y
        outcome = "You win!" if self.game.is_won else "Out of tiles"
        color = HIGHLIGHT if self.game.is_won else PENDING
        self.screen.blit(self.big.render(outcome, True, color), (x, y))
        y += 34
        self.screen.blit(self.font.render(f"Score: {self.game.score}", True, TEXT), (x, y))
        return y + 30

    def _layout_buttons(self, x: int) -> None:
        state = self.game.state
        self.buttons["draw"].enabled = state is GameState.DRAW
        self.buttons["rotate"].enabled = state is GameState.PLACE
        self.buttons["discard"].enabled = (
            state is GameState.PLACE and not self.game.has_legal_placement()
        )
        self.buttons["new"].enabled = True
        width = (SIDEBAR_W - 50) // 2
        positions = [
            ("draw", 0, 0),
            ("rotate", 1, 0),
            ("discard", 0, 1),
            ("new", 1, 1),
        ]
        base_y = WINDOW_H - 90
        for name, col, row in positions:
            self.buttons[name].rect = pygame.Rect(
                x + col * (width + 10), base_y + row * 40, width, 32
            )


def run(seed: int | None = None) -> None:
    GameUI(seed=seed).run()
