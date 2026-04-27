#!/usr/bin/env bash
set -euo pipefail

IMAGE="${M4BENCH_IMAGE:-m4bench:latest}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DOCKER_BIN="${DOCKER_BIN:-docker}"
CLAUDE_AUTH_VOLUME="${M4BENCH_CLAUDE_AUTH_VOLUME:-m4bench-claude-auth}"
CLAUDE_LOGIN_CONTAINER="${M4BENCH_CLAUDE_LOGIN_CONTAINER:-m4bench-claude-login}"

if [[ -x "$HOME/.orbstack/bin/docker" ]]; then
    CURRENT_DOCKER_CONTEXT="$("$DOCKER_BIN" context show 2>/dev/null || true)"
    if [[ "$CURRENT_DOCKER_CONTEXT" == "orbstack" ]]; then
        DOCKER_BIN="$HOME/.orbstack/bin/docker"
    fi
fi

if [[ "${M4BENCH_REBUILD:-0}" == "1" ]] || ! "$DOCKER_BIN" image inspect "$IMAGE" &>/dev/null; then
    echo "Building $IMAGE..."
    "$DOCKER_BIN" build -t "$IMAGE" "$SCRIPT_DIR"
fi

"$DOCKER_BIN" volume create "$CLAUDE_AUTH_VOLUME" >/dev/null

if ! "$DOCKER_BIN" ps -a --format '{{.Names}}' | grep -Fxq "$CLAUDE_LOGIN_CONTAINER"; then
    "$DOCKER_BIN" run -d \
        --name "$CLAUDE_LOGIN_CONTAINER" \
        -v "$CLAUDE_AUTH_VOLUME:/claude-auth" \
        "$IMAGE" >/dev/null
elif ! "$DOCKER_BIN" ps --format '{{.Names}}' | grep -Fxq "$CLAUDE_LOGIN_CONTAINER"; then
    "$DOCKER_BIN" start "$CLAUDE_LOGIN_CONTAINER" >/dev/null
fi

echo "Logging Claude Code into persistent Docker container: $CLAUDE_LOGIN_CONTAINER"
echo "Auth volume: $CLAUDE_AUTH_VOLUME"
echo "Only allowlisted auth files will be persisted; project memory is discarded."

"$DOCKER_BIN" exec -it "$CLAUDE_LOGIN_CONTAINER" \
    bash -lc '
set -euo pipefail

LOGIN_HOME="$(mktemp -d -t claude-login-home-XXXXXX)"
cleanup() {
    rm -rf "$LOGIN_HOME"
}
trap cleanup EXIT

export HOME="$LOGIN_HOME"
unset ANTHROPIC_API_KEY

claude login

mkdir -p /claude-auth/.claude

copied=0
for relative_path in \
    ".claude.json" \
    ".claude/.credentials.json" \
    ".claude/credentials.json"
do
    src="$HOME/$relative_path"
    if [[ -f "$src" ]]; then
        mkdir -p "/claude-auth/$(dirname "$relative_path")"
        cp "$src" "/claude-auth/$relative_path"
        copied=$((copied + 1))
        echo "Persisted $relative_path"
    fi
done

if [[ "$copied" -eq 0 ]]; then
    echo "Error: Claude login completed but no allowlisted auth files were found." >&2
    echo "Inspect a clean Claude login and update CLAUDE_CONTAINER_LOGIN_AUTH_SEEDS." >&2
    exit 1
fi

chmod -R go-rwx /claude-auth

echo "Testing persisted login in a fresh HOME..."
TEST_HOME="$(mktemp -d -t claude-test-home-XXXXXX)"
trap "rm -rf \"$LOGIN_HOME\" \"$TEST_HOME\"" EXIT
mkdir -p "$TEST_HOME/.claude"

for relative_path in \
    ".claude.json" \
    ".claude/.credentials.json" \
    ".claude/credentials.json"
do
    src="/claude-auth/$relative_path"
    if [[ -f "$src" ]]; then
        mkdir -p "$TEST_HOME/$(dirname "$relative_path")"
        cp "$src" "$TEST_HOME/$relative_path"
    fi
done

HOME="$TEST_HOME" claude -p "Reply with exactly: claude-ok"
'

echo
echo "Use this mode for Claude benchmark runs:"
echo "  M4BENCH_CLAUDE_AUTH_MODE=container-login bash benchmark/bench.sh ..."
