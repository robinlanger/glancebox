"""Source prusalink: the printer directly through the PrusaLink API v1 (Prusa Buddy firmware).

Sources, read 2026-11-25: Prusa-Firmware-Buddy v8.0.2 (lib/WUI/nhttp/status_renderer.cpp,
lib/WUI/link_content/prusa_link_api_v1.cpp, basic_gets.cpp (get_job_v1), previews.cpp,
src/state/printer_state.cpp) and the Prusa-Link-Web OpenAPI description (spec/openapi.yaml).
- Every request, the thumbnail included, carries HTTP Digest auth (user "maker" by default)
  or, when an API key is set instead, the header X-Api-Key.
- GET /api/v1/status -> printer {state, temp_nozzle, target_nozzle, temp_bed, target_bed, …};
  job {id, progress (%), time_remaining (s, only when known), time_printing (s)} only while
  the firmware has a job (PRINTING, PAUSED, ATTENTION during a print). printer.state is one
  of IDLE BUSY PRINTING PAUSED FINISHED STOPPED ERROR ATTENTION READY (or UNKNOWN).
- GET /api/v1/job -> 204 without a job (so also at FINISHED and STOPPED); else id, state,
  progress, time_remaining, time_printing, file {name (8.3), display_name, path (folder),
  refs {icon "/thumb/s<path>", thumbnail "/thumb/l<path>", download}}. The image address is
  only ever taken from refs.thumbnail, never built from the file name.

The last job seen (file, duration, image address) is kept per url, so FINISHED, which the
firmware reports without a job, still names the print; it is dropped when the printer is idle.

Derived from the OpenAPI description and firmware source; never run against a printer.
"""

from __future__ import annotations

import logging
import re
import threading
import time

import requests

from glancebox import http

from . import _common
from ._common import (
    MAX_IMAGE_BYTES,
    Budget,
    PrinterStatus,
    SourceError,
    Thumbnail,
    clamp_progress,
    clean_filename,
    number,
    source_error,
    temp,
)

log = logging.getLogger(__name__)

NAME = "PrusaLink"
KEYS = ("api_key", "user", "password")
DEFAULT_USER = "maker"
STATE_MAP: dict[str, str] = {
    "PRINTING": "printing", "PAUSED": "paused", "ATTENTION": "paused",
    "FINISHED": "finished", "ERROR": "error",
    "IDLE": "idle", "READY": "idle", "BUSY": "idle", "STOPPED": "idle",
}
_ATTENTION = {"de": "Eingriff nötig", "en": "Attention needed"}
_JOB_STATES = ("printing", "paused", "finished", "error")
_SHORT_EXTENSION = re.compile(r"\.(gco|bgc)$", re.IGNORECASE)   # 8.3 name of .gcode/.bgcode


def _filled(options: dict, key: str) -> bool:
    if key not in options:
        return False
    value = options[key]
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be non-empty text")
    return True


def validate(options: dict) -> None:
    password, key = _filled(options, "password"), _filled(options, "api_key")
    if "user" in options:
        _filled(options, "user")
        if not password:
            raise ValueError("user only goes with password")
    if password and key:
        raise ValueError("set password or api_key, not both")
    if not password and not key:
        raise ValueError("password or api_key is required (PrusaLink: printer menu "
                         "Settings > Network > PrusaLink)")


# --- memory per url ---------------------------------------------------------------------

_warned: set[str] = set()
_warned_lock = threading.Lock()


def _warn_once(word: str) -> None:
    with _warned_lock:
        if word in _warned:
            return
        _warned.add(word)
    log.warning("printer (prusalink): unknown state %r shown as idle", word)


# url -> (job id, filename, time_printing, thumbnail address) of the last job seen
_jobs: dict[str, tuple] = {}
_jobs_lock = threading.Lock()


# --- fetch ----------------------------------------------------------------------------------

def _dict(value: object, key: str) -> dict:
    found = value.get(key) if isinstance(value, dict) else None
    return found if isinstance(found, dict) else {}


def _text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _seconds(value: object) -> int | None:
    result = number(value)
    return None if result is None or result < 0 else round(result)


def _job(base: str, budget: Budget, call: dict) -> dict:
    """The /api/v1/job answer; {} for 204 or any failure (the file is optional)."""
    try:
        answer = http.get_json(f"{base}/api/v1/job", timeout=budget.timeout(), **call)
    except (requests.RequestException, ValueError, SourceError):
        return {}
    return answer if isinstance(answer, dict) else {}


def _thumbnail(base: str, url: str, address: str, job_id: object, budget: Budget,
               call: dict) -> Thumbnail | None:
    if budget.left() <= 0:
        return None

    def load() -> Thumbnail:
        data, mime = http.get_bytes(address, timeout=budget.timeout(),
                                    max_bytes=MAX_IMAGE_BYTES, **call)
        return Thumbnail(data, mime)

    return _common.cached_thumbnail(("prusalink", url, address, job_id), load)


def fetch(options: dict, ctx) -> PrinterStatus:
    url = options["url"]
    base = url.rstrip("/")
    lang = options.get("lang", "de")
    if options.get("api_key"):
        call = {"headers": {"X-Api-Key": options["api_key"]}, "auth": None}
    else:   # a new object per fetch: it keeps the state of the digest handshake
        call = {"headers": None, "auth": requests.auth.HTTPDigestAuth(
            options.get("user", DEFAULT_USER), options["password"])}
    budget = Budget(clock=time.monotonic)

    status_url = f"{base}/api/v1/status"
    try:
        status = http.get_json(status_url, timeout=budget.timeout(), **call)
    except (requests.RequestException, ValueError) as e:
        raise source_error(e, status_url, direct=True) from e
    printer = _dict(status, "printer")
    word = printer.get("state")
    if not isinstance(word, str):
        raise SourceError("data", "no printer.state", url=status_url)
    word = word.strip().upper()
    nozzle = temp(printer.get("temp_nozzle"), printer.get("target_nozzle"))
    bed = temp(printer.get("temp_bed"), printer.get("target_bed"))
    state = STATE_MAP.get(word)
    if state is None:
        _warn_once(word)
        state = "idle"
    if state not in _JOB_STATES:
        with _jobs_lock:
            _jobs.pop(url, None)
        return PrinterStatus("idle", nozzle=nozzle, bed=bed,
                             message=None if word in STATE_MAP else word)

    job = _dict(status, "job")
    answer = _job(base, budget, call)
    file = _dict(answer, "file")

    def value(key: str) -> object:
        return job[key] if key in job else answer.get(key)

    job_id = value("id")
    name = _text(file.get("display_name"))
    if name is None and (short := _text(file.get("name"))):
        name = _SHORT_EXTENSION.sub("", short) or None
    address = _common.same_host_url(base, _dict(file, "refs").get("thumbnail"))
    duration = _seconds(value("time_printing"))
    with _jobs_lock:
        if name is not None:
            _jobs[url] = (job_id, name, duration, address)
        elif state == "finished" and url in _jobs:
            job_id, name, remembered, address = _jobs[url]
            duration = duration if duration is not None else remembered

    thumb = None
    if address is not None and options.get("thumbnail", True):
        thumb = _thumbnail(base, url, address, job_id, budget, call)
    common = {"filename": clean_filename(name), "nozzle": nozzle, "bed": bed,
              "thumbnail": thumb}
    if state == "finished":
        return PrinterStatus("finished", progress=100.0, duration_s=duration, **common)
    progress = clamp_progress(value("progress"))
    if state == "error":
        return PrinterStatus("error", progress=progress, **common)
    return PrinterStatus(state, progress=progress, remaining_s=_seconds(value("time_remaining")),
                         message=_ATTENTION.get(lang, _ATTENTION["de"]) if word == "ATTENTION"
                         else None, **common)
