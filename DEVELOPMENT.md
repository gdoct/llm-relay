# Development

## Layout

```
llm_relay/
  protocol.py   # binary stream framing (shared by client & server)
  config.py     # YAML config dataclasses
server/server.py  # Docker-side: TCP listener + WebSocket acceptor
client/client.py  # Mac-side: WebSocket dialer + backend connector
tests/            # protocol, config, and end-to-end tunnel tests
```

## How it works

The relay is a **transparent raw-TCP tunnel**, not an HTTP proxy. It never
inspects or rewrites payloads, so any protocol spoken over TCP passes through.

1. The Mac **client** opens a WebSocket to the server and authenticates with a
   shared token (`{"type":"auth","token":...}` → `{"type":"auth_ok"}`).
2. A consumer (WSL) opens a TCP connection to the server's `listen_port`. The
   server assigns a `stream_id` and sends an `OPEN` frame to the client.
3. The client dials the local backend (llama-server) for that stream.
4. Bytes are relayed in both directions as `DATA` frames; either side closing
   its TCP connection sends a `CLOSE` frame. Many streams are multiplexed over
   the one WebSocket concurrently.

### Frame format

Each WebSocket **binary** message is one frame (see `llm_relay/protocol.py`):

```
+--------+------------------+--------------------+
| 1 byte | 4 bytes (uint32) | payload (variable) |
| type   | stream_id        | raw TCP bytes      |
+--------+------------------+--------------------+
```

Types: `OPEN=1`, `DATA=2`, `CLOSE=3`. Auth uses **text** frames (JSON); all
other traffic is binary. The server ignores any text frames after auth.

### Design notes

- **Single client.** The server tracks one attached client (last one wins). If
  no client is attached, inbound TCP connections are closed immediately.
- **Ordering.** On `OPEN` the client opens the backend connection *before*
  processing the next frame, so the first `DATA` frame can't race ahead of the
  socket being registered.
- **Backpressure.** Reads are bounded (`READ_CHUNK`) and writes `await
  drain()`, so a slow peer slows the producer rather than buffering unbounded.

## Common commands

```bash
uv sync                      # install deps (incl. dev group)
uv run pytest -v             # run tests
uv run black .               # format
uv run flake8                # lint
uv run pyright               # type-check
```

## Testing

`tests/test_tunnel.py` stands up a fake echo backend, the server, and the
client on ephemeral ports and verifies bytes flow through unchanged — including
streamed chunks and concurrent connections. It's the closest thing to the real
Mac↔Docker↔WSL path without external services.
