"""Command-line entry point: launch the pygame UI.

python -m agentle_rain [--seed N]
"""

from __future__ import annotations

import argparse


def main() -> None:
    parser = argparse.ArgumentParser(description="Play A Gentle Rain.")
    parser.add_argument(
        "--seed", type=int, default=None, help="seed the shuffle for a repeatable game"
    )
    args = parser.parse_args()

    from .ui.pygame_ui import run

    run(seed=args.seed)


if __name__ == "__main__":
    main()
