"""Shared fixtures. Tests never touch the network: any socket connect fails loudly."""
import socket
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def guard(*args, **kwargs):
        raise RuntimeError("network access in tests is not allowed")
    monkeypatch.setattr(socket.socket, "connect", guard)
    monkeypatch.setattr(socket, "create_connection", guard)


@pytest.fixture
def fixture_bytes():
    return lambda name: (FIXTURES / name).read_bytes()
