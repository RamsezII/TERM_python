import argparse
import asyncio
import json

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.document import Document
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit.styles import Style


dict_styles = {
    "prompt": "ansicyan bold",
    "info": "ansiblue",
    "log": "ansiwhite",
    "result": "ansigreen",
    "error": "ansired bold",
}

STYLE = Style.from_dict(dict_styles)


async def send_json(writer: asyncio.StreamWriter, message: dict) -> None:
    """Envoie un objet JSON terminé par un saut de ligne."""
    text = json.dumps(message, ensure_ascii=False, separators=(",", ":"))
    writer.write((text + "\n").encode("utf-8"))
    await writer.drain()


async def read_json(reader: asyncio.StreamReader) -> dict:
    """Lit un objet JSON terminé par un saut de ligne."""
    raw = await reader.readline()
    if not raw:
        raise ConnectionError("Unity closed the connection.")
    return json.loads(raw.decode("utf-8"))


class CommandChannel:
    """Dialogue ordonné requête/réponse sur la connexion de commande."""

    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self.reader = reader
        self.writer = writer

        # Une seule requête à la fois : sa prochaine réponse lui appartient.
        self.lock = asyncio.Lock()

    async def request(self, message: dict) -> dict:
        async with self.lock:
            await send_json(self.writer, message)
            return await read_json(self.reader)


class UnityCompleter(Completer):
    """Quand TAB est pressé, demande les propositions à Unity."""

    def __init__(self, command_channel: CommandChannel) -> None:
        self.command_channel = command_channel

    async def get_completions_async(self, document: Document, complete_event):
        response = await self.command_channel.request(
            {
                "type": "complete",
                "cmdline": document.text,
                "cursor": document.cursor_position
            })

        word = document.get_word_before_cursor()
        for candidate in response.get("candidates", []):
            yield Completion(str(candidate), start_position=-len(word))

    def get_completions(self, document: Document, complete_event):
        # prompt_toolkit demande cette méthode, mais nous utilisons sa version async.
        return []


async def command_dialogue(session: PromptSession, command_channel: CommandChannel, project_name: str) -> None:
    """Affiche le prompt, exécute avec ENTRÉE, puis attend le résultat."""
    while True:
        try:
            command = await session.prompt_async(make_prompt(project_name))
        except KeyboardInterrupt:
            continue
        except EOFError:
            command = "quit"

        # Pendant cette attente, aucun nouveau prompt n'est affiché.
        # En revanche, log_loop continue sur l'autre connexion.
        response = await command_channel.request(
            {
                "type": "execute",
                "cmdline": command
            })

        message_type = str(response.get("type", "result"))

        if "result" in response:
            result = str(response.get("result", ""))
            print_message(message_type, result)


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

        project_name = str(intro.get("project_name", "")).strip()

        # Connexion 2 : réception indépendante des logs.
        log_reader, log_writer = await asyncio.open_connection(host, log_port)
    except (OSError, ConnectionError, json.JSONDecodeError) as error:
        if command_writer is not None:
            command_writer.close()
            await command_writer.wait_closed()

        print_message("error", f"Connection failed: {error}")
        return

    command_channel = CommandChannel(command_reader, command_writer)
    session = PromptSession(style=STYLE, completer=UnityCompleter(command_channel), complete_while_typing=False)

    # Le dialogue de commande et les logs tournent simultanément,
    # mais sur deux connexions différentes.
    command_task = asyncio.create_task(command_dialogue(session, command_channel, project_name))
    log_task = asyncio.create_task(log_loop(log_reader))

    try:
        with patch_stdout():
            done, pending = await asyncio.wait({command_task, log_task}, return_when=asyncio.FIRST_COMPLETED)

            for task in pending:
                task.cancel()

            await asyncio.gather(*pending, return_exceptions=True)

            for result in await asyncio.gather(*done, return_exceptions=True):
                if isinstance(result, Exception):
                    raise result

    except (ConnectionError, json.JSONDecodeError) as error:
        print_message("error", str(error))

    finally:
        command_writer.close()
        log_writer.close()
        await asyncio.gather(command_writer.wait_closed(), log_writer.wait_closed(), return_exceptions=True)


def escape_html(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def make_prompt(text: str) -> HTML:
    return HTML(f"<prompt>{escape_html(text)}&gt; </prompt>")


def print_message(message_type: str, text: str) -> None:
    from prompt_toolkit import print_formatted_text

    style = message_type
    if style not in dict_styles:
        style = "info"

    escaped = escape_html(text)
    print_formatted_text(HTML(f"<{style}>{escaped}</{style}>"), style=STYLE)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Unity TERM client")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--command-port", type=int, default=5050)
    parser.add_argument("--log-port", type=int, default=5051)
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    asyncio.run(run_client(arguments.host, arguments.command_port, arguments.log_port))
