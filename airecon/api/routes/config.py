from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from prisma import Prisma
from pydantic import BaseModel, Field

from ..deps import get_db, reload_global_config

logger = logging.getLogger("airecon.api.config")

router = APIRouter(prefix="/api/config", tags=["config"])


class SettingResponse(BaseModel):
    key: str
    value: Any
    default: Any
    category: str
    description: str


class SettingUpdate(BaseModel):
    value: Any


class BatchSettingUpdate(BaseModel):
    settings: dict[str, Any] = Field(..., description="Key-value pairs to update")


@router.get("", response_model=list[SettingResponse])
async def list_settings(db: Prisma = Depends(get_db)):
    from airecon.proxy.config import DEFAULT_CONFIG, _CONFIG_SCHEMA

    settings = await db.setting.find_many(order={"key": "asc"})
    db_map = {s.key: s for s in settings}

    result: list[SettingResponse] = []
    for key, (default, description) in _CONFIG_SCHEMA.items():
        s = db_map.get(key)
        result.append(SettingResponse(
            key=key,
            value=s.value if s else default,
            default=default,
            category=s.category if s else "",
            description=description,
        ))
    return result


@router.get("/{key}", response_model=SettingResponse)
async def get_setting(key: str, db: Prisma = Depends(get_db)):
    from airecon.proxy.config import DEFAULT_CONFIG, _CONFIG_SCHEMA

    if key not in _CONFIG_SCHEMA:
        raise HTTPException(status_code=404, detail=f"Unknown setting: {key}")

    s = await db.setting.find_unique(where={"key": key})
    default, description = _CONFIG_SCHEMA[key]

    return SettingResponse(
        key=key,
        value=s.value if s else default,
        default=default,
        category=s.category if s else "",
        description=description,
    )


@router.put("/{key}", response_model=SettingResponse)
async def update_setting(key: str, body: SettingUpdate, db: Prisma = Depends(get_db)):
    from airecon.proxy.config import DEFAULT_CONFIG, _CONFIG_SCHEMA

    if key not in _CONFIG_SCHEMA:
        raise HTTPException(status_code=404, detail=f"Unknown setting: {key}")

    default, description = _CONFIG_SCHEMA[key]
    category = ""
    from airecon.proxy.config import _CONFIG_CATEGORIES
    for cat_name, cat_keys in _CONFIG_CATEGORIES:
        if key in cat_keys:
            category = cat_name
            break

    serialized = json.loads(json.dumps(body.value, default=str))
    await db.setting.upsert(
        where={"key": key},
        data={
            "create": {"key": key, "value": serialized, "category": category},
            "update": {"value": serialized},
        },
    )

    await reload_global_config()
    logger.info("Setting updated: %s", key)

    return SettingResponse(
        key=key,
        value=serialized,
        default=default,
        category=category,
        description=description,
    )


@router.put("", response_model=dict[str, int])
async def batch_update_settings(body: BatchSettingUpdate, db: Prisma = Depends(get_db)):
    from airecon.proxy.config import _CONFIG_SCHEMA, _CONFIG_CATEGORIES

    updated = 0
    for key, value in body.settings.items():
        if key not in _CONFIG_SCHEMA:
            continue
        category = ""
        for cat_name, cat_keys in _CONFIG_CATEGORIES:
            if key in cat_keys:
                category = cat_name
                break
        serialized = json.loads(json.dumps(value, default=str))
        await db.setting.upsert(
            where={"key": key},
            data={
                "create": {"key": key, "value": serialized, "category": category},
                "update": {"value": serialized},
            },
        )
        updated += 1

    await reload_global_config()
    logger.info("Batch settings updated: %d keys", updated)
    return {"updated": updated}


@router.delete("/{key}", status_code=204)
async def reset_setting(key: str, db: Prisma = Depends(get_db)):
    from airecon.proxy.config import _CONFIG_SCHEMA

    if key not in _CONFIG_SCHEMA:
        raise HTTPException(status_code=404, detail=f"Unknown setting: {key}")

    await db.setting.delete(where={"key": key})
    await reload_global_config()
    logger.info("Setting reset to default: %s", key)
