FROM node:20-slim

ARG CLAUDE_CODE_VERSION=2.1.119
ARG GEMINI_CLI_VERSION=0.39.1
ARG CODEX_CLI_VERSION=0.124.0

ENV NPM_CONFIG_AUDIT=false \
    NPM_CONFIG_FUND=false \
    NPM_CONFIG_UPDATE_NOTIFIER=false

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip python3-venv git curl \
    iptables iproute2 dnsutils \
    && rm -rf /var/lib/apt/lists/*

# Install agent CLIs separately so Docker can cache partial success and
# failures are easier to isolate when a provider package changes upstream.
RUN npm install -g --loglevel=warn @anthropic-ai/claude-code@${CLAUDE_CODE_VERSION}
RUN npm install -g --loglevel=warn @google/gemini-cli@${GEMINI_CLI_VERSION}
RUN npm install -g --loglevel=warn @openai/codex@${CODEX_CLI_VERSION}

# Non-root user for agent execution.
# The orchestrator runs as root; the agent subprocess runs as benchagent.
# Ground truth and task directories are root-owned with mode 700, so
# benchagent cannot read them — even if the sandbox hook is bypassed.
RUN useradd -m -s /bin/bash benchagent

WORKDIR /benchmark
CMD ["sleep", "infinity"]
