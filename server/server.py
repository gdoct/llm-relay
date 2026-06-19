"""Docker-side relay server.

Listens on two ports:

  * ``listen_port`` (TCP) -- where consumers (e.g. an LLM client on WSL) connect.
    Every inbound connection becomes a multiplexed *stream*.
  * ``ws_port`` (WebSocket) -- where the Mac-side relay client attaches.

Raw bytes are piped, unmodified, in both directions. The server never parses
HTTP, so streaming responses, chunked encoding and keep-alive all just work.
"""

import argparse
import asyncio
import json
import logging
from typing import Optional

from websockets.asyncio.server import ServerConnection, serve

from llm_relay.config import RelayConfig, ServerConfig
from llm_relay.protocol import CLOSE, DATA, OPEN, decode, encode

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("llm_relay.server")

READ_CHUNK = 65536


class RelayServer:
    """Tunnels inbound TCP connections to the attached WebSocket client."""

    def __init__(self, config: ServerConfig) -> None:
        self.config = config
        # The single attached Mac client (last one wins).
        self.client: Optional[ServerConnection] = None
        # stream_id -> StreamWriter for the consumer-side TCP connection.
        self.streams: dict[int, asyncio.StreamWriter] = {}
        self._next_id = 1

    # -- consumer side (TCP) ------------------------------------------------

    async def _handle_tcp(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        """A consumer connected to ``listen_port``; forward it over the tunnel."""
        client = self.client
        peer = writer.get_extra_info("peername")
        if client is None:
            logger.warning("Rejecting %s: no relay client attached", peer)
            writer.close()
            return

        stream_id = self._next_id
        self._next_id += 1
        self.streams[stream_id] = writer
        logger.info("Stream %d opened for %s", stream_id, peer)

        try:
            await client.send(encode(OPEN, stream_id))
            while True:
                data = await reader.read(READ_CHUNK)
                if not data:
                    break
                await client.send(encode(DATA, stream_id, data))
        except Exception as e:  # consumer or client went away
            logger.debug("Stream %d read/forward ended: %s", stream_id, e)
        finally:
            self.streams.pop(stream_id, None)
            await self._safe_send(client, encode(CLOSE, stream_id))
            writer.close()
            logger.info("Stream %d closed", stream_id)

    # -- client side (WebSocket) -------------------------------------------

    async def _handle_ws(self, ws: ServerConnection) -> None:
        """The Mac relay client attached; pump its frames to the right stream."""
        if not await self._authenticate(ws):
            return

        self.client = ws
        logger.info("Relay client attached from %s", ws.remote_address)
        try:
            async for message in ws:
                if isinstance(message, str):
                    continue  # control/keepalive text frames are ignored
                msg_type, stream_id, payload = decode(message)
                writer = self.streams.get(stream_id)
                if writer is None:
                    continue
                if msg_type == DATA:
                    writer.write(payload)
                    await writer.drain()
                elif msg_type == CLOSE:
                    self.streams.pop(stream_id, None)
                    writer.close()
        except Exception as e:
            logger.debug("Relay client connection ended: %s", e)
        finally:
            if self.client is ws:
                self.client = None
            for writer in list(self.streams.values()):
                writer.close()
            self.streams.clear()
            logger.info("Relay client detached")

    async def _authenticate(self, ws: ServerConnection) -> bool:
        """Run the JSON auth handshake. Returns True if the client may attach."""
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=10.0)
            auth = json.loads(raw)
        except Exception:
            await self._safe_send(ws, json.dumps({"type": "auth_err"}))
            return False

        if self.config.auth_token and auth.get("token") != self.config.auth_token:
            logger.warning("Rejecting relay client: bad token")
            await self._safe_send(ws, json.dumps({"type": "auth_err"}))
            return False

        await ws.send(json.dumps({"type": "auth_ok"}))
        return True

    @staticmethod
    async def _safe_send(ws: Optional[ServerConnection], data: str | bytes) -> None:
        if ws is None:
            return
        try:
            await ws.send(data)
        except Exception:
            pass

    # -- lifecycle ----------------------------------------------------------

    async def run(self) -> None:
        ws_server = await serve(self._handle_ws, self.config.host, self.config.ws_port)
        tcp_server = await asyncio.start_server(
            self._handle_tcp, self.config.host, self.config.listen_port
        )
        logger.info(
            "Listening: TCP %s:%d (consumers), WebSocket %s:%d (relay client)",
            self.config.host,
            self.config.listen_port,
            self.config.host,
            self.config.ws_port,
        )
        async with ws_server, tcp_server:
            await asyncio.gather(ws_server.serve_forever(), tcp_server.serve_forever())


async def main() -> None:
    parser = argparse.ArgumentParser(description="Relay server (Docker side)")
    parser.add_argument("--config", default="server-config.yaml", help="YAML config path")
    args = parser.parse_args()

    relay_config = RelayConfig.from_file(args.config)
    if not relay_config.server:
        raise ValueError("No 'server' section found in config file")
    await RelayServer(relay_config.server).run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutting down")
