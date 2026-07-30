from __future__ import annotations

import argparse
import importlib.util
import platform
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
APP_NAME = "unity-term"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the Unity TERM client for the current operating system.")
    parser.add_argument("--onedir", action="store_true", help="Build a folder instead of a single executable.")
    parser.add_argument("--output", type=Path, default=ROOT / "dist", help="Output directory (default: ./dist).")
    return parser.parse_args()


def main() -> int:
    arguments = parse_args()

    if importlib.util.find_spec("PyInstaller") is None:
        print("PyInstaller is missing.", file=sys.stderr)
        print(f'Install the build dependencies with:\n  "{sys.executable}" -m pip install -r requirements-build.txt', file=sys.stderr)
        return 1

    output = arguments.output.resolve()
    work = ROOT / "build" / "pyinstaller"
    spec = ROOT / "build"
    spec.mkdir(parents=True, exist_ok=True)
    mode = "--onedir" if arguments.onedir else "--onefile"
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--console",
        mode,
        "--name",
        APP_NAME,
        "--distpath",
        str(output),
        "--workpath",
        str(work),
        "--specpath",
        str(spec),
        str(ROOT / "term_client.py"),
    ]

    print(f"Building {APP_NAME} for {platform.system()} {platform.machine()}...")
    subprocess.run(command, cwd=ROOT, check=True)

    executable_name = f"{APP_NAME}.exe" if sys.platform == "win32" else APP_NAME
    executable = output / APP_NAME / executable_name if arguments.onedir else output / executable_name
    print(f"Built: {executable}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
