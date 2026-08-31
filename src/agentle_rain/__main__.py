"""Command-line entry point: launch the game UI or the tile editor.

python -m agentle_rain [--seed N] [--path tiles.json]
python -m agentle_rain --edit [--path tiles.json]
"""

from __future__ import annotations

import argparse


def main() -> None:
    parser = argparse.ArgumentParser(description="Play A Gentle Rain.")
    parser.add_argument(
        "--seed", type=int, default=None, help="seed the shuffle for a repeatable game"
    )
    parser.add_argument(
        "--edit", action="store_true", help="launch the tile editor instead of playing"
    )
    parser.add_argument(
        "--path",
        default=None,
        help="tiles.json to play or edit (defaults to the bundled file)",
    )
    args = parser.parse_args()

    if args.edit:
        from pathlib import Path

        from .data_loader import default_data_path
        from .ui.editor import TileEditor

        path = Path(args.path) if args.path is not None else default_data_path()
        TileEditor(path).run()
        return

    if args.path is not None:
        from pathlib import Path

        from .data_loader import load_colors_and_tiles

        if not Path(args.path).exists():
            parser.error(
                f"no such tile file: {args.path}. "
                f"Create it with: python -m agentle_rain --edit --path {args.path}"
            )
        try:
            load_colors_and_tiles(args.path)  # pre-flight so errors are friendly, not a traceback
        except (OSError, ValueError) as exc:
            parser.error(f"could not load {args.path}: {exc}")

    from .ui.pygame_ui import run

    run(seed=args.seed, data_path=args.path)


if __name__ == "__main__":
    main()
