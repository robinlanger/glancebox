"""Keep rendered pages away from Home Assistant internals.

Every browser context sends all its traffic through a ``GuardProxy`` listener. The proxy checks
the target host name and every address it resolves to, then connects to exactly the address it
checked, so redirects, DNS rebinding and WebSockets cannot get around the rules.
"""

import asyncio
import ipaddress
import logging
import re
import socket
import weakref
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from functools import partial

log = logging.getLogger(__name__)

BLOCKED_HOSTS = frozenset({"supervisor", "hassio", "homeassistant", "observer", "localhost"})
BLOCKED_HOST_SUFFIXES = (".localhost", ".local.hass.io")
BLOCKED_NETWORKS = tuple(ipaddress.ip_network(n) for n in (
    "0.0.0.0/8", "127.0.0.0/8", "169.254.0.0/16",
    "172.30.32.0/23",  # hassio network (Supervisor, add-ons)
    "172.30.232.0/23",  # HAOS docker0
    "::/128", "::1/128", "fe80::/10",
    "fd0c:ac1e:2100::/48",  # hassio network, IPv6
))

HEAD_LIMIT = 65536  # bytes of request head the proxy reads at most
HEAD_TIMEOUT_S = 10
RESOLVE_TIMEOUT_S = 10
CONNECT_TIMEOUT_S = 10
CLIENT_GONE_GRACE_S = 5  # once the client side ended, wait at most this long for the upstream
MAX_CONNECTION_S = 120  # every proxy connection (tunnels included) is closed after this
RELAY_CHUNK = 65536

_TOKEN = re.compile(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+")
_HOST_NAME = re.compile(r"[0-9A-Za-z_.-]+")
_PORT = re.compile(r"[0-9]{1,5}")
_HOP_HEADERS = frozenset({"connection", "proxy-connection", "proxy-authorization"})
_ERRORS = {
    400: ("Bad Request", "bad request\n"),
    403: ("Forbidden", "blocked by glancebox\n"),
    502: ("Bad Gateway", "upstream unreachable\n"),
}

Resolver = Callable[[str, int], Awaitable[list[str]]]


def normalize_host(host: str) -> str:
    """Lower case, without trailing dots and without the brackets of an IPv6 literal."""
    host = host.lower().rstrip(".")
    if host.startswith("[") and host.endswith("]"):
        host = host[1:-1]
    return host


def blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """True if ``ip`` lies in a network pages must not reach (IPv4-mapped IPv6 counts as IPv4)."""
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return any(ip.version == net.version and ip in net for net in BLOCKED_NETWORKS)


def _internal_name(host: str) -> bool:
    return host in BLOCKED_HOSTS or host.endswith(BLOCKED_HOST_SUFFIXES)


def _ip_literal(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return False
    return True


def blocked_host(host: str, page_host: str | None) -> bool:
    """True if a page must not request ``host`` judged by its name or IP literal alone.

    ``page_host`` is the host of the configured ``url`` page, or None for templates; it is always
    allowed, even when it is an internal name or address.
    """
    host = normalize_host(host)
    if not host:
        return True
    if page_host is not None and host == normalize_host(page_host):
        return False
    if _internal_name(host):
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False  # an ordinary host name
    return blocked_ip(ip)


async def _getaddrinfo(host: str, port: int) -> list[str]:
    infos = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return [info[4][0] for info in infos]


class _BadRequest(Exception):
    pass


@dataclass(frozen=True)
class _Request:
    method: str
    host: str  # normalized
    port: int
    target: str | None  # origin form ("/path?q") for plain HTTP, None for CONNECT
    version: str
    headers: list[str]


def _parse_authority(authority: str, default_port: int | None) -> tuple[str, int]:
    """``host[:port]`` or ``[v6]:port`` -> (normalized host, port); anything odd is refused."""
    if authority.startswith("["):
        end = authority.find("]")
        if end < 0:
            raise _BadRequest
        host, rest = authority[1:end], authority[end + 1:]
        if "%" in host:  # zone ids have no business in a page request
            raise _BadRequest
        try:
            ipaddress.IPv6Address(host)
        except ValueError:
            raise _BadRequest from None
    else:
        host, sep, port = authority.partition(":")
        rest = sep + port
        if not _HOST_NAME.fullmatch(host):
            raise _BadRequest
    if not rest:
        if default_port is None:
            raise _BadRequest
        return normalize_host(host), default_port
    if not rest.startswith(":") or not _PORT.fullmatch(rest[1:]):
        raise _BadRequest
    port = int(rest[1:])
    if not 1 <= port <= 65535:
        raise _BadRequest
    return normalize_host(host), port


def _parse_request(head: bytes) -> _Request:
    """Parse a proxy request head (ending in a blank line); raise _BadRequest on anything odd."""
    try:
        text = head.decode("ascii")
    except UnicodeDecodeError:
        raise _BadRequest from None
    request_line, *headers = text[:-4].split("\r\n")
    parts = request_line.split(" ")
    if len(parts) != 3:
        raise _BadRequest
    method, target, version = parts
    if not _TOKEN.fullmatch(method) or version not in ("HTTP/1.0", "HTTP/1.1"):
        raise _BadRequest
    if not target or any(not "!" <= c <= "~" for c in target):
        raise _BadRequest
    for line in headers:
        name, sep, value = line.partition(":")
        if not sep or not _TOKEN.fullmatch(name) or any(
                c < " " and c != "\t" or c == "\x7f" for c in value):
            raise _BadRequest
    if method == "CONNECT":
        host, port = _parse_authority(target, None)
        return _Request(method, host, port, None, version, headers)
    if target[:7].lower() != "http://":
        raise _BadRequest
    rest = target[7:]
    cut = min((i for i in (rest.find("/"), rest.find("?")) if i >= 0), default=len(rest))
    authority, path = rest[:cut], rest[cut:]
    if "#" in path:
        raise _BadRequest
    host, port = _parse_authority(authority, 80)
    if not path.startswith("/"):
        path = "/" + path
    return _Request(method, host, port, path, version, headers)


def _origin_head(req: _Request) -> bytes:
    lines = [f"{req.method} {req.target} {req.version}"]
    lines += [h for h in req.headers if h.partition(":")[0].lower() not in _HOP_HEADERS]
    lines.append("Connection: close")
    return ("\r\n".join(lines) + "\r\n\r\n").encode("ascii")


async def _answer(writer: asyncio.StreamWriter, status: int) -> None:
    reason, body = _ERRORS[status]
    writer.write(f"HTTP/1.1 {status} {reason}\r\nContent-Type: text/plain\r\n"
                 f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n{body}".encode())
    await writer.drain()


async def _pump(src: asyncio.StreamReader, dst: asyncio.StreamWriter) -> None:
    while data := await src.read(RELAY_CHUNK):
        dst.write(data)
        await dst.drain()
    if dst.can_write_eof():
        dst.write_eof()  # pass a half close on


class GuardProxy:
    """Filtering forward proxy on 127.0.0.1; one listener per page host."""

    def __init__(self, resolve: Resolver | None = None) -> None:
        self._resolve = resolve or _getaddrinfo
        self._servers: dict[str | None, asyncio.Server] = {}
        self._lock = asyncio.Lock()
        self._tasks: set[asyncio.Task] = set()
        # Every connection's transports, so close() can end ones still flushing to a slow reader.
        self._transports: weakref.WeakSet[asyncio.Transport] = weakref.WeakSet()
        self._closed = False

    async def url_for(self, page_host: str | None) -> str:
        """Proxy address for pages whose own host is ``page_host`` (None: no exempt host)."""
        key = normalize_host(page_host or "") or None
        async with self._lock:
            if self._closed:
                raise RuntimeError("proxy closed")
            server = self._servers.get(key)
            if server is None:
                server = await asyncio.start_server(
                    partial(self._handle, key), "127.0.0.1", 0, limit=HEAD_LIMIT)
                self._servers[key] = server
        return f"http://127.0.0.1:{server.sockets[0].getsockname()[1]}"

    async def close(self) -> None:
        """Stop all listeners and end every open connection."""
        async with self._lock:
            self._closed = True
            servers = list(self._servers.values())
            self._servers.clear()
        for server in servers:
            server.close()
        tasks = list(self._tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        for transport in list(self._transports):
            transport.abort()
        for server in servers:
            await server.wait_closed()

    async def _handle(self, page_host: str | None, reader: asyncio.StreamReader,
                      writer: asyncio.StreamWriter) -> None:
        task = asyncio.current_task()
        self._tasks.add(task)
        self._transports.add(writer.transport)
        opened: list[asyncio.StreamWriter] = []  # upstream connection, once there is one
        graceful = False
        try:
            if self._closed:
                return
            async with asyncio.timeout(MAX_CONNECTION_S):
                graceful = await self._serve(page_host, reader, writer, opened)
        except TimeoutError:
            log.debug("proxy connection closed after %s s", MAX_CONNECTION_S)
        except OSError as exc:
            log.debug("page request connection error: %s", exc)
        finally:
            for w in (*opened, writer):
                if graceful:
                    w.close()
                else:
                    w.transport.abort()
            self._tasks.discard(task)

    async def _serve(self, page_host: str | None, reader: asyncio.StreamReader,
                     writer: asyncio.StreamWriter, opened: list[asyncio.StreamWriter]) -> bool:
        """Handle one proxy request; True if the connection ended normally (close, not abort)."""
        try:
            async with asyncio.timeout(HEAD_TIMEOUT_S):
                head = await reader.readuntil(b"\r\n\r\n")
        except (TimeoutError, asyncio.IncompleteReadError, asyncio.LimitOverrunError):
            return False
        try:
            req = _parse_request(head)
        except _BadRequest:
            log.debug("malformed proxy request refused")
            await _answer(writer, 400)
            return True
        status, address = await self._check(page_host, req.host, req.port)
        if address is None:
            await _answer(writer, status)
            return True
        try:
            async with asyncio.timeout(CONNECT_TIMEOUT_S):
                up_reader, upstream = await asyncio.open_connection(
                    address, req.port, flags=socket.AI_NUMERICHOST)
        except (OSError, TimeoutError) as exc:
            log.debug("page request to %s failed: %s", req.host, exc)
            await _answer(writer, 502)
            return True
        opened.append(upstream)
        self._transports.add(upstream.transport)
        if req.target is None:
            writer.write(b"HTTP/1.1 200 Connection established\r\n\r\n")
        else:
            upstream.write(_origin_head(req))
        await self._relay(reader, writer, up_reader, upstream)
        return True

    async def _check(self, page_host: str | None, host: str, port: int) -> tuple[int, str | None]:
        """(status, None) to refuse, or (0, address) to connect to; resolves exactly once.

        The page's own host is exempt from the name rule. Its addresses are still checked unless
        it is an IP literal or an internal Home Assistant name, so a public name whose DNS points
        at loopback or an internal network cannot be used as a door.
        """
        exempt = page_host is not None and host == page_host
        trust_address = exempt and (_ip_literal(host) or _internal_name(host))
        if not exempt and blocked_host(host, None):
            log.info("page request blocked: %s", host)
            return 403, None
        try:
            async with asyncio.timeout(RESOLVE_TIMEOUT_S):
                addresses = list(await self._resolve(host, port))
        except (OSError, TimeoutError, ValueError) as exc:  # ValueError: bad IDNA label
            log.debug("cannot resolve %s: %s", host, exc)
            return 502, None
        if not addresses:
            return 502, None
        if not trust_address:
            for address in addresses:
                try:
                    ip = ipaddress.ip_address(str(address).split("%", 1)[0])
                except ValueError:
                    ip = None
                if ip is None or blocked_ip(ip):
                    log.info("page request blocked: %s", host)
                    return 403, None
        return 0, str(addresses[0])

    @staticmethod
    async def _relay(reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
                     up_reader: asyncio.StreamReader, upstream: asyncio.StreamWriter) -> None:
        """Copy bytes both ways until the upstream closes or the client side ends.

        After the client side ended (closed, half closed or failed) the answer gets at most
        CLIENT_GONE_GRACE_S more, so a silent upstream cannot keep the connection alive.
        """
        down = asyncio.create_task(_pump(up_reader, writer))
        up = asyncio.create_task(_pump(reader, upstream))
        try:
            done, _ = await asyncio.wait({down, up}, return_when=asyncio.FIRST_COMPLETED)
            if down not in done and up.exception() is None:
                await asyncio.wait({down}, timeout=CLIENT_GONE_GRACE_S)
        finally:
            for t in (down, up):
                t.cancel()
            await asyncio.gather(down, up, return_exceptions=True)
