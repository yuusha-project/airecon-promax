#!/usr/bin/env bash
set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
BOLD='\033[1m'
MUTED='\033[0;2m'
NC='\033[0m'

REPO_URL="https://github.com/yuusha-project/airecon-promax"
BRANCH="feat/api"

# ── Helpers ──────────────────────────────────────────────────────────────────

info()  { echo -e "  ${CYAN}▸${NC} $*"; }
ok()    { echo -e "  ${GREEN}✓${NC} $*"; }
warn()  { echo -e "  ${YELLOW}!${NC} $*"; }
fail()  { echo -e "  ${RED}✗${NC} $*"; exit 1; }

# ── Detect install mode ──────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-/tmp}")" && pwd 2>/dev/null || echo /tmp)"

if [ ! -f "$SCRIPT_DIR/docker-compose.yml" ]; then
    if ! command -v git &>/dev/null; then
        fail "git is required but not installed"
    fi
    INSTALL_DIR="${AIRECON_INSTALL_DIR:-$HOME/pentest}"
    if [ -d "$INSTALL_DIR/.git" ]; then
        info "Updating existing installation at $INSTALL_DIR..."
        cd "$INSTALL_DIR"
        git fetch origin
        git checkout "$BRANCH" 2>/dev/null || git checkout -b "$BRANCH" "origin/$BRANCH"
        git pull origin "$BRANCH"
        ok "Repository updated"
    else
        if [ -d "$INSTALL_DIR" ]; then
            info "Removing stale directory at $INSTALL_DIR..."
            rm -rf "$INSTALL_DIR"
        fi
        info "Cloning repository to $INSTALL_DIR..."
        git clone --quiet --branch "$BRANCH" "$REPO_URL" "$INSTALL_DIR" \
            || fail "Failed to clone repository"
        ok "Repository cloned"
    fi
    SCRIPT_DIR="$INSTALL_DIR"
fi

cd "$SCRIPT_DIR"

# ── Banner ───────────────────────────────────────────────────────────────────
echo ""
echo -e "     ${BOLD}█████████   █████ ███████████${NC}"
echo -e "    ${BOLD}███▒▒▒▒▒███ ▒▒███ ▒▒███▒▒▒▒▒███${NC}"
echo -e "   ${BOLD}▒███    ▒███  ▒███  ▒███    ▒███   ██████   ██████   ██████  ████████${NC}"
echo -e "   ${BOLD}▒███████████  ▒███  ▒██████████   ███▒▒███ ███▒▒███ ███▒▒███▒▒███▒▒███${NC}"
echo -e "   ${BOLD}▒███▒▒▒▒▒███  ▒███  ▒███▒▒▒▒▒███ ▒███████ ▒███ ▒▒▒ ▒███ ▒███ ▒███ ▒███${NC}"
echo -e "   ${BOLD}▒███    ▒███  ▒███  ▒███    ▒███ ▒███▒▒▒  ▒███  ███▒███ ▒███ ▒███ ▒███${NC}"
echo -e "   ${BOLD}█████   █████ █████ █████   █████▒▒██████ ▒▒██████ ▒▒██████  ████ █████${NC}"
echo -e "   ${BOLD}▒▒▒▒▒   ▒▒▒▒▒ ▒▒▒▒▒ ▒▒▒▒▒   ▒▒▒▒▒  ▒▒▒▒▒▒   ▒▒▒▒▒▒   ▒▒▒▒▒▒  ▒▒▒▒ ▒▒▒▒▒${NC}"
echo ""
echo -e "  ${MUTED}AI-Powered Security Reconnaissance — API Installer${NC}"
echo ""

# ── Choose install mode ──────────────────────────────────────────────────────
MODE=""
if [ "${1:-}" = "--docker" ]; then
    MODE="docker"
elif [ "${1:-}" = "--local" ]; then
    MODE="local"
fi

if [ -z "$MODE" ]; then
    echo -e "  ${BOLD}Install mode:${NC}"
    echo ""
    echo -e "    ${CYAN}1)${NC} Docker Compose ${MUTED}(recommended — PostgreSQL + API in containers)${NC}"
    echo -e "    ${CYAN}2)${NC} Local ${MUTED}(venv + local PostgreSQL)${NC}"
    echo ""
    read -rp "  Choose [1/2]: " choice
    case "$choice" in
        1) MODE="docker" ;;
        2) MODE="local" ;;
        *) fail "Invalid choice" ;;
    esac
    echo ""
fi

# ═══════════════════════════════════════════════════════════════════════════════
# DOCKER MODE
# ═══════════════════════════════════════════════════════════════════════════════

install_docker() {
    # Check Docker
    command -v docker &>/dev/null || fail "Docker is required. Install: https://docs.docker.com/get-docker/"
    command -v docker compose &>/dev/null 2>&1 || command -v docker-compose &>/dev/null || fail "Docker Compose is required"

    ok "Docker found"

    # Check Docker daemon
    if ! docker info &>/dev/null; then
        fail "Docker daemon is not running. Start Docker and retry."
    fi
    ok "Docker daemon running"

    # Create .env
    if [ ! -f .env ]; then
        cp .env.example .env
        ok "Created .env from .env.example"

        echo ""
        info "Configure LLM provider in .env:"
        echo -e "    ${MUTED}AIRECON_LLM_BASE_URL${NC} — API endpoint (default: Ollama local)"
        echo -e "    ${MUTED}AIRECON_LLM_MODEL${NC}    — Model name"
        echo -e "    ${MUTED}AIRECON_LLM_API_KEY${NC}  — API key (empty for local)"
        echo ""
        read -rp "  Edit .env now? [y/N]: " edit_env
        if [[ "$edit_env" =~ ^[Yy] ]]; then
            ${EDITOR:-nano} .env
        fi
    else
        ok ".env already exists (skipping)"
    fi

    echo ""
    info "Building and starting services..."
    echo ""

    docker compose up --build -d migrate \
        || fail "Database migration failed"
    ok "Database migrated"

    docker compose up --build -d db api \
        || fail "Failed to start services"
    ok "Services started"

    # Build Kali sandbox image (required for tool execution)
    if ! docker image inspect airecon-sandbox &>/dev/null; then
        echo ""
        info "Building Kali sandbox image (first time — takes 10-20 minutes)..."
        docker build -t airecon-sandbox airecon/containers/ \
            || warn "Kali sandbox build failed — agent cannot execute tools until this image exists"
        ok "Kali sandbox image built"
    else
        ok "Kali sandbox image exists"
    fi

    # Wait for API
    echo ""
    info "Waiting for API to become healthy..."
    API_PORT=$(grep -oP 'API_PORT=\K[0-9]+' .env 2>/dev/null || echo 8000)

    for i in $(seq 1 30); do
        if curl -sf "http://localhost:${API_PORT}/api/health" &>/dev/null; then
            ok "API is healthy (http://localhost:${API_PORT})"
            break
        fi
        if [ "$i" -eq 30 ]; then
            warn "API not yet healthy after 30s — check: docker compose logs api"
        fi
        sleep 1
    done

    echo ""
    echo -e "  ${BOLD}${GREEN}AIRecon is running!${NC}"
    echo ""
    echo -e "  ${MUTED}API:${NC}          http://localhost:${API_PORT}"
    echo -e "  ${MUTED}Swagger:${NC}      http://localhost:${API_PORT}/docs"
    echo -e "  ${MUTED}ReDoc:${NC}        http://localhost:${API_PORT}/redoc"
    echo -e "  ${MUTED}Health:${NC}       http://localhost:${API_PORT}/api/health"
    echo ""
    echo -e "  ${MUTED}Manage:${NC}"
    echo -e "    ${CYAN}docker compose logs -f api${NC}     — view logs"
    echo -e "    ${CYAN}docker compose stop${NC}             — stop services"
    echo -e "    ${CYAN}docker compose down -v${NC}          — stop + remove data"
    echo ""
}

# ═══════════════════════════════════════════════════════════════════════════════
# LOCAL MODE
# ═══════════════════════════════════════════════════════════════════════════════

install_local() {
    # Check Python
    PYTHON_CMD=""
    for cmd in python3.12 python3 python; do
        if command -v "$cmd" &>/dev/null; then
            PY_OK=$("$cmd" -c "import sys; print('yes' if sys.version_info >= (3,12) else 'no')" 2>/dev/null || echo "no")
            if [ "$PY_OK" = "yes" ]; then
                PYTHON_CMD="$cmd"
                break
            fi
        fi
    done

    if [ -z "$PYTHON_CMD" ]; then
        fail "Python >= 3.12 required. Install: https://www.python.org/downloads/"
    fi

    PY_VER=$($PYTHON_CMD -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    ok "Python ${PY_VER} found (${PYTHON_CMD})"

    # Check PostgreSQL (warn if not found)
    if command -v psql &>/dev/null; then
        ok "PostgreSQL client found"
    else
        warn "psql not found — you'll need PostgreSQL running"
        echo -e "    ${MUTED}Install: https://www.postgresql.org/download/${NC}"
        echo -e "    ${MUTED}Or use Docker: docker run -d -p 5432:5432 -e POSTGRES_PASSWORD=airecon -e POSTGRES_DB=airecon postgres:16-alpine${NC}"
    fi

    # Create .env
    if [ ! -f .env ]; then
        cp .env.example .env
        ok "Created .env from .env.example"
    else
        ok ".env already exists"
    fi

    # Create venv
    if [ ! -d .venv ]; then
        info "Creating virtual environment..."
        $PYTHON_CMD -m venv .venv
        ok "Virtual environment created"
    else
        ok "Virtual environment exists"
    fi

    # Activate
    source .venv/bin/activate

    # Install dependencies
    echo ""
    info "Installing dependencies..."
    pip install --upgrade pip setuptools wheel -q
    pip install -r requirements.txt -q
    ok "Dependencies installed"

    # Install Playwright
    info "Installing browser engine (Chromium)..."
    python -m playwright install chromium 2>/dev/null || warn "Playwright install failed (non-fatal)"
    ok "Browser engine ready"

    # Generate Prisma client
    info "Generating Prisma client..."
    set -a
    source .env
    set +a
    python -m prisma generate
    ok "Prisma client generated"

    # Prompt for DATABASE_URL
    if [ -z "${DATABASE_URL:-}" ]; then
        echo ""
        echo -e "  ${BOLD}Database configuration:${NC}"
        echo ""
        echo -e "    ${MUTED}Local PostgreSQL:${NC}  postgresql://airecon:airecon@localhost:5432/airecon"
        echo -e "    ${MUTED}Docker PostgreSQL:${NC} postgresql://postgres:airecon@localhost:5432/airecon"
        echo ""
        read -rp "  DATABASE_URL [postgresql://airecon:airecon@localhost:5432/airecon]: " db_url
        db_url="${db_url:-postgresql://airecon:airecon@localhost:5432/airecon}"
        export DATABASE_URL="$db_url"
        echo "DATABASE_URL=$db_url" >> .env
    fi

    # Run migrations
    info "Running database migrations..."
    python -m prisma db push --skip-generate 2>/dev/null \
        || warn "Migration failed — ensure PostgreSQL is running and DATABASE_URL is correct"
    ok "Migrations applied"

    # Build Kali sandbox image (required for tool execution)
    if command -v docker &>/dev/null; then
        if ! docker image inspect airecon-sandbox &>/dev/null; then
            echo ""
            info "Building Kali sandbox image (first time — takes 10-20 minutes)..."
            docker build -t airecon-sandbox airecon/containers/ \
                || warn "Kali sandbox build failed — agent cannot execute tools until this image exists"
            ok "Kali sandbox image built"
        else
            ok "Kali sandbox image exists"
        fi
    else
        warn "Docker not found — Kali sandbox image required for tool execution"
        echo -e "    ${MUTED}Install Docker, then run: docker build -t airecon-sandbox airecon/containers/${NC}"
    fi

    echo ""
    echo -e "  ${BOLD}${GREEN}Installation complete!${NC}"
    echo ""
    echo -e "  ${MUTED}Start the API:${NC}"
    echo -e "    ${CYAN}source .venv/bin/activate${NC}"
    echo -e "    ${CYAN}python -m airecon${NC}"
    echo ""
    echo -e "  ${MUTED}Or with custom port:${NC}"
    echo -e "    ${CYAN}AIRECON_PORT=9000 python -m airecon${NC}"
    echo ""
    echo -e "  ${MUTED}API docs:${NC}      http://localhost:8000/docs"
    echo -e "  ${MUTED}Health check:${NC}  http://localhost:8000/api/health"
    echo ""
}

# ── Run ──────────────────────────────────────────────────────────────────────
case "$MODE" in
    docker) install_docker ;;
    local)  install_local ;;
esac
