"""A pygame tile editor for *A Gentle Rain*.

Lets you author the tile set without hand-editing JSON:

* **Define colours** — add, remove, rename and set the hex of each flower colour.
* **Paint tiles** — click an edge of the shown tile to set its colour.
* **Add / remove tiles** — build up the full deck.

The result is written back to the compact ``tiles.json`` used by the game. Note
that agents can also build tile sets purely in code via
:mod:`agentle_rain.tilesets`; this editor is just for humans.

Run with ``python -m agentle_rain --edit`` or ``agentle-rain-editor``.
"""

from __future__ import annotations

import argparse
import contextlib
from pathlib import Path

import pygame

from ..data_loader import default_data_path, read_raw, write_tiles_file
from ..tilesets import DEFAULT_PALETTE
from .pygame_ui import hex_to_rgb

WINDOW_W, WINDOW_H = 1060, 700
EDGE_NAMES = ("N", "E", "S", "W")

BG = (24, 28, 36)
PANEL = (32, 38, 48)
TILE_FILL = (44, 54, 64)
TILE_EDGE = (70, 84, 96)
TEXT = (226, 230, 236)
MUTED = (140, 150, 162)
ACCENT = (90, 200, 140)
WARN = (240, 200, 90)
ERROR = (230, 100, 100)
BUTTON = (54, 64, 78)
BUTTON_HOVER = (74, 88, 106)


def _normalize_hex(value: str) -> str | None:
    """Return a canonical ``#rrggbb`` string, or None if ``value`` is not valid."""
    text = value.strip().lstrip("#")
    if len(text) == 3:
        text = "".join(ch * 2 for ch in text)
    if len(text) == 6 and all(c in "0123456789abcdefABCDEF" for c in text):
        return "#" + text.lower()
    return None


def _initial_data(path: Path) -> tuple[list[dict], list[list[int]], str]:
    """Load ``path``, or seed a new set (default palette + one blank tile) if missing."""
    if path.exists():
        colors, tiles = read_raw(path)
        message = f"Loaded {len(tiles)} tiles, {len(colors)} colours."
    else:
        colors = [{"name": name, "hex": hex_} for name, hex_ in DEFAULT_PALETTE]
        tiles = [[0, 0, 0, 0]]
        message = f"New file — press S to create {path}"
    if not colors:
        colors = [{"name": "colour0", "hex": "#cccccc"}]
    if not tiles:
        tiles = [[0, 0, 0, 0]]
    return colors, tiles, message


class TileEditor:
    """Interactive editor over a colour palette and a list of tiles."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.colors, self.tiles, self.message = _initial_data(path)

        self.tile_index = 0
        self.active_color = 0
        self.text_edit: dict | None = None  # {"field": "name"|"hex", "buffer": str}

        pygame.init()
        pygame.display.set_caption("A Gentle Rain — Tile Editor")
        self.screen = pygame.display.set_mode((WINDOW_W, WINDOW_H))
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("helvetica,arial", 18)
        self.small = pygame.font.SysFont("helvetica,arial", 15)
        self.big = pygame.font.SysFont("helvetica,arial", 26, bold=True)

        self.tile_rect = pygame.Rect(60, 120, 360, 360)
        self.buttons = self._make_buttons()
        self._palette_rects: list[pygame.Rect] = []
        self._cursor: int | None = None

    # --------------------------------------------------------------- buttons
    def _make_buttons(self) -> list[dict]:
        def btn(label, x, y, w, action, key=None):
            return {"label": label, "rect": pygame.Rect(x, y, w, 34), "action": action, "key": key}

        return [
            btn("< Prev", 60, 520, 110, self._prev_tile, "left"),
            btn("Next >", 180, 520, 110, self._next_tile, "right"),
            btn("Add tile (A)", 300, 520, 130, self._add_tile, "a"),
            btn("Del tile (D)", 60, 562, 130, self._del_tile, "d"),
            btn("Add colour (C)", 560, 520, 150, self._add_color, "c"),
            btn("Del colour (X)", 720, 520, 150, self._del_color, "x"),
            btn("Rename (N)", 560, 562, 150, self._rename_color, "n"),
            btn("Edit hex (H)", 720, 562, 150, self._edit_hex, "h"),
            btn("SAVE (S)", 890, 640, 150, self._save, "s"),
        ]

    # ----------------------------------------------------------------- loop
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
            pygame.display.flip()
            self.clock.tick(60)
        pygame.quit()

    # --------------------------------------------------------------- actions
    @property
    def tile(self) -> list[int]:
        return self.tiles[self.tile_index]

    def _prev_tile(self) -> None:
        self.tile_index = (self.tile_index - 1) % len(self.tiles)

    def _next_tile(self) -> None:
        self.tile_index = (self.tile_index + 1) % len(self.tiles)

    def _add_tile(self) -> None:
        self.tiles.insert(self.tile_index + 1, [0, 0, 0, 0])
        self.tile_index += 1
        self.message = f"Added tile ({len(self.tiles)} total)."

    def _del_tile(self) -> None:
        if len(self.tiles) <= 1:
            self.message = "Cannot delete the last tile."
            return
        del self.tiles[self.tile_index]
        self.tile_index = min(self.tile_index, len(self.tiles) - 1)
        self.message = f"Deleted tile ({len(self.tiles)} left)."

    def _add_color(self) -> None:
        self.colors.append({"name": f"colour{len(self.colors)}", "hex": "#cccccc"})
        self.active_color = len(self.colors) - 1
        self.message = "Added colour — use Rename / Edit hex to set it."

    def _del_color(self) -> None:
        if len(self.colors) <= 1:
            self.message = "Cannot delete the last colour."
            return
        removed = self.active_color
        del self.colors[removed]
        for edges in self.tiles:
            for e in range(4):
                if edges[e] == removed:
                    edges[e] = 0
                elif edges[e] > removed:
                    edges[e] -= 1
        self.active_color = min(removed, len(self.colors) - 1)
        self.message = "Deleted colour and remapped affected edges."

    def _rename_color(self) -> None:
        self.text_edit = {"field": "name", "buffer": self.colors[self.active_color]["name"]}

    def _edit_hex(self) -> None:
        self.text_edit = {"field": "hex", "buffer": self.colors[self.active_color]["hex"]}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        write_tiles_file(self.path, self.colors, self.tiles)
        ok, why = self._validity()
        note = "" if ok else f"  (note: {why})"
        self.message = f"Saved to {self.path}{note}"

    # ------------------------------------------------------------ text input
    def _commit_text(self) -> None:
        assert self.text_edit is not None
        field, buffer = self.text_edit["field"], self.text_edit["buffer"]
        if field == "name":
            if buffer.strip():
                self.colors[self.active_color]["name"] = buffer.strip()
            self.text_edit = None
        else:
            normalized = _normalize_hex(buffer)
            if normalized is None:
                self.message = "Invalid hex — use e.g. #3f6fd0. Press Esc to cancel."
                return
            self.colors[self.active_color]["hex"] = normalized
            self.text_edit = None

    def _on_key(self, event: pygame.event.Event) -> bool:
        if self.text_edit is not None:
            if event.key == pygame.K_ESCAPE:
                self.text_edit = None
            elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self._commit_text()
            elif event.key == pygame.K_BACKSPACE:
                self.text_edit["buffer"] = self.text_edit["buffer"][:-1]
            elif event.unicode and event.unicode.isprintable():
                self.text_edit["buffer"] += event.unicode
            return True

        if event.key == pygame.K_ESCAPE:
            return False
        if pygame.K_0 <= event.key <= pygame.K_9:
            index = event.key - pygame.K_0  # number keys match the shown colour ids
            if index < len(self.colors):
                self.active_color = index
            return True
        keyname = pygame.key.name(event.key)
        for button in self.buttons:
            if button["key"] == keyname:
                button["action"]()
                break
        return True

    def _on_click(self, mouse: tuple[int, int]) -> None:
        if self.text_edit is not None:
            return
        for button in self.buttons:
            if button["rect"].collidepoint(mouse):
                button["action"]()
                return
        for i, rect in enumerate(self._palette_rects):
            if rect.collidepoint(mouse):
                self.active_color = i
                return
        edge = self._edge_at(mouse)
        if edge is not None:
            self.tile[edge] = self.active_color
            self.message = (
                f"Set {EDGE_NAMES[edge]} edge to '{self.colors[self.active_color]['name']}'."
            )

    def _edge_at(self, pos: tuple[int, int]) -> int | None:
        if not self.tile_rect.collidepoint(pos):
            return None
        dx = pos[0] - self.tile_rect.centerx
        dy = pos[1] - self.tile_rect.centery
        if abs(dx) > abs(dy):
            return 1 if dx > 0 else 3  # E or W
        return 2 if dy > 0 else 0  # S or N

    # --------------------------------------------------------------- cursor
    def _update_cursor(self, mouse: tuple[int, int]) -> None:
        cursor = (
            pygame.SYSTEM_CURSOR_HAND if self._is_clickable(mouse) else pygame.SYSTEM_CURSOR_ARROW
        )
        if cursor != self._cursor:
            self._cursor = cursor
            with contextlib.suppress(pygame.error):
                pygame.mouse.set_cursor(cursor)

    def _is_clickable(self, mouse: tuple[int, int]) -> bool:
        if self.text_edit is not None:
            return False
        if any(b["rect"].collidepoint(mouse) for b in self.buttons):
            return True
        if any(rect.collidepoint(mouse) for rect in self._palette_rects):
            return True
        return self._edge_at(mouse) is not None

    # ------------------------------------------------------------- validity
    def _validity(self) -> tuple[bool, str]:
        n = len(self.colors)
        for i, edges in enumerate(self.tiles):
            for e in edges:
                if not (0 <= e < n):
                    return False, f"tile {i + 1} references missing colour {e}"
        if n == 8 and len(self.tiles) == 28:
            return True, "ready for play (retail 8/28)"
        return True, f"playable \u2014 {n} colours, {len(self.tiles)} tiles"

    # --------------------------------------------------------------- drawing
    def _color_rgb(self, color_id: int) -> tuple[int, int, int]:
        if 0 <= color_id < len(self.colors):
            return hex_to_rgb(self.colors[color_id]["hex"])
        return ERROR

    def _draw(self, mouse: tuple[int, int]) -> None:
        self.screen.fill(BG)
        self._draw_tile(mouse)
        self._draw_palette(mouse)
        self._draw_buttons(mouse)
        self._draw_footer()
        self._update_cursor(mouse)
        if self.text_edit is not None:
            self._draw_text_modal()

    def _draw_tile(self, mouse: tuple[int, int]) -> None:
        self.screen.blit(
            self.big.render(f"Tile {self.tile_index + 1} / {len(self.tiles)}", True, TEXT),
            (60, 70),
        )
        pygame.draw.rect(self.screen, TILE_FILL, self.tile_rect, border_radius=12)
        pygame.draw.rect(self.screen, TILE_EDGE, self.tile_rect, width=2, border_radius=12)

        r = self.tile_rect
        off = 46
        centers = {
            0: (r.centerx, r.top + off),
            1: (r.right - off, r.centery),
            2: (r.centerx, r.bottom - off),
            3: (r.left + off, r.centery),
        }
        hover = self._edge_at(mouse)
        for edge, center in centers.items():
            pygame.draw.circle(self.screen, self._color_rgb(self.tile[edge]), center, 34)
            ring = ACCENT if edge == hover else TILE_EDGE
            pygame.draw.circle(self.screen, ring, center, 34, width=3 if edge == hover else 1)
            self.screen.blit(
                self.small.render(EDGE_NAMES[edge], True, MUTED), (center[0] - 5, center[1] - 8)
            )

        active = self.colors[self.active_color]
        label = "Click an edge to paint it with:"
        self.screen.blit(self.small.render(label, True, MUTED), (60, 500))
        dot_x = 60 + self.small.size(label)[0] + 16
        pygame.draw.circle(self.screen, self._color_rgb(self.active_color), (dot_x, 507), 9)
        self.screen.blit(self.small.render(active["name"], True, TEXT), (dot_x + 16, 500))

    def _draw_palette(self, mouse: tuple[int, int]) -> None:
        x, y = 560, 70
        pygame.draw.rect(self.screen, PANEL, (x - 12, y - 12, 480, 420), border_radius=10)
        self.screen.blit(
            self.font.render("Colours (click, or press its number)", True, TEXT), (x, y)
        )
        y += 34
        self._palette_rects = []
        for i, color in enumerate(self.colors):
            rect = pygame.Rect(x, y, 456, 34)
            self._palette_rects.append(rect)
            if i == self.active_color:
                pygame.draw.rect(self.screen, BUTTON_HOVER, rect, border_radius=6)
            pygame.draw.rect(
                self.screen, self._color_rgb(i), (x + 6, y + 5, 24, 24), border_radius=4
            )
            pygame.draw.rect(self.screen, MUTED, (x + 6, y + 5, 24, 24), width=1, border_radius=4)
            label = f"{i}:  {color['name']}"
            self.screen.blit(self.font.render(label, True, TEXT), (x + 42, y + 6))
            self.screen.blit(self.small.render(color["hex"], True, MUTED), (x + 330, y + 8))
            y += 38

    def _draw_buttons(self, mouse: tuple[int, int]) -> None:
        for button in self.buttons:
            rect = button["rect"]
            hovered = rect.collidepoint(mouse)
            pygame.draw.rect(
                self.screen, BUTTON_HOVER if hovered else BUTTON, rect, border_radius=8
            )
            text = self.small.render(button["label"], True, TEXT)
            self.screen.blit(text, text.get_rect(center=rect.center))

    def _draw_footer(self) -> None:
        ok, why = self._validity()
        mark = "\u2713" if ok else "\u2717"
        status = f"{mark} {why}"
        self.screen.blit(self.font.render(status, True, ACCENT if ok else WARN), (60, 620))
        self.screen.blit(self.small.render(self.message, True, MUTED), (60, 656))
        hint = "Esc: quit   Enter: confirm edit"
        self.screen.blit(self.small.render(hint, True, MUTED), (60, 676))

    def _draw_text_modal(self) -> None:
        assert self.text_edit is not None
        overlay = pygame.Surface((WINDOW_W, WINDOW_H), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 150))
        self.screen.blit(overlay, (0, 0))
        box = pygame.Rect(WINDOW_W // 2 - 260, WINDOW_H // 2 - 60, 520, 120)
        pygame.draw.rect(self.screen, PANEL, box, border_radius=12)
        pygame.draw.rect(self.screen, ACCENT, box, width=2, border_radius=12)
        field = self.text_edit["field"]
        prompt = "New name:" if field == "name" else "New hex (e.g. #3f6fd0):"
        self.screen.blit(self.font.render(prompt, True, TEXT), (box.x + 20, box.y + 18))
        buffer = self.text_edit["buffer"] + "_"
        self.screen.blit(self.big.render(buffer, True, ACCENT), (box.x + 20, box.y + 54))


def main() -> None:
    parser = argparse.ArgumentParser(description="Edit the A Gentle Rain tile set.")
    parser.add_argument(
        "--path", type=Path, default=None, help="tiles.json to edit (defaults to the bundled file)"
    )
    args = parser.parse_args()
    path = args.path if args.path is not None else default_data_path()
    TileEditor(path).run()


if __name__ == "__main__":
    main()
