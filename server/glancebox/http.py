"""HTTP helper for pages: timeout and User-Agent are always set."""

import re
import time
from typing import Any

import requests

from . import __version__

USER_AGENT = f"glancebox/{__version__} (+https://github.com/robinlanger/glancebox)"

_URL_RE = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)
# urllib3/requests errors quote only path and query: "Max retries exceeded with url: /x?k=v"
_SCHEMELESS_RE = re.compile(r"(\burl: /[^\s?#\"'<>]*)[?#][^\s\"'<>]*")
_TRAILING = ".,;)]>"

IMAGE_TYPES = ("image/png", "image/jpeg")
_CHUNK_SIZE = 8192


def get_json(url: str, *, params: dict | None = None, headers: dict | None = None,
             timeout: float = 10, auth=None) -> Any:
    """GET ``url`` and return the decoded JSON body, or ``None`` on HTTP 204."""
    resp = requests.get(url, params=params, timeout=timeout, auth=auth,
                        headers={**(headers or {}), "User-Agent": USER_AGENT})
    resp.raise_for_status()
    if resp.status_code == 204:
        return None
    return resp.json()


def get_bytes(url: str, *, headers: dict | None = None, timeout: float = 10,
              max_bytes: int, auth=None) -> tuple[bytes, str]:
    """GET an image and return ``(body, mime)``.

    Redirects are not followed; a 3xx raises ``requests.HTTPError`` like any error status.
    Raises ``ValueError`` if the type is not in ``IMAGE_TYPES`` ("type"), the body exceeds
    ``max_bytes`` ("large") or the whole download takes longer than ``timeout`` ("slow").
    """
    start = time.monotonic()
    resp = requests.get(url, timeout=timeout, auth=auth, stream=True, allow_redirects=False,
                        headers={**(headers or {}), "User-Agent": USER_AGENT})
    try:
        if 300 <= resp.status_code < 400:
            raise requests.HTTPError(f"{resp.status_code} redirect not followed", response=resp)
        resp.raise_for_status()
        mime = resp.headers.get("Content-Type", "").split(";")[0].strip().lower()
        if mime not in IMAGE_TYPES:
            raise ValueError(f"unexpected content type {mime or 'missing'!r}")
        try:
            declared = int(resp.headers.get("Content-Length", ""))
        except ValueError:
            declared = None
        if declared is not None and declared > max_bytes:
            raise ValueError(f"image too large: {declared} > {max_bytes} bytes")
        body = bytearray()
        for chunk in resp.iter_content(_CHUNK_SIZE):
            body += chunk
            if len(body) > max_bytes:
                raise ValueError(f"image too large: more than {max_bytes} bytes")
            if time.monotonic() - start > timeout:
                raise ValueError(f"image download too slow: over {timeout} s")
        return bytes(body), mime
    finally:
        resp.close()


def _split_trailing(text: str) -> tuple[str, str]:
    core = text.rstrip(_TRAILING)
    return core, text[len(core):]


def _redact_url(match: re.Match) -> str:
    core, tail = _split_trailing(match.group(0))
    scheme, _, rest = core.partition("://")
    at = rest.rfind("@")
    cut = min((pos for pos in (rest.find("?"), rest.find("#")) if pos != -1), default=-1)
    if at != -1 and cut != -1 and at > cut:
        # Ambiguous: an unencoded "?"/"#" in the userinfo or an "@" in the query or fragment.
        # Print nothing of the address beyond its scheme.
        return f"{scheme}://***{tail}"
    prefix = ""
    if at != -1:
        # Everything up to the last "@" is userinfo, even if it holds an unencoded "/"; a path
        # containing "@" then hides the host, which errs on the safe side.
        prefix, rest = "***@", rest[at + 1:]
        cut = min((pos for pos in (rest.find("?"), rest.find("#")) if pos != -1), default=-1)
    if cut != -1:
        rest = rest[:cut] + "?***"
    return f"{scheme}://{prefix}{rest}{tail}"


def _redact_schemeless(match: re.Match) -> str:
    _, tail = _split_trailing(match.group(0))
    return f"{match.group(1)}?***{tail}"


def redact_urls(text: str) -> str:
    """Strip credentials, query and fragment from every http(s) URL in ``text``.

    Scheme, host, port and path stay; ``user:pass@`` becomes ``***@`` and ``?query``/``#frag``
    become ``?***``. Trailing ``.,;)]>`` are treated as punctuation, not part of the URL. The
    scheme-less ``url: /path?query`` that requests/urllib3 errors use is redacted the same way.
    An address whose last ``@`` follows its first ``?`` or ``#`` is ambiguous and becomes just
    ``scheme://***``. A secret that is part of the path itself is not masked.
    """
    return _SCHEMELESS_RE.sub(_redact_schemeless, _URL_RE.sub(_redact_url, text))
