from __future__ import annotations

import argparse
import hashlib
import importlib.util
import platform
import subprocess
import sys
from pathlib import Path
from typing import Optional


ROOT = Path(__file__).resolve().parent
APP_NAME = "unity-term"
VENV = ROOT / ".venv"
BUILD_REQUIREMENTS = ROOT / "requirements-build.txt"
RUNTIME_REQUIREMENTS = ROOT / "requirements.txt"
REQUIREMENTS_STAMP = VENV / ".requirements.sha256"


def venv_python() -> Path:
    if sys.platform == "win32":
        return VENV / "Scripts" / "python.exe"
    return VENV / "bin" / "python"


def requirements_fingerprint() -> str:
    digest = hashlib.sha256()
    for path in (RUNTIME_REQUIREMENTS, BUILD_REQUIREMENTS):
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def environment_is_ready(python: Path, fingerprint: str) -> bool:
    if not python.is_file() or not REQUIREMENTS_STAMP.is_file():
        return False

    if REQUIREMENTS_STAMP.read_text(encoding="utf-8").strip() != fingerprint:
        return False

    result = subprocess.run(
        [str(python), "-c", "import prompt_toolkit, PyInstaller"],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


def ensure_build_environment() -> Optional[int]:
    python = venv_python()
    fingerprint = requirements_fingerprint()

    if not python.is_file():
        print(f"Creating isolated build environment: {VENV}")
        subprocess.run(
            [sys.executable, "-m", "venv", str(VENV)],
            cwd=ROOT,
            check=True,
        )

    if not environment_is_ready(python, fingerprint):
        print("Installing build dependencies in .venv...")
        subprocess.run(
            [
                str(python),
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                "-r",
                str(BUILD_REQUIREMENTS),
            ],
            cwd=ROOT,
            check=True,
        )
        REQUIREMENTS_STAMP.write_text(fingerprint, encoding="utf-8")

    if Path(sys.prefix).resolve() != VENV.resolve():
        print("Building with the isolated .venv interpreter...")
        result = subprocess.run(
            [str(python), str(Path(__file__).resolve()), *sys.argv[1:]],
            cwd=ROOT,
            check=False,
        )
        return result.returncode

    return None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the Unity TERM client for the current operating system.")
    parser.add_argument("--onedir", action="store_true", help="Build a folder instead of a single executable.")
    parser.add_argument("--output", type=Path, default=ROOT / "dist", help="Output directory (default: ./dist).")
    return parser.parse_args()


def main() -> int:
    arguments = parse_args()
    environment_result = ensure_build_environment()
    if environment_result is not None:
        return environment_result

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

    executable_name = f"{APP_NAME}.exe" if sys.platform == "win32" else f"{APP_NAME}.x86_64"
    executable = output / APP_NAME / executable_name if arguments.onedir else output / executable_name
    print(f"Built: {executable}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
