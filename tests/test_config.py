"""Tests for configuration loading."""

import textwrap

import pytest

from llm_relay.config import RelayConfig


def test_server_config_from_dict_defaults():
    cfg = RelayConfig.from_dict({"server": {}})
    assert cfg.server is not None
    assert cfg.client is None
    assert cfg.server.listen_port == 1234
    assert cfg.server.ws_port == 1235
    assert cfg.server.host == "0.0.0.0"


def test_client_config_from_dict():
    cfg = RelayConfig.from_dict(
        {
            "client": {
                "server_url": "ws://docker:1235",
                "backend_host": "127.0.0.1",
                "backend_port": 9000,
                "auth_token": "secret",
            }
        }
    )
    assert cfg.client is not None
    assert cfg.client.server_url == "ws://docker:1235"
    assert cfg.client.backend_port == 9000
    assert cfg.client.auth_token == "secret"


def test_from_file(tmp_path):
    path = tmp_path / "server-config.yaml"
    path.write_text(textwrap.dedent("""
            server:
              listen_port: 1234
              ws_port: 1235
              auth_token: hunter2
            """))
    cfg = RelayConfig.from_file(str(path))
    assert cfg.server is not None
    assert cfg.server.auth_token == "hunter2"


def test_from_file_missing():
    with pytest.raises(FileNotFoundError):
        RelayConfig.from_file("/no/such/config.yaml")
