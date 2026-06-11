from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from prisma import Prisma

from airecon._version import __version__
from ..deps import get_db
from ..schemas import HealthResponse

logger = logging.getLogger("airecon.api.health")

router = APIRouter(tags=["health"])


@router.get("/api/health", response_model=HealthResponse)
async def health_check(db: Prisma = Depends(get_db)):
    db_status = "ok"
    try:
        await db.query_raw("SELECT 1")
    except Exception as e:
        db_status = f"error: {e}"

    llm_status = "unknown"
    try:
        from airecon.proxy.config import get_config
        cfg = get_config()
        llm_status = f"{cfg.llm_base_url} ({cfg.llm_model})"
    except Exception:
        llm_status = "not configured"

    return HealthResponse(
        status="ok" if db_status == "ok" else "degraded",
        version=__version__,
        database=db_status,
        llm=llm_status,
    )
