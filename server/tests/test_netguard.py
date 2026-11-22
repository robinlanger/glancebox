import asyncio
import contextlib
import logging

import pytest

from glancebox import netguard
from glancebox.netguard import GuardProxy, blocked_host


@pytest.mark.parametrize("host,page_host,expected", [
    ("example.org", None, False),
    ("192.168.1.20", None, False),
    ("homeassistant", "homeassistant", False),
    ("HomeAssistant.", "homeassistant", False),
    ("homeassistant", "example.org", True),
    ("SUPERVISOR", None, True),
    ("supervisor.", None, True),
    ("localhost.", None, True),
    ("foo.localhost", None, True),
    ("a0d7b954-ssh.local.hass.io", None, True),
    ("x.local.hass.io.", None, True),
    ("172.30.32.2", None, True),
    ("172.30.33.5", None, True),
    ("172.30.34.1", None, False),
    ("127.0.0.1", None, True),
    ("127.0.0.1", "127.0.0.1", False),
    ("0.0.0.0", None, True),
    ("[::1]", None, True),
    ("::", None, True),
    ("::ffff:127.0.0.1", None, True),
    ("169.254.169.254", None, True),
    ("fe80::1", None, True),
    ("", None, True),
])
def test_blocked_host(host, page_host, expected):
    assert blocked_host(host, page_host) is expected


class Upstream:
    """A local HTTP server on 127.0.0.1 that records the request heads it saw."""

    def __init__(self) -> None:
        self.seen: list[str] = []
        self.server: asyncio.Server | None = None

    @property
    def port(self) -> int:
        return self.server.sockets[0].getsockname()[1]

    async def _handle(self, reader, writer):
        try:
            head = await reader.readuntil(b"\r\n\r\n")
            self.seen.append(head.decode("latin-1"))
            writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 8\r\nConnection: close\r\n\r\n"
                         b"upstream")
            await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionError):
            pass
        finally:
            writer.close()

    def paths(self) -> list[str]:
        return [head.split(" ")[1] for head in self.seen]


@pytest.fixture
async def upstream():
    up = Upstream()
    up.server = await asyncio.start_server(up._handle, "127.0.0.1", 0)
    yield up
    up.server.close()
    await up.server.wait_closed()


@pytest.fixture
async def make_proxy():
    proxies: list[GuardProxy] = []

    def make(resolve=None) -> GuardProxy:
        proxies.append(GuardProxy(resolve))
        return proxies[-1]

    yield make
    for p in proxies:
        await p.close()


def _port(url: str) -> int:
    assert url.startswith("http://127.0.0.1:")
    return int(url.rsplit(":", 1)[1])


async def _ask(url: str, raw: bytes) -> bytes:
    """Send raw bytes to the proxy and read until it closes."""
    reader, writer = await asyncio.open_connection("127.0.0.1", _port(url))
    try:
        writer.write(raw)
        await writer.drain()
        async with asyncio.timeout(5):
            return await reader.read()
    finally:
        writer.close()
        await writer.wait_closed()


def _status(answer: bytes) -> int:
    return int(answer.split(b" ", 2)[1])


def _resolver(mapping: dict[str, list[str]], calls: list[str] | None = None):
    async def resolve(host: str, port: int) -> list[str]:
        if calls is not None:
            calls.append(host)
        return mapping[host]
    return resolve


async def test_proxy_forwards_allowed_page_host(make_proxy, upstream):
    url = await make_proxy().url_for("127.0.0.1")
    answer = await _ask(url, f"GET http://127.0.0.1:{upstream.port}/ok HTTP/1.1\r\n"
                             f"Host: 127.0.0.1:{upstream.port}\r\nProxy-Connection: keep-alive\r\n"
                             "Proxy-Authorization: Basic eDp5\r\nConnection: keep-alive\r\n"
                             "\r\n".encode())
    assert _status(answer) == 200
    assert answer.endswith(b"\r\n\r\nupstream")
    assert upstream.paths() == ["/ok"]
    head = upstream.seen[0]
    assert head.startswith("GET /ok HTTP/1.1\r\n")
    assert "proxy-" not in head.lower()
    assert "\r\nConnection: close\r\n" in head
    assert "keep-alive" not in head


async def test_proxy_blocks_loopback_without_exemption(make_proxy, upstream):
    url = await make_proxy().url_for(None)
    answer = await _ask(url, f"GET http://127.0.0.1:{upstream.port}/ok HTTP/1.1\r\n\r\n".encode())
    assert _status(answer) == 403
    assert b"Connection: close" in answer
    assert answer.endswith(b"blocked by glancebox\n")
    assert upstream.seen == []


async def test_proxy_blocks_name_resolving_to_internal_address(make_proxy, upstream):
    proxy = make_proxy(_resolver({"rebind.test": ["127.0.0.1"]}))
    url = await proxy.url_for(None)
    answer = await _ask(url, f"GET http://rebind.test:{upstream.port}/x HTTP/1.1\r\n\r\n".encode())
    assert _status(answer) == 403
    assert upstream.seen == []


async def test_proxy_blocks_if_any_address_is_internal(make_proxy, upstream):
    proxy = make_proxy(_resolver({"mixed.test": ["93.184.216.34", "172.30.32.2"]}))
    url = await proxy.url_for(None)
    answer = await _ask(url, b"GET http://mixed.test/x HTTP/1.1\r\n\r\n")
    assert _status(answer) == 403


async def test_proxy_connect_blocked(make_proxy, caplog):
    url = await make_proxy().url_for(None)
    with caplog.at_level(logging.INFO, logger="glancebox.netguard"):
        answer = await _ask(url, b"CONNECT supervisor:443 HTTP/1.1\r\nHost: supervisor:443\r\n\r\n")
    assert _status(answer) == 403
    assert "page request blocked: supervisor" in caplog.text


async def test_proxy_connect_ipv6_loopback_blocked(make_proxy):
    url = await make_proxy().url_for(None)
    answer = await _ask(url, b"CONNECT [::1]:443 HTTP/1.1\r\n\r\n")
    assert _status(answer) == 403


async def test_proxy_connect_tunnels(make_proxy, upstream):
    url = await make_proxy().url_for("127.0.0.1")
    reader, writer = await asyncio.open_connection("127.0.0.1", _port(url))
    try:
        writer.write(f"CONNECT 127.0.0.1:{upstream.port} HTTP/1.1\r\n\r\n".encode())
        async with asyncio.timeout(5):
            reply = await reader.readuntil(b"\r\n\r\n")
            assert reply == b"HTTP/1.1 200 Connection established\r\n\r\n"
            writer.write(b"GET /tunnel HTTP/1.1\r\nHost: x\r\n\r\n")
            answer = await reader.read()
    finally:
        writer.close()
        await writer.wait_closed()
    assert _status(answer) == 200
    assert upstream.paths() == ["/tunnel"]


async def test_proxy_pins_checked_address(make_proxy, upstream):
    calls: list[str] = []
    proxy = make_proxy(_resolver({"pin.test": ["127.0.0.1"]}, calls))
    url = await proxy.url_for("pin.test")
    answer = await _ask(url, f"GET http://pin.test:{upstream.port}/p HTTP/1.1\r\n\r\n".encode())
    assert _status(answer) == 200
    assert calls == ["pin.test"]
    assert upstream.paths() == ["/p"]


async def test_proxy_unreachable_upstream_is_502(make_proxy):
    server = await asyncio.start_server(lambda r, w: None, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    server.close()
    await server.wait_closed()
    url = await make_proxy().url_for("127.0.0.1")
    answer = await _ask(url, f"GET http://127.0.0.1:{port}/ HTTP/1.1\r\n\r\n".encode())
    assert _status(answer) == 502


async def test_proxy_unresolvable_name_is_502(make_proxy):
    proxy = make_proxy(_resolver({"empty.test": []}))
    url = await proxy.url_for(None)
    answer = await _ask(url, b"GET http://empty.test/ HTTP/1.1\r\n\r\n")
    assert _status(answer) == 502


async def test_proxy_name_the_resolver_rejects_is_502(make_proxy):
    url = await make_proxy().url_for(None)  # real getaddrinfo: an empty label fails to encode
    answer = await _ask(url, b"GET http://a..b/ HTTP/1.1\r\n\r\n")
    assert _status(answer) == 502


@pytest.mark.parametrize("raw", [
    b"FOO\r\n\r\n",
    b"GET /relative HTTP/1.1\r\n\r\n",
    b"GET https://example.org/ HTTP/1.1\r\n\r\n",
    b"GET http://user@example.org/ HTTP/1.1\r\n\r\n",
    b"GET http://[::1/ HTTP/1.1\r\n\r\n",
    b"GET http://example.org:http/ HTTP/1.1\r\n\r\n",
    b"GET  http://example.org/ HTTP/1.1\r\n\r\n",
    b"GET http://example.org/ HTTP/2\r\n\r\n",
    b"GET http://example.org/ HTTP/1.1\r\nno colon here\r\n\r\n",
    b"CONNECT example.org HTTP/1.1\r\n\r\n",
    b"CONNECT a@example.org:443 HTTP/1.1\r\n\r\n",
    b"CONNECT example.org:0 HTTP/1.1\r\n\r\n",
    b"CONNECT example.org:99999 HTTP/1.1\r\n\r\n",
    b"CONNECT ::1:443 HTTP/1.1\r\n\r\n",
    b"CONNECT [fe80::1%25lo]:443 HTTP/1.1\r\n\r\n",
    "GET http://exämple.org/ HTTP/1.1\r\n\r\n".encode(),
])
async def test_proxy_rejects_malformed_requests(make_proxy, raw):
    url = await make_proxy(_resolver({})).url_for(None)
    assert _status(await _ask(url, raw)) == 400


async def test_proxy_rejects_garbage_and_oversized_head(make_proxy):
    url = await make_proxy().url_for(None)
    assert _status(await _ask(url, b"FOO\r\n\r\n")) == 400
    try:
        answer = await _ask(url, b"GET http://example.org/ HTTP/1.1\r\nX: " + b"a" * 70000)
    except ConnectionResetError:
        answer = b""
    assert answer == b""


async def test_proxy_closes_slow_head(make_proxy, monkeypatch):
    monkeypatch.setattr(netguard, "HEAD_TIMEOUT_S", 0.2)
    url = await make_proxy().url_for(None)
    reader, writer = await asyncio.open_connection("127.0.0.1", _port(url))
    try:
        writer.write(b"GET http://example.org/ HTTP/1.1\r\n")
        async with asyncio.timeout(5):
            assert await reader.read() == b""
    finally:
        writer.close()
        await writer.wait_closed()


async def test_proxy_close_stops_listeners(upstream):
    proxy = GuardProxy()
    url = await proxy.url_for("127.0.0.1")
    # One idle tunnel stays open; close() must end it too.
    reader, writer = await asyncio.open_connection("127.0.0.1", _port(url))
    writer.write(f"CONNECT 127.0.0.1:{upstream.port} HTTP/1.1\r\n\r\n".encode())
    await reader.readuntil(b"\r\n\r\n")
    await proxy.close()
    async with asyncio.timeout(5):
        assert await reader.read() == b""
    writer.close()
    await writer.wait_closed()
    with pytest.raises(OSError):
        await asyncio.open_connection("127.0.0.1", _port(url))


async def test_proxy_close_does_not_wait_for_a_client_that_never_reads():
    body = b"x" * (4 * 1024 * 1024)

    async def flood(reader, writer):
        await reader.readuntil(b"\r\n\r\n")
        writer.write(b"HTTP/1.1 200 OK\r\nConnection: close\r\n\r\n" + body)
        with contextlib.suppress(ConnectionError):
            await writer.drain()
        writer.close()

    server = await asyncio.start_server(flood, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    proxy = GuardProxy()
    url = await proxy.url_for("127.0.0.1")
    _, writer = await asyncio.open_connection("127.0.0.1", _port(url))
    writer.write(f"GET http://127.0.0.1:{port}/big HTTP/1.1\r\n\r\n".encode())
    await asyncio.sleep(0.5)  # never read: the proxy's buffers towards the client fill up
    async with asyncio.timeout(5):
        await proxy.close()
    writer.transport.abort()
    server.close()
    async with asyncio.timeout(5):
        await server.wait_closed()


async def test_url_for_reuses_listener_per_page_host(make_proxy):
    proxy = make_proxy()
    a = await proxy.url_for("Example.org.")
    assert a == await proxy.url_for("example.org")
    assert a != await proxy.url_for(None)
