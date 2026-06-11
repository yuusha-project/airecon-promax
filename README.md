<h1 align="center">
  <img src="images/logo.png" alt="AIRecon" width="200">
</h1>
<h4 align="center">AI-Powered Autonomous Penetration Testing API</h4>
<p align="center">
  <a href="https://github.com/yuusha-project/airecon-promax/releases"><img src="https://img.shields.io/badge/version-v0.2.0--beta-green.svg">
  <img src="https://img.shields.io/badge/language-python-green.svg">
  <img src="https://img.shields.io/badge/python-3.12%2B-blue.svg">
  <img src="https://img.shields.io/badge/LLM-OpenAI%20Compatible-orange.svg">
  <img src="https://img.shields.io/badge/database-PostgreSQL-blue.svg">
  <a href="https://github.com/yuusha-project/airecon-promax/blob/main/LICENSE">
    <img src="https://img.shields.io/badge/LICENSE-MIT-red.svg">
  </a>
</p>

AIRecon is an autonomous penetration testing platform that combines an **OpenAI-compatible LLM** with a **Kali Linux Docker sandbox**, native **Caido proxy integration**, and a structured **RECON → ANALYSIS → EXPLOIT → REPORT pipeline** — exposed as a REST API with background workers.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        Client (curl / UI)                    │
└──────────────────────────┬──────────────────────────────────┘
                           │ REST API
┌──────────────────────────▼──────────────────────────────────┐
│                    FastAPI Server (:8000)                     │
│  ┌──────────┐  ┌───────────┐  ┌──────────┐  ┌───────────┐  │
│  │ /scans   │  │ /findings │  │ /health  │  │ /docs     │  │
│  └────┬─────┘  └───────────┘  └──────────┘  └───────────┘  │
│       │ enqueue                                                │
│  ┌────▼──────────────────────────────────────────────────┐   │
│  │              Worker (async task queue)                  │   │
│  │  AgentLoop → LLM Client → Docker Sandbox → Tools      │   │
│  └──────────────────────┬────────────────────────────────┘   │
└──────────────────────────┼────────────────────────────────────┘
                           │
              ┌────────────▼────────────┐
              │  PostgreSQL (Prisma)    │
              │  Scans, Findings,       │
              │  Subdomains, Ports,     │
              │  ToolCalls              │
              └─────────────────────────┘
```

## Quick Start

```bash
# Clone
git clone https://github.com/yuusha-project/airecon-promax.git
cd airecon-promax

# Configure
cp .env.example .env
# Edit .env — set your LLM provider

# Start with Docker Compose
docker compose up --build
```

API available at `http://localhost:8000`. Swagger docs at `http://localhost:8000/docs`.

### One-line Install

```bash
curl -fsSL https://raw.githubusercontent.com/yuusha-project/airecon-promax/feat/api/scripts/install.sh | bash
```

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/scans` | Create a new scan |
| `GET` | `/api/scans` | List scans (filter by status/target) |
| `GET` | `/api/scans/{id}` | Get scan details |
| `POST` | `/api/scans/{id}/start` | Start scan (enqueues worker) |
| `POST` | `/api/scans/{id}/stop` | Cancel running scan |
| `DELETE` | `/api/scans/{id}` | Delete scan and all results |
| `GET` | `/api/scans/{id}/findings` | List vulnerabilities |
| `GET` | `/api/scans/{id}/subdomains` | List discovered subdomains |
| `GET` | `/api/scans/{id}/ports` | List open ports |
| `GET` | `/api/scans/{id}/tool-calls` | List tool execution log |
| `GET` | `/api/health` | Health check (DB + LLM) |
| `GET` | `/docs` | Swagger UI |
| `GET` | `/redoc` | ReDoc documentation |

### Create & Start a Scan

```bash
# Create scan with custom config
curl -X POST http://localhost:8000/api/scans \
  -H "Content-Type: application/json" \
  -d '{
    "target": "example.com",
    "config": {
      "llm_model": "qwen3.5:35b",
      "agent_recon_mode": "full",
      "agent_max_tool_iterations": 200
    }
  }'

# Start the scan
curl -X POST http://localhost:8000/api/scans/<scan_id>/start

# Check findings
curl http://localhost:8000/api/scans/<scan_id>/findings
```

---

## Per-Scan Configuration

Scan parameters are stored in the database and applied per-scan. Override any of these when creating a scan:

### LLM Provider
| Key | Default | Description |
|-----|---------|-------------|
| `llm_base_url` | `http://127.0.0.1:11434/v1` | OpenAI-compatible API endpoint |
| `llm_model` | `qwen3.5:122b` | Model name |
| `llm_api_key` | `""` | API key (empty for local providers) |
| `llm_temperature` | `0.15` | Output randomness (0.0–1.0) |
| `llm_max_tokens` | `16384` | Max tokens to generate |
| `llm_context_length` | `65536` | Context window size |
| `llm_enable_thinking` | `true` | Enable reasoning traces |
| `llm_thinking_mode` | `low` | `low` / `medium` / `high` / `adaptive` |

### Agent Behavior
| Key | Default | Description |
|-----|---------|-------------|
| `agent_recon_mode` | `standard` | `standard` or `full` |
| `agent_max_tool_iterations` | `600` | Max tool calls per scan |
| `agent_exploration_mode` | `true` | Enable broader scanning |
| `agent_exploration_intensity` | `0.7` | Exploration aggressiveness (0.5–1.0) |
| `agent_stagnation_threshold` | `3` | Iterations before forcing new approach |
| `allow_destructive_testing` | `false` | Enable destructive tests |

### Pipeline
| Key | Default | Description |
|-----|---------|-------------|
| `pipeline_recon_max_iterations` | `500` | Max RECON phase iterations |
| `pipeline_exploit_max_iterations` | `800` | Max EXPLOIT phase iterations |
| `pipeline_confidence_threshold_recon` | `0.6` | Confidence to transition from RECON |

Global settings (Docker, browser, proxy) stay in `~/.airecon/config.yaml`.

---

## LLM Provider Support

Any OpenAI-compatible endpoint works:

| Provider | `llm_base_url` | `llm_api_key` |
|----------|----------------|---------------|
| **Ollama** (local) | `http://localhost:11434/v1` | *(empty)* |
| **OpenAI** | `https://api.openai.com/v1` | `sk-...` |
| **OpenRouter** | `https://openrouter.ai/api/v1` | `sk-or-...` |
| **Groq** | `https://api.groq.com/openai/v1` | `gsk_...` |
| **Together AI** | `https://api.together.xyz/v1` | Your key |
| **vLLM** (self-hosted) | `http://your-server:8000/v1` | *(empty)* |
| **LiteLLM** (proxy) | `http://localhost:4000/v1` | Your key |

### Model Requirements

> **Tool calling support is REQUIRED.** The model must support native function/tool calling.

| Model | VRAM | Notes |
|-------|------|-------|
| **Qwen3.5 122B** | 48+ GB | Best quality, most reliable |
| **Qwen3.5 35B** | 20 GB | **Recommended for most users** |
| **GPT-4o** | Cloud | Excellent tool calling |
| **Claude 3.5 Sonnet** | Cloud | Strong reasoning |
| **Qwen3.5 9B** | 6 GB | **Minimum viable** — expect errors |

---

## Installation

### Docker Compose (Recommended)

```bash
git clone https://github.com/yuusha-project/airecon-promax.git
cd airecon-promax
cp .env.example .env
# Edit .env to set your LLM provider
docker compose up --build
```

Services:
- **api** — FastAPI server on port 8000
- **db** — PostgreSQL 16 on port 5432
- **migrate** — Auto-runs Prisma migrations

### Local Development

```bash
git clone https://github.com/yuusha-project/airecon-promax.git
cd airecon-promax

# Create venv
python3.12 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Set up database
export DATABASE_URL="postgresql://user:pass@localhost:5432/airecon"
python -m prisma generate
python -m prisma db push

# Start API
python -m airecon
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | *(required)* | PostgreSQL connection string |
| `AIRECON_HOST` | `0.0.0.0` | API bind host |
| `AIRECON_PORT` | `8000` | API bind port |
| `AIRECON_LOG_LEVEL` | `info` | Log level |
| `AIRECON_LLM_BASE_URL` | `http://host.docker.internal:11434/v1` | LLM endpoint |
| `AIRECON_LLM_MODEL` | `qwen3.5:35b` | LLM model name |
| `AIRECON_LLM_API_KEY` | *(empty)* | LLM API key |

---

## Pipeline

```
RECON → ANALYSIS → EXPLOIT → REPORT
```

Each phase has specific objectives, recommended tools, and automatic transition criteria. Phase enforcement is **soft** — the agent is guided but never blocked.

- **RECON** — Subdomain enumeration, port scanning, technology detection, URL discovery
- **ANALYSIS** — Injection point identification, parameter fuzzing, WAF detection
- **EXPLOIT** — Vulnerability exploitation, proof-of-concept generation, chain building
- **REPORT** — Vulnerability reporting with evidence, remediation, and severity scoring

---

## Project Structure

```
airecon-promax/
├── airecon/
│   ├── __main__.py          # Entry point (uvicorn)
│   ├── api/                 # FastAPI REST API
│   │   ├── app.py           # App factory + lifespan
│   │   ├── deps.py          # Prisma DB client
│   │   ├── schemas.py       # Pydantic models
│   │   └── routes/          # Route handlers
│   ├── worker/              # Background job processor
│   │   └── runner.py        # Scan job runner
│   ├── proxy/               # Core engine
│   │   ├── llm_client.py    # OpenAI-compatible LLM client
│   │   ├── agent/           # Agent loop, pipeline, executors
│   │   ├── config.py        # Configuration system
│   │   ├── docker.py        # Kali sandbox management
│   │   └── ...              # Tools, fuzzers, browser, MCP
│   └── _version.py          # Version info
├── prisma/
│   └── schema.prisma        # PostgreSQL schema
├── docker-compose.yml       # Service orchestration
├── Dockerfile               # API container image
├── scripts/
│   └── install.sh           # Installation script
└── .env.example             # Environment template
```

---

## Troubleshooting

**API not starting** — Check database connectivity:
```bash
docker compose logs db
docker compose logs api
```

**LLM connection failed** — Verify the endpoint is reachable from the container:
```bash
docker compose exec api curl -s http://host.docker.internal:11434/v1/models
```

**Database migration failed** — Reset and re-migrate:
```bash
docker compose down -v
docker compose up --build
```

**Worker stuck** — Check scan status and cancel if needed:
```bash
curl http://localhost:8000/api/scans/<id>
curl -X POST http://localhost:8000/api/scans/<id>/stop
```

---

## Contributing

Issues and PRs are welcome. If you report a bug, include logs, config, and minimal steps to reproduce.

## Responsible Use

AIRecon is for authorized security testing only. Always obtain explicit permission and follow applicable laws and program scope.

## License

See [LICENSE](LICENSE).
