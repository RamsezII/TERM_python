from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import dataclass
from typing import Any

from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.history import FileHistory
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit.styles import Style


STYLE = Style.from_dict(
    {
        "prompt": "ansicyan bold",
        "result": "ansigreen",
        "error": "ansired bold",
        "info": "ansiblue",
    }
)


@dataclass(frozen=True)
class Config:
    host: str
    port: int


async def read_message(reader: asyncio.StreamReader) -> dict[str, Any] | None:
    raw = await reader.readline()
    if not raw:
        return None
    return json.loads(raw.decode("utf-8"))


async def run_terminal(config: Config) -> None:
    try:
        reader, writer = await asyncio.open_connection(config.host, config.port)
    except OSError as error:
        print_formatted("error", f"Connection failed: {error}")
        return

    session: PromptSession[str] = PromptSession(
        history=FileHistory(".term_history"),
        style=STYLE,
    )

    try:
        welcome = await read_message(reader)
        if welcome:
            print_formatted("info", str(welcome.get("text", "")))

        with patch_stdout():
            while True:
                try:
                    command = await session.prompt_async(
                        HTML("<prompt>term&gt; </prompt>")
                    )
                except (EOFError, KeyboardInterrupt):
                    command = "quit"

                request = json.dumps(
                    {"type": "command", "text": command},
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                writer.write((request + "\n").encode("utf-8"))
                await writer.drain()

                response = await read_message(reader)
                if response is None:
                    print_formatted("error", "Server closed the connection.")
                    break

                message_type = str(response.get("type", "result"))
                text = str(response.get("text", ""))
                if text:
                    print_formatted(
                        "error" if message_type == "error" else "result",
                        text,
                    )

                if response.get("close"):
                    break
    except (ConnectionError, json.JSONDecodeError) as error:
        print_formatted("error", f"Connection lost: {error}")
    finally:
        writer.close()
        await writer.wait_closed()


def print_formatted(style_class: str, text: str) -> None:
    from prompt_toolkit import print_formatted_text

    print_formatted_text(HTML(f"<{style_class}>{html_escape(text)}</{style_class}>"), style=STYLE)


def html_escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def parse_args() -> Config:
    parser = argparse.ArgumentParser(description="TERM TCP client")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5050)
    args = parser.parse_args()
    return Config(args.host, args.port)


if __name__ == "__main__":
    asyncio.run(run_terminal(parse_args()))
