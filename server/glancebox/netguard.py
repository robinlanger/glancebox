"""Decide which requests a rendered page may make (keeps pages away from Home Assistant internals)."""

import ipaddress
from urllib.parse import urlsplit

ALLOWED_SCHEMES = frozenset({"data", "blob", "about"})
WEB_SCHEMES = frozenset({"http", "https"})
BLOCKED_HOSTS = frozenset({"supervisor", "hassio", "homeassistant", "observer", "localhost"})
BLOCKED_HOST_SUFFIX = ".local.hass.io"
BLOCKED_NETWORKS = tuple(ipaddress.ip_network(n) for n in (
    "127.0.0.0/8", "172.30.32.0/23", "169.254.0.0/16", "::1/128"))


def blocked(url: str, page_host: str | None) -> bool:
    """True if a page must not request ``url``.

    ``page_host`` is the host of the configured ``url`` page (lower case, no port), or None for
    templates; requests to it are always allowed, even when it is an internal address.
    """
    try:
        parts = urlsplit(url)
        scheme = parts.scheme.lower()
        if scheme in ALLOWED_SCHEMES:
            return False
        if scheme not in WEB_SCHEMES:
            return True
        host = parts.hostname  # lower case, without brackets and port
    except ValueError:
        return True
    if not host:
        return True
    if host == page_host:
        return False
    if host in BLOCKED_HOSTS or host.endswith(BLOCKED_HOST_SUFFIX):
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False  # an ordinary host name
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped  # [::ffff:127.0.0.1] is 127.0.0.1
    return any(ip in net for net in BLOCKED_NETWORKS)
