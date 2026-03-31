#!/usr/bin/env bash
set -euo pipefail

CONTAINER="m4bench"
IMAGE="m4bench:latest"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Load .env file if it exists (expects ANTHROPIC_API_KEY=sk-ant-api03-...)
if [[ -f "$SCRIPT_DIR/.env" ]]; then
    set -a
    source "$SCRIPT_DIR/.env"
    set +a
fi

# Fallback: on macOS, extract a fresh OAuth token from the keychain.
# This uses your Claude subscription (no API credits).
# On Linux/Windows, set ANTHROPIC_API_KEY in benchmark/.env instead.
if [[ -z "${ANTHROPIC_API_KEY:-}" ]] && command -v security &>/dev/null; then
    ANTHROPIC_API_KEY=$(
        security find-generic-password -s "Claude Code-credentials" -w 2>/dev/null \
        | python3 -c "import sys,json; print(json.loads(sys.stdin.read()).get('claudeAiOauth',{}).get('accessToken',''))" 2>/dev/null
    ) || true
    if [[ -n "$ANTHROPIC_API_KEY" ]]; then
        echo "Using OAuth token from macOS keychain (expires in a few hours)"
    fi
fi

if [[ -z "${ANTHROPIC_API_KEY:-}" ]]; then
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
docker run -d --name "$CONTAINER" \
    -v "$SCRIPT_DIR":/benchmark \
    -e ANTHROPIC_API_KEY="$ANTHROPIC_API_KEY" \
    "$IMAGE" >/dev/null

# Install benchmark dependencies (lightweight, no M4 package)
docker exec "$CONTAINER" pip3 install --break-system-packages --quiet \
    duckdb pandas pytest tomli 2>/dev/null

# Forward all arguments to run.py inside the container
docker exec "$CONTAINER" python3 /benchmark/run.py "$@"
