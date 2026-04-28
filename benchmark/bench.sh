#!/usr/bin/env bash
set -euo pipefail

CONTAINER="${M4BENCH_CONTAINER_NAME:-m4bench}"
IMAGE="${M4BENCH_IMAGE:-m4bench:latest}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
AUTH_ROOT="/host-auth"
AUTH_STAGING_DIR="$(mktemp -d -t m4bench-auth-XXXXXX)"
DOCKER_BIN="${DOCKER_BIN:-docker}"
M4_DATA_DIR="${M4BENCH_M4_DATA_DIR:-$REPO_ROOT/m4_data}"
M4_DATA_CONTAINER_DIR="${M4BENCH_M4_DATA_CONTAINER_DIR:-/m4_data}"
CLAUDE_AUTH_VOLUME="${M4BENCH_CLAUDE_AUTH_VOLUME:-m4bench-claude-auth}"
CLAUDE_AUTH_ROOT="/claude-auth"

cleanup() {
    local status=$?
    rm -rf "$AUTH_STAGING_DIR"
    return "$status"
}
trap cleanup EXIT

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
if [[ -f "$SCRIPT_DIR/.env" ]]; then
    set -a
    source "$SCRIPT_DIR/.env"
    set +a
fi

stage_auth_file() {
    local relative_path="$1"
    local src="$HOME/$relative_path"
    local dest="$AUTH_STAGING_DIR/$relative_path"
    if [[ -f "$src" ]]; then
        mkdir -p "$(dirname "$dest")"
        cp "$src" "$dest"
    fi
}

# Stage only the minimal auth/config files the harness explicitly copies into
# per-run HOME directories. Do not mount full provider config directories into
# the benchmark container; they may contain histories, memories, or prior runs.
stage_auth_file ".codex/auth.json"
stage_auth_file ".gemini/oauth_creds.json"
stage_auth_file ".gemini/google_accounts.json"
stage_auth_file ".gemini/state.json"
stage_auth_file ".gemini/settings.json"
stage_auth_file ".gemini/installation_id"
stage_auth_file ".pi/agent/models.json"
chmod -R go-rwx "$AUTH_STAGING_DIR"

NEEDS_BUILD=0
if [[ "${M4BENCH_REBUILD:-0}" == "1" ]] || ! "$DOCKER_BIN" image inspect "$IMAGE" &>/dev/null; then
    NEEDS_BUILD=1
elif [[ "$AGENT" == "pi-ollama" ]] && ! "$DOCKER_BIN" run --rm "$IMAGE" \
    sh -lc 'command -v pi >/dev/null 2>&1'; then
    echo "Existing $IMAGE image does not include Pi; rebuilding..."
    NEEDS_BUILD=1
elif ! "$DOCKER_BIN" run --rm "$IMAGE" \
    python3 -c 'import duckdb, pandas, pytest, tomli' >/dev/null 2>&1; then
    echo "Existing $IMAGE image is missing benchmark Python dependencies; rebuilding..."
    NEEDS_BUILD=1
fi

# Build image if it doesn't exist, when explicitly requested, or when the
# selected agent requires tooling missing from an older local image.
if [[ "$NEEDS_BUILD" == "1" ]]; then
    echo "Building $IMAGE..."
    "$DOCKER_BIN" build -t "$IMAGE" "$SCRIPT_DIR"
fi

if [[ "$AGENT" == "claude" ]]; then
    echo "Using Claude login auth volume: $CLAUDE_AUTH_VOLUME"
fi

if [[ "$AGENT" == "pi-ollama" ]]; then
    M4BENCH_OLLAMA_HOST="${M4BENCH_OLLAMA_HOST:-host.docker.internal}"
    M4BENCH_OLLAMA_PORT="${M4BENCH_OLLAMA_PORT:-11434}"
    M4BENCH_OLLAMA_BASE_URL="${M4BENCH_OLLAMA_BASE_URL:-http://${M4BENCH_OLLAMA_HOST}:${M4BENCH_OLLAMA_PORT}/v1}"
    export M4BENCH_ALLOW_OLLAMA=1
    export M4BENCH_OLLAMA_HOST
    export M4BENCH_OLLAMA_PORT
    export M4BENCH_OLLAMA_BASE_URL
fi

DATA_MOUNT_SOURCES=()

add_data_mount_source() {
    local source="$1"
    if (( ${#DATA_MOUNT_SOURCES[@]} > 0 )); then
        for existing in "${DATA_MOUNT_SOURCES[@]}"; do
            [[ "$existing" == "$source" ]] && return
        done
    fi
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

AGENT_MOUNTS_SPEC=""
if (( ${#DATA_MOUNT_SOURCES[@]} > 0 )); then
    for source in "${DATA_MOUNT_SOURCES[@]}"; do
        host_source="$M4_DATA_DIR/parquet/$source"
        container_source="$M4_DATA_CONTAINER_DIR/parquet/$source"
        if [[ -d "$host_source" ]]; then
            AGENT_MOUNTS_SPEC+="${host_source}=${container_source}"$'\n'
        else
            echo "Warning: required parquet source not found at $host_source"
            echo "         Agent DB views that reference $source may fail."
        fi
    done
fi

translate_benchmark_path() {
    local value="$1"
    if [[ "$value" == /benchmark/* ]]; then
        printf '%s/%s' "$SCRIPT_DIR" "${value#/benchmark/}"
    else
        printf '%s' "$value"
    fi
}

RUN_ARGS=()
PREFLIGHT_RESULTS_ROOT=""
for ((i=0; i<${#ARGS[@]}; i++)); do
    case "${ARGS[$i]}" in
        --results-root)
            RUN_ARGS+=("${ARGS[$i]}")
            if (( i + 1 < ${#ARGS[@]} )); then
                translated="$(translate_benchmark_path "${ARGS[$((i + 1))]}")"
                RUN_ARGS+=("$translated")
                PREFLIGHT_RESULTS_ROOT="$translated"
                ((i+=1))
            fi
            ;;
        --results-root=*)
            value="${ARGS[$i]#--results-root=}"
            translated="$(translate_benchmark_path "$value")"
            RUN_ARGS+=("--results-root=$translated")
            PREFLIGHT_RESULTS_ROOT="$translated"
            ;;
        *)
            RUN_ARGS+=("${ARGS[$i]}")
            ;;
    esac
done

export M4BENCH_AGENT_CONTAINER=1
export M4BENCH_AGENT_CONTAINER_IMAGE="$IMAGE"
export M4BENCH_DOCKER_BIN="$DOCKER_BIN"
export M4BENCH_AUTH_ROOT="$AUTH_STAGING_DIR"
export M4BENCH_CLAUDE_AUTH_ROOT="$CLAUDE_AUTH_ROOT"
export M4BENCH_CLAUDE_AUTH_VOLUME="$CLAUDE_AUTH_VOLUME"
export M4BENCH_DATA_ROOT="$M4_DATA_CONTAINER_DIR"
export M4BENCH_AGENT_CONTAINER_MOUNTS="$AGENT_MOUNTS_SPEC"

echo "Running host orchestrator with agent-only Docker isolation..."
echo "Agent image: $IMAGE"

if [[ "${M4BENCH_BENCH_SH_NO_RUN:-0}" == "1" ]]; then
    exit 0
fi

echo "Running preflight checks..."
PREFLIGHT_CMD=("$SCRIPT_DIR/preflight.py")
if [[ -n "$PREFLIGHT_RESULTS_ROOT" ]]; then
    PREFLIGHT_CMD+=(--results-root "$PREFLIGHT_RESULTS_ROOT" --allow-existing-results-root)
fi
if command -v uv >/dev/null 2>&1; then
    (cd "$REPO_ROOT" && uv run python "${PREFLIGHT_CMD[@]}")
else
    (cd "$REPO_ROOT" && python3 "${PREFLIGHT_CMD[@]}")
fi

if command -v uv >/dev/null 2>&1; then
    (cd "$REPO_ROOT" && uv run python "$SCRIPT_DIR/run.py" "${RUN_ARGS[@]}")
else
    (cd "$REPO_ROOT" && python3 "$SCRIPT_DIR/run.py" "${RUN_ARGS[@]}")
fi
