"""Home Assistant page (homeassistant): current state of a few Home Assistant entities.

Response shape per the Home Assistant developer docs, REST API (GET /api/states/<entity_id>,
header "Authorization: Bearer <long-lived access token>"):
- 200 answers {"entity_id", "state", "attributes", "last_changed", "last_updated"};
  `state` is always a string (may be "unavailable" / "unknown"), `attributes` may carry
  friendly_name and unit_of_measurement.
- 404 for an unknown entity, 401 for a wrong or missing token.
"""

from __future__ import annotations

import logging
import math
import re
import time
from functools import lru_cache
from typing import NamedTuple
from urllib.parse import urlparse

import requests
from PIL import ImageFont

from glancebox import http
from glancebox.render import FONTS_DIR

log = logging.getLogger(__name__)

LANGS = ("de", "en")
LAYOUTS = ("tiles", "list")
MAX_TILES = 4
MAX_LIST = 6
ENTITY_RE = re.compile(r"^[a-z0-9_]+\.[a-z0-9_]+$")
DEFAULT_TITLE = "Home Assistant"


class Entry(NamedTuple):
    entity_id: str
    label: str | None
    decimals: int | None


def default_layout(n: int) -> str:
    return "tiles" if n <= MAX_TILES else "list"


def _entity_id(value: object) -> str:
    if not isinstance(value, str) or not ENTITY_RE.match(value):
        raise ValueError(f"entity id {value!r} must look like 'sensor.name' (a-z, 0-9, _)")
    return value


def _entry(item: object) -> Entry:
    if isinstance(item, str):
        return Entry(_entity_id(item), None, None)
    if not isinstance(item, dict) or "entity" not in item:
        raise ValueError("each entity must be an entity id or a mapping with 'entity'")
    label = item.get("label")
    if label is not None and not isinstance(label, str):
        raise ValueError("label must be a string")
    decimals = item.get("decimals")
    if decimals is not None and (isinstance(decimals, bool) or not isinstance(decimals, int)
                                 or not 0 <= decimals <= 3):
        raise ValueError("decimals must be an integer from 0 to 3")
    return Entry(_entity_id(item["entity"]), label, decimals)


def entries(options: dict) -> list[Entry]:
    return [_entry(item) for item in options["entities"]]


def validate(options: dict) -> None:
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
    items = options.get("entities")
    if not isinstance(items, list) or not items:
        raise ValueError("entities is required and must be a non-empty list")
    if len(items) > MAX_LIST:
        raise ValueError(f"entities: at most {MAX_LIST} entries")
    parsed_entries = entries(options)
    layout = options.get("layout")
    if layout is not None and layout not in LAYOUTS:
        raise ValueError("layout must be 'tiles' or 'list'")
    if (layout or default_layout(len(parsed_entries))) == "tiles" and len(items) > MAX_TILES:
        raise ValueError(f"layout 'tiles' allows at most {MAX_TILES} entities")
    if options.get("lang", "de") not in LANGS:
        raise ValueError("lang must be 'de' or 'en'")
    if "title" in options and not isinstance(options["title"], str):
        raise ValueError("title must be a string")


class Cell(NamedTuple):
    value: str
    unit: str | None
    tone: str  # "" (white), "warn" (orange), "open" (orange), "on" (yellow)


MINUS = "\u2212"
NA = {"de": "n. v.", "en": "n/a"}
OPEN_CLASSES = ("window", "door", "opening", "garage_door")
PRESENCE_CLASSES = ("motion", "occupancy", "presence")
ON_OFF_DOMAINS = ("binary_sensor", "light", "switch", "input_boolean", "fan")
WORDS = {
    "open": {"de": ("offen", "zu"), "en": ("open", "closed")},
    "presence": {"de": ("erkannt", "frei"), "en": ("detected", "clear")},
    "plain": {"de": ("an", "aus"), "en": ("on", "off")},
}


def _number(text: str) -> float | None:
    try:
        number = float(text)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def _non_finite(text: str) -> bool:
    try:
        return not math.isfinite(float(text))
    except ValueError:
        return False


def _format_number(number: float, unit: str | None, decimals: int | None,
                   lang: str) -> Cell:
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
    return Cell(text, unit, "")


def _binary(entity_id: str, device_class: str | None, state: str, lang: str) -> Cell | None:
    domain = entity_id.split(".", 1)[0]
    if domain not in ON_OFF_DOMAINS or state not in ("on", "off"):
        return None
    is_on = state == "on"
    kind = "plain"
    if domain == "binary_sensor" and device_class in OPEN_CLASSES:
        kind = "open"
    elif domain == "binary_sensor" and device_class in PRESENCE_CLASSES:
        kind = "presence"
    word = WORDS[kind][lang][0 if is_on else 1]
    tone = ""
    if is_on and kind == "open":
        tone = "open"
    elif is_on and domain in ("light", "switch"):
        tone = "on"
    return Cell(word, None, tone)


def format_state(state: dict, decimals: int | None, lang: str) -> Cell:
    """Turn a /api/states/<id> answer into the text shown in a cell."""
    raw = str(state.get("state", ""))
    attrs = state.get("attributes") or {}
    if raw in ("unavailable", "unknown"):
        return Cell(NA[lang], None, "warn")
    binary = _binary(str(state.get("entity_id", "")), attrs.get("device_class"), raw, lang)
    if binary:
        return binary
    number = _number(raw)
    if number is not None:
        return _format_number(number, attrs.get("unit_of_measurement") or None, decimals, lang)
    if _non_finite(raw):
        return Cell(NA[lang], None, "warn")
    return Cell(raw, None, "")


# Font sizes per size class and the width a value may use, both taken from template.html.
# Each entry: available px, {class: (value font px, unit font px, unit margin px)}.
# Tiles have padding 8 px left and 2 px right; tiles in the right column also have a 1 px
# border. 3 and 4 tiles use the narrow cell (120 px) for every tile, also the wide first one of
# 3. A list value may take 60 % of the 224 px row content.
_BOXES = {
    "tiles_few": (230, {"l": (44, 15, 3), "m": (24, 15, 3), "s": (18, 15, 3)}),
    "tiles": (109, {"l": (30, 15, 3), "m": (22, 15, 3), "s": (14, 12, 2)}),
    "list": (134, {"m": (17, 13, 3), "s": (14, 13, 3)}),
}
_SAFETY_PX = 1  # rounding of the layout box
_FONT_FILE = FONTS_DIR / "DejaVuSans-Bold.ttf"
# The server gives a page FETCH_TIMEOUT_S = 20 s; stay well below it for all entities together.
_BUDGET_S = 15.0
_CALL_TIMEOUT_S = 5.0
_FONT_UNITS = 1000  # measure at a large size and scale: no hinting, matches Chromium to ~0.5 px


@lru_cache(maxsize=1)
def _font() -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(_FONT_FILE), _FONT_UNITS)


def text_width(value: str, unit: str | None, sizes: tuple[int, int, int]) -> float:
    """Estimated rendered width in px of value + unit in bold DejaVu Sans (the page font)."""
    value_px, unit_px, margin = sizes
    width = _font().getlength(value) * value_px / _FONT_UNITS
    if unit:
        width += margin + _font().getlength(unit) * unit_px / _FONT_UNITS
    return width


def size_class(value: str, unit: str | None, layout: str, count: int) -> str:
    """Pick the largest font size class ("l", "m", "s") whose estimated width fits the cell.

    If not even "s" fits, the template shortens the value with an ellipsis.
    """
    key = "list" if layout == "list" else ("tiles_few" if count <= 2 else "tiles")
    available, classes = _BOXES[key]
    for name, sizes in classes.items():
        if text_width(value, unit, sizes) <= available - _SAFETY_PX:
            return name
    return "s"


TEXT = {
    "de": {"error": "Keine Verbindung zu Home Assistant", "asof": "Stand",
           "token": "Token abgelehnt", "token_sub": "Long-Lived Access Token prüfen",
           "missing": "fehlt"},
    "en": {"error": "Cannot reach Home Assistant", "asof": "As of",
           "token": "Token rejected", "token_sub": "Check the long-lived access token",
           "missing": "missing"},
}


def _status(exc: Exception) -> int | None:
    response = getattr(exc, "response", None)
    return getattr(response, "status_code", None)


def _log_failure(url: str, exc: Exception) -> None:
    """Log without ever echoing a message that might carry the Authorization header.

    Only HTTPError/ConnectionError/Timeout messages (URL and status) are logged; anything else
    (e.g. requests' InvalidHeader, which quotes the header value) logs just its type.
    """
    if isinstance(exc, (requests.HTTPError, requests.ConnectionError, requests.Timeout)):
        log.warning("homeassistant: %s: %s: %s", http.redact_urls(url), type(exc).__name__,
                    http.redact_urls(str(exc)))
    else:
        log.warning("homeassistant: %s: %s", http.redact_urls(url), type(exc).__name__)


def fetch(options: dict, ctx) -> dict:
    lang = options.get("lang", ctx.lang if ctx.lang in LANGS else "de")
    clock = ctx.now.strftime("%H:%M")
    title = options.get("title") or DEFAULT_TITLE
    texts = TEXT[lang]
    parsed = entries(options)
    layout = options.get("layout") or default_layout(len(parsed))
    base = f"{options['url'].rstrip('/')}/api/states"
    headers = {"Authorization": f"Bearer {options['token']}"}

    def result(state: str, items=(), **extra) -> dict:
        data = {"title": title, "clock": clock, "lang": lang, "layout": layout,
                "state": state, "items": list(items), "message": None, "sub": None}
        data.update(extra)
        return data

    cells = []
    deadline = time.monotonic() + _BUDGET_S
    for entry in parsed:
        url = f"{base}/{entry.entity_id}"
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            log.warning("homeassistant: time budget used up before %s", entry.entity_id)
            return result("error", message=texts["error"], sub=f"{texts['asof']} {clock}")
        try:
            state = http.get_json(url, headers=headers,
                                  timeout=min(_CALL_TIMEOUT_S, remaining))
            if not isinstance(state, dict):
                raise TypeError("unexpected response shape")
        except (requests.RequestException, ValueError, TypeError) as exc:
            status = _status(exc)
            if status == 404:
                cells.append((entry.label or entry.entity_id,
                              Cell(texts["missing"], None, "warn")))
                continue
            _log_failure(url, exc)
            if status in (401, 403):
                return result("token", message=texts["token"], sub=texts["token_sub"])
            return result("error", message=texts["error"], sub=f"{texts['asof']} {clock}")
        attrs = state.get("attributes") or {}
        label = entry.label or attrs.get("friendly_name") or entry.entity_id
        cells.append((label, format_state(state, entry.decimals, lang)))

    items = [{"label": label, "value": cell.value, "unit": cell.unit, "tone": cell.tone,
              "size": size_class(cell.value, cell.unit, layout, len(cells))}
             for label, cell in cells]
    return result("ok", items)
