# AIRecon Configuration Reference

AIRecon uses a two-layer configuration system:

1. **Global config** (`~/.airecon/config.yaml`) — infrastructure settings (Docker, browser, proxy)
2. **Per-scan config** (database) — LLM provider, agent behavior, pipeline settings

Per-scan settings are passed via the `config` field when creating a scan through the API. Unspecified values fall back to global defaults.

---

## Table of Contents

1. [Global Config (config.yaml)](#1-global-config)
2. [Per-Scan Config (API)](#2-per-scan-config)
3. [LLM Provider Settings](#3-llm-provider-settings)
4. [Agent Behavior](#4-agent-behavior)
5. [Pipeline Settings](#5-pipeline-settings)
6. [Verification Engine](#6-verification-engine)
7. [Intelligence Engine](#7-intelligence-engine)
8. [Environment Variables](#8-environment-variables)

---

## 1. Global Config

Config file: `~/.airecon/config.yaml` (auto-created on first run).

These settings apply to all scans and cannot be overridden per-scan:

```yaml
# Docker Sandbox
docker_image: airecon-sandbox
docker_auto_build: true
docker_memory_limit: 16g
command_timeout: 900.0

# Browser Automation
browser_cdp_port: 9222
browser_cdp_bind_address: "0.0.0.0"
browser_connect_timeout_ms: 3000
browser_navigation_timeout_ms: 60000
browser_action_timeout: 120
browser_page_load_delay: 1.0

# Caido Integration
caido_graphql_url: "http://127.0.0.1:48080/graphql"

# Search
searxng_url: "http://localhost:8080"
searxng_engines: "google,bing,duckduckgo,brave"

# Fuzzer
fuzzer_threads: 5
fuzzer_timeout: 15

# Rate Limiter
rate_limiter_base_delay: 1.0
rate_limiter_max_delay: 60.0
rate_limiter_max_retries: 5
```

---

## 2. Per-Scan Config

Passed via the `config` field in `POST /api/scans`. All fields are optional — unspecified fields use global defaults from `config.yaml`.

```bash
curl -X POST http://localhost:8000/api/scans \
  -H "Content-Type: application/json" \
  -d '{
    "target": "example.com",
    "config": {
      "llm_model": "gpt-4o",
      "llm_base_url": "https://api.openai.com/v1",
      "llm_api_key": "sk-...",
      "agent_recon_mode": "full",
      "agent_max_tool_iterations": 200,
      "allow_destructive_testing": false
    }
  }'
```

---

## 3. LLM Provider Settings

| Key | Default | Description |
|-----|---------|-------------|
| `llm_base_url` | `http://127.0.0.1:11434/v1` | OpenAI-compatible API endpoint |
| `llm_model` | `qwen3.5:122b` | Model name |
| `llm_api_key` | `""` | API key (empty for local providers) |
| `llm_extra_body` | `{}` | Extra body params for provider-specific features |
| `llm_timeout` | `180.0` | Total request timeout (seconds) |
| `llm_chunk_timeout` | `180.0` | Per-chunk stream timeout (seconds) |
| `llm_context_length` | `65536` | Context window size |
| `llm_context_length_small` | `32768` | Context for CTF/summary mode |
| `llm_temperature` | `0.15` | Output randomness (0.0 = deterministic) |
| `llm_max_tokens` | `16384` | Max tokens to generate |
| `llm_enable_thinking` | `true` | Enable reasoning traces |
| `llm_thinking_mode` | `low` | `low` / `medium` / `high` / `adaptive` |
| `llm_supports_thinking` | `true` | Model supports `<think>` blocks |
| `llm_supports_native_tools` | `true` | Model supports native tool calling |
| `llm_max_concurrent_requests` | `1` | Max concurrent LLM requests |
| `llm_num_keep` | `4096` | Protected tokens from KV eviction |
| `llm_repeat_penalty` | `1.05` | Repetition penalty (1.0–1.2) |

### Provider Examples

```json
// Ollama (local)
{ "llm_base_url": "http://localhost:11434/v1", "llm_model": "qwen3.5:35b" }

// OpenAI
{ "llm_base_url": "https://api.openai.com/v1", "llm_model": "gpt-4o", "llm_api_key": "sk-..." }

// OpenRouter
{ "llm_base_url": "https://openrouter.ai/api/v1", "llm_model": "anthropic/claude-3.5-sonnet", "llm_api_key": "sk-or-..." }

// OpenAI reasoning models
{ "llm_model": "o1-preview", "llm_extra_body": {"reasoning_effort": "low"} }
```

---

## 4. Agent Behavior

| Key | Default | Description |
|-----|---------|-------------|
| `agent_recon_mode` | `standard` | `standard` (respect scope) or `full` (auto-expand) |
| `agent_max_tool_iterations` | `600` | Max tool calls per scan |
| `agent_repeat_tool_call_limit` | `2` | Max times to repeat same tool |
| `agent_missing_tool_retry_limit` | `2` | Max retries for missing tool |
| `agent_plan_revision_interval` | `20` | Revise attack plan every N iterations |
| `agent_exploration_mode` | `true` | Enable broader scanning |
| `agent_exploration_intensity` | `0.7` | Aggressiveness (0.5–1.0) |
| `agent_exploration_temperature` | `0.3` | Temperature for exploration |
| `agent_stagnation_threshold` | `3` | Iterations before forcing new approach |
| `agent_tool_diversity_window` | `6` | Window for tool diversity check |
| `agent_max_same_tool_streak` | `2` | Max consecutive same tool calls |
| `agent_phase_creative_temperature` | `0.15` | Temperature for ANALYSIS/EXPLOIT phases |
| `allow_destructive_testing` | `false` | Enable destructive tests (DELETE, etc.) |
| `agent_ctf_max_iterations` | `150` | Max iterations in CTF mode |
| `agent_max_empty_retries` | `4` | Max retries for empty LLM responses |
| `deep_recon_autostart` | `true` | Auto-start deep recon on session start |

### Context Management

| Key | Default | Description |
|-----|---------|-------------|
| `agent_max_conversation_messages` | *auto* | Max messages (auto-calculated from context length) |
| `agent_compression_trigger_ratio` | `0.7` | Compress at X% of max messages |
| `agent_uncompressed_keep_count` | `10` | Keep last N messages uncompressed |
| `agent_llm_compression_num_ctx` | `4096` | Context window for compression |
| `agent_llm_compression_num_predict` | `512` | Output tokens for compression |
| `agent_context_reset_cooldown_seconds` | `45` | Cooldown between context resets |

---

## 5. Pipeline Settings

### Phase Limits

| Key | Default | Description |
|-----|---------|-------------|
| `pipeline_recon_max_iterations` | `500` | Max RECON iterations |
| `pipeline_analysis_max_iterations` | `300` | Max ANALYSIS iterations |
| `pipeline_exploit_max_iterations` | `800` | Max EXPLOIT iterations |
| `pipeline_report_max_iterations` | `100` | Max REPORT iterations |
| `pipeline_max_iterations_cap` | `350` | Hard cap per phase |

### Phase Transitions

| Key | Default | Description |
|-----|---------|-------------|
| `pipeline_recon_min_subdomains` | `3` | Min subdomains before RECON→ANALYSIS |
| `pipeline_recon_min_urls` | `1` | Min URLs before RECON→ANALYSIS |
| `pipeline_recon_soft_timeout` | `30` | Force transition after N iterations |
| `pipeline_analysis_min_injection_points` | `3` | Min injection points for ANALYSIS→EXPLOIT |
| `pipeline_exploit_min_signals` | `2` | Min signals for EXPLOIT→REPORT |

### Confidence Thresholds

| Key | Default | Description |
|-----|---------|-------------|
| `pipeline_confidence_threshold_recon` | `0.6` | Confidence to leave RECON |
| `pipeline_confidence_threshold_analysis` | `0.58` | Confidence to leave ANALYSIS |
| `pipeline_confidence_threshold_exploit` | `0.55` | Confidence to leave EXPLOIT |
| `pipeline_confidence_threshold_report` | `0.5` | Confidence to leave REPORT |

### Tool Budgets

| Key | Default | Description |
|-----|---------|-------------|
| `pipeline_recon_budget` | `10` | Tool budget for RECON |
| `pipeline_analysis_budget` | `30` | Tool budget for ANALYSIS |
| `pipeline_exploit_budget` | `60` | Tool budget for EXPLOIT |
| `pipeline_report_budget` | `0` | Tool budget for REPORT (0 = blocked) |

---

## 6. Verification Engine

Zero false-positive verification system that re-tests findings with independent payloads.

| Key | Default | Description |
|-----|---------|-------------|
| `verification_enabled` | `true` | Enable verification engine |
| `verification_enable_replay` | `true` | Re-test with independent payloads |
| `verification_enable_cross_tool` | `true` | Require 2+ independent signals |
| `verification_enable_negative_test` | `true` | Test clean payloads for calibration |
| `verification_enable_fp_detection` | `true` | Detect dynamic content, WAF, CDN |
| `verification_max_replays` | `3` | Max replay payloads per finding |
| `verification_timeout` | `15` | HTTP timeout per verification request |
| `verification_min_certified_confidence` | `0.90` | Minimum for CERTIFIED tier |
| `verification_min_report_confidence` | `0.75` | Minimum to include in report |

---

## 7. Intelligence Engine

| Key | Default | Description |
|-----|---------|-------------|
| `intelligence_enabled` | `true` | Enable intelligence features |
| `intelligence_adaptive_learning_enabled` | `true` | Adaptive tool performance tracking |
| `intelligence_adaptive_min_observations` | `3` | Min observations before recommendations |
| `intelligence_generative_fuzzing_enabled` | `true` | Genetic algorithm payload evolution |
| `intelligence_generative_population_size` | `50` | Population size for fuzzing |
| `intelligence_generative_max_generations` | `10` | Max evolution generations |
| `intelligence_target_profiling_enabled` | `true` | Auto tech detection + attack surface |
| `intelligence_attack_chain_synthesis_enabled` | `true` | Automatic attack chain building |

### Deduplication

| Key | Default | Description |
|-----|---------|-------------|
| `vuln_similarity_threshold` | `0.7` | Vulnerability dedup (Jaccard) |
| `evidence_similarity_threshold` | `0.70` | Evidence dedup threshold |

---

## 8. Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | *(required)* | PostgreSQL connection string |
| `AIRECON_HOST` | `0.0.0.0` | API bind host |
| `AIRECON_PORT` | `8000` | API bind port |
| `AIRECON_LOG_LEVEL` | `info` | `debug` / `info` / `warning` / `error` |
| `AIRECON_LLM_BASE_URL` | `http://host.docker.internal:11434/v1` | Default LLM endpoint |
| `AIRECON_LLM_MODEL` | `qwen3.5:35b` | Default model name |
| `AIRECON_LLM_API_KEY` | *(empty)* | Default API key |

Any global config key can also be overridden via environment variable with the `AIRECON_` prefix:

```bash
AIRECON_DOCKER_MEMORY_LIMIT=8g python -m airecon
AIRECON_COMMAND_TIMEOUT=600 python -m airecon
```
