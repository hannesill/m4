#!/usr/bin/env bash
# Restrict the benchagent user to LLM-API-only network access.
#
# Uses iptables/ip6tables with --uid-owner matching so that only the agent subprocess
# (running as benchagent) is restricted.  The orchestrator (root) keeps full
# network access for package installs and ground-truth downloads.
#
# Requires: --cap-add=NET_ADMIN on the Docker container.
set -euo pipefail

AGENT_USER="benchagent"

# LLM API hosts — the only external services the agent should reach. OAuth,
# product UI, and telemetry endpoints are intentionally not included.
ALLOWED_HOSTS=(
    # Anthropic (Claude)
    api.anthropic.com
    # OpenAI (Codex)
    api.openai.com
    # Google (Gemini)
    cloudcode-pa.googleapis.com
    generativelanguage.googleapis.com
)

if ! id "$AGENT_USER" &>/dev/null; then
    echo "Warning: user '$AGENT_USER' does not exist — skipping network lock"
    exit 0
fi

AGENT_UID=$(id -u "$AGENT_USER")

# Flush any previous benchagent rules (idempotent re-runs)
iptables -F OUTPUT 2>/dev/null || true
if command -v ip6tables >/dev/null 2>&1; then
    ip6tables -F OUTPUT 2>/dev/null || true
fi

PROXY_PORT="${M4BENCH_LLM_PROXY_PORT:-18080}"
EGRESS_LOG="${M4BENCH_EGRESS_LOG:-/tmp/m4bench-egress.jsonl}"
ALLOWED_CSV="$(IFS=,; echo "${ALLOWED_HOSTS[*]}")"
export M4BENCH_ALLOWED_LLM_HOSTS="$ALLOWED_CSV"
export M4BENCH_LLM_PROXY_PORT="$PROXY_PORT"
export M4BENCH_EGRESS_LOG="$EGRESS_LOG"

echo "Starting LLM API hostname proxy on 127.0.0.1:${PROXY_PORT}..."
python3 - <<'PY' >/tmp/m4bench-llm-proxy.log 2>&1 &
from __future__ import annotations

import json
import os
import select
import socket
import socketserver
import time
from http.server import BaseHTTPRequestHandler

ALLOWED = {
    host.strip().lower()
    for host in os.environ["M4BENCH_ALLOWED_LLM_HOSTS"].split(",")
    if host.strip()
}
PORT = int(os.environ["M4BENCH_LLM_PROXY_PORT"])
LOG_PATH = os.environ["M4BENCH_EGRESS_LOG"]


def log_event(**event):
    event.setdefault("ts", time.time())
    with open(LOG_PATH, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True) + "\n")


class Handler(BaseHTTPRequestHandler):
    timeout = 30

    def log_message(self, fmt, *args):
        return

    def do_CONNECT(self):
        target = self.path
        host, sep, port_text = target.rpartition(":")
        host = host.strip("[]").lower()
        try:
            port = int(port_text) if sep else 443
        except ValueError:
            port = -1
        allowed = host in ALLOWED and port == 443
        log_event(method="CONNECT", host=host, port=port, allowed=allowed)
        if not allowed:
            self.send_error(403, "host not in LLM API allowlist")
            return

        try:
            upstream = socket.create_connection((host, port), timeout=10)
        except OSError as exc:
            log_event(method="CONNECT", host=host, port=port, allowed=True, error=str(exc))
            self.send_error(502, "upstream connection failed")
            return

        self.send_response(200, "Connection Established")
        self.end_headers()
        sockets = [self.connection, upstream]
        try:
            while True:
                readable, _, _ = select.select(sockets, [], [], self.timeout)
                if not readable:
                    break
                for sock in readable:
                    data = sock.recv(65536)
                    if not data:
                        return
                    (upstream if sock is self.connection else self.connection).sendall(data)
        finally:
            upstream.close()

    def do_GET(self):
        host = (self.headers.get("Host") or "").split(":", 1)[0].lower()
        log_event(method="GET", host=host, port=80, allowed=False)
        self.send_error(403, "plain HTTP is blocked")

    do_POST = do_PUT = do_PATCH = do_DELETE = do_HEAD = do_GET


class Server(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


with Server(("127.0.0.1", PORT), Handler) as server:
    server.serve_forever()
PY

for _ in {1..20}; do
    if (echo >"/dev/tcp/127.0.0.1/${PROXY_PORT}") >/dev/null 2>&1; then
        break
    fi
    sleep 0.1
done

echo "Allowed LLM API hosts: ${ALLOWED_CSV}"

if [[ "${M4BENCH_ALLOW_OLLAMA:-0}" == "1" ]]; then
    OLLAMA_HOST="${M4BENCH_OLLAMA_HOST:-host.docker.internal}"
    OLLAMA_PORT="${M4BENCH_OLLAMA_PORT:-11434}"
    echo "Resolving Ollama host for local Pi baseline..."
    for ip in $(getent ahostsv4 "$OLLAMA_HOST" 2>/dev/null | awk '{print $1}' | sort -u); do
        iptables -A OUTPUT -m owner --uid-owner "$AGENT_UID" \
            -d "$ip" -p tcp --dport "$OLLAMA_PORT" -j ACCEPT
        echo "  $OLLAMA_HOST:$OLLAMA_PORT -> $ip"
        if ! grep -qE "^[[:space:]]*$ip[[:space:]].*(^|[[:space:]])$OLLAMA_HOST($|[[:space:]])" /etc/hosts; then
            printf "%s\t%s\n" "$ip" "$OLLAMA_HOST" >> /etc/hosts
        fi
    done
fi

# Allow loopback (agent CLI reaches the local hostname-enforcing proxy here)
iptables -A OUTPUT -m owner --uid-owner "$AGENT_UID" -o lo -j ACCEPT
if command -v ip6tables >/dev/null 2>&1; then
    ip6tables -A OUTPUT -m owner --uid-owner "$AGENT_UID" -o lo -j ACCEPT
fi

# Do not allow benchagent DNS or direct external HTTPS. API hostnames are
# resolved by the root-owned proxy after it validates the CONNECT hostname.

# Allow already-established connections (handles TCP handshake completion)
iptables -A OUTPUT -m owner --uid-owner "$AGENT_UID" \
    -m state --state ESTABLISHED,RELATED -j ACCEPT

# Reject everything else from benchagent.  REJECT is intentional here: if an
# agent tries curl/urllib/etc., it should fail immediately rather than burning
# minutes on a network timeout.
iptables -A OUTPUT -m owner --uid-owner "$AGENT_UID" \
    -p tcp -j REJECT --reject-with tcp-reset
iptables -A OUTPUT -m owner --uid-owner "$AGENT_UID" -j REJECT
if command -v ip6tables >/dev/null 2>&1; then
    ip6tables -A OUTPUT -m owner --uid-owner "$AGENT_UID" \
        -p tcp -j REJECT --reject-with tcp-reset
    ip6tables -A OUTPUT -m owner --uid-owner "$AGENT_UID" -j REJECT
fi

echo "Network locked for $AGENT_USER (uid=$AGENT_UID): LLM API proxy only"
