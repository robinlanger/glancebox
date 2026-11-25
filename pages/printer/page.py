"""3D printer page (printer): state, progress and times of one printer, selected with `source:`.

Each source module in providers/ has NAME, KEYS (its options besides COMMON_KEYS),
validate(options) and fetch(options, ctx) -> PrinterStatus; anything that is not a printer
state it raises as SourceError. `options["lang"]` is already resolved when its fetch runs.
This module applies the state rules shared by all sources (finished_for) and turns the status
into the template data of build()/notice().
"""

from __future__ import annotations

import dataclasses
import logging
import threading
from datetime import datetime, timedelta
from types import ModuleType
from urllib.parse import urlparse

import requests

from glancebox import hass

from .providers._common import (
    LANGS,
    PrinterStatus,
    SourceError,
    ago_text,
    clamp_progress,
    clock_text,
    data_uri,
    duration_text,
    remaining_text,
)

log = logging.getLogger(__name__)

MIN_REFRESH = 5
DEFAULT_REFRESH = 10
SKIP_UNCHANGED = True
DEFAULT_FINISHED_FOR = 120
COMMON_KEYS = ("source", "url", "title", "lang", "thumbnail", "finished_for")
PROVIDERS: dict[str, ModuleType] = {}     # filled by the source modules, in the spec's order
DEFAULT_TITLE = {"de": "Drucker", "en": "Printer"}
HEATING_GAP = 5.0                         # °C below the target that still counts as heating

TEXT = {
    "de": {"printing": "Druckt", "paused": "Pausiert", "finished": "Fertig", "error": "Fehler",
           "ready": "Bereit", "offline": "Drucker nicht erreichbar", "done": "fertig",
           "layer": "Schicht", "last": "Zuletzt", "since": "seit", "nozzle": "Düse",
           "bed": "Bett", "heating": "heizt", "auth": "Zugang abgelehnt",
           "auth_key": "API-Key prüfen", "auth_password": "Passwort prüfen",
           "token": "Token abgelehnt", "token_sub": "Long-Lived Access Token prüfen",
           "unreachable": "Keine Verbindung zu Home Assistant",
           "data": "Antwort nicht lesbar", "asof": "Stand"},
    "en": {"printing": "Printing", "paused": "Paused", "finished": "Finished", "error": "Error",
           "ready": "Ready", "offline": "Printer not reachable", "done": "done",
           "layer": "Layer", "last": "Last", "since": "since", "nozzle": "Nozzle",
           "bed": "Bed", "heating": "heating", "auth": "Access denied",
           "auth_key": "Check the API key", "auth_password": "Check the password",
           "token": "Token rejected", "token_sub": "Check the long-lived access token",
           "unreachable": "Cannot reach Home Assistant",
           "data": "Unexpected answer", "asof": "As of"},
}
_TONE = {"printing": "green", "paused": "orange", "finished": "green", "error": "red"}
_UNEXPECTED = (requests.RequestException, ValueError, TypeError, KeyError, AttributeError)


# --- validation -------------------------------------------------------------------

def validate(options: dict) -> None:
    source = options.get("source")
    if source not in PROVIDERS:
        raise ValueError(f"source must be one of: {', '.join(PROVIDERS)}")
    url = options.get("url")
    if not isinstance(url, str) or not url:
        raise ValueError("url is required")
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("url must start with http:// or https://")
    if options.get("lang", "de") not in LANGS:
        raise ValueError("lang must be 'de' or 'en'")
    if "title" in options and not isinstance(options["title"], str):
        raise ValueError("title must be text")
    if type(options.get("thumbnail", True)) is not bool:
        raise ValueError("thumbnail must be true or false")
    finished_for = options.get("finished_for", DEFAULT_FINISHED_FOR)
    if isinstance(finished_for, bool) or not isinstance(finished_for, int) or finished_for < 0:
        raise ValueError("finished_for must be a whole number of minutes, 0 or more")
    provider = PROVIDERS[source]
    allowed = (*COMMON_KEYS, *provider.KEYS)
    for key in options:
        if key not in allowed:
            raise ValueError(f"unknown key {key!r} for source {source!r}; "
                             f"allowed: {', '.join(allowed)}")
    provider.validate(options)


# --- state rules -----------------------------------------------------------------

@dataclasses.dataclass
class _Memory:
    finished_seen: datetime | None = None     # when `finished` was first seen without an end
    last_job: tuple[str, datetime | None] | None = None
    offline: bool = False                      # last fetch ended offline (log on change only)


_memory: dict[tuple, _Memory] = {}
_memory_lock = threading.Lock()


def memory_key(options: dict) -> tuple:
    return (options.get("source"), options.get("url"), options.get("integration"),
            options.get("device"))


def settle(status: PrinterStatus, key: tuple, finished_for: int, now: datetime) -> PrinterStatus:
    """Apply the shared state rules: `finished` turns `idle` after `finished_for` minutes.

    The end of a print is ``ended_at``, else ``state_since``, else when this page first saw
    `finished` (in memory only). The last finished print is kept for "Last: …" once the source
    itself reports idle without a last job of its own.
    """
    with _memory_lock:
        mem = _memory.setdefault(key, _Memory())
        if status.state != "finished":
            mem.finished_seen = None
            if status.state == "idle" and status.last_job is None and mem.last_job:
                return dataclasses.replace(status, last_job=mem.last_job)
            return status
        end = status.ended_at or status.state_since
        if end is None:
            mem.finished_seen = mem.finished_seen or now
            end = mem.finished_seen
        if status.filename:
            mem.last_job = (status.filename, end)
    if finished_for and now - end <= timedelta(minutes=finished_for):
        return dataclasses.replace(status, ended_at=end)
    last = (status.filename, end) if status.filename else status.last_job
    return PrinterStatus("idle", nozzle=status.nozzle, bed=status.bed, last_job=last)


# --- display data ----------------------------------------------------------------

def _base(options: dict, lang: str, now: datetime, view: str, tone: str, **extra) -> dict:
    data = {"title": options.get("title") or DEFAULT_TITLE[lang],
            "clock": now.strftime("%H:%M"), "lang": lang, "alert": False, "view": view,
            "tone": tone, "label": "", "big": None, "big_unit": None, "main": None,
            "main_muted": False, "lines": [], "message": None, "bar": None, "filename": None,
            "thumb": None, "temps": [], "notice": None}
    data.update(extra)
    return data


def _temps(status: PrinterStatus, lang: str) -> list[dict]:
    texts = TEXT[lang]
    out = []
    for kind, value in (("nozzle", status.nozzle), ("bed", status.bed)):
        if value is None:
            continue
        actual, target = value
        label = texts[kind]
        if target is not None and actual < target - HEATING_GAP:
            label = f"{label} {texts['heating']}"
        out.append({"kind": kind, "actual": f"{round(actual)}°",
                    "target": None if target is None else str(round(target)),
                    "label": label, "on": target is not None})
    return out


def _times(status: PrinterStatus, now: datetime) -> tuple[int | None, datetime | None]:
    """(remaining_s, eta), each completed from the other; an ETA before now is dropped."""
    remaining, eta = status.remaining_s, status.eta
    if remaining is not None and remaining < 0:
        remaining = None
    if eta is not None and eta < now:
        eta = None
    if remaining is None and eta is not None:
        remaining = int((eta - now).total_seconds())
    if eta is None and remaining is not None:
        eta = now + timedelta(seconds=remaining)
    return remaining, eta


def _layer(status: PrinterStatus, lang: str) -> str | None:
    if status.layer is None:
        return None
    current, total = status.layer
    shown = f"{current}/{total}" if total is not None else f"{current}"
    return f"{TEXT[lang]['layer']} {shown}"


def build(status: PrinterStatus, options: dict, lang: str, now: datetime) -> dict:
    texts = TEXT[lang]
    state = status.state
    if state == "offline":
        return _offline(options, lang, now, status.message)
    temps = _temps(status, lang)
    if state == "idle":
        lines = []
        if status.last_job:
            name, ended = status.last_job
            lines.append(f"{texts['last']}: {name}")
            if ended is not None:
                lines.append(f"{texts['done']} {clock_text(ended, now, lang)}")
        return _base(options, lang, now, "idle", "muted", big=texts["ready"], lines=lines,
                     message=status.message, temps=temps)

    progress = clamp_progress(status.progress)
    percent = None if progress is None else int(progress)
    big, big_unit = (None, None) if percent is None else (str(percent), "%")
    main, lines = None, []
    remaining, eta = _times(status, now)
    if state == "printing":
        main = None if remaining is None else remaining_text(remaining, lang)
        if eta is not None:
            lines.append(f"{texts['done']} {clock_text(eta, now, lang)}")
    elif state == "paused":
        main = None if remaining is None else remaining_text(remaining, lang)
        if status.state_since is not None:
            lines.append(f"{texts['since']} {clock_text(status.state_since, now, lang)}")
    elif state == "finished":
        percent = 100
        big, big_unit = None, None
        if status.ended_at is not None:
            big = clock_text(status.ended_at, now, lang)
            lines.append(ago_text(status.ended_at, now, lang))
        if status.duration_s is not None:
            main = duration_text(status.duration_s, lang)
    if state in ("printing", "paused") and (layer := _layer(status, lang)):
        lines.append(layer)
    thumb = data_uri(status.thumbnail) if options.get("thumbnail", True) else None
    return _base(options, lang, now, "job", _TONE[state], alert=state == "error",
                 label=texts[state], big=big, big_unit=big_unit, main=main,
                 main_muted=state == "paused", lines=lines[:2], message=status.message,
                 bar=percent, filename=status.filename, thumb=thumb, temps=temps)


def _offline(options: dict, lang: str, now: datetime, sub: str | None) -> dict:
    return _base(options, lang, now, "notice", "muted",
                 notice={"message": TEXT[lang]["offline"], "sub": sub, "tone": "muted"})


def notice(options: dict, lang: str, now: datetime, err: SourceError) -> dict:
    """Template data for a fetch that gave no printer state."""
    texts = TEXT[lang]
    source = options.get("source")
    asof = f"{texts['asof']} {now.strftime('%H:%M')}"
    kind = err.kind
    if kind == "unreachable" and source != "hass":
        kind = "offline"            # e.g. the time budget of a direct source ran out
    if kind == "offline":
        return _offline(options, lang, now, None)
    if kind == "auth" and source == "hass":
        message, sub = texts["token"], texts["token_sub"]
    elif kind == "auth":
        password = source == "prusalink" and not options.get("api_key")
        message, sub = texts["auth"], texts["auth_password" if password else "auth_key"]
    elif kind == "unreachable":
        message, sub = texts["unreachable"], asof
    elif kind == "config":
        message, sub = err.detail or texts["data"], None
    else:
        message, sub = texts["data"], asof
    return _base(options, lang, now, "notice", "orange",
                 notice={"message": message, "sub": sub, "tone": "warn"})


# --- fetch -----------------------------------------------------------------------

def _log(key: tuple, options: dict, err: SourceError) -> None:
    """Log a failure; "offline" of a direct source only when the page was not offline before."""
    offline = err.kind == "offline" or (err.kind == "unreachable"
                                        and options.get("source") != "hass")
    with _memory_lock:
        mem = _memory.setdefault(key, _Memory())
        was_offline, mem.offline = mem.offline, offline
    if offline and was_offline:
        return
    if err.cause is not None:
        hass.log_failure("printer", err.url or options.get("url", ""), err.cause)
    else:
        log.warning("printer: %s", err)     # str(SourceError) is redacted


def fetch(options: dict, ctx) -> dict:
    lang = options.get("lang", ctx.lang if ctx.lang in LANGS else "de")
    key = memory_key(options)
    provider = PROVIDERS[options["source"]]
    try:
        try:
            status = provider.fetch({**options, "lang": lang}, ctx)
        except _UNEXPECTED as e:
            raise SourceError("data", url=options.get("url"), cause=e) from e
    except SourceError as err:
        _log(key, options, err)
        return notice(options, lang, ctx.now, err)
    with _memory_lock:
        _memory.setdefault(key, _Memory()).offline = False
    finished_for = options.get("finished_for", DEFAULT_FINISHED_FOR)
    return build(settle(status, key, finished_for, ctx.now), options, lang, ctx.now)
