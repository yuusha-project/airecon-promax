"""Deploy airecon-promax to remote server via SSH."""
import paramiko
import sys
import time

HOST = "143.14.13.18"
PORT = 50070
USER = "ubuntu"
PASS = "vhQ2JIVedWa5"
DEPLOY_DIR = "$HOME/pentest"
REPO = "https://github.com/yuusha-project/airecon-promax.git"
BRANCH = "feat/api"

def ssh_exec(client, cmd, timeout=300):
    """Execute command and print output in real-time."""
    print(f"\n>>> {cmd}")
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    
    # Stream output
    for line in iter(stdout.readline, ""):
        print(f"  {line}", end="")
    
    err = stderr.read().decode()
    if err:
        for line in err.splitlines():
            print(f"  [stderr] {line}")
    
    exit_code = stdout.channel.recv_exit_status()
    print(f"  [exit: {exit_code}]")
    return exit_code

def main():
    print(f"Connecting to {HOST}:{PORT} as {USER}...")
    
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, port=PORT, username=USER, password=PASS, timeout=30)
    
    print("Connected!\n")
    
    # Check prerequisites
    print("=== Checking prerequisites ===")
    ssh_exec(client, "docker --version")
    ssh_exec(client, "docker compose version 2>/dev/null || docker-compose version 2>/dev/null")
    ssh_exec(client, "git --version")
    
    # Clone or update repo
    print("\n=== Setting up repository ===")
    stdin, stdout, stderr = client.exec_command(f'test -d "{DEPLOY_DIR}/.git" && echo "EXISTS" || echo "NOT_FOUND"')
    exists = stdout.read().decode().strip()
    
    if exists == "EXISTS":
        print("Repo exists, pulling latest changes...")
        ssh_exec(client, f'cd {DEPLOY_DIR} && git fetch origin && git checkout {BRANCH} && git pull origin {BRANCH}')
    else:
        stdin2, stdout2, stderr2 = client.exec_command(f'test -d "{DEPLOY_DIR}" && echo "EXISTS" || echo "NOT_FOUND"')
        dir_exists = stdout2.read().decode().strip()
        if dir_exists == "EXISTS":
            print(f"Removing stale directory {DEPLOY_DIR}...")
            ssh_exec(client, f'rm -rf {DEPLOY_DIR}')
        print("Cloning repository...")
        ssh_exec(client, f'git clone --branch {BRANCH} {REPO} {DEPLOY_DIR}', timeout=120)
    
    # Check .env
    print("\n=== Configuring environment ===")
    stdin, stdout, stderr = client.exec_command(f'test -f {DEPLOY_DIR}/.env && echo "EXISTS" || echo "NOT_FOUND"')
    env_exists = stdout.read().decode().strip()
    
    if env_exists != "EXISTS":
        print("Creating .env from .env.example...")
        ssh_exec(client, f'cd {DEPLOY_DIR} && cp .env.example .env')
        
        # Generate random PostgreSQL password
        ssh_exec(client, f'''cd {DEPLOY_DIR} && PG_PASS=$(openssl rand -base64 24 | tr -d '/+=' | head -c 32) && sed -i "s/POSTGRES_PASSWORD=airecon/POSTGRES_PASSWORD=${{PG_PASS}}/" .env && sed -i "s|DATABASE_URL=.*|DATABASE_URL=postgresql://airecon:${{PG_PASS}}@db:5432/airecon|" docker-compose.yml''')
        
        # Configure LLM - use Dahono gateway as default (already seeded in .env.example)
        print("LLM provider: using defaults from .env.example (Dahono gateway)")
    else:
        print(".env already exists, skipping setup")
    
    # Sync DB password in docker-compose.yml
    print("\n=== Syncing database password ===")
    ssh_exec(client, f'''cd {DEPLOY_DIR} && PG_USER=$(grep -oP 'POSTGRES_USER=\\K.*' .env 2>/dev/null || echo "airecon") && PG_PASS=$(grep -oP 'POSTGRES_PASSWORD=\\K.*' .env 2>/dev/null || echo "airecon") && PG_DB=$(grep -oP 'POSTGRES_DB=\\K.*' .env 2>/dev/null || echo "airecon") && sed -i "s|postgresql://[^:]*:[^@]*@db:5432/.*|postgresql://${{PG_USER}}:${{PG_PASS}}@db:5432/${{PG_DB}}|g" docker-compose.yml 2>/dev/null || true''')
    
    # Build and start services
    print("\n=== Building and starting services ===")
    
    # Determine compose command
    stdin, stdout, stderr = client.exec_command('docker compose version &>/dev/null 2>&1 && echo "docker compose" || echo "docker-compose"')
    compose = stdout.read().decode().strip()
    print(f"Using: {compose}")
    
    ssh_exec(client, f'cd {DEPLOY_DIR} && {compose} down 2>/dev/null || true')
    
    print("Running database migration...")
    rc = ssh_exec(client, f'cd {DEPLOY_DIR} && {compose} up --build -d migrate', timeout=180)
    if rc != 0:
        print("WARNING: Migration may have issues, continuing...")
    
    print("Starting API and DB services...")
    rc = ssh_exec(client, f'cd {DEPLOY_DIR} && {compose} up --build -d db api', timeout=300)
    if rc != 0:
        print("ERROR: Failed to start services!")
        ssh_exec(client, f'cd {DEPLOY_DIR} && {compose} logs --tail=50')
        client.close()
        sys.exit(1)
    
    # Build Kali sandbox image
    print("\n=== Building Kali sandbox image ===")
    stdin, stdout, stderr = client.exec_command('docker image inspect airecon-sandbox &>/dev/null && echo "EXISTS" || echo "NOT_FOUND"')
    sandbox_exists = stdout.read().decode().strip()
    
    if sandbox_exists != "EXISTS":
        print("Building Kali sandbox (this takes 10-20 minutes on first run)...")
        ssh_exec(client, f'cd {DEPLOY_DIR} && docker build -t airecon-sandbox airecon/containers/', timeout=1200)
    else:
        print("Kali sandbox image already exists")
    
    # Wait for health
    print("\n=== Checking API health ===")
    stdin, stdout, stderr = client.exec_command(f'grep -oP "API_PORT=\\K[0-9]+" {DEPLOY_DIR}/.env 2>/dev/null || echo 8000')
    api_port = stdout.read().decode().strip()
    
    for i in range(30):
        stdin, stdout, stderr = client.exec_command(f'curl -sf http://localhost:{api_port}/api/health')
        rc = stdout.channel.recv_exit_status()
        if rc == 0:
            health = stdout.read().decode()
            print(f"API is healthy: {health}")
            break
        time.sleep(1)
    else:
        print("API not healthy after 30s, checking logs...")
        ssh_exec(client, f'cd {DEPLOY_DIR} && {compose} logs --tail=30 api')
    
    # Print status
    print("\n=== Deployment Summary ===")
    ssh_exec(client, f'cd {DEPLOY_DIR} && {compose} ps')
    
    stdin, stdout, stderr = client.exec_command("hostname -I | awk '{print $1}'")
    server_ip = stdout.read().decode().strip()
    
    print(f"\n✓ Deployment complete!")
    print(f"  API:     http://{server_ip}:{api_port}")
    print(f"  Swagger: http://{server_ip}:{api_port}/docs")
    print(f"  Health:  http://{server_ip}:{api_port}/api/health")
    
    client.close()
    print("\nSSH connection closed.")

if __name__ == "__main__":
    main()
