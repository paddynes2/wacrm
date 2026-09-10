"""Make the extracted core importable in a clean checkout test invocation."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest


@pytest.fixture(autouse=True)
def chris_offline_network_guard(request, monkeypatch):
    if 'test_chris_' not in request.node.nodeid:
        return
    def unexpected(*args, **kwargs):
        raise AssertionError('Unexpected network access in Chris offline acceptance')
    monkeypatch.setattr('urllib.request.OpenerDirector.open', unexpected)
    monkeypatch.setattr('socket.create_connection', unexpected)
    import socket
    original_connect = socket.socket.connect
    def connect(sock, address):
        # Windows event-loop wakeups can use a local socket pair. Real provider
        # connections are never permitted, including HTTP libraries outside urllib.
        if isinstance(address,tuple) and address[0] not in {'127.0.0.1','::1','localhost'}:
            unexpected()
        return original_connect(sock,address)
    monkeypatch.setattr(socket.socket,'connect',connect)
