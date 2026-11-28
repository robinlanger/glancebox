"""Schema and helpers shared by the printer page and its sources.

Every source turns its answer into a PrinterStatus; anything that is not a printer state is a
SourceError. The text helpers here format times for the template in de/en.
"""

from __future__ import annotations

import base64
import io
import logging
import math
import re
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from urllib.parse import SplitResult, urlsplit

import requests
from PIL import Image

from glancebox.http import redact_urls
from glancebox.timefmt import format_time

log = logging.getLogger(__name__)

STATES = ("printing", "paused", "finished", "error", "idle", "offline")
LANGS = ("de", "en")
MAX_IMAGE_BYTES = 512 * 1024
THUMB_PX = 100
BUDGET_S, CALL_TIMEOUT_S = 15.0, 5.0

ERROR_KINDS = ("offline", "auth", "unreachable", "config", "data")
MAX_SOURCE_PX = 4096          # an image larger than this per side is not decoded
THUMB_CACHE_SIZE = 4

_WEEKDAYS = {"de": ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"),
             "en": ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")}
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
           "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
_LOST_MCU = "lost communication with mcu"
_EXTENSION = re.compile(r"\.(gcode|bgcode|3mf)$", re.IGNORECASE)


@dataclass(frozen=True)
class Thumbnail:
    data: bytes
    mime: str


@dataclass(frozen=True)
class PrinterStatus:
    state: str                                         # one of STATES
    progress: float | None = None                      # 0..100
    remaining_s: int | None = None
    eta: datetime | None = None                        # aware
    filename: str | None = None                        # already cleaned
    nozzle: tuple[float, float | None] | None = None   # (actual, target)
    bed: tuple[float, float | None] | None = None
    layer: tuple[int, int | None] | None = None
    message: str | None = None
    duration_s: int | None = None
    ended_at: datetime | None = None
    state_since: datetime | None = None
    thumbnail: Thumbnail | None = None
    last_job: tuple[str, datetime | None] | None = None
    powered_off: bool = False                          # offline: the printer itself is off


class SourceError(Exception):
    """kind: "offline" | "auth" | "unreachable" | "config" | "data".

    ``url`` is kept only redacted; the text of ``cause`` goes through redact_urls as well, so
    str() and repr() never show a query, a key in it or user:password.
    """

    def __init__(self, kind: str, detail: str | None = None, *, url: str | None = None,
                 cause: Exception | None = None) -> None:
        if kind not in ERROR_KINDS:
            raise ValueError(f"unknown SourceError kind {kind!r}")
        self.kind = kind
        self.detail = detail
        self.url = redact_urls(url) if url else None
        self.cause = cause
        parts = [kind]
        if detail:
            parts.append(detail)
        if self.url:
            parts.append(self.url)
        if cause is not None:
            parts.append(redact_urls(f"{type(cause).__name__}: {cause}"))
        super().__init__(": ".join(parts))


class Budget:
    """Time budget of one fetch: ``total`` seconds overall, at most ``per_call`` per request."""

    def __init__(self, total: float = BUDGET_S, per_call: float = CALL_TIMEOUT_S,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self._total = total
        self._per_call = per_call
        self._clock = clock
        self._start = clock()

    def left(self) -> float:
        return self._total - (self._clock() - self._start)

    def timeout(self) -> float:
        left = self.left()
        if left <= 0:
            raise SourceError("unreachable", "time budget used up")
        return min(self._per_call, left)


# --- values -------------------------------------------------------------------

def clean_filename(path: str | None) -> str | None:
    """Last path part without .gcode/.bgcode/.3mf (any case, repeated); None if empty."""
    if not path:
        return None
    name = re.split(r"[/\\]", path)[-1]
    while (stripped := _EXTENSION.sub("", name)) != name:
        name = stripped
    return name or None


def number(value: object) -> float | None:
    """A finite float from a number or numeric string, else None; never raises."""
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        result = float(value)
    except (ValueError, OverflowError):
        return None
    return result if math.isfinite(result) else None


def clamp_progress(value: object) -> float | None:
    result = number(value)
    return None if result is None else min(100.0, max(0.0, result))


def temp(actual: object, target: object) -> tuple[float, float | None] | None:
    """(actual, target) in °C; None without an actual value, a target of 0 or less is None."""
    current = number(actual)
    if current is None:
        return None
    goal = number(target)
    return current, (goal if goal is not None and goal > 0 else None)


def klipper_lost_mcu(message: object) -> bool:
    """Klipper's shutdown message says the printer (its MCU) is gone: it is switched off.

    Klipper 7558e8c2 klippy/mcu.py (check_timeout): "Lost communication with MCU '<name>'".
    """
    return isinstance(message, str) and _LOST_MCU in message.lower()


def first_line(message: object) -> str | None:
    """The first non-empty line, stripped: Klipper puts the cause there, then instructions."""
    if not isinstance(message, str):
        return None
    return next((line.strip() for line in message.splitlines() if line.strip()), None)


# --- texts --------------------------------------------------------------------

def _span(seconds: int) -> str:
    seconds = max(0, int(seconds))
    if seconds < 60:
        return "<1 min"
    if seconds < 3600:
        return f"{seconds // 60} min"
    if seconds < 86400:
        return f"{seconds // 3600}:{seconds % 3600 // 60:02d} h"
    return f"{seconds // 86400} d {seconds % 86400 // 3600} h"


def remaining_text(seconds: int, lang: str) -> str:
    span = _span(seconds)
    return f"noch {span}" if lang == "de" else f"{span} left"


def duration_text(seconds: int, lang: str) -> str:
    span = _span(seconds)
    return f"Dauer {span}" if lang == "de" else f"Took {span}"


def clock_text(when: datetime, now: datetime, lang: str, time_format: str = "24h") -> str:
    """HH:MM today, else "gestern HH:MM", a weekday within 6 days, or the date.

    In 12 hours: "4:47 PM" today, the weekday within 6 days (also for yesterday) and the date
    alone further away; "yesterday" and a date with a time would not fit the column.
    """
    when = when.astimezone(now.tzinfo)
    hm = format_time(when, time_format)
    days = (when.date() - now.date()).days
    twelve = time_format == "12h"
    if days == 0:
        return hm
    if days == -1 and not twelve:
        return f"gestern {hm}" if lang == "de" else f"yesterday {hm}"
    if abs(days) <= 6:
        return f"{_WEEKDAYS['de' if lang == 'de' else 'en'][when.weekday()]} {hm}"
    if lang == "de":
        date = f"{when.day:02d}.{when.month:02d}."
    else:
        date = f"{_MONTHS[when.month - 1]} {when.day}"
    return date if twelve else f"{date} {hm}"


def ago_text(when: datetime, now: datetime, lang: str) -> str:
    seconds = (now - when) / timedelta(seconds=1)
    if seconds < 60:
        return "gerade eben" if lang == "de" else "just now"
    if seconds < 3600:
        span = f"{int(seconds // 60)} min"
    elif seconds < 86400:
        span = f"{int(seconds // 3600)} h"
    else:
        span = f"{int(seconds // 86400)} d"
    return f"vor {span}" if lang == "de" else f"{span} ago"


# --- thumbnails ------------------------------------------------------------------

def data_uri(thumb: Thumbnail | None) -> str | None:
    """The image scaled to at most THUMB_PX square and re-encoded as PNG, or None.

    Whatever the source claims, only what Pillow can open and decode is shown; a broken,
    foreign or oversized image gives None.
    """
    if thumb is None or len(thumb.data) > MAX_IMAGE_BYTES:
        return None
    try:
        with Image.open(io.BytesIO(thumb.data)) as img:
            if max(img.size) > MAX_SOURCE_PX:
                return None
            img.load()
            alpha = img.mode in ("RGBA", "LA", "PA") or "transparency" in img.info
            small = img.convert("RGBA" if alpha else "RGB")
        small.thumbnail((THUMB_PX, THUMB_PX))
        out = io.BytesIO()
        small.save(out, "PNG", optimize=True)
    except Exception:  # noqa: BLE001 - any Pillow failure only means: no image
        return None
    return "data:image/png;base64," + base64.b64encode(out.getvalue()).decode("ascii")


_DEFAULT_PORTS = {"http": 80, "https": 443}


def _origin(parts: SplitResult) -> tuple[str, str | None, int | None]:
    scheme = parts.scheme.lower()
    return scheme, parts.hostname, parts.port or _DEFAULT_PORTS.get(scheme)


def same_host_url(base: str, ref: object) -> str | None:
    """The address of an image reference the printer gave, or None if it leaves the printer.

    A relative path is appended to ``base`` (a path starting with "/" to its host); an absolute
    address only counts with the same scheme, host and port as ``base`` and no user part.
    "//host/…" and every other form give None, so a reference never sends the key elsewhere.
    """
    if not isinstance(ref, str) or not ref:
        return None
    try:
        parts, home = urlsplit(ref), urlsplit(base)
        if not parts.scheme and not parts.netloc:
            if ref.startswith("/"):
                return f"{home.scheme}://{home.netloc}{ref}"
            return f"{base.rstrip('/')}/{ref}"
        if (parts.scheme and parts.netloc and parts.username is None
                and parts.password is None and _origin(parts) == _origin(home)):
            return ref
    except ValueError:                      # a port that is no number or out of range
        return None
    return None


_thumbs: OrderedDict[tuple, Thumbnail] = OrderedDict()
_thumbs_lock = threading.Lock()


def cached_thumbnail(key: tuple, load: Callable[[], Thumbnail | None]) -> Thumbnail | None:
    """The thumbnail for ``key``, loaded once; a failed or empty load is tried again next time.

    Keeps the THUMB_CACHE_SIZE most recently used images in memory.
    """
    with _thumbs_lock:
        if key in _thumbs:
            _thumbs.move_to_end(key)
            return _thumbs[key]
    try:
        thumb = load()
    except Exception as e:  # noqa: BLE001 - the image is optional, the status is not
        log.debug("printer thumbnail not loaded: %s", type(e).__name__)
        return None
    if thumb is None:
        return None
    with _thumbs_lock:
        _thumbs[key] = thumb
        _thumbs.move_to_end(key)
        while len(_thumbs) > THUMB_CACHE_SIZE:
            _thumbs.popitem(last=False)
    return thumb


# --- errors -----------------------------------------------------------------------

def source_error(exc: Exception, url: str, *, direct: bool) -> SourceError:
    """Map a request failure to a SourceError; ``direct`` is False for Home Assistant.

    401/403 is "auth"; no connection or a timeout is "offline" (direct) or "unreachable" (HA);
    anything else is "data" (direct) or "unreachable" (HA). A SourceError passes unchanged.
    """
    if isinstance(exc, SourceError):
        return exc
    response = getattr(exc, "response", None)
    if isinstance(exc, requests.HTTPError) and response is not None \
            and response.status_code in (401, 403):
        kind = "auth"
    elif isinstance(exc, (requests.ConnectionError, requests.Timeout)):
        kind = "offline" if direct else "unreachable"
    else:
        kind = "data" if direct else "unreachable"
    return SourceError(kind, url=url, cause=exc)
