from __future__ import annotations

import logging
import os

from prisma import Prisma

logger = logging.getLogger("airecon.db")

_client: Prisma | None = None


async def get_db() -> Prisma:
    global _client
    if _client is None:
        _client = Prisma()
        await _client.connect()
        logger.info("Database connected")
    return _client


async def close_db() -> None:
    global _client
    if _client is not None:
        await _client.disconnect()
        _client = None
        logger.info("Database disconnected")
