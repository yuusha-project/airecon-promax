from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ScanStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class Severity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


class ScanCreate(BaseModel):
    target: str = Field(..., min_length=1, description="Target domain, URL, or IP")
    config: dict[str, Any] | None = Field(None, description="Override config values")


class ScanResponse(BaseModel):
    id: str
    target: str
    status: ScanStatus
    phase: str
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    error: str | None
    finding_count: int = 0
    subdomain_count: int = 0

    class Config:
        from_attributes = True


class FindingResponse(BaseModel):
    id: str
    scan_id: str
    title: str
    severity: Severity
    confidence: float
    category: str
    url: str
    endpoint: str
    parameter: str
    description: str
    evidence: dict[str, Any] | None
    remediation: str
    cve: str | None
    verified: bool
    created_at: datetime

    class Config:
        from_attributes = True


class SubdomainResponse(BaseModel):
    id: str
    scan_id: str
    domain: str
    alive: bool
    ip: str | None
    created_at: datetime

    class Config:
        from_attributes = True


class PortResponse(BaseModel):
    id: str
    scan_id: str
    host: str
    port: int
    protocol: str
    service: str
    state: str
    created_at: datetime

    class Config:
        from_attributes = True


class ToolCallResponse(BaseModel):
    id: str
    scan_id: str
    tool: str
    args: dict[str, Any] | None
    result: str | None
    success: bool
    phase: str
    duration_ms: int
    tokens_used: int
    created_at: datetime

    class Config:
        from_attributes = True


class HealthResponse(BaseModel):
    status: str
    version: str
    database: str
    llm: str
