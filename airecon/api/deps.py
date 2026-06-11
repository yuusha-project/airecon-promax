from __future__ import annotations

import json
import logging
import os
from typing import Any

from prisma import Prisma

logger = logging.getLogger("airecon.db")

_client: Prisma | None = None


async def get_db() -> Prisma:
    global _client
    if _client is None:
        _client = Prisma()
        await _client.connect()
        logger.info("Database connected: %s", _mask_url(os.getenv("DATABASE_URL", "")))
    return _client


async def close_db() -> None:
    global _client
    if _client is not None:
        await _client.disconnect()
        _client = None
        logger.info("Database disconnected")


async def check_db_health() -> bool:
    try:
        db = await get_db()
        await db.query_raw("SELECT 1")
        return True
    except Exception:
        return False


async def seed_default_settings() -> int:
    from airecon.proxy.config import DEFAULT_CONFIG, _CONFIG_SCHEMA

    db = await get_db()
    seeded = 0

    for key, default_value in DEFAULT_CONFIG.items():
        existing = await db.setting.find_unique(where={"key": key})
        if existing is None:
            category = ""
            for cat_name, cat_keys in _get_config_categories():
                if key in cat_keys:
                    category = cat_name
                    break
            await db.setting.create(
                data={
                    "key": key,
                    "value": json.dumps(default_value),
                    "category": category,
                }
            )
            seeded += 1

    logger.info("Settings seeded: %d new (total: %d)", seeded, len(DEFAULT_CONFIG))
    return seeded


async def load_config_from_db() -> dict[str, Any]:
    db = await get_db()
    settings = await db.setting.find_many()
    result: dict[str, Any] = {}
    for s in settings:
        try:
            result[s.key] = json.loads(s.value)
        except (json.JSONDecodeError, TypeError):
            result[s.key] = s.value
    return result


async def reload_global_config() -> None:
    from airecon.proxy.config import Config, set_global_config

    db_values = await load_config_from_db()
    config = Config.load_with_defaults(db_values)
    set_global_config(config)
    logger.info("Global config reloaded from database")


def _get_config_categories() -> list[tuple[str, list[str]]]:
    from airecon.proxy.config import _CONFIG_CATEGORIES
    return _CONFIG_CATEGORIES


def _mask_url(url: str) -> str:
    if not url or "@" not in url:
        return url or "(not set)"
    _, suffix = url.rsplit("@", 1)
    return f"***:***@{suffix}"
