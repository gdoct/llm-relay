"""Binary framing for the TCP-over-WebSocket tunnel.

Each WebSocket binary message carries one frame:

    +--------+------------------+--------------------+
    | 1 byte | 4 bytes (uint32) | payload (variable) |
    | type   | stream_id        | raw TCP bytes      |
    +--------+------------------+--------------------+

A *stream* is one end-to-end TCP connection (one WSL client connection on the
server side, mapped to one backend connection on the client side). Streams are
multiplexed over the single WebSocket so many connections run concurrently.
"""

import struct

# Frame types
OPEN = 1  # a new TCP connection arrived; open the matching backend connection
DATA = 2  # raw bytes belonging to a stream
CLOSE = 3  # the stream's TCP connection closed

_HEADER = struct.Struct(">BI")  # type (1 byte) + stream_id (uint32, big-endian)


def encode(msg_type: int, stream_id: int, payload: bytes = b"") -> bytes:
    """Encode a frame to bytes for sending as a WebSocket binary message."""
    return _HEADER.pack(msg_type, stream_id) + payload


def decode(frame: bytes) -> tuple[int, int, bytes]:
    """Decode a frame into (msg_type, stream_id, payload)."""
    msg_type, stream_id = _HEADER.unpack_from(frame, 0)
    return msg_type, stream_id, frame[_HEADER.size :]
