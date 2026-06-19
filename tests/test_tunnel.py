"""End-to-end tunnel test.

Wires up a fake backend (TCP echo server) + RelayServer + RelayClient, then
connects as a consumer and verifies bytes flow through unmodified, including
streamed chunks and two concurrent connections.
"""

import asyncio
import socket

import pytest

from llm_relay.config import ClientConfig, ServerConfig
from client.client import RelayClient
from server.server import RelayServer

pytestmark = pytest.mark.asyncio


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


async def _start_echo_server(port: int) -> asyncio.AbstractServer:
    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        try:
            while True:
                data = await reader.read(65536)
                if not data:
                    break
                writer.write(data)  # echo back
                await writer.drain()
        finally:
            writer.close()

    return await asyncio.start_server(handle, "127.0.0.1", port)


async def _wait_port_open(port: int) -> None:
    """Wait until something is accepting TCP connections on ``port``."""
    for _ in range(200):
        try:
            _, writer = await asyncio.open_connection("127.0.0.1", port)
            writer.close()
            return
        except OSError:
            await asyncio.sleep(0.02)
    raise TimeoutError(f"port {port} never opened")


async def _wait_for_attach(server: RelayServer) -> None:
    for _ in range(200):
        if server.client is not None:
            return
        await asyncio.sleep(0.02)
    raise TimeoutError("relay client never attached")


@pytest.fixture
async def tunnel():
    listen_port = _free_port()
    ws_port = _free_port()
    backend_port = _free_port()
    token = "test-token"

    echo = await _start_echo_server(backend_port)

    server = RelayServer(
        ServerConfig(
            listen_port=listen_port,
            ws_port=ws_port,
            host="127.0.0.1",
            auth_token=token,
        )
    )
    server_task = asyncio.create_task(server.run())
    await _wait_port_open(ws_port)

    client = RelayClient(
        ClientConfig(
            server_url=f"ws://127.0.0.1:{ws_port}",
            backend_host="127.0.0.1",
            backend_port=backend_port,
            auth_token=token,
        )
    )
    client_task = asyncio.create_task(client.run())

    await _wait_for_attach(server)

    yield listen_port

    for task in (client_task, server_task):
        task.cancel()
    echo.close()
    await asyncio.gather(client_task, server_task, return_exceptions=True)
    await echo.wait_closed()


async def test_single_roundtrip(tunnel):
    listen_port = tunnel
    reader, writer = await asyncio.open_connection("127.0.0.1", listen_port)
    writer.write(b"ping")
    await writer.drain()
    data = await asyncio.wait_for(reader.readexactly(4), timeout=5)
    assert data == b"ping"
    writer.close()


async def test_streamed_chunks(tunnel):
    listen_port = tunnel
    reader, writer = await asyncio.open_connection("127.0.0.1", listen_port)
    chunks = [f"chunk-{i:03d};".encode() for i in range(50)]
    for c in chunks:
        writer.write(c)
        await writer.drain()
        await asyncio.sleep(0.001)
    expected = b"".join(chunks)
    data = await asyncio.wait_for(reader.readexactly(len(expected)), timeout=5)
    assert data == expected
    writer.close()


async def test_concurrent_connections(tunnel):
    listen_port = tunnel

    async def roundtrip(tag: bytes) -> bytes:
        reader, writer = await asyncio.open_connection("127.0.0.1", listen_port)
        writer.write(tag)
        await writer.drain()
        data = await asyncio.wait_for(reader.readexactly(len(tag)), timeout=5)
        writer.close()
        return data

    results = await asyncio.gather(
        roundtrip(b"AAAAAAAA"), roundtrip(b"BBBBBBBB"), roundtrip(b"CCCCCCCC")
    )
    assert results == [b"AAAAAAAA", b"BBBBBBBB", b"CCCCCCCC"]
