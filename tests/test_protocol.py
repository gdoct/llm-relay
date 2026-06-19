"""Tests for the binary tunnel framing."""

from llm_relay.protocol import CLOSE, DATA, OPEN, decode, encode


def test_roundtrip_data():
    frame = encode(DATA, 42, b"hello world")
    msg_type, stream_id, payload = decode(frame)
    assert msg_type == DATA
    assert stream_id == 42
    assert payload == b"hello world"


def test_roundtrip_open_close_empty_payload():
    for kind in (OPEN, CLOSE):
        msg_type, stream_id, payload = decode(encode(kind, 7))
        assert msg_type == kind
        assert stream_id == 7
        assert payload == b""


def test_large_stream_id():
    big = 4_000_000_000  # within uint32 range
    _, stream_id, _ = decode(encode(DATA, big, b"x"))
    assert stream_id == big


def test_payload_with_binary_bytes():
    blob = bytes(range(256))
    _, _, payload = decode(encode(DATA, 1, blob))
    assert payload == blob
