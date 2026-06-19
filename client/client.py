"""Mac-side relay client.

Connects out to the Docker server over WebSocket and, for each stream the
server opens, dials the local backend (llama-server) and pipes raw bytes both
ways. Reconnects automatically if the WebSocket drops.
"""

import argparse
import asyncio
import json
import logging
from typing import Optional

from websockets.asyncio.client import ClientConnection, connect

from llm_relay.config import RelayConfig, ClientConfig
from llm_relay.protocol import CLOSE, DATA, OPEN, decode, encode

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("llm_relay.client")

READ_CHUNK = 65536
RECONNECT_DELAY = 3.0


class RelayClient:
    """Attaches to the relay server and forwards streams to a local backend."""

    def __init__(self, config: ClientConfig) -> None:
        self.config = config
        self.ws: Optional[ClientConnection] = None
        # stream_id -> StreamWriter for the backend (llama-server) connection.
        self.streams: dict[int, asyncio.StreamWriter] = {}

    async def run(self) -> None:
        """Connect, serve, and reconnect forever."""
        while True:
            try:
                await self._serve()
            except Exception as e:
                logger.error("Connection error: %s", e)
            logger.info("Reconnecting in %.0fs ...", RECONNECT_DELAY)
            await asyncio.sleep(RECONNECT_DELAY)

    async def _serve(self) -> None:
        async with connect(self.config.server_url) as ws:
            self.ws = ws
            await ws.send(json.dumps({"type": "auth", "token": self.config.auth_token}))
            reply = json.loads(await ws.recv())
            if reply.get("type") != "auth_ok":
                raise RuntimeError("authentication rejected by server")
            logger.info(
                "Attached to %s, forwarding to backend %s:%d",
                self.config.server_url,
                self.config.backend_host,
                self.config.backend_port,
            )
            try:
                async for message in ws:
                    if isinstance(message, str):
                        continue
                    await self._dispatch(message)
            finally:
                self.ws = None
                for writer in list(self.streams.values()):
                    writer.close()
                self.streams.clear()

    async def _dispatch(self, message: bytes) -> None:
        msg_type, stream_id, payload = decode(message)
        if msg_type == OPEN:
            # Open the backend connection synchronously so that DATA frames
            # arriving right after OPEN find the writer already registered.
            await self._open_backend(stream_id)
        elif msg_type == DATA:
            writer = self.streams.get(stream_id)
            if writer is not None:
                writer.write(payload)
                await writer.drain()
        elif msg_type == CLOSE:
            writer = self.streams.pop(stream_id, None)
            if writer is not None:
                writer.close()

    async def _open_backend(self, stream_id: int) -> None:
        try:
            reader, writer = await asyncio.open_connection(
                self.config.backend_host, self.config.backend_port
            )
        except Exception as e:
            logger.error("Stream %d: backend connect failed: %s", stream_id, e)
            await self._safe_send(encode(CLOSE, stream_id))
            return
        self.streams[stream_id] = writer
        asyncio.create_task(self._pump_backend(stream_id, reader, writer))

    async def _pump_backend(
        self,
        stream_id: int,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Forward backend -> server until the backend closes the connection."""
        try:
            while True:
                data = await reader.read(READ_CHUNK)
                if not data:
                    break
                await self._safe_send(encode(DATA, stream_id, data))
        except Exception as e:
            logger.debug("Stream %d backend pump ended: %s", stream_id, e)
        finally:
            self.streams.pop(stream_id, None)
            await self._safe_send(encode(CLOSE, stream_id))
            writer.close()

    async def _safe_send(self, data: bytes) -> None:
        ws = self.ws
        if ws is None:
            return
        try:
            await ws.send(data)
        except Exception:
            pass


async def main() -> None:
    parser = argparse.ArgumentParser(description="Relay client (Mac side)")
    parser.add_argument("--config", default="client-config.yaml", help="YAML config path")
    args = parser.parse_args()

    relay_config = RelayConfig.from_file(args.config)
    if not relay_config.client:
        raise ValueError("No 'client' section found in config file")
    await RelayClient(relay_config.client).run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutting down")
