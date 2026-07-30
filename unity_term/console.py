from __future__ import annotations

from prompt_toolkit import PromptSession, print_formatted_text
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.document import Document
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.styles import Style

from .protocol import CommandChannel


MESSAGE_STYLES = {
    "prompt": "ansicyan bold",
    "info": "ansiblue",
    "log": "ansiwhite",
    "result": "ansigreen",
    "error": "ansired bold",
}

STYLE = Style.from_dict(MESSAGE_STYLES)


class UnityCompleter(Completer):
    """Quand TAB est pressé, demande les propositions à Unity."""

    def __init__(self, command_channel: CommandChannel, use_lock: bool = True) -> None:
        self.command_channel = command_channel
        self.use_lock = use_lock

    async def get_completions_async(self, document: Document, complete_event):
        response = await self.command_channel.request(
            {
                "type": "complete",
                "cmdline": document.text,
                "cursor": document.cursor_position,
            },
            use_lock=self.use_lock,
        )

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


async def command_dialogue(
    session: PromptSession,
    command_channel: CommandChannel,
    default_prompt: str,
) -> None:
    """Affiche le prompt, exécute avec ENTRÉE, puis attend le résultat."""
    root_completer = session.completer
    prompt_completer = UnityCompleter(command_channel, use_lock=False)

    while True:
        try:
            command = await session.prompt_async(
                make_prompt(default_prompt),
                completer=root_completer,
            )
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
                        user_input = await session.prompt_async(
                            make_prompt(prompt),
                            completer=prompt_completer,
                        )
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


def escape_html(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def make_prompt(text: str) -> HTML:
    return HTML(f"<prompt>{escape_html(text)}&gt; </prompt>")


def print_message(message_type: str, text: str) -> None:
    style = message_type
    if style not in MESSAGE_STYLES:
        style = "info"

    escaped = escape_html(text)
    print_formatted_text(HTML(f"<{style}>{escaped}</{style}>"), style=STYLE)
