#!/usr/bin/env bash
# Restrict the benchagent user to LLM-API-only network access.
#
# Uses iptables with --uid-owner matching so that only the agent subprocess
# (running as benchagent) is restricted.  The orchestrator (root) keeps full
# network access for package installs and ground-truth downloads.
#
# Requires: --cap-add=NET_ADMIN on the Docker container.
set -euo pipefail

AGENT_USER="benchagent"

# LLM API hosts — the only external services the agent should reach.
ALLOWED_HOSTS=(
    # Anthropic (Claude)
    api.anthropic.com
    statsig.anthropic.com
    sentry.io
    # OpenAI (Codex)
    api.openai.com
    # Google (Gemini)
    generativelanguage.googleapis.com
    oauth2.googleapis.com
    accounts.google.com
)

if ! id "$AGENT_USER" &>/dev/null; then
    echo "Warning: user '$AGENT_USER' does not exist — skipping network lock"
    exit 0
fi

AGENT_UID=$(id -u "$AGENT_USER")

# Flush any previous benchagent rules (idempotent re-runs)
iptables -F OUTPUT 2>/dev/null || true

echo "Resolving API hosts for network allowlist..."
for host in "${ALLOWED_HOSTS[@]}"; do
    for ip in $(dig +short "$host" 2>/dev/null | grep -E '^[0-9]+\.' || true); do
        iptables -A OUTPUT -m owner --uid-owner "$AGENT_UID" \
            -d "$ip" -p tcp --dport 443 -j ACCEPT
        echo "  $host -> $ip"
    done
done

# Allow loopback (agent CLI may use local sockets)
iptables -A OUTPUT -m owner --uid-owner "$AGENT_UID" -o lo -j ACCEPT

# Allow DNS so the agent CLI can resolve API hostnames on its own
iptables -A OUTPUT -m owner --uid-owner "$AGENT_UID" -p udp --dport 53 -j ACCEPT
iptables -A OUTPUT -m owner --uid-owner "$AGENT_UID" -p tcp --dport 53 -j ACCEPT

# Allow already-established connections (handles TCP handshake completion)
iptables -A OUTPUT -m owner --uid-owner "$AGENT_UID" \
    -m state --state ESTABLISHED,RELATED -j ACCEPT

# Drop everything else from benchagent
iptables -A OUTPUT -m owner --uid-owner "$AGENT_UID" -j DROP

echo "Network locked for $AGENT_USER (uid=$AGENT_UID): LLM API only"
