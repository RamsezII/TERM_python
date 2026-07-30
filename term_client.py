import argparse
import asyncio
import json

import comm
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


async def close_writer(writer) -> None:
    if writer is None:
        return

    try:
        writer.close()
        await writer.wait_closed()
    except (ConnectionError, OSError):
        pass


class CommandChannel:
    """Dialogue ordonné requête/réponse sur la connexion de commande."""

    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self.reader = reader
        self.writer = writer

        # Une seule requête à la fois : sa prochaine réponse lui appartient.
        self.lock = asyncio.Lock()

    async def request(self, message: dict, use_lock: bool = True) -> dict:
        if use_lock:
            async with self.lock:
                return await self._request(message)

        return await self._request(message)

    async def _request(self, message: dict) -> dict:
        await self.send(message)
        receive_task = asyncio.create_task(self.receive())

        try:
            return await asyncio.shield(receive_task)
        except asyncio.CancelledError:
            try:
                await asyncio.shield(receive_task)
            except Exception:
                pass
            raise

    async def send(self, message: dict) -> None:
        await send_json(self.writer, message)

    async def receive(self) -> dict:
        return await read_json(self.reader)


class UnityCompleter(Completer):
    """Quand TAB est pressé, demande les propositions à Unity."""

    def __init__(self, command_channel: CommandChannel, use_lock: bool = True) -> None:
        self.command_channel = command_channel
        self.use_lock = use_lock

    async def get_completions_async(self, document: Document, complete_event):
        response = await self.command_channel.request({
            "type": "complete",
            "cmdline": document.text,
            "cursor": document.cursor_position
        }, use_lock=self.use_lock)

        response_type = str(response.get("type", ""))

        if response_type == "exception":
            message = str(response.get("message", "")).strip() or "Unity completion failed."
            print_message("error", message)

            stacktrace = str(response.get("stacktrace", "")).strip()
            if stacktrace:
                print_message("error", stacktrace)
            return

        if response_type != "completion":
            return

        try:
            start = int(response.get("start", document.cursor_position))
        except (TypeError, ValueError):
            start = document.cursor_position

        start = max(0, min(start, document.cursor_position))
        for candidate in response.get("candidates", []) or []:
            yield Completion(str(candidate), start_position=start - document.cursor_position)

    def get_completions(self, document: Document, complete_event):
        # prompt_toolkit demande cette méthode, mais nous utilisons sa version async.
        return []


async def command_dialogue(session: PromptSession, command_channel: CommandChannel, default_prompt: str) -> None:
    """Affiche le prompt, exécute avec ENTRÉE, puis attend le résultat."""
    root_completer = session.completer
    prompt_completer = UnityCompleter(command_channel, use_lock=False)

    while True:
        try:
            command = await session.prompt_async(make_prompt(default_prompt), completer=root_completer)
        except KeyboardInterrupt:
            continue
        except EOFError:
            return

        if not command:
            continue

        # Cette connexion reste réservée à la commande jusqu'à son résultat.
        # Les logs continuent sur leur propre connexion.
        async with command_channel.lock:
            await command_channel.send({"type": "execute", "cmdline": command})

            while True:
                response = await command_channel.receive()
                message_type = str(response.get("type", "error"))

                if message_type == "prompt":
                    prompt = str(response.get("prompt", "")).strip()

                    try:
                        user_input = await session.prompt_async(make_prompt(prompt), completer=prompt_completer)
                    except KeyboardInterrupt:
                        await command_channel.send({"type": "cancel"})
                        continue
                    except EOFError:
                        await command_channel.send({"type": "cancel"})
                        return

                    await command_channel.send({"type": "input", "cmdline": user_input})

                elif message_type == "status":
                    message = str(response.get("message", "")).strip()
                    if message:
                        print_message("info", message)

                elif message_type == "result":
                    result = response.get("result")
                    if result:
                        print_message("result", str(result))
                    break

                elif message_type == "cancelled":
                    break

                elif message_type in {"error", "exception"}:
                    message = str(response.get("message", "")).strip() or "Unknown Unity error."
                    print_message("error", message)

                    stacktrace = str(response.get("stacktrace", "")).strip()
                    if stacktrace:
                        print_message("error", stacktrace)
                    break

                else:
                    print_message("error", f"Unexpected Unity response type: {message_type}")
                    break


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
    session = PromptSession(style=STYLE, completer=UnityCompleter(command_channel), complete_while_typing=False)

    # Le dialogue de commande et les logs tournent simultanément,
    # mais sur deux connexions différentes.
    command_task = asyncio.create_task(command_dialogue(session, command_channel, default_prompt))
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
        await asyncio.gather(close_writer(command_writer), close_writer(log_writer))


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
