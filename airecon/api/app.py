from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from airecon._version import __version__
from .deps import close_db, get_db
from .routes.scans import router as scans_router
from .routes.health import router as health_router

logger = logging.getLogger("airecon.api")

_worker_task: asyncio.Task | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _worker_task

    await get_db()
    logger.info("Database connected")

    from ..worker.runner import start_worker_loop
    _worker_task = asyncio.create_task(
        start_worker_loop(),
        name="worker-loop",
    )
    logger.info("Worker started")

    yield

    if _worker_task and not _worker_task.done():
        _worker_task.cancel()
        try:
            await _worker_task
        except asyncio.CancelledError:
            pass

    await close_db()
    logger.info("Shutdown complete")


def create_app() -> FastAPI:
    app = FastAPI(
        title="AIRecon API",
        version=__version__,
        description="AI-powered security reconnaissance API",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(scans_router)
    app.include_router(health_router)

    return app
