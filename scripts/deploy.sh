#!/usr/bin/env bash
set -euo pipefail

GREEN='\033[0;32m'
CYAN='\033[0;36m'
RED='\033[0;31m'
BOLD='\033[1m'
MUTED='\033[0;2m'
NC='\033[0m'

REPO="https://github.com/yuusha-project/airecon-promax.git"
BRANCH="feat/api"
DEPLOY_DIR="$HOME/pentest"

ok()   { echo -e "  ${GREEN}✓${NC} $*"; }
info() { echo -e "  ${CYAN}▸${NC} $*"; }
fail() { echo -e "  ${RED}✗${NC} $*"; exit 1; }

echo ""
echo -e "  ${BOLD}AIRecon Deployment${NC}"
echo -e "  ${MUTED}Target: ${DEPLOY_DIR}${NC}"
echo ""

# ── Check prerequisites ──────────────────────────────────────────────────

command -v docker &>/dev/null || fail "Docker is required. Install: curl -fsSL https://get.docker.com | sh"
command -v git &>/dev/null || fail "Git is required"

if ! docker compose version &>/dev/null 2>&1; then
    if ! docker-compose version &>/dev/null 2>&1; then
        fail "Docker Compose is required. Install: apt install docker-compose-plugin"
    fi
    COMPOSE="docker-compose"
else
    COMPOSE="docker compose"
fi

ok "Docker + Compose found"

# ── Clone or update repo ─────────────────────────────────────────────────

if [ -d "$DEPLOY_DIR/.git" ]; then
    info "Updating existing repo..."
    cd "$DEPLOY_DIR"
    git fetch origin
    git checkout "$BRANCH" 2>/dev/null || git checkout -b "$BRANCH" "origin/$BRANCH"
    git pull origin "$BRANCH"
    ok "Repo updated"
else
    info "Cloning repository..."
    mkdir -p "$(dirname "$DEPLOY_DIR")"
    git clone --branch "$BRANCH" "$REPO" "$DEPLOY_DIR"
    cd "$DEPLOY_DIR"
    ok "Repo cloned"
fi

# ── Configure .env ───────────────────────────────────────────────────────

if [ ! -f .env ]; then
    cp .env.example .env
    ok "Created .env from .env.example"

    # Generate a strong random password for PostgreSQL
    PG_PASS=$(openssl rand -base64 24 | tr -d '/+=' | head -c 32)
    sed -i "s/POSTGRES_PASSWORD=airecon/POSTGRES_PASSWORD=${PG_PASS}/" .env
    sed -i "s|DATABASE_URL=.*|DATABASE_URL=postgresql://airecon:${PG_PASS}@db:5432/airecon|" docker-compose.yml 2>/dev/null || true
    ok "Generated random PostgreSQL password"

    echo ""
    echo -e "  ${BOLD}Configure LLM provider:${NC}"
    echo ""
    echo -e "    ${CYAN}1)${NC} Ollama (local, on this server)"
    echo -e "    ${CYAN}2)${NC} OpenAI"
    echo -e "    ${CYAN}3)${NC} OpenRouter"
    echo -e "    ${CYAN}4)${NC} Custom endpoint"
    echo ""
    read -rp "  Choose [1/2/3/4]: " llm_choice

    case "$llm_choice" in
        1)
            sed -i 's|AIRECON_LLM_BASE_URL=.*|AIRECON_LLM_BASE_URL=http://host.docker.internal:11434/v1|' .env
            read -rp "  Model name [qwen3.5:35b]: " model
            model="${model:-qwen3.5:35b}"
            sed -i "s|AIRECON_LLM_MODEL=.*|AIRECON_LLM_MODEL=${model}|" .env
            sed -i 's|AIRECON_LLM_API_KEY=.*|AIRECON_LLM_API_KEY=|' .env
            ;;
        2)
            sed -i 's|AIRECON_LLM_BASE_URL=.*|AIRECON_LLM_BASE_URL=https://api.openai.com/v1|' .env
            read -rp "  OpenAI API key: " api_key
            sed -i "s|AIRECON_LLM_API_KEY=.*|AIRECON_LLM_API_KEY=${api_key}|" .env
            read -rp "  Model [gpt-4o]: " model
            model="${model:-gpt-4o}"
            sed -i "s|AIRECON_LLM_MODEL=.*|AIRECON_LLM_MODEL=${model}|" .env
            ;;
        3)
            sed -i 's|AIRECON_LLM_BASE_URL=.*|AIRECON_LLM_BASE_URL=https://openrouter.ai/api/v1|' .env
            read -rp "  OpenRouter API key: " api_key
            sed -i "s|AIRECON_LLM_API_KEY=.*|AIRECON_LLM_API_KEY=${api_key}|" .env
            read -rp "  Model [anthropic/claude-3.5-sonnet]: " model
            model="${model:-anthropic/claude-3.5-sonnet}"
            sed -i "s|AIRECON_LLM_MODEL=.*|AIRECON_LLM_MODEL=${model}|" .env
            ;;
        4)
            read -rp "  Base URL: " base_url
            read -rp "  API key (empty for none): " api_key
            read -rp "  Model name: " model
            sed -i "s|AIRECON_LLM_BASE_URL=.*|AIRECON_LLM_BASE_URL=${base_url}|" .env
            sed -i "s|AIRECON_LLM_API_KEY=.*|AIRECON_LLM_API_KEY=${api_key}|" .env
            sed -i "s|AIRECON_LLM_MODEL=.*|AIRECON_LLM_MODEL=${model}|" .env
            ;;
        *)
            echo -e "  ${MUTED}Using defaults (Ollama local)${NC}"
            ;;
    esac
    ok "LLM provider configured"
else
    ok ".env already exists (skipping setup)"
fi

# ── Update docker-compose DB password from .env ─────────────────────────

PG_USER=$(grep -oP 'POSTGRES_USER=\K.*' .env 2>/dev/null || echo "airecon")
PG_PASS=$(grep -oP 'POSTGRES_PASSWORD=\K.*' .env 2>/dev/null || echo "airecon")
PG_DB=$(grep -oP 'POSTGRES_DB=\K.*' .env 2>/dev/null || echo "airecon")

# Ensure docker-compose uses the .env password
sed -i "s|postgresql://[^:]*:[^@]*@db:5432/.*|postgresql://${PG_USER}:${PG_PASS}@db:5432/${PG_DB}|g" docker-compose.yml 2>/dev/null || true

# ── Build and start ──────────────────────────────────────────────────────

echo ""
info "Building and starting services..."
echo ""

$COMPOSE down 2>/dev/null || true
$COMPOSE up --build -d migrate || fail "Database migration failed"
ok "Database migrated"

$COMPOSE up --build -d db api || fail "Failed to start services"
ok "Services started"

# Build Kali sandbox image (required for tool execution)
if ! docker image inspect airecon-sandbox &>/dev/null; then
    echo ""
    info "Building Kali sandbox image (first time — takes 10-20 minutes)..."
    docker build -t airecon-sandbox airecon/containers/ \
        || echo -e "  ${RED}✗${NC} Kali sandbox build failed — agent cannot execute tools"
    ok "Kali sandbox image built"
else
    ok "Kali sandbox image exists"
fi

# ── Wait for health ──────────────────────────────────────────────────────

API_PORT=$(grep -oP 'API_PORT=\K[0-9]+' .env 2>/dev/null || echo 8000)

echo ""
info "Waiting for API to become healthy..."

for i in $(seq 1 30); do
    if curl -sf "http://localhost:${API_PORT}/api/health" &>/dev/null; then
        ok "API is healthy"
        break
    fi
    if [ "$i" -eq 30 ]; then
        echo -e "  ${RED}✗${NC} API not healthy after 30s"
        echo -e "  ${MUTED}Check logs: $COMPOSE logs api${NC}"
    fi
    sleep 1
done

# ── Print status ─────────────────────────────────────────────────────────

echo ""
echo -e "  ${BOLD}${GREEN}Deployment complete!${NC}"
echo ""
echo -e "  ${MUTED}API:${NC}          http://$(hostname -I | awk '{print $1}'):${API_PORT}"
echo -e "  ${MUTED}Swagger:${NC}      http://$(hostname -I | awk '{print $1}'):${API_PORT}/docs"
echo -e "  ${MUTED}Health:${NC}       curl http://localhost:${API_PORT}/api/health"
echo ""
echo -e "  ${MUTED}Management:${NC}"
echo -e "    ${CYAN}$COMPOSE logs -f api${NC}     — view logs"
echo -e "    ${CYAN}$COMPOSE restart api${NC}      — restart API"
echo -e "    ${CYAN}$COMPOSE down${NC}             — stop all services"
echo -e "    ${CYAN}$COMPOSE down -v${NC}          — stop + delete data"
echo -e "    ${CYAN}git pull && $COMPOSE up --build -d${NC}  — update"
echo ""
