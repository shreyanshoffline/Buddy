"""Local backend lifecycle tests without binding a real port."""

from backend.runtime import LocalBackend, _port


class FakeServer:
    def __init__(self):
        self.stopped = False
        self.closed = False

    def shutdown(self):
        self.stopped = True

    def server_close(self):
        self.closed = True


def test_local_backend_stop_only_closes_its_own_server():
    server = FakeServer()
    handle = LocalBackend("127.0.0.1", 5000, server=server)
    assert handle.url == "http://127.0.0.1:5000"
    handle.stop()
    assert server.stopped and server.closed and handle.server is None


def test_backend_port_has_safe_default(monkeypatch):
    monkeypatch.delenv("BUDDY_BACKEND_PORT", raising=False)
    assert _port() == 5000
    monkeypatch.setenv("BUDDY_BACKEND_PORT", "not-a-port")
    assert _port() == 5000
