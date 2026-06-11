from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from prisma import Prisma
from prisma.models import Scan

from ..deps import get_db
from ..schemas import (
    FindingResponse,
    PortResponse,
    ScanCreate,
    ScanResponse,
    ScanStatus,
    SubdomainResponse,
    ToolCallResponse,
)

logger = logging.getLogger("airecon.api.scans")

router = APIRouter(prefix="/api/scans", tags=["scans"])


def _scan_to_response(scan: Any, finding_count: int = 0, subdomain_count: int = 0) -> ScanResponse:
    return ScanResponse(
        id=scan.id,
        target=scan.target,
        status=scan.status,
        phase=scan.phase,
        created_at=scan.createdAt,
        updated_at=scan.updatedAt,
        started_at=scan.startedAt,
        finished_at=scan.finishedAt,
        error=scan.error,
        finding_count=finding_count,
        subdomain_count=subdomain_count,
    )


@router.post("", response_model=ScanResponse, status_code=201)
async def create_scan(body: ScanCreate, db: Prisma = Depends(get_db)):
    scan = await db.scan.create(
        data={
            "target": body.target,
            "config": body.config,
        }
    )
    logger.info("Scan created: %s for target=%s", scan.id, body.target)
    return _scan_to_response(scan)


@router.get("", response_model=list[ScanResponse])
async def list_scans(
    status: ScanStatus | None = None,
    target: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Prisma = Depends(get_db),
):
    where: dict[str, Any] = {}
    if status:
        where["status"] = status.value
    if target:
        where["target"] = {"contains": target}

    scans = await db.scan.find_many(
        where=where,
        order={"createdAt": "desc"},
        take=limit,
        skip=offset,
    )

    results: list[ScanResponse] = []
    for scan in scans:
        fc = await db.finding.count(where={"scanId": scan.id})
        sc = await db.subdomain.count(where={"scanId": scan.id})
        results.append(_scan_to_response(scan, fc, sc))
    return results


@router.get("/{scan_id}", response_model=ScanResponse)
async def get_scan(scan_id: str, db: Prisma = Depends(get_db)):
    scan = await db.scan.find_unique(where={"id": scan_id})
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")
    fc = await db.finding.count(where={"scanId": scan_id})
    sc = await db.subdomain.count(where={"scanId": scan_id})
    return _scan_to_response(scan, fc, sc)


@router.post("/{scan_id}/start", response_model=ScanResponse)
async def start_scan(scan_id: str, db: Prisma = Depends(get_db)):
    scan = await db.scan.find_unique(where={"id": scan_id})
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")
    if scan.status not in ("PENDING", "PAUSED"):
        raise HTTPException(status_code=409, detail=f"Cannot start scan in {scan.status} state")

    from datetime import datetime, timezone

    updated = await db.scan.update(
        where={"id": scan_id},
        data={"status": "RUNNING", "startedAt": datetime.now(timezone.utc)},
    )

    from ...worker.runner import enqueue_scan
    enqueue_scan(scan_id)

    logger.info("Scan started: %s", scan_id)
    return _scan_to_response(updated)


@router.post("/{scan_id}/stop", response_model=ScanResponse)
async def stop_scan(scan_id: str, db: Prisma = Depends(get_db)):
    scan = await db.scan.find_unique(where={"id": scan_id})
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")
    if scan.status != "RUNNING":
        raise HTTPException(status_code=409, detail="Scan is not running")

    updated = await db.scan.update(
        where={"id": scan_id},
        data={"status": "CANCELLED"},
    )

    from ...worker.runner import cancel_scan
    await cancel_scan(scan_id)

    logger.info("Scan stopped: %s", scan_id)
    return _scan_to_response(updated)


@router.delete("/{scan_id}", status_code=204)
async def delete_scan(scan_id: str, db: Prisma = Depends(get_db)):
    scan = await db.scan.find_unique(where={"id": scan_id})
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")
    if scan.status == "RUNNING":
        raise HTTPException(status_code=409, detail="Cannot delete running scan. Stop it first.")
    await db.scan.delete(where={"id": scan_id})
    logger.info("Scan deleted: %s", scan_id)


@router.get("/{scan_id}/findings", response_model=list[FindingResponse])
async def list_findings(
    scan_id: str,
    severity: str | None = None,
    db: Prisma = Depends(get_db),
):
    scan = await db.scan.find_unique(where={"id": scan_id})
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")

    where: dict[str, Any] = {"scanId": scan_id}
    if severity:
        where["severity"] = severity.upper()

    findings = await db.finding.find_many(
        where=where,
        order={"createdAt": "desc"},
    )
    return [
        FindingResponse(
            id=f.id,
            scan_id=f.scanId,
            title=f.title,
            severity=f.severity,
            confidence=f.confidence,
            category=f.category,
            url=f.url,
            endpoint=f.endpoint,
            parameter=f.parameter,
            description=f.description,
            evidence=f.evidence,
            remediation=f.remediation,
            cve=f.cve,
            verified=f.verified,
            created_at=f.createdAt,
        )
        for f in findings
    ]


@router.get("/{scan_id}/subdomains", response_model=list[SubdomainResponse])
async def list_subdomains(scan_id: str, db: Prisma = Depends(get_db)):
    scan = await db.scan.find_unique(where={"id": scan_id})
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")
    subs = await db.subdomain.find_many(
        where={"scanId": scan_id},
        order={"createdAt": "desc"},
    )
    return [
        SubdomainResponse(
            id=s.id, scan_id=s.scanId, domain=s.domain,
            alive=s.alive, ip=s.ip, created_at=s.createdAt,
        )
        for s in subs
    ]


@router.get("/{scan_id}/ports", response_model=list[PortResponse])
async def list_ports(scan_id: str, db: Prisma = Depends(get_db)):
    scan = await db.scan.find_unique(where={"id": scan_id})
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")
    ports = await db.port.find_many(
        where={"scanId": scan_id},
        order={"port": "asc"},
    )
    return [
        PortResponse(
            id=p.id, scan_id=p.scanId, host=p.host, port=p.port,
            protocol=p.protocol, service=p.service, state=p.state,
            created_at=p.createdAt,
        )
        for p in ports
    ]


@router.get("/{scan_id}/tool-calls", response_model=list[ToolCallResponse])
async def list_tool_calls(
    scan_id: str,
    limit: int = Query(100, ge=1, le=500),
    db: Prisma = Depends(get_db),
):
    scan = await db.scan.find_unique(where={"id": scan_id})
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")
    calls = await db.toolcall.find_many(
        where={"scanId": scan_id},
        order={"createdAt": "desc"},
        take=limit,
    )
    return [
        ToolCallResponse(
            id=t.id, scan_id=t.scanId, tool=t.tool, args=t.args,
            result=t.result, success=t.success, phase=t.phase,
            duration_ms=t.durationMs, tokens_used=t.tokensUsed,
            created_at=t.createdAt,
        )
        for t in calls
    ]
