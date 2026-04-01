FROM node:20-slim

RUN apt-get update && apt-get install -y \
    python3 python3-pip python3-venv git curl \
    iptables iproute2 dnsutils \
    && rm -rf /var/lib/apt/lists/*

# Agent CLIs
RUN npm install -g \
    @anthropic-ai/claude-code \
    @google/gemini-cli \
    @openai/codex

# Non-root user for agent execution.
# The orchestrator runs as root; the agent subprocess runs as benchagent.
# Ground truth and task directories are root-owned with mode 700, so
# benchagent cannot read them — even if the sandbox hook is bypassed.
RUN useradd -m -s /bin/bash benchagent

WORKDIR /benchmark
CMD ["sleep", "infinity"]
