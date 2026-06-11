# AIRecon Installation Guide

## Table of Contents

1. [System Requirements](#1-system-requirements)
2. [Docker Compose Install (Recommended)](#2-docker-compose-install)
3. [Local Development Install](#3-local-development-install)
4. [LLM Provider Setup](#4-llm-provider-setup)
5. [Verify Installation](#5-verify-installation)
6. [Updating](#6-updating)
7. [Troubleshooting](#7-troubleshooting)

---

## 1. System Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| OS | Linux, macOS, WSL2 | Linux |
| Python | 3.12+ | 3.12+ |
| Docker | 20.10+ | 24+ with Compose v2 |
| PostgreSQL | 15+ (or via Docker) | 16 |
| RAM | 8 GB | 32 GB+ |
| Storage | 20 GB free | 50 GB+ |
| GPU | Optional (for local LLM) | 20 GB+ VRAM |

---

## 2. Docker Compose Install

The fastest way to get started. All services (API, PostgreSQL, migrations) run in containers.

```bash
# Clone repository
git clone https://github.com/yuusha-project/airecon-promax.git
cd airecon-promax

# Create environment config
cp .env.example .env

# Edit .env to configure your LLM provider
nano .env

# Start all services
docker compose up --build
```

Services started:
- **api** — FastAPI server on port 8000
- **db** — PostgreSQL 16 on port 5432
- **migrate** — Runs Prisma database migrations (one-shot)

### Using the Installer Script

```bash
curl -fsSL https://raw.githubusercontent.com/yuusha-project/airecon-promax/feat/api/scripts/install.sh | bash
```

Select option **1** (Docker Compose) when prompted.

---

## 3. Local Development Install

For development or when you need direct access to the Python environment.

### Prerequisites

- Python 3.12+
- PostgreSQL 15+ running locally or accessible via network
- Docker (for Kali sandbox container)

### Steps

```bash
# Clone repository
git clone https://github.com/yuusha-project/airecon-promax.git
cd airecon-promax

# Create virtual environment
python3.12 -m venv .venv
source .venv/bin/activate

# Install Python dependencies
pip install -r requirements.txt

# Install Playwright browser engine
python -m playwright install chromium

# Configure database URL
export DATABASE_URL="postgresql://user:password@localhost:5432/airecon"

# Generate Prisma client
python -m prisma generate

# Run database migrations
python -m prisma db push

# Start the API server
python -m airecon
```

### Quick PostgreSQL Setup (Docker)

If you don't have PostgreSQL installed:

```bash
docker run -d \
  --name airecon-db \
  -p 5432:5432 \
  -e POSTGRES_USER=airecon \
  -e POSTGRES_PASSWORD=airecon \
  -e POSTGRES_DB=airecon \
  postgres:16-alpine
```

Then set:
```bash
export DATABASE_URL="postgresql://airecon:airecon@localhost:5432/airecon"
```

---

## 4. LLM Provider Setup

AIRecon works with any OpenAI-compatible API. Configure via `.env` (Docker) or environment variables (local).

### Ollama (Local, Free)

```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Pull a model
ollama pull qwen3.5:35b

# Configure .env
AIRECON_LLM_BASE_URL=http://host.docker.internal:11434/v1   # Docker mode
# or
AIRECON_LLM_BASE_URL=http://127.0.0.1:11434/v1              # Local mode
AIRECON_LLM_MODEL=qwen3.5:35b
AIRECON_LLM_API_KEY=
```

### OpenAI

```bash
AIRECON_LLM_BASE_URL=https://api.openai.com/v1
AIRECON_LLM_MODEL=gpt-4o
AIRECON_LLM_API_KEY=sk-...
```

### OpenRouter

```bash
AIRECON_LLM_BASE_URL=https://openrouter.ai/api/v1
AIRECON_LLM_MODEL=anthropic/claude-3.5-sonnet
AIRECON_LLM_API_KEY=sk-or-...
```

### Other Providers

Any endpoint that implements the OpenAI Chat Completions API (`/v1/chat/completions`):

| Provider | Base URL |
|----------|----------|
| Groq | `https://api.groq.com/openai/v1` |
| Together AI | `https://api.together.xyz/v1` |
| Fireworks | `https://api.fireworks.ai/inference/v1` |
| vLLM (self-hosted) | `http://your-server:8000/v1` |
| LiteLLM (proxy) | `http://localhost:4000/v1` |

### Model Requirements

> **Tool calling support is REQUIRED.** The model must support native function/tool calling.

| Model Size | Quality | Notes |
|------------|---------|-------|
| ≥32B | Reliable | Good tool calling accuracy |
| 8B–14B | Usable | Expect 20–40% tool call errors |
| <8B | Unreliable | Not recommended for serious testing |

---

## 5. Verify Installation

```bash
# Health check
curl http://localhost:8000/api/health

# Expected response:
# {"status":"ok","version":"0.2.0b0","database":"ok","llm":"..."}

# Create a test scan
curl -X POST http://localhost:8000/api/scans \
  -H "Content-Type: application/json" \
  -d '{"target": "example.com"}'

# Open API docs in browser
# http://localhost:8000/docs
```

---

## 6. Updating

### Docker Compose

```bash
cd airecon-promax
git pull
docker compose up --build
```

### Local

```bash
cd airecon-promax
git pull
source .venv/bin/activate
pip install -r requirements.txt
python -m prisma generate
python -m prisma db push
```

---

## 7. Troubleshooting

### API not starting

```bash
# Check logs
docker compose logs api

# Common causes:
# - Database not ready → wait for db healthcheck
# - Port 8000 in use → change API_PORT in .env
# - Missing DATABASE_URL → check .env file
```

### LLM connection failed

```bash
# Test from inside the container
docker compose exec api curl -s http://host.docker.internal:11434/v1/models

# If using Ollama on Linux, ensure it listens on all interfaces:
OLLAMA_HOST=0.0.0.0 ollama serve
```

### Database migration failed

```bash
# Reset and re-migrate
docker compose down -v
docker compose up --build

# Or manually:
docker compose exec api python -m prisma db push
```

### Docker sandbox not building

```bash
# Build manually
docker build -t airecon-sandbox airecon/containers/
```

### Playwright browser missing (local mode)

```bash
source .venv/bin/activate
python -m playwright install chromium
```

### Ollama OOM errors

Reduce context window in scan config:
```bash
curl -X POST http://localhost:8000/api/scans \
  -H "Content-Type: application/json" \
  -d '{
    "target": "example.com",
    "config": {
      "llm_context_length": 32768,
      "llm_max_tokens": 8192
    }
  }'
```
