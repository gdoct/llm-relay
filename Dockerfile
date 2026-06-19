FROM python:3.13-slim

# uv for dependency management
RUN pip install --no-cache-dir uv

WORKDIR /app

# Unbuffered stdio so logs appear immediately in `docker compose logs`.
ENV PYTHONUNBUFFERED=1

# Project metadata + source (needed to build the local package)
COPY pyproject.toml uv.lock README.md ./
COPY llm_relay ./llm_relay
COPY server ./server
COPY client ./client

RUN uv sync --frozen --no-dev

# 1234: consumers (WSL); 1235: Mac relay client (WebSocket)
EXPOSE 1234 1235

# Mount your server-config.yaml at /config/server-config.yaml.
# Run the venv's Python directly (not `uv run`, which swallows child stderr).
CMD ["/app/.venv/bin/python", "-u", "-m", "server.server", "--config", "/config/server-config.yaml"]
