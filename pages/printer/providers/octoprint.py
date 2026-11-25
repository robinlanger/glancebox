"""Source octoprint: the printer directly through the OctoPrint REST API.

Sources, read 2026-11-25: OctoPrint 2.0.2 (docs/api/job.rst, printer.rst, files.rst,
datamodel.rst; src/octoprint/server/api/job.py, printer.py, files.py,
src/octoprint/printer/standard.py, plugins/serial_connector/serial_comm.py) and the
PrusaSlicer Thumbnails plugin 1.2.4 (octoprint_prusaslicerthumbnails/__init__.py).
- Every request carries the header X-Api-Key. No X-OctoPrint-Api-Version header is sent, so
  OctoPrint 2.x answers in the pre-2.0 shape that 1.x also uses.
- GET /api/printer?exclude=sd -> temperature.tool0/bed {actual, target}, state {text, flags,
  error}; flags: operational, printing, cancelling, pausing, resuming, finishing,
  closedOrError, error, paused, ready, sdReady. HTTP 409 "Printer is not operational" when
  nothing is connected and also in the states Error and Offline after error.
- GET /api/job -> job.file {name, display, path, origin, size, date}, progress {completion
  (0-100), printTime, printTimeLeft}, state (text, e.g. "Printing", "Error", "Offline after
  error"), error. Finished and cancelled prints go back to Operational.
- GET /api/files/local/<path> -> OctoPrint 2.x: refs.thumbnail, an absolute address
  <index>/downloads/thumbs/local/<path>?_cb=<n>; 1.x with the PrusaSlicer Thumbnails plugin:
  the field thumbnail "plugin/prusaslicerthumbnails/thumbnail/<path>.png?<timestamp>",
  relative to the OctoPrint address. Only an address on the printer itself is fetched.

The file's thumbnail address is looked up once per url, path and upload time.

Derived from the documentation; not yet run against OctoPrint.
"""

from __future__ import annotations

import threading
import time
from urllib.parse import quote

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

NAME = "OctoPrint"
KEYS = ("api_key",)
_ERROR_TEXTS = ("Error", "Offline after error")      # /api/job state while not operational
_JOB_STATES = ("printing", "paused", "finished", "error")


def validate(options: dict) -> None:
    key = options.get("api_key")
    if not isinstance(key, str) or not key:
        raise ValueError("api_key is required (OctoPrint: Settings > Application Keys)")


def state_of(flags: dict, completion: float | None, has_file: bool) -> str:
    """The page state from /api/printer state.flags; the first rule that matches wins."""
    on = {name for name, value in flags.items() if value is True}
    if on & {"error", "closedOrError"}:
        return "error"
    if on & {"paused", "pausing"}:
        return "paused"
    if "cancelling" in on:
        return "idle"
    if on & {"printing", "finishing", "resuming"}:
        return "printing"
    if "operational" in on and completion is not None and completion >= 100 and has_file:
        return "finished"
    if on & {"operational", "ready"}:
        return "idle"
    return "offline"


# --- thumbnail address per url ----------------------------------------------------------------

_files: dict[str, tuple[tuple, str | None]] = {}     # url -> ((path, date), address or None)
_files_lock = threading.Lock()


def _thumbnail_address(base: str, url: str, file: dict, budget: Budget,
                       headers: dict) -> str | None:
    """Address of the file's thumbnail, asked once per (path, upload time); None if none."""
    path = file.get("path")
    if not isinstance(path, str) or not path or file.get("origin") != "local":
        return None
    key = (path, file.get("date"))
    with _files_lock:
        known = _files.get(url)
    if known is not None and known[0] == key:
        return known[1]
    encoded = "/".join(quote(p, safe="") for p in path.split("/") if p)
    try:
        info = http.get_json(f"{base}/api/files/local/{encoded}", headers=headers,
                             timeout=budget.timeout())
    except requests.HTTPError as e:
        if e.response is None or e.response.status_code != 404:
            return None                              # tried again on the next fetch
        info = None
    except (requests.RequestException, ValueError, SourceError):
        return None
    address = None
    if isinstance(info, dict):
        refs = info.get("refs")
        ref = refs.get("thumbnail") if isinstance(refs, dict) else None
        address = _common.same_host_url(base, ref or info.get("thumbnail"))
    with _files_lock:
        _files[url] = (key, address)
    return address


def _thumbnail(base: str, url: str, file: dict, budget: Budget,
               headers: dict) -> Thumbnail | None:
    address = _thumbnail_address(base, url, file, budget, headers)
    if address is None or budget.left() <= 0:
        return None

    def load() -> Thumbnail:
        data, mime = http.get_bytes(address, headers=headers, timeout=budget.timeout(),
                                    max_bytes=MAX_IMAGE_BYTES)
        return Thumbnail(data, mime)

    return _common.cached_thumbnail(("octoprint", url, address), load)


# --- fetch ----------------------------------------------------------------------------------

def _dict(value: object, key: str) -> dict:
    found = value.get(key) if isinstance(value, dict) else None
    return found if isinstance(found, dict) else {}


def _text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _get(url: str, budget: Budget, headers: dict, params: dict | None = None) -> dict:
    try:
        answer = http.get_json(url, params=params, headers=headers, timeout=budget.timeout())
    except (requests.RequestException, ValueError) as e:
        raise source_error(e, url, direct=True) from e
    if not isinstance(answer, dict):
        raise SourceError("data", "answer is no object", url=url)
    return answer


def _not_operational(base: str, budget: Budget, headers: dict) -> PrinterStatus:
    """After 409 from /api/printer: error if /api/job names an error state, else offline."""
    try:
        job = _get(f"{base}/api/job", budget, headers)
    except SourceError:
        return PrinterStatus("offline")
    if job.get("state") in _ERROR_TEXTS:
        return PrinterStatus("error", message=_text(job.get("error")))
    return PrinterStatus("offline")


def fetch(options: dict, ctx) -> PrinterStatus:
    url = options["url"]
    base = url.rstrip("/")
    headers = {"X-Api-Key": options["api_key"]}
    budget = Budget(clock=time.monotonic)

    printer_url = f"{base}/api/printer"
    try:
        printer = _get(printer_url, budget, headers, {"exclude": "sd"})
    except SourceError as e:
        response = getattr(e.cause, "response", None)
        if isinstance(e.cause, requests.HTTPError) and response is not None \
                and response.status_code == 409:
            return _not_operational(base, budget, headers)
        raise
    flags = _dict(printer, "state").get("flags")
    if not isinstance(flags, dict):
        raise SourceError("data", "no state.flags", url=printer_url)
    temperature = _dict(printer, "temperature")
    nozzle = temp(_dict(temperature, "tool0").get("actual"),
                  _dict(temperature, "tool0").get("target"))
    bed = temp(_dict(temperature, "bed").get("actual"), _dict(temperature, "bed").get("target"))

    job = _get(f"{base}/api/job", budget, headers)
    file = _dict(job.get("job"), "file")
    progress = _dict(job, "progress")
    completion = number(progress.get("completion"))
    name = _text(file.get("name")) or _text(file.get("path"))
    state = state_of(flags, completion, name is not None)
    if state not in _JOB_STATES:
        return PrinterStatus(state, nozzle=nozzle, bed=bed)

    thumb = None
    if options.get("thumbnail", True) and budget.left() > 0:
        thumb = _thumbnail(base, url, file, budget, headers)
    common = {"filename": clean_filename(name), "nozzle": nozzle, "bed": bed,
              "thumbnail": thumb}
    if state == "finished":
        duration = number(progress.get("printTime"))
        return PrinterStatus("finished", progress=100.0, **common,
                             duration_s=None if duration is None or duration < 0
                             else round(duration))
    percent = clamp_progress(completion)
    if state == "error":
        return PrinterStatus("error", progress=percent, message=_text(job.get("error")),
                             **common)
    left = number(progress.get("printTimeLeft"))
    return PrinterStatus(state, progress=percent, **common,
                         remaining_s=None if left is None or left < 0 else round(left))
