import asyncio
import contextlib
import logging
import socket

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
    ("172.30.232.1", None, True),
    ("172.30.234.1", None, False),
    ("fd0c:ac1e:2100::2", None, True),
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
    # Only the injected resolver knows this name; the answer arriving proves the proxy connected
    # to the address it checked instead of resolving again. (An internal page host is used
    # because the only server here is on loopback.)
    calls: list[str] = []
    proxy = make_proxy(_resolver({"pin.local.hass.io": ["127.0.0.1"]}, calls))
    url = await proxy.url_for("pin.local.hass.io")
    answer = await _ask(url, f"GET http://pin.local.hass.io:{upstream.port}/p HTTP/1.1\r\n\r\n"
                        .encode())
    assert _status(answer) == 200
    assert calls == ["pin.local.hass.io"]
    assert upstream.paths() == ["/p"]


async def test_proxy_exempt_name_still_checked_by_address(make_proxy, upstream):
    proxy = make_proxy(_resolver({"page.test": ["127.0.0.1"]}))
    url = await proxy.url_for("page.test")
    answer = await _ask(url, f"GET http://page.test:{upstream.port}/ HTTP/1.1\r\n\r\n".encode())
    assert _status(answer) == 403
    assert upstream.seen == []


async def test_proxy_exempt_internal_name_skips_address_check(make_proxy, upstream):
    calls: list[str] = []
    proxy = make_proxy(_resolver({"homeassistant": ["127.0.0.1"]}, calls))
    url = await proxy.url_for("homeassistant")
    answer = await _ask(url, f"GET http://homeassistant:{upstream.port}/ha HTTP/1.1\r\n\r\n"
                        .encode())
    assert _status(answer) == 200
    assert upstream.paths() == ["/ha"]
    assert calls == ["homeassistant"]  # resolved once, then connected to that address


async def test_proxy_exempt_single_label_name_skips_address_check(make_proxy, upstream):
    # Other add-ons are reached by a single-label host name that resolves into the hassio
    # network; the configured page host may show one.
    proxy = make_proxy(_resolver({"a0d7b954-grafana": ["127.0.0.1"]}))
    url = await proxy.url_for("a0d7b954-grafana")
    answer = await _ask(url, f"GET http://a0d7b954-grafana:{upstream.port}/g HTTP/1.1\r\n\r\n"
                        .encode())
    assert _status(answer) == 200
    assert upstream.paths() == ["/g"]


@pytest.mark.parametrize("page_host", [None, "page.test", "other-addon"])
async def test_proxy_single_label_name_checked_unless_it_is_the_page_host(
        make_proxy, upstream, page_host):
    proxy = make_proxy(_resolver({"a0d7b954-grafana": ["127.0.0.1"], "page.test": ["127.0.0.1"],
                                  "other-addon": ["127.0.0.1"]}))
    url = await proxy.url_for(page_host)
    answer = await _ask(url, f"GET http://a0d7b954-grafana:{upstream.port}/g HTTP/1.1\r\n\r\n"
                        .encode())
    assert _status(answer) == 403
    assert upstream.seen == []


def _closed_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def test_proxy_tries_each_checked_address_in_order(make_proxy, upstream, monkeypatch):
    monkeypatch.setattr(netguard, "CONNECT_TIMEOUT_S", 2)
    # ::1 has nothing listening on this port (the upstream is IPv4 only): refused or unroutable.
    calls: list[str] = []
    proxy = make_proxy(_resolver({"multi.local.hass.io": ["::1", "127.0.0.1"]}, calls))
    url = await proxy.url_for("multi.local.hass.io")
    answer = await _ask(url, f"GET http://multi.local.hass.io:{upstream.port}/m HTTP/1.1\r\n\r\n"
                        .encode())
    assert _status(answer) == 200
    assert upstream.paths() == ["/m"]
    assert calls == ["multi.local.hass.io"]


async def test_proxy_all_addresses_unreachable_is_502_and_logged(make_proxy, caplog):
    port = _closed_port()
    proxy = make_proxy(_resolver({"dead.local.hass.io": ["127.0.0.1", "127.0.0.1"]}))
    url = await proxy.url_for("dead.local.hass.io")
    with caplog.at_level(logging.INFO, logger="glancebox.netguard"):
        answer = await _ask(url, f"GET http://dead.local.hass.io:{port}/ HTTP/1.1\r\n\r\n"
                            .encode())
    assert _status(answer) == 502
    assert b"X-Glancebox-Guard: unreachable\r\n" in answer
    msgs = [r for r in caplog.records if r.name == "glancebox.netguard"]
    assert [(r.levelno, r.getMessage()) for r in msgs] == [
        (logging.INFO, "page request failed: dead.local.hass.io: cannot connect")]


@pytest.mark.parametrize("mapping", [{"empty.test": []}, {}])
async def test_proxy_resolve_failure_is_logged_with_host_only(make_proxy, caplog, mapping):
    async def resolve(host, port):
        if host not in mapping:
            raise OSError("resolver says no for http://x/?secret")
        return mapping[host]

    url = await make_proxy(resolve).url_for(None)
    with caplog.at_level(logging.INFO, logger="glancebox.netguard"):
        answer = await _ask(url, b"GET http://empty.test/ HTTP/1.1\r\n\r\n")
    assert _status(answer) == 502
    msgs = [r for r in caplog.records if r.name == "glancebox.netguard"]
    assert [(r.levelno, r.getMessage()) for r in msgs] == [
        (logging.INFO, "page request failed: empty.test: cannot resolve")]


async def test_proxy_error_answers_carry_guard_header(make_proxy):
    url = await make_proxy(_resolver({"empty.test": []})).url_for(None)
    blocked = await _ask(url, b"GET http://supervisor/ HTTP/1.1\r\n\r\n")
    assert b"\r\nX-Glancebox-Guard: blocked\r\n" in blocked
    unresolved = await _ask(url, b"GET http://empty.test/ HTTP/1.1\r\n\r\n")
    assert b"\r\nX-Glancebox-Guard: unreachable\r\n" in unresolved
    bad = await _ask(url, b"FOO\r\n\r\n")
    assert b"\r\nX-Glancebox-Guard: unreachable\r\n" in bad


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


class SilentUpstream:
    """Accepts connections, reads the request head, then never answers nor closes."""

    def __init__(self) -> None:
        self.release = asyncio.Event()
        self.heads = 0
        self.server: asyncio.Server | None = None

    async def _handle(self, reader, writer):
        try:
            with contextlib.suppress(asyncio.IncompleteReadError, ConnectionError):
                await reader.readuntil(b"\r\n\r\n")
                self.heads += 1
            await self.release.wait()
        finally:
            writer.close()

    @property
    def port(self) -> int:
        return self.server.sockets[0].getsockname()[1]


@pytest.fixture
async def silent():
    up = SilentUpstream()
    up.server = await asyncio.start_server(up._handle, "127.0.0.1", 0)
    yield up
    up.release.set()
    up.server.close()
    async with asyncio.timeout(5):
        await up.server.wait_closed()


def _live(proxy: GuardProxy) -> tuple[int, int]:
    """(handler tasks, transports not closing) the proxy still holds."""
    return len(proxy._tasks), sum(not t.is_closing() for t in proxy._transports)


async def _wait_until_idle(proxy: GuardProxy, within_s: float) -> tuple[int, int]:
    deadline = asyncio.get_running_loop().time() + within_s
    while _live(proxy) != (0, 0) and asyncio.get_running_loop().time() < deadline:
        await asyncio.sleep(0.05)
    return _live(proxy)


@pytest.mark.parametrize("connect", [False, True])
async def test_proxy_ends_connection_when_client_left_and_upstream_is_silent(
        make_proxy, silent, monkeypatch, connect):
    monkeypatch.setattr(netguard, "CLIENT_GONE_GRACE_S", 0.2)
    proxy = make_proxy()
    url = await proxy.url_for("127.0.0.1")
    reader, writer = await asyncio.open_connection("127.0.0.1", _port(url))
    if connect:
        writer.write(f"CONNECT 127.0.0.1:{silent.port} HTTP/1.1\r\n\r\n".encode())
        await reader.readuntil(b"\r\n\r\n")
        writer.write(b"GET / HTTP/1.1\r\nHost: x\r\n\r\n")
    else:
        writer.write(f"GET http://127.0.0.1:{silent.port}/ HTTP/1.1\r\n\r\n".encode())
    await writer.drain()
    while silent.heads == 0:
        await asyncio.sleep(0.01)
    writer.close()  # Chromium is done with this connection
    await writer.wait_closed()
    assert await _wait_until_idle(proxy, 3) == (0, 0)


async def test_proxy_closes_connection_after_lifetime_cap(make_proxy, silent, monkeypatch):
    monkeypatch.setattr(netguard, "MAX_CONNECTION_S", 0.3)
    proxy = make_proxy()
    url = await proxy.url_for("127.0.0.1")
    reader, writer = await asyncio.open_connection("127.0.0.1", _port(url))
    try:
        writer.write(f"CONNECT 127.0.0.1:{silent.port} HTTP/1.1\r\n\r\n".encode())
        async with asyncio.timeout(5):
            assert await reader.readuntil(b"\r\n\r\n") == (
                b"HTTP/1.1 200 Connection established\r\n\r\n")
            assert await reader.read() == b""  # idle tunnel, client still there: cap closes it
    finally:
        writer.close()
        with contextlib.suppress(ConnectionError):
            await writer.wait_closed()
    assert await _wait_until_idle(proxy, 3) == (0, 0)


async def test_url_for_reuses_listener_per_page_host(make_proxy):
    proxy = make_proxy()
    a = await proxy.url_for("Example.org.")
    assert a == await proxy.url_for("example.org")
    assert a != await proxy.url_for(None)
