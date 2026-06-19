"""Configuration for the relay.

The relay has two roles, each described by one top-level key in a YAML file:

    server:   # runs on the Docker host
      listen_port: 1234   # WSL / LLM clients connect here (plain TCP/HTTP)
      ws_port: 1235       # the Mac relay client connects here (WebSocket)
      auth_token: "..."   # shared secret the client must present

    client:   # runs on the Mac, next to llama-server
      server_url: "ws://your-docker-host:1235"
      backend_host: "127.0.0.1"
      backend_port: 8080  # the local llama-server port
      auth_token: "..."   # must match the server

A file contains exactly one of these keys.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import yaml


@dataclass
class ServerConfig:
    """Configuration for the Docker-side server."""

    listen_port: int = 1234
    ws_port: int = 1235
    host: str = "0.0.0.0"
    auth_token: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ServerConfig":
        return cls(
            listen_port=int(data.get("listen_port", 1234)),
            ws_port=int(data.get("ws_port", 1235)),
            host=str(data.get("host", "0.0.0.0")),
            auth_token=str(data.get("auth_token", "")),
        )


@dataclass
class ClientConfig:
    """Configuration for the Mac-side client."""

    server_url: str = "ws://localhost:1235"
    backend_host: str = "127.0.0.1"
    backend_port: int = 8080
    auth_token: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ClientConfig":
        return cls(
            server_url=str(data.get("server_url", "ws://localhost:1235")),
            backend_host=str(data.get("backend_host", "127.0.0.1")),
            backend_port=int(data.get("backend_port", 8080)),
            auth_token=str(data.get("auth_token", "")),
        )


@dataclass
class RelayConfig:
    """Root configuration; holds whichever role the file describes."""

    server: Optional[ServerConfig] = None
    client: Optional[ClientConfig] = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RelayConfig":
        config = cls()
        if data.get("server") is not None:
            config.server = ServerConfig.from_dict(data["server"])
        if data.get("client") is not None:
            config.client = ClientConfig.from_dict(data["client"])
        return config

    @classmethod
    def from_file(cls, config_path: str) -> "RelayConfig":
        path = Path(config_path)
        if not path.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_path}")
        with open(path) as f:
            data: dict[str, Any] = yaml.safe_load(f) or {}
        return cls.from_dict(data)
