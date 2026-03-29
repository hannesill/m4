#!/usr/bin/env bash
set -euo pipefail

CONTAINER="m4bench"
IMAGE="m4bench:latest"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Load .env file if it exists
if [[ -f "$SCRIPT_DIR/.env" ]]; then
    set -a
    source "$SCRIPT_DIR/.env"
    set +a
fi

# If no API key set, try extracting the OAuth token from macOS keychain
# (works with Claude Max subscription — no API credits needed)
if [[ -z "${ANTHROPIC_API_KEY:-}" ]]; then
    ANTHROPIC_API_KEY=$(
        security find-generic-password -s "Claude Code-credentials" -w 2>/dev/null \
        | python3 -c "import sys,json; print(json.loads(sys.stdin.read()).get('claudeAiOauth',{}).get('accessToken',''))" 2>/dev/null
    ) || true
    if [[ -z "$ANTHROPIC_API_KEY" ]]; then
        echo "Error: No ANTHROPIC_API_KEY found."
        echo "Set it in benchmark/.env or log in to Claude CLI (claude login)."
        exit 1
    fi
    echo "Using OAuth token from macOS keychain"
fi

# Build image if it doesn't exist
if ! docker image inspect "$IMAGE" &>/dev/null; then
    echo "Building $IMAGE..."
    docker build -t "$IMAGE" "$SCRIPT_DIR"
fi

# Start or restart container (always pass fresh token since OAuth tokens expire)
if docker ps -q -f name="^${CONTAINER}$" | grep -q .; then
    docker rm -f "$CONTAINER" >/dev/null
fi
docker rm "$CONTAINER" 2>/dev/null || true
docker run -d --name "$CONTAINER" \
    -v "$REPO_ROOT":/app \
    -e ANTHROPIC_API_KEY="$ANTHROPIC_API_KEY" \
    -e UV_PROJECT_ENVIRONMENT=/tmp/m4bench-venv \
    -e UV_LINK_MODE=copy \
    "$IMAGE" >/dev/null

# Install project dependencies (cached in container volume)
docker exec "$CONTAINER" uv sync --no-dev --quiet 2>/dev/null

# Forward all arguments to run.py inside the container
docker exec "$CONTAINER" uv run python benchmark/run.py "$@"
