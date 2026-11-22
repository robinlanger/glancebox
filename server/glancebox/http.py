"""HTTP helper for pages: timeout and User-Agent are always set."""

import re
from typing import Any

import requests

from . import __version__

USER_AGENT = f"glancebox/{__version__} (+https://github.com/robinlanger/glancebox)"

_URL_RE = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)
_TRAILING = ".,;)"


def get_json(url: str, *, params: dict | None = None, headers: dict | None = None,
             timeout: float = 10) -> Any:
    resp = requests.get(url, params=params, timeout=timeout,
                        headers={**(headers or {}), "User-Agent": USER_AGENT})
    resp.raise_for_status()
    return resp.json()


def _redact_url(match: re.Match) -> str:
    url = match.group(0)
    core = url.rstrip(_TRAILING)
    tail = url[len(core):]
    scheme, _, rest = core.partition("://")
    end = len(rest)
    for sep in "/?#":
        pos = rest.find(sep)
        if pos != -1:
            end = min(end, pos)
    authority, remainder = rest[:end], rest[end:]
    if "@" in authority:
        authority = "***@" + authority.rpartition("@")[2]
    cut = min((pos for pos in (remainder.find("?"), remainder.find("#")) if pos != -1),
              default=-1)
    if cut != -1:
        remainder = remainder[:cut] + "?***"
    return f"{scheme}://{authority}{remainder}{tail}"


def redact_urls(text: str) -> str:
    """Strip credentials, query and fragment from every http(s) URL in ``text``.

    Scheme, host, port and path stay; ``user:pass@`` becomes ``***@`` and ``?query``/``#frag``
    become ``?***``. Trailing ``.,;)`` are treated as punctuation, not part of the URL.
    """
    return _URL_RE.sub(_redact_url, text)
