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

import contextlib
import os
import time

import pygame
from pygame._sdl2 import video as sdl2

from .. import leaderboard
from ..agents import HeuristicAgent
from ..engine import Game, GameState
from ..geometry import Direction
from ..model import Placement

# Layout -----------------------------------------------------------------------
WINDOW_W, WINDOW_H = 1100, 760
SIDEBAR_W = 300
BOARD_W = WINDOW_W - SIDEBAR_W
MIN_CELL, MAX_CELL = 26, 96
# The scene is rendered this many times larger than the window and presented at
# the display's native pixel resolution, which anti-aliases every shape and glyph
# and keeps them crisp on high-DPI (Retina) displays.
SUPERSAMPLE = 2

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
PANEL = (30, 36, 46)
ROW_HIGHLIGHT = (54, 64, 78)


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

    def draw(self, ui: GameUI, mouse: tuple[int, int]) -> None:
        hovered = self.enabled and self.rect.collidepoint(mouse)
        color = BUTTON_HOVER if hovered else BUTTON
        if not self.enabled:
            color = (38, 44, 52)
        ui.draw_rect(color, self.rect, radius=8)
        label = f"{self.label}  ({self.key})"
        ui.draw_text_center(ui.small, label, self.rect.center, TEXT if self.enabled else MUTED)


class GameUI:
    """Interactive pygame front-end wrapping a :class:`Game`."""

    def __init__(
        self, seed: int | None = None, data_path: str | None = None, cheat: bool = False
    ) -> None:
        pygame.init()
        self._init_display()
        self.canvas = pygame.Surface((WINDOW_W * self.s, WINDOW_H * self.s))
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("helvetica,arial", 18 * self.s)
        self.small = pygame.font.SysFont("helvetica,arial", 15 * self.s)
        self.big = pygame.font.SysFont("helvetica,arial", 26 * self.s, bold=True)

        self._seed = seed
        self._data_path = data_path
        self._cheat = cheat
        self._advisor = HeuristicAgent()  # suggests moves for cheat mode (and future hints)
        self.game = Game(seed=seed, data_path=data_path)
        self.orientation = 0
        self.message = ""
        self._legal_cache: list[Placement] = []
        self._mouse: tuple[int, int] = (0, 0)
        self._cursor: int | None = None
        self._timer_start: float | None = None  # set on the first draw
        self._timer_end: float | None = None  # set when the game ends
        self._tileset_id = leaderboard.tileset_id(self.game.colors, self.game.tiles)
        self._leaderboard_open = False
        self._name_entry: str | None = None  # name being typed on game over (None = not entering)
        self._end_handled = False  # whether the game-over prompt has been shown
        self._entries: list[leaderboard.Entry] = []
        self._just_added: leaderboard.Entry | None = None
        self._selected: tuple[int, int] | None = None  # keyboard placement cursor
        self._bloom_index = 0  # keyboard selection among bloom colour swatches

        self.buttons = {
            "draw": Button("Draw tile", "Space", "draw"),
            "rotate": Button("Rotate", "R", "rotate"),
            "discard": Button("Discard", "D", "discard"),
            "new": Button("New Game", "N", "new"),
            "board": Button("Leaderboard", "L", "board"),
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
                    running = self._on_key(event)
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    self._on_click(mouse)
            self._draw(mouse)
            self._present()
            self.clock.tick(60)
        pygame.quit()

    # ---------------------------------------------------------------- actions
    def _new_game(self) -> None:
        self.game = Game(seed=self._seed, data_path=self._data_path)
        self.orientation = 0
        self.message = ""
        self._timer_start = None
        self._timer_end = None
        self._tileset_id = leaderboard.tileset_id(self.game.colors, self.game.tiles)
        self._leaderboard_open = False
        self._name_entry = None
        self._end_handled = False
        self._just_added = None
        self._selected = None
        self._bloom_index = 0

    def _do_draw(self) -> None:
        if self.game.state is not GameState.DRAW:
            return
        self.game.draw()
        if self._timer_start is None:
            self._timer_start = time.perf_counter()
        self.orientation = 0
        self._init_cursor()
        self._apply_cheat_placement()
        if self.game.state is GameState.PLACE and not self.game.has_legal_placement():
            self.message = "No legal placement — discard this tile."
        else:
            self.message = ""

    def _apply_cheat_placement(self) -> None:
        if not self._cheat or self.game.state is not GameState.PLACE:
            return
        placements = self.game.legal_placements()
        if not placements:
            return
        rec = self._advisor.choose_placement(self.game, placements)
        self.orientation = rec.orientation
        self._selected = (rec.row, rec.col)

    def _apply_cheat_bloom(self) -> None:
        if not self._cheat:
            return
        options = self._bloom_options()
        if not options:
            return
        rec = self._advisor.choose_bloom_color(self.game, set(options))
        if rec in options:
            self._bloom_index = options.index(rec)

    def _do_discard(self) -> None:
        if self.game.state is GameState.PLACE and not self.game.has_legal_placement():
            self.game.discard()
            self.message = "Tile discarded."
            self._selected = None

    def _rotate(self) -> None:
        if self.game.state is GameState.PLACE:
            self.orientation = (self.orientation + 1) % 4
            self._resnap_cursor()

    def _try_place(self, cell: tuple[int, int]) -> None:
        if self.game.state is not GameState.PLACE or self.game.current_tile is None:
            return
        placement = Placement(cell[0], cell[1], self.orientation)
        if placement in self._legal_cache:
            self.game.place(placement)
            self.message = ""
            self._selected = None
            self._bloom_index = 0
            self._apply_cheat_bloom()

    # ------------------------------------------------------------ keyboard cursor
    def _board_center(self) -> tuple[int, int]:
        coords = self.game.board.occupied_coords()
        if not coords:
            return (0, 0)
        rows = [r for r, _ in coords]
        cols = [c for _, c in coords]
        return (round(sum(rows) / len(rows)), round(sum(cols) / len(cols)))

    @staticmethod
    def _nearest_cell(cells: set[tuple[int, int]], target: tuple[int, int]) -> tuple[int, int]:
        return min(cells, key=lambda c: (abs(c[0] - target[0]) + abs(c[1] - target[1]), c))

    def _legal_cells(self) -> set[tuple[int, int]]:
        return {
            (p.row, p.col)
            for p in self.game.legal_placements()
            if p.orientation == self.orientation
        }

    def _init_cursor(self) -> None:
        if self.game.state is not GameState.PLACE:
            self._selected = None
            return
        placements = self.game.legal_placements()
        if not placements:
            self._selected = None
            return
        orientations = {p.orientation for p in placements}
        if self.orientation not in orientations:
            self.orientation = min(orientations)  # auto-advance to a playable rotation
        cells = {(p.row, p.col) for p in placements if p.orientation == self.orientation}
        self._selected = self._nearest_cell(cells, self._board_center())

    def _resnap_cursor(self) -> None:
        cells = self._legal_cells()
        if not cells:
            self._selected = None
            return
        if self._selected in cells:
            return
        target = self._selected if self._selected is not None else self._board_center()
        self._selected = self._nearest_cell(cells, target)

    def _move_cursor(self, key: int) -> None:
        cells = self._legal_cells()
        if not cells:
            return
        if self._selected not in cells:
            self._selected = self._nearest_cell(cells, self._board_center())
            return
        dr, dc = {
            pygame.K_UP: (-1, 0),
            pygame.K_DOWN: (1, 0),
            pygame.K_LEFT: (0, -1),
            pygame.K_RIGHT: (0, 1),
        }[key]
        cur = self._selected
        best: tuple[int, int] | None = None
        best_score: tuple[int, int] | None = None
        for cell in cells:
            ddr, ddc = cell[0] - cur[0], cell[1] - cur[1]
            if dr:  # vertical move: target must be further along dr
                if (dr > 0 and ddr <= 0) or (dr < 0 and ddr >= 0):
                    continue
                score = (abs(ddr), abs(ddc))
            else:  # horizontal move
                if (dc > 0 and ddc <= 0) or (dc < 0 and ddc >= 0):
                    continue
                score = (abs(ddc), abs(ddr))
            if best_score is None or score < best_score:
                best_score, best = score, cell
        if best is not None:
            self._selected = best

    def _place_selected(self) -> None:
        if self.game.state is not GameState.PLACE or self._selected is None:
            return
        placement = Placement(self._selected[0], self._selected[1], self.orientation)
        if placement in self.game.legal_placements():
            self.game.place(placement)
            self.message = ""
            self._selected = None
            self._bloom_index = 0
            self._apply_cheat_bloom()

    def _bloom_options(self) -> list[int]:
        if self.game.state is not GameState.BLOOM or not self.game.pending_blooms:
            return []
        bloom = self.game.pending_blooms[0]
        return sorted(bloom.candidate_colors & self.game.available_colors())

    def _pick_color(self, color_id: int) -> None:
        if self.game.state is not GameState.BLOOM:
            return
        bloom = self.game.pending_blooms[0]
        options = bloom.candidate_colors & self.game.available_colors()
        if color_id in options:
            self.game.resolve_bloom(bloom.hole, color_id)
            self._bloom_index = 0
            self._apply_cheat_bloom()

    def _on_key(self, event: pygame.event.Event) -> bool:
        if self._name_entry is not None:
            return self._handle_name_key(event)
        key = event.key
        if self._leaderboard_open:
            if key in (pygame.K_l, pygame.K_ESCAPE):
                self._leaderboard_open = False
            return True
        if key == pygame.K_ESCAPE:
            return False
        if key == pygame.K_n:
            self._new_game()
            return True
        if key == pygame.K_l:
            self._open_leaderboard()
            return True

        state = self.game.state
        if state is GameState.DRAW:
            if key == pygame.K_SPACE:
                self._do_draw()
        elif state is GameState.PLACE:
            self._on_place_key(key)
        elif state is GameState.BLOOM:
            self._on_bloom_key(key)
        return True

    _CONFIRM_KEYS = (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE)
    _ARROW_KEYS = (pygame.K_UP, pygame.K_DOWN, pygame.K_LEFT, pygame.K_RIGHT)

    def _on_place_key(self, key: int) -> None:
        if key == pygame.K_r:
            self._rotate()
        elif key == pygame.K_d:
            self._do_discard()
        elif key in self._CONFIRM_KEYS:
            self._place_selected()
        elif key in self._ARROW_KEYS:
            self._move_cursor(key)

    def _on_bloom_key(self, key: int) -> None:
        options = self._bloom_options()
        if not options:
            return
        self._bloom_index %= len(options)
        if key in (pygame.K_LEFT, pygame.K_UP):
            self._bloom_index = (self._bloom_index - 1) % len(options)
        elif key in (pygame.K_RIGHT, pygame.K_DOWN):
            self._bloom_index = (self._bloom_index + 1) % len(options)
        elif key in self._CONFIRM_KEYS:
            self._pick_color(options[self._bloom_index])
        elif pygame.K_1 <= key <= pygame.K_9:
            index = key - pygame.K_1
            if index < len(options):
                self._pick_color(options[index])

    def _handle_name_key(self, event: pygame.event.Event) -> bool:
        assert self._name_entry is not None
        if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            self._commit_name()
        elif event.key == pygame.K_ESCAPE:
            self._name_entry = None  # skip saving; show the board read-only
            self._leaderboard_open = True
        elif event.key == pygame.K_BACKSPACE:
            self._name_entry = self._name_entry[:-1]
        elif event.unicode and event.unicode.isprintable() and len(self._name_entry) < 20:
            self._name_entry += event.unicode
        return True

    def _open_leaderboard(self) -> None:
        self._entries = leaderboard.load(self._tileset_id)
        self._leaderboard_open = True

    def _commit_name(self) -> None:
        name = (self._name_entry or "").strip()
        if name:
            self._just_added = leaderboard.make_entry(
                name, self.game.score, self._elapsed_seconds(), self.game.is_won
            )
            self._entries = leaderboard.add(self._tileset_id, self._just_added)
        else:
            self._entries = leaderboard.load(self._tileset_id)
        self._name_entry = None
        self._leaderboard_open = True

    def _on_click(self, mouse: tuple[int, int]) -> None:
        if self._name_entry is not None:
            return  # name entry is keyboard-only
        if self._leaderboard_open:
            self._leaderboard_open = False  # click anywhere to close the board
            return
        for name, button in self.buttons.items():
            if button.enabled and button.rect.collidepoint(mouse):
                {
                    "draw": self._do_draw,
                    "rotate": self._rotate,
                    "discard": self._do_discard,
                    "new": self._new_game,
                    "board": self._open_leaderboard,
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
        self._mouse = mouse
        if self._timer_start is not None and self._timer_end is None and self.game.is_over:
            self._timer_end = time.perf_counter()
        if self.game.is_over and not self._end_handled:
            self._end_handled = True
            self._entries = leaderboard.load(self._tileset_id)
            if self._cheat:
                self._leaderboard_open = True  # cheat games can't be saved
            else:
                self._name_entry = ""  # prompt for a name to save
        self.canvas.fill(BG)
        self.draw_rect(BOARD_BG, (0, 0, BOARD_W, WINDOW_H))
        self._legal_cache = (
            self.game.legal_placements() if self.game.state is GameState.PLACE else []
        )
        self._draw_legal_cells()
        self._draw_tiles()
        self._draw_holes()
        self._draw_sidebar(mouse)
        if self._name_entry is not None or self._leaderboard_open:
            self._draw_leaderboard_overlay()
        self._update_cursor(mouse)

    def _update_cursor(self, mouse: tuple[int, int]) -> None:
        cursor = (
            pygame.SYSTEM_CURSOR_HAND if self._is_clickable(mouse) else pygame.SYSTEM_CURSOR_ARROW
        )
        if cursor != self._cursor:
            self._cursor = cursor
            # Some platforms/headless drivers cannot create system cursors.
            with contextlib.suppress(pygame.error):
                pygame.mouse.set_cursor(cursor)

    def _is_clickable(self, mouse: tuple[int, int]) -> bool:
        if any(b.enabled and b.rect.collidepoint(mouse) for b in self.buttons.values()):
            return True
        if any(rect.collidepoint(mouse) for rect, _ in self._swatch_rects):
            return True
        return self._hovered_placement(mouse) is not None

    def _hovered_placement(self, mouse: tuple[int, int]) -> Placement | None:
        """The legal placement under the mouse at the current orientation, if any."""
        if self.game.state is not GameState.PLACE or mouse[0] >= BOARD_W:
            return None
        row, col = self._pixel_to_cell(mouse)
        target = Placement(row, col, self.orientation)
        return target if target in self._legal_cache else None

    def _color_rgb(self, color_id: int) -> tuple[int, int, int]:
        return hex_to_rgb(self.game.colors[color_id].hex)

    def _elapsed_seconds(self) -> float:
        if self._timer_start is None:
            return 0.0
        end = self._timer_end if self._timer_end is not None else time.perf_counter()
        return end - self._timer_start

    @staticmethod
    def _format_time(seconds: float) -> str:
        minutes = int(seconds // 60)
        return f"{minutes:d}:{seconds - minutes * 60:04.1f}"

    # --------------------------------------------------------- display / present
    def _init_display(self) -> None:
        # Render at the display's native pixel resolution and present through an
        # accelerated renderer, so the image is crisp on high-DPI (Retina)
        # screens instead of being upscaled by the OS.
        os.environ.setdefault("SDL_RENDER_SCALE_QUALITY", "best")
        try:
            self.window = sdl2.Window(
                "A Gentle Rain", size=(WINDOW_W, WINDOW_H), allow_highdpi=True
            )
            self.renderer = sdl2.Renderer(self.window, vsync=True)
            native_w = self.renderer.get_viewport().width
            self.s = max(SUPERSAMPLE, round(native_w / WINDOW_W))
            self.use_renderer = True
            self.screen = None
        except Exception:
            # Fall back to a classic scaled display surface if no renderer is available.
            self.window = None
            self.renderer = None
            self.use_renderer = False
            self.s = SUPERSAMPLE
            pygame.display.set_caption("A Gentle Rain")
            try:
                self.screen = pygame.display.set_mode((WINDOW_W, WINDOW_H), pygame.SCALED, vsync=1)
            except pygame.error:
                self.screen = pygame.display.set_mode((WINDOW_W, WINDOW_H))

    def _present(self) -> None:
        if self.use_renderer:
            texture = sdl2.Texture.from_surface(self.renderer, self.canvas)
            self.renderer.clear()
            texture.draw()
            self.renderer.present()
        else:
            pygame.transform.smoothscale(self.canvas, (WINDOW_W, WINDOW_H), self.screen)
            pygame.display.flip()

    # ------------------------------------------------------------ draw helpers
    # These take logical coordinates and render onto the supersampled canvas.
    def _scaled_rect(self, rect) -> pygame.Rect:
        s = self.s
        return pygame.Rect(rect[0] * s, rect[1] * s, rect[2] * s, rect[3] * s)

    def draw_rect(self, color, rect, width: int = 0, radius: int = 0) -> None:
        pygame.draw.rect(
            self.canvas,
            color,
            self._scaled_rect(rect),
            width * self.s,
            border_radius=radius * self.s,
        )

    def draw_circle(self, color, center, radius: int, width: int = 0) -> None:
        s = self.s
        pygame.draw.circle(
            self.canvas, color, (center[0] * s, center[1] * s), radius * s, width * s
        )

    def draw_alpha_rect(self, rgba, rect, radius: int = 0) -> None:
        r = self._scaled_rect(rect)
        surf = pygame.Surface(r.size, pygame.SRCALPHA)
        if radius:
            pygame.draw.rect(surf, rgba, surf.get_rect(), border_radius=radius * self.s)
        else:
            surf.fill(rgba)
        self.canvas.blit(surf, r.topleft)

    def draw_text(self, font: pygame.font.Font, text: str, topleft, color) -> None:
        s = self.s
        self.canvas.blit(font.render(text, True, color), (topleft[0] * s, topleft[1] * s))

    def draw_text_center(self, font: pygame.font.Font, text: str, center, color) -> None:
        s = self.s
        surf = font.render(text, True, color)
        self.canvas.blit(surf, surf.get_rect(center=(center[0] * s, center[1] * s)))

    def _draw_legal_cells(self) -> None:
        hovered = self._hovered_placement(self._mouse)
        for placement in self._legal_cache:
            if placement.orientation != self.orientation:
                continue
            rect = self._cell_rect(placement.row, placement.col)
            cell = (placement.row, placement.col)
            is_hover = hovered is not None and cell == (hovered.row, hovered.col)
            is_selected = cell == self._selected
            active = is_hover or is_selected
            self.draw_alpha_rect((*HIGHLIGHT, 110 if active else 55), rect, radius=6)
            self.draw_rect(HIGHLIGHT, rect, width=3 if active else 2, radius=6)
        if self._selected is not None and self.game.current_tile is not None:
            self._draw_tile_preview(self._selected)

    def _draw_tile_preview(self, cell: tuple[int, int]) -> None:
        rect = self._cell_rect(cell[0], cell[1])
        self.draw_rect(TILE_FILL, rect, radius=6)
        self.draw_rect(HIGHLIGHT, rect, width=3, radius=6)
        flower_r = max(4, int(self._view()[0] * 0.16))
        centers = {
            Direction.N: (rect.centerx, rect.top),
            Direction.E: (rect.right, rect.centery),
            Direction.S: (rect.centerx, rect.bottom),
            Direction.W: (rect.left, rect.centery),
        }
        for direction, center in centers.items():
            color_id = self.game.current_tile.edge_color(direction, self.orientation)
            self.draw_circle(self._color_rgb(color_id), center, flower_r)
            self.draw_circle(BOARD_BG, center, flower_r, width=1)

    def _draw_tiles(self) -> None:
        cell = self._view()[0]
        flower_r = max(4, int(cell * 0.16))
        for (row, col), placed in self.game.board:
            rect = self._cell_rect(row, col)
            self.draw_rect(TILE_FILL, rect, radius=6)
            self.draw_rect(TILE_EDGE, rect, width=1, radius=6)
            centers = {
                Direction.N: (rect.centerx, rect.top),
                Direction.E: (rect.right, rect.centery),
                Direction.S: (rect.centerx, rect.bottom),
                Direction.W: (rect.left, rect.centery),
            }
            for direction, center in centers.items():
                color = self._color_rgb(placed.edge_color(direction))
                self.draw_circle(color, center, flower_r)
                self.draw_circle(BOARD_BG, center, flower_r, width=1)

    def _draw_holes(self) -> None:
        cell = self._view()[0]
        radius = max(6, int(cell * 0.24))
        pending = {b.hole for b in self.game.pending_blooms}
        for (row, col), color in self.game.holes.items():
            rect = self._cell_rect(row, col)
            center = (rect.right, rect.bottom)
            if color is None:
                self.draw_circle(HOLE_EMPTY, center, radius)
                self.draw_circle(TILE_EDGE, center, radius, width=2)
            else:
                self.draw_circle(self._color_rgb(color), center, radius)
                self.draw_circle(TEXT, center, radius, width=2)
        for row, col in pending:
            rect = self._cell_rect(row, col)
            center = (rect.right, rect.bottom)
            self.draw_circle(HOLE_EMPTY, center, radius)
            self.draw_circle(PENDING, center, radius, width=3)

    # ---------------------------------------------------------------- sidebar
    def _draw_sidebar(self, mouse: tuple[int, int]) -> None:
        x = BOARD_W + 20
        y = 20
        self.draw_text(self.big, "A Gentle Rain", (x, y), TEXT)
        y += 44

        rows = [
            f"State: {self.game.state.name.title()}",
            f"Tiles left: {self.game.deck_remaining}",
            f"Blooms: {self.game.blooms_placed} / {self.game.num_colors}",
            f"Discarded: {len(self.game.discarded)}",
            f"Time: {self._format_time(self._elapsed_seconds())}",
        ]
        for line in rows:
            self.draw_text(self.font, line, (x, y), TEXT)
            y += 26
        y += 6

        y = self._draw_available(x, y)
        y = self._draw_hand(x, y)
        y = self._draw_bloom_picker(x, y)
        y = self._draw_result(x, y)

        self._layout_buttons(x)
        for button in self.buttons.values():
            button.draw(self, mouse)

        if self.message:
            self.draw_text(self.small, self.message, (x, WINDOW_H - 158), PENDING)

    def _draw_available(self, x: int, y: int) -> int:
        self.draw_text(self.small, "Lily colours (dim = bloomed)", (x, y), MUTED)
        y += 22
        available = self.game.available_colors()
        for i, color in enumerate(self.game.colors):
            cx = x + (i % 4) * 62
            cy = y + (i // 4) * 46
            rgb = hex_to_rgb(color.hex)
            if i not in available:
                rgb = tuple(c // 3 for c in rgb)  # type: ignore[assignment]
            self.draw_circle(rgb, (cx + 12, cy + 12), 12)
            self.draw_circle(MUTED, (cx + 12, cy + 12), 12, width=1)
            self.draw_text(self.small, color.name[:6], (cx, cy + 24), MUTED)
        return y + 2 * 46 + 6

    def _draw_hand(self, x: int, y: int) -> int:
        self.draw_text(self.small, "Tile in hand", (x, y), MUTED)
        y += 22
        size = 96
        rect = pygame.Rect(x, y, size, size)
        if self.game.current_tile is None:
            self.draw_rect(TILE_FILL, rect, radius=8)
            self.draw_text_center(self.small, "—", rect.center, MUTED)
            return y + size + 12
        self.draw_rect(TILE_FILL, rect, radius=8)
        self.draw_rect(TILE_EDGE, rect, width=1, radius=8)
        centers = {
            Direction.N: (rect.centerx, rect.top),
            Direction.E: (rect.right, rect.centery),
            Direction.S: (rect.centerx, rect.bottom),
            Direction.W: (rect.left, rect.centery),
        }
        for direction, center in centers.items():
            color_id = self.game.current_tile.edge_color(direction, self.orientation)
            self.draw_circle(self._color_rgb(color_id), center, 14)
            self.draw_circle(BOARD_BG, center, 14, width=1)
        return y + size + 12

    def _draw_bloom_picker(self, x: int, y: int) -> int:
        self._swatch_rects = []
        if self.game.state is not GameState.BLOOM or not self.game.pending_blooms:
            return y
        bloom = self.game.pending_blooms[0]
        options = sorted(bloom.candidate_colors & self.game.available_colors())
        if options:
            self._bloom_index %= len(options)
        self.draw_text(self.font, "Choose a lily colour (\u2190/\u2192, Enter):", (x, y), PENDING)
        y += 30
        for i, color_id in enumerate(options):
            rect = pygame.Rect(x + i * 52, y, 44, 44)
            self.draw_rect(self._color_rgb(color_id), rect, radius=8)
            selected = i == self._bloom_index
            self.draw_rect(
                HIGHLIGHT if selected else TEXT, rect, width=4 if selected else 2, radius=8
            )
            self._swatch_rects.append((rect, color_id))
        return y + 60

    def _draw_result(self, x: int, y: int) -> int:
        if not self.game.is_over:
            return y
        outcome = "You win!" if self.game.is_won else "Out of tiles"
        color = HIGHLIGHT if self.game.is_won else PENDING
        self.draw_text(self.big, outcome, (x, y), color)
        y += 34
        self.draw_text(self.font, f"Score: {self.game.score}", (x, y), TEXT)
        return y + 30

    def _layout_buttons(self, x: int) -> None:
        state = self.game.state
        self.buttons["draw"].enabled = state is GameState.DRAW
        self.buttons["rotate"].enabled = state is GameState.PLACE
        self.buttons["discard"].enabled = (
            state is GameState.PLACE and not self.game.has_legal_placement()
        )
        self.buttons["new"].enabled = True
        self.buttons["board"].enabled = True
        width = (SIDEBAR_W - 50) // 2
        positions = [
            ("draw", 0, 0),
            ("rotate", 1, 0),
            ("discard", 0, 1),
            ("new", 1, 1),
        ]
        base_y = WINDOW_H - 132
        for name, col, row in positions:
            self.buttons[name].rect = pygame.Rect(
                x + col * (width + 10), base_y + row * 40, width, 32
            )
        self.buttons["board"].rect = pygame.Rect(x, base_y + 2 * 40, SIDEBAR_W - 40, 32)

    def _draw_leaderboard_overlay(self) -> None:
        self.draw_alpha_rect((0, 0, 0, 190), (0, 0, WINDOW_W, WINDOW_H))
        pw, ph = 660, 540
        px = (WINDOW_W - pw) // 2
        py = (WINDOW_H - ph) // 2
        self.draw_rect(PANEL, (px, py, pw, ph), radius=14)
        self.draw_rect(TILE_EDGE, (px, py, pw, ph), width=2, radius=14)
        x = px + 30
        y = py + 26

        if self._name_entry is not None:
            outcome = "You win!" if self.game.is_won else "Out of tiles"
            colour = HIGHLIGHT if self.game.is_won else PENDING
            self.draw_text(self.big, outcome, (x, y), colour)
            y += 40
            summary = (
                f"Score {self.game.score}    Time {self._format_time(self._elapsed_seconds())}"
            )
            self.draw_text(self.font, summary, (x, y), TEXT)
            y += 34
            self.draw_text(
                self.small,
                "Type your name to save it (leave blank to skip), then Enter:",
                (x, y),
                MUTED,
            )
            y += 26
            box = pygame.Rect(x, y, pw - 60, 34)
            self.draw_rect(BG, box, radius=6)
            self.draw_rect(HIGHLIGHT, box, width=2, radius=6)
            self.draw_text(self.font, self._name_entry + "_", (x + 8, y + 6), TEXT)
            y += 52
        else:
            self.draw_text(self.big, "Leaderboard", (x, y), TEXT)
            self.draw_text(self.small, "L / Esc / click to close", (x + pw - 220, y + 10), MUTED)
            y += 44

        self.draw_text(self.small, "#", (x, y), MUTED)
        self.draw_text(self.small, "Name", (x + 46, y), MUTED)
        self.draw_text(self.small, "Score", (x + pw - 210, y), MUTED)
        self.draw_text(self.small, "Time", (x + pw - 110, y), MUTED)
        y += 24

        entries = self._entries[:12]
        if not entries:
            self.draw_text(self.font, "No scores yet — be the first!", (x, y + 8), MUTED)
            return
        for i, entry in enumerate(entries):
            if self._just_added is not None and entry == self._just_added:
                self.draw_rect(ROW_HIGHLIGHT, (px + 16, y - 2, pw - 32, 26), radius=4)
            self.draw_text(self.font, str(i + 1), (x, y), TEXT)
            self.draw_text(self.font, entry.name[:16], (x + 46, y), TEXT)
            self.draw_text(self.font, str(entry.score), (x + pw - 210, y), TEXT)
            self.draw_text(self.font, self._format_time(entry.time), (x + pw - 110, y), TEXT)
            y += 28


def run(seed: int | None = None, data_path: str | None = None, cheat: bool = False) -> None:
    GameUI(seed=seed, data_path=data_path, cheat=cheat).run()
