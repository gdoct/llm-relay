# llm-relay

`llm-relay` tunnels raw TCP connections over a single WebSocket. It lets a
machine that can only make *outbound* connections expose a local service to a
machine that can only reach it through the relay.

The original use case: run an LLM (llama-server) on your Mac and use it as a
backend from another machine, with a Docker host in the middle as the relay.

```
[ Mac ]                         [ Docker host ]                 [ WSL ]
 llama-server  <--TCP--  relay client ==WS==> relay server  <--TCP--  LLM app
   :8080                          (:1235)         (:1234)
```

- The **Mac** runs `llama-server` and the **relay client**. The client dials
  *out* to the Docker host over WebSocket — no inbound ports needed on the Mac.
- The **Docker host** runs the **relay server**. It listens on `1234` for
  consumers and on `1235` for the WebSocket from the Mac.
- **WSL** points its LLM client at `http://<docker-host>:1234` as if it were
  the model server. Requests are tunnelled to the Mac and responses stream back.

Because the relay forwards **raw bytes** and never parses HTTP, any path
(`/v1/chat/completions`, `/completion`, …), streaming token output, chunked
encoding and keep-alive all work transparently.

Written for Python 3.13. Uses `uv`, `pytest`, `flake8`, `black`, `pyright`.

## Components

- **server** (`server/server.py`) — runs on the Docker host. Listens on a TCP
  port for consumers and a WebSocket port for the client. Each inbound TCP
  connection becomes a multiplexed *stream* on the WebSocket.
- **client** (`client/client.py`) — runs on the Mac. Connects out to the server,
  and for each stream opens a TCP connection to the local backend
  (llama-server), piping bytes both ways. Reconnects automatically.

See [QUICKSTART.md](QUICKSTART.md) for setup and [DEVELOPMENT.md](DEVELOPMENT.md)
for the protocol and internals.
