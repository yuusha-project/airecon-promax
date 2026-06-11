from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from prisma import Prisma

logger = logging.getLogger("airecon.worker")

_scan_queue: asyncio.Queue[str] = asyncio.Queue()
_active_tasks: dict[str, asyncio.Task] = {}
_cancel_events: dict[str, asyncio.Event] = {}


def enqueue_scan(scan_id: str) -> None:
    _scan_queue.put_nowait(scan_id)
    logger.info("Scan %s enqueued", scan_id)


async def cancel_scan(scan_id: str) -> None:
    evt = _cancel_events.get(scan_id)
    if evt:
        evt.set()
    task = _active_tasks.get(scan_id)
    if task and not task.done():
        task.cancel()
        logger.info("Scan %s cancel requested", scan_id)


async def _run_scan_worker(scan_id: str) -> None:
    from prisma import Prisma as PrismaClient

    db = PrismaClient()
    await db.connect()

    try:
        scan = await db.scan.find_unique(where={"id": scan_id})
        if not scan:
            logger.error("Scan %s not found in DB", scan_id)
            return

        cancel_event = asyncio.Event()
        _cancel_events[scan_id] = cancel_event

        logger.info("Worker starting scan %s: target=%s", scan_id, scan.target)

        from airecon.proxy.llm_client import LLMClient
        from airecon.proxy.docker import DockerEngine
        from airecon.proxy.agent.loop import AgentLoop

        llm = LLMClient()
        await llm._async_init()
        engine = DockerEngine()
        agent = AgentLoop(ollama=llm, engine=engine)

        try:
            await agent.initialize()
        except Exception as e:
            logger.error("Agent init failed for scan %s: %s", scan_id, e)
            await db.scan.update(
                where={"id": scan_id},
                data={"status": "FAILED", "error": str(e), "finishedAt": datetime.now(timezone.utc)},
            )
            return

        try:
            async for event in agent.run(target=scan.target):
                if cancel_event.is_set():
                    logger.info("Scan %s cancelled", scan_id)
                    await db.scan.update(
                        where={"id": scan_id},
                        data={"status": "CANCELLED", "finishedAt": datetime.now(timezone.utc)},
                    )
                    break

                if event.type == "phase_change":
                    phase = event.data.get("phase", "RECON")
                    await db.scan.update(
                        where={"id": scan_id},
                        data={"phase": phase},
                    )

                elif event.type == "finding":
                    d = event.data
                    await db.finding.create(
                        data={
                            "scanId": scan_id,
                            "title": d.get("title", "Unknown"),
                            "severity": d.get("severity", "INFO"),
                            "confidence": d.get("confidence", 0.0),
                            "category": d.get("category", ""),
                            "url": d.get("url", ""),
                            "endpoint": d.get("endpoint", ""),
                            "parameter": d.get("parameter", ""),
                            "description": d.get("description", ""),
                            "evidence": d.get("evidence"),
                        }
                    )

                elif event.type == "subdomain":
                    d = event.data
                    await db.subdomain.upsert(
                        where={"scanId_domain": {"scanId": scan_id, "domain": d.get("domain", "")}},
                        data={
                            "create": {"scanId": scan_id, "domain": d.get("domain", ""), "alive": d.get("alive", False), "ip": d.get("ip")},
                            "update": {"alive": d.get("alive", False), "ip": d.get("ip")},
                        },
                    )

                elif event.type == "tool_result":
                    d = event.data
                    await db.toolcall.create(
                        data={
                            "scanId": scan_id,
                            "tool": d.get("tool", ""),
                            "args": d.get("args"),
                            "result": str(d.get("result", ""))[:10000],
                            "success": d.get("success", False),
                            "phase": d.get("phase", "RECON"),
                            "durationMs": int(d.get("duration_ms", 0)),
                            "tokensUsed": int(d.get("tokens_used", 0)),
                        }
                    )

            if not cancel_event.is_set():
                await db.scan.update(
                    where={"id": scan_id},
                    data={"status": "COMPLETED", "finishedAt": datetime.now(timezone.utc)},
                )
                logger.info("Scan %s completed", scan_id)

        except Exception as e:
            logger.exception("Scan %s failed: %s", scan_id, e)
            await db.scan.update(
                where={"id": scan_id},
                data={"status": "FAILED", "error": str(e)[:2000], "finishedAt": datetime.now(timezone.utc)},
            )
        finally:
            await agent.stop()

    finally:
        await db.disconnect()
        _active_tasks.pop(scan_id, None)
        _cancel_events.pop(scan_id, None)


async def start_worker_loop() -> None:
    logger.info("Worker loop started")
    while True:
        scan_id = await _scan_queue.get()
        task = asyncio.create_task(
            _run_scan_worker(scan_id),
            name=f"scan-{scan_id}",
        )
        _active_tasks[scan_id] = task
        _scan_queue.task_done()
