FROM node:20-slim

RUN apt-get update && apt-get install -y \
    python3 python3-pip python3-venv git curl \
    && rm -rf /var/lib/apt/lists/*

# Claude CLI
RUN npm install -g @anthropic-ai/claude-code

WORKDIR /benchmark
CMD ["sleep", "infinity"]
