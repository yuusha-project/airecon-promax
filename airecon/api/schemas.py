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


class ScanConfigInput(BaseModel):
    llm_base_url: str | None = None
    llm_model: str | None = None
    llm_api_key: str | None = None
    llm_extra_body: dict[str, Any] | None = None
    llm_timeout: float | None = None
    llm_chunk_timeout: float | None = None
    llm_context_length: int | None = None
    llm_context_length_small: int | None = None
    llm_temperature: float | None = None
    llm_max_tokens: int | None = None
    llm_enable_thinking: bool | None = None
    llm_thinking_mode: str | None = None
    llm_supports_thinking: bool | None = None
    llm_supports_native_tools: bool | None = None
    llm_max_concurrent_requests: int | None = None
    llm_num_keep: int | None = None
    llm_repeat_penalty: float | None = None
    deep_recon_autostart: bool | None = None
    agent_recon_mode: str | None = None
    agent_max_tool_iterations: int | None = None
    agent_repeat_tool_call_limit: int | None = None
    agent_missing_tool_retry_limit: int | None = None
    agent_plan_revision_interval: int | None = None
    agent_exploration_mode: bool | None = None
    agent_exploration_intensity: float | None = None
    agent_exploration_temperature: float | None = None
    agent_stagnation_threshold: int | None = None
    agent_tool_diversity_window: int | None = None
    agent_max_same_tool_streak: int | None = None
    agent_phase_creative_temperature: float | None = None
    allow_destructive_testing: bool | None = None
    agent_max_conversation_messages: int | None = None
    agent_compression_trigger_ratio: float | None = None
    agent_uncompressed_keep_count: int | None = None
    agent_llm_compression_num_ctx: int | None = None
    agent_llm_compression_num_predict: int | None = None
    agent_context_reset_cooldown_seconds: int | None = None
    agent_ctf_max_iterations: int | None = None
    agent_max_empty_retries: int | None = None
    agent_idle_hard_timeout: float | None = None
    agent_max_browser_visits_per_domain: int | None = None
    pipeline_recon_min_subdomains: int | None = None
    pipeline_recon_min_urls: int | None = None
    pipeline_recon_soft_timeout: int | None = None
    pipeline_recon_max_iterations: int | None = None
    pipeline_analysis_max_iterations: int | None = None
    pipeline_exploit_max_iterations: int | None = None
    pipeline_report_max_iterations: int | None = None
    pipeline_recon_budget: int | None = None
    pipeline_analysis_budget: int | None = None
    pipeline_exploit_budget: int | None = None
    pipeline_report_budget: int | None = None
    pipeline_max_iterations_cap: int | None = None
    pipeline_confidence_threshold_recon: float | None = None
    pipeline_confidence_threshold_analysis: float | None = None
    pipeline_confidence_threshold_exploit: float | None = None
    pipeline_confidence_threshold_report: float | None = None
    vuln_similarity_threshold: float | None = None
    evidence_similarity_threshold: float | None = None
    command_timeout: float | None = None
    per_tool_timeout_seconds: float | None = None
    verification_enabled: bool | None = None
    verification_max_replays: int | None = None
    verification_timeout: int | None = None
    verification_min_certified_confidence: float | None = None
    verification_min_report_confidence: float | None = None
    intelligence_enabled: bool | None = None
    intelligence_adaptive_learning_enabled: bool | None = None
    intelligence_generative_fuzzing_enabled: bool | None = None
    intelligence_target_profiling_enabled: bool | None = None
    intelligence_attack_chain_synthesis_enabled: bool | None = None
    payload_memory_enabled: bool | None = None
    session_persistence_enabled: bool | None = None
    exploration_meaningful_evidence_threshold: float | None = None


class ScanCreate(BaseModel):
    target: str = Field(..., min_length=1, description="Target domain, URL, or IP")
    config: ScanConfigInput | None = Field(None, description="Per-scan config overrides")


class ScanResponse(BaseModel):
    id: str
    target: str
    status: ScanStatus
    phase: str
    config: dict[str, Any] | None = None
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
