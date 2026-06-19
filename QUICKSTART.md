# Quick Start

Two configs, one shared token. Pick a token and use the same value on both sides.

## 1. Deploy the server on your Docker host

Edit [server-config.yaml](server-config.yaml) — really only `auth_token` needs
changing:

```yaml
server:
  listen_port: 1234        # WSL / LLM clients connect here
  ws_port: 1235            # the Mac relay client connects here
  host: "0.0.0.0"
  auth_token: "change-me"  # pick a secret
```

Build and run with Docker Compose (config is mounted, so edits don't need a
rebuild — just restart):

```bash
docker compose up -d --build
docker compose logs -f
```

You should see:

```
Listening: TCP 0.0.0.0:1234 (consumers), WebSocket 0.0.0.0:1235 (relay client)
```

Make sure ports **1234** and **1235** are reachable from your Mac and WSL.

## 2. Run the client on your Mac

First start llama-server (defaults to port 8080):

```bash
llama-server -m model.gguf --port 8080
```

Edit [client-config.yaml](client-config.yaml):

```yaml
client:
  server_url: "ws://YOUR_DOCKER_HOST:1235"  # the server's ws_port
  backend_host: "127.0.0.1"
  backend_port: 8080                        # llama-server's port
  auth_token: "change-me"                   # same token as the server
```

Then:

```bash
uv sync
uv run python -m client.client --config client-config.yaml
```

You should see `Attached to ws://YOUR_DOCKER_HOST:1235, forwarding to backend 127.0.0.1:8080`.

## 3. Use it from WSL

Point any LLM client at the Docker host's `listen_port`:

```bash
curl http://YOUR_DOCKER_HOST:1234/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"x","messages":[{"role":"user","content":"hi"}],"stream":true}'
```

Or in an OpenAI-compatible client, set the base URL to
`http://YOUR_DOCKER_HOST:1234/v1`. Streaming works — tokens arrive as they're
generated.

## Running without Docker

The server is plain Python too:

```bash
uv run python -m server.server --config server-config.yaml
```

## Troubleshooting

- **`Rejecting <peer>: no relay client attached`** — the Mac client isn't
  connected. Start it / check `server_url` and that port 1235 is reachable.
- **`authentication rejected by server`** — the `auth_token` values differ.
- **Consumer connection drops immediately** — usually no client attached, or
  llama-server isn't running on `backend_port`.
- **Client keeps reconnecting** — the server is unreachable; check the Docker
  host's firewall and that port 1235 is published.
