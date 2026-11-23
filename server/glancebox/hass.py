"""Home Assistant access shared by the pages that read /api/states: connection options,
one state call, number format, failure log. The token never reaches a log line."""

from __future__ import annotations

import logging
import math
import re
from urllib.parse import urlparse

import requests

from . import http

log = logging.getLogger(__name__)

LANGS = ("de", "en")
MINUS = "\u2212"
NA = {"de": "n. v.", "en": "n/a"}
MISSING = {"de": "fehlt", "en": "missing"}
ENTITY_RE = re.compile(r"^[a-z0-9_]+\.[a-z0-9_]+$")


def entity_id(value: object) -> str:
    if not isinstance(value, str) or not ENTITY_RE.match(value):
        raise ValueError(f"entity id {value!r} must look like 'sensor.name' (a-z, 0-9, _)")
    return value


def validate_connection(options: dict) -> None:
    url = options.get("url")
    if not isinstance(url, str) or not url:
        raise ValueError("url is required")
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("url must start with http:// or https://")
    token = options.get("token")
    if not isinstance(token, str) or not token:
        raise ValueError("token is required (long-lived access token)")
    if any(c.isspace() or not c.isprintable() for c in token):
        raise ValueError("token must not contain whitespace or control characters")
    if options.get("lang", "de") not in LANGS:
        raise ValueError("lang must be 'de' or 'en'")
    if "title" in options and not isinstance(options["title"], str):
        raise ValueError("title must be a string")


def state_url(base_url: str, entity: str) -> str:
    return f"{base_url.rstrip('/')}/api/states/{entity}"


def get_state(url: str, token: str, timeout: float) -> dict:
    headers = {"Authorization": f"Bearer {token}"}
    state = http.get_json(url, headers=headers, timeout=timeout)
    if not isinstance(state, dict):
        raise TypeError("unexpected response shape")
    return state


def status_of(exc: Exception) -> int | None:
    response = getattr(exc, "response", None)
    return getattr(response, "status_code", None)


def log_failure(page: str, url: str, exc: Exception) -> None:
    """Log without ever echoing a message that might carry the Authorization header.

    Only HTTPError/ConnectionError/Timeout messages (URL and status) are logged; anything else
    (e.g. requests' InvalidHeader, which quotes the header value) logs just its type.
    """
    if isinstance(exc, (requests.HTTPError, requests.ConnectionError, requests.Timeout)):
        log.warning("%s: %s: %s: %s", page, http.redact_urls(url), type(exc).__name__,
                    http.redact_urls(str(exc)))
    else:
        log.warning("%s: %s: %s", page, http.redact_urls(url), type(exc).__name__)


def number(text: str) -> float | None:
    try:
        value = float(text)
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def format_number(number: float, unit: str | None, decimals: int | None,
                  lang: str) -> tuple[str, str | None]:
    shown = round(number, 1 if decimals is None else decimals)
    if unit in ("W", "Wh") and abs(shown) >= 1000:
        number /= 1000
        unit = "k" + unit
    if decimals is None:
        decimals = 0 if round(number, 1) == int(round(number, 1)) else 1
    rounded = round(number, decimals)
    text = f"{abs(rounded):.{decimals}f}"
    if rounded < 0:
        text = MINUS + text
    if lang == "de":
        text = text.replace(".", ",")
    return text, unit
