#!/usr/bin/env bash
set -euo pipefail

CONTAINER="m4bench"
IMAGE="m4bench:latest"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
AUTH_ROOT="/host-auth"

# Parse --agent from arguments (needed for API-key logic below).
AGENT=""
ARGS=("$@")
for ((i=0; i<${#ARGS[@]}; i++)); do
    case "${ARGS[$i]}" in
        --agent)
            if (( i + 1 < ${#ARGS[@]} )); then
                AGENT="${ARGS[$((i + 1))]}"
                ((i+=1))
            fi
            ;;
        --agent=*)
            AGENT="${ARGS[$i]#--agent=}"
            ;;
    esac
done

# Load .env file if it exists (expects ANTHROPIC_API_KEY=sk-ant-api03-...)
if [[ -f "$SCRIPT_DIR/.env" ]]; then
    set -a
    source "$SCRIPT_DIR/.env"
    set +a
fi

# Fallback: on macOS, extract a fresh OAuth token from the keychain.
# This uses your Claude subscription (no API credits).
# On Linux/Windows, set ANTHROPIC_API_KEY in benchmark/.env instead.
if [[ "$AGENT" == "claude" ]] && [[ -z "${ANTHROPIC_API_KEY:-}" ]] && command -v security &>/dev/null; then
    ANTHROPIC_API_KEY=$(
        security find-generic-password -s "Claude Code-credentials" -w 2>/dev/null \
        | python3 -c "import sys,json; print(json.loads(sys.stdin.read()).get('claudeAiOauth',{}).get('accessToken',''))" 2>/dev/null
    ) || true
    if [[ -n "$ANTHROPIC_API_KEY" ]]; then
        echo "Using OAuth token from macOS keychain (expires in a few hours)"
    fi
fi

if [[ "$AGENT" == "claude" ]] && [[ -z "${ANTHROPIC_API_KEY:-}" ]]; then
    echo "Error: No ANTHROPIC_API_KEY found."
    echo "Options:"
    echo "  1. Create benchmark/.env with: ANTHROPIC_API_KEY=sk-ant-api03-..."
    echo "     (from console.anthropic.com — uses API credits)"
    echo "  2. On macOS: log in with 'claude login' and the keychain fallback will work"
    exit 1
fi

# Build image if it doesn't exist
if ! docker image inspect "$IMAGE" &>/dev/null; then
    echo "Building $IMAGE..."
    docker build -t "$IMAGE" "$SCRIPT_DIR"
fi

# Start or restart container (always restart to pick up fresh token)
if docker ps -q -f name="^${CONTAINER}$" | grep -q .; then
    docker rm -f "$CONTAINER" >/dev/null
fi
docker rm "$CONTAINER" 2>/dev/null || true

DOCKER_ARGS=(
    -d
    --name "$CONTAINER"
    --cap-add NET_ADMIN
    -v "$SCRIPT_DIR":/benchmark
    -e "M4BENCH_AUTH_ROOT=$AUTH_ROOT"
)

if [[ -n "${ANTHROPIC_API_KEY:-}" ]]; then
    DOCKER_ARGS+=(-e "ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY")
fi

if [[ -d "$HOME/.codex" ]]; then
    DOCKER_ARGS+=(-v "$HOME/.codex:$AUTH_ROOT/.codex:ro")
fi

if [[ -d "$HOME/.gemini" ]]; then
    DOCKER_ARGS+=(-v "$HOME/.gemini:$AUTH_ROOT/.gemini:ro")
fi

docker run "${DOCKER_ARGS[@]}" "$IMAGE" >/dev/null

# Install benchmark dependencies (lightweight, no M4 package)
docker exec "$CONTAINER" pip3 install --break-system-packages --quiet \
    duckdb pandas pytest tomli 2>/dev/null

# ── Isolation hardening ─────────────────────────────────────────────────
# 1. Lock sensitive directories: ground truth, tasks, and agent DBs become
#    root-only (mode 700).  The orchestrator (root) can still read them;
#    the agent subprocess (benchagent) cannot.
echo "Locking sensitive directories (root-only)..."
docker exec "$CONTAINER" bash -c \
    'for d in ground_truth tasks agent_db; do
        [ -d "/benchmark/$d" ] && chmod 700 "/benchmark/$d"
    done'

# 2. Lock network: iptables rules restrict the benchagent user to
#    LLM-API-only outbound traffic (no web search, no package downloads).
echo "Locking network (API-only for agent)..."
docker exec "$CONTAINER" bash /benchmark/network_lock.sh

# Forward all arguments to run.py inside the container.
# Isolation is on by default in run.py; bench.sh no longer needs to inject it.
docker exec "$CONTAINER" python3 /benchmark/run.py "$@"
