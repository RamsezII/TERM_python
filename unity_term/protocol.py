from __future__ import annotations

import asyncio
import json
from typing import Optional


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


async def close_writer(writer: Optional[asyncio.StreamWriter]) -> None:
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
