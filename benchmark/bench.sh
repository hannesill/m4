#!/usr/bin/env bash
set -euo pipefail

CONTAINER="${M4BENCH_CONTAINER_NAME:-m4bench}"
IMAGE="${M4BENCH_IMAGE:-m4bench:latest}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
AUTH_ROOT="/host-auth"
DOCKER_BIN="${DOCKER_BIN:-docker}"
M4_DATA_DIR="${M4BENCH_M4_DATA_DIR:-$REPO_ROOT/m4_data}"
M4_DATA_CONTAINER_DIR="${M4BENCH_M4_DATA_CONTAINER_DIR:-/m4_data}"

# OrbStack's doctor warns against using the Homebrew docker client against the
# OrbStack daemon. Prefer OrbStack's bundled client when that is the active
# context so benchmark runs use the supported pairing on macOS.
if [[ -x "$HOME/.orbstack/bin/docker" ]]; then
    CURRENT_DOCKER_CONTEXT="$("$DOCKER_BIN" context show 2>/dev/null || true)"
    if [[ "$CURRENT_DOCKER_CONTEXT" == "orbstack" ]]; then
        DOCKER_BIN="$HOME/.orbstack/bin/docker"
    fi
fi

# Parse selected arguments (needed for API-key and data-mount logic below).
AGENT=""
TASK=""
SCHEMA="native"
FAMILY=""
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
        --task)
            if (( i + 1 < ${#ARGS[@]} )); then
                TASK="${ARGS[$((i + 1))]}"
                ((i+=1))
            fi
            ;;
        --task=*)
            TASK="${ARGS[$i]#--task=}"
            ;;
        --schema)
            if (( i + 1 < ${#ARGS[@]} )); then
                SCHEMA="${ARGS[$((i + 1))]}"
                ((i+=1))
            fi
            ;;
        --schema=*)
            SCHEMA="${ARGS[$i]#--schema=}"
            ;;
        --family)
            if (( i + 1 < ${#ARGS[@]} )); then
                FAMILY="${ARGS[$((i + 1))]}"
                ((i+=1))
            fi
            ;;
        --family=*)
            FAMILY="${ARGS[$i]#--family=}"
            ;;
    esac
done

# Load .env file if it exists.
# Only stable API keys should live here; Claude OAuth tokens expire quickly.
if [[ -f "$SCRIPT_DIR/.env" ]]; then
    set -a
    source "$SCRIPT_DIR/.env"
    set +a
fi

# Claude subscription auth should come from a fresh macOS keychain token when
# available. If benchmark/.env contains an OAuth token from a past session, try
# to replace it before launching Docker.
if [[ "$AGENT" == "claude" ]] && command -v security &>/dev/null; then
    FRESH_CLAUDE_OAUTH=$(
        security find-generic-password -s "Claude Code-credentials" -w 2>/dev/null \
        | python3 -c "import sys,json; print(json.loads(sys.stdin.read()).get('claudeAiOauth',{}).get('accessToken',''))" 2>/dev/null
    ) || true
    if [[ -n "${FRESH_CLAUDE_OAUTH:-}" ]]; then
        ANTHROPIC_API_KEY="$FRESH_CLAUDE_OAUTH"
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

if [[ "$AGENT" == "claude" ]] && [[ "${ANTHROPIC_API_KEY:-}" == sk-ant-oat* ]] && ! command -v security &>/dev/null; then
    echo "Error: benchmark/.env contains an expiring Claude OAuth token."
    echo "Use a real Anthropic API key in benchmark/.env, or run via macOS with 'claude login'."
    exit 1
fi

NEEDS_BUILD=0
if [[ "${M4BENCH_REBUILD:-0}" == "1" ]] || ! "$DOCKER_BIN" image inspect "$IMAGE" &>/dev/null; then
    NEEDS_BUILD=1
elif [[ "$AGENT" == "pi-ollama" ]] && ! "$DOCKER_BIN" run --rm "$IMAGE" \
    sh -lc 'command -v pi >/dev/null 2>&1'; then
    echo "Existing $IMAGE image does not include Pi; rebuilding..."
    NEEDS_BUILD=1
fi

# Build image if it doesn't exist, when explicitly requested, or when the
# selected agent requires tooling missing from an older local image.
if [[ "$NEEDS_BUILD" == "1" ]]; then
    echo "Building $IMAGE..."
    "$DOCKER_BIN" build -t "$IMAGE" "$SCRIPT_DIR"
fi

# Start or restart container (always restart to pick up fresh token)
if "$DOCKER_BIN" ps -q -f name="^${CONTAINER}$" | grep -q .; then
    "$DOCKER_BIN" rm -f "$CONTAINER" >/dev/null
fi
"$DOCKER_BIN" rm "$CONTAINER" 2>/dev/null || true

DOCKER_ARGS=(
    -d
    --name "$CONTAINER"
    --cap-add NET_ADMIN
    -v "$SCRIPT_DIR":/benchmark
    -e "M4BENCH_AUTH_ROOT=$AUTH_ROOT"
)

if [[ "$AGENT" == "pi-ollama" ]]; then
    M4BENCH_OLLAMA_HOST="${M4BENCH_OLLAMA_HOST:-host.docker.internal}"
    M4BENCH_OLLAMA_PORT="${M4BENCH_OLLAMA_PORT:-11434}"
    M4BENCH_OLLAMA_BASE_URL="${M4BENCH_OLLAMA_BASE_URL:-http://${M4BENCH_OLLAMA_HOST}:${M4BENCH_OLLAMA_PORT}/v1}"
    DOCKER_ARGS+=(
        --add-host=host.docker.internal:host-gateway
        -e "M4BENCH_ALLOW_OLLAMA=1"
        -e "M4BENCH_OLLAMA_HOST=$M4BENCH_OLLAMA_HOST"
        -e "M4BENCH_OLLAMA_PORT=$M4BENCH_OLLAMA_PORT"
        -e "M4BENCH_OLLAMA_BASE_URL=$M4BENCH_OLLAMA_BASE_URL"
    )
fi

DATA_MOUNT_SOURCES=()

add_data_mount_source() {
    local source="$1"
    for existing in "${DATA_MOUNT_SOURCES[@]}"; do
        [[ "$existing" == "$source" ]] && return
    done
    DATA_MOUNT_SOURCES+=("$source")
}

if [[ "$SCHEMA" == "obfuscated" ]]; then
    add_data_mount_source "obfuscated-mimic-iv"
elif [[ "$SCHEMA" == "restructured" ]]; then
    # Restructured DBs retain obfuscated source-table views plus merged tables.
    add_data_mount_source "obfuscated-mimic-iv"
    add_data_mount_source "restructured-mimic-iv"
elif [[ "$TASK" == eicu-* ]] || [[ "$FAMILY" == "gcs" ]] || [[ "$FAMILY" == "oasis" ]]; then
    add_data_mount_source "eicu"
    # The gcs/oasis families include both eICU and MIMIC tasks when invoked by
    # family, so include MIMIC as well only for family-wide runs.
    [[ -n "$FAMILY" ]] && add_data_mount_source "mimic-iv"
elif [[ "$TASK" == "all" ]] || [[ -n "$FAMILY" ]] || [[ -z "$TASK" ]]; then
    add_data_mount_source "mimic-iv"
    add_data_mount_source "eicu"
else
    add_data_mount_source "mimic-iv"
fi

DOCKER_ARGS+=(-e "M4BENCH_DATA_ROOT=$M4_DATA_CONTAINER_DIR")
for source in "${DATA_MOUNT_SOURCES[@]}"; do
    host_source="$M4_DATA_DIR/parquet/$source"
    container_source="$M4_DATA_CONTAINER_DIR/parquet/$source"
    if [[ -d "$host_source" ]]; then
        DOCKER_ARGS+=(-v "$host_source:$container_source:ro")
    else
        echo "Warning: required parquet source not found at $host_source"
        echo "         Agent DB views that reference $source may fail."
    fi
done

if [[ -n "${ANTHROPIC_API_KEY:-}" ]]; then
    DOCKER_ARGS+=(-e "ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY")
fi

if [[ -d "$HOME/.codex" ]]; then
    DOCKER_ARGS+=(-v "$HOME/.codex:$AUTH_ROOT/.codex:ro")
fi

if [[ -d "$HOME/.gemini" ]]; then
    DOCKER_ARGS+=(-v "$HOME/.gemini:$AUTH_ROOT/.gemini:ro")
fi

if [[ -d "$HOME/.pi" ]]; then
    DOCKER_ARGS+=(-v "$HOME/.pi:$AUTH_ROOT/.pi:ro")
fi

"$DOCKER_BIN" run "${DOCKER_ARGS[@]}" "$IMAGE" >/dev/null

# Install benchmark dependencies (lightweight, no M4 package)
"$DOCKER_BIN" exec "$CONTAINER" pip3 install --break-system-packages --quiet \
    duckdb pandas pytest tomli 2>/dev/null
"$DOCKER_BIN" exec "$CONTAINER" bash -lc \
    'ln -sf /benchmark/lib/duckdb_cli.py /usr/local/bin/duckdb && chmod +x /benchmark/lib/duckdb_cli.py /usr/local/bin/duckdb'

# ── Isolation hardening ─────────────────────────────────────────────────
# 1. Lock sensitive directories: ground truth, tasks, and agent DBs become
#    root-only (mode 700).  The orchestrator (root) can still read them;
#    the agent subprocess (benchagent) cannot.
echo "Locking sensitive directories (root-only)..."
"$DOCKER_BIN" exec "$CONTAINER" bash -c \
    'for d in ground_truth tasks agent_db; do
        [ -d "/benchmark/$d" ] && chmod 700 "/benchmark/$d"
    done'

# 2. Lock network: iptables rules restrict the benchagent user to
#    LLM-API-only outbound traffic (no web search, no package downloads).
echo "Locking network (API-only for agent)..."
"$DOCKER_BIN" exec "$CONTAINER" bash /benchmark/network_lock.sh

# Forward all arguments to run.py inside the container.
# Isolation is on by default in run.py; bench.sh no longer needs to inject it.
"$DOCKER_BIN" exec "$CONTAINER" python3 /benchmark/run.py "$@"
