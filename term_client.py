from __future__ import annotations

import argparse
import asyncio
import sys

from unity_term.client import run_client


def set_terminal_title(title: str) -> None:
    title = title.replace("\x1b", "").replace("\x07", "").strip()
    if not title:
        return

    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.kernel32.SetConsoleTitleW(title)
            return
        except (AttributeError, OSError):
            pass

    if sys.stdout.isatty():
        sys.stdout.write(f"\x1b]0;{title}\x07")
        sys.stdout.flush()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Unity TERM client")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--command-port", type=int, default=5050)
    parser.add_argument("--log-port", type=int, default=5051)
    parser.add_argument("--title", default="Unity TERM")
    return parser.parse_args()


def main() -> None:
    arguments = parse_args()
    set_terminal_title(arguments.title)
    asyncio.run(
        run_client(
            arguments.host,
            arguments.command_port,
            arguments.log_port,
        )
    )


if __name__ == "__main__":
    main()
