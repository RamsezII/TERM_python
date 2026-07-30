from __future__ import annotations

import asyncio
import json

from prompt_toolkit import PromptSession
from prompt_toolkit.patch_stdout import patch_stdout

from .console import STYLE, UnityCompleter, command_dialogue, print_message
from .protocol import CommandChannel, close_writer, read_json


async def log_loop(reader: asyncio.StreamReader) -> None:
    """Écoute uniquement la connexion réservée aux logs Unity."""
    while True:
        message = await read_json(reader)
        message_type = str(message.get("type", "log"))
        text = str(message.get("message", ""))
        print_message(message_type, text)


async def run_client(host: str, command_port: int, log_port: int) -> None:
    command_writer = None
    log_writer = None

    try:
        # Connexion 1 : TAB, exécution et réponses.
        command_reader, command_writer = await asyncio.open_connection(host, command_port)
        intro = await read_json(command_reader)

        if intro.get("type") != "intro":
            raise ConnectionError("Unity did not send the command introduction.")

        default_prompt = str(intro.get("default_prompt", "")).strip() or "term"

        # Connexion 2 : réception indépendante des logs.
        log_reader, log_writer = await asyncio.open_connection(host, log_port)
    except (OSError, ConnectionError, json.JSONDecodeError) as error:
        await close_writer(command_writer)

        print_message("error", f"Connection failed: {error}")
        return

    command_channel = CommandChannel(command_reader, command_writer)
    session = PromptSession(
        style=STYLE,
        completer=UnityCompleter(command_channel),
        complete_while_typing=False,
    )

    # Le dialogue de commande et les logs tournent simultanément,
    # mais sur deux connexions différentes.
    command_task = asyncio.create_task(
        command_dialogue(session, command_channel, default_prompt)
    )
    log_task = asyncio.create_task(log_loop(log_reader))

    try:
        with patch_stdout():
            done, pending = await asyncio.wait(
                {command_task, log_task},
                return_when=asyncio.FIRST_COMPLETED,
            )

            for task in pending:
                task.cancel()

            await asyncio.gather(*pending, return_exceptions=True)

            for result in await asyncio.gather(*done, return_exceptions=True):
                if isinstance(result, Exception):
                    raise result

    except (ConnectionError, json.JSONDecodeError) as error:
        print_message("error", str(error))

    finally:
        await asyncio.gather(
            close_writer(command_writer),
            close_writer(log_writer),
        )
