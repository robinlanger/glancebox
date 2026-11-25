"""Source moonraker: the printer directly through Moonraker (Klipper).

Sources, read 2026-11-25: Moonraker master b559b9a8 (docs/external_api/printer.md,
file_manager.md, history.md; moonraker/components/klippy_connection.py, history.py,
file_manager/metadata.py), Klipper 7558e8c2 (docs/Status_Reference.md), Mainsail ce96e4d7
and Fluidd 8509fc70 (progress, remaining time and layer formulas).
- GET /printer/objects/query?<QUERY> -> {"result": {"eventtime", "status": {...}}}; read:
  webhooks.state/state_message (ready | startup | shutdown | error), print_stats.state
  (standby | printing | paused | complete | cancelled | error), .filename, .print_duration,
  .total_duration, .message, .info.current_layer/total_layer (null unless the slicer emits
  SET_PRINT_STATS_INFO); virtual_sdcard.file_position/progress; display_status.progress;
  extruder and heater_bed .temperature/.target; gcode_move.gcode_position [x, y, z, e].
  HTTP 503 means Moonraker runs but Klippy is not connected ("Klippy Host not connected").
- GET /server/files/metadata?filename=<print_stats.filename> -> {"result": {...}}; read:
  estimated_time, gcode_start_byte, gcode_end_byte, layer_count, object_height,
  layer_height, first_layer_height, thumbnails[] {width, height, size, relative_path}.
- Thumbnail: relative_path is relative to the folder of the G-code file ->
  GET /server/files/gcodes/<dirname(filename)>/<relative_path>, every part percent-encoded.
  Moonraker writes .png (QOI is converted) or .jpg.
- GET /server/history/list?limit=1&order=desc -> {"result": {"count", "jobs": [{filename,
  status, end_time, total_duration, ...}]}}; 404 when the history component is off.
- Auth: none for trusted_clients, else header X-Api-Key (key from /access/api_key).

Metadata and the thumbnail are fetched once per file and url and dropped when the file name
changes or a new print starts; the history is read only when nothing is printing.

Derived from documentation and source code; not yet checked against a device.
"""

from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from posixpath import dirname, splitext
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

NAME = "Moonraker"
KEYS = ("api_key",)
QUERY = "webhooks&print_stats&virtual_sdcard&display_status&extruder&heater_bed&gcode_move"

THUMB_MAX_WIDTH = 300
FILE_ESTIMATE_FROM = 1.0          # % progress before the file-based estimate counts (Fluidd)
_STATES = {"standby": "idle", "printing": "printing", "paused": "paused",
           "complete": "finished", "cancelled": "idle", "error": "error"}
_JOB_STATES = ("printing", "paused", "complete", "error")      # with a file worth showing
_TEXT = {"de": {"startup": "Klipper startet", "disconnected": "Klipper nicht verbunden"},
         "en": {"startup": "Klipper is starting", "disconnected": "Klipper not connected"}}


def validate(options: dict) -> None:
    if "api_key" in options:
        key = options["api_key"]
        if not isinstance(key, str) or not key:
            raise ValueError("api_key must be non-empty text")


# --- computation ---------------------------------------------------------------------

def _obj(status: dict, name: str) -> dict:
    value = status.get(name)
    return value if isinstance(value, dict) else {}


def _meta(meta: dict | None, key: str) -> float | None:
    return number(meta.get(key)) if isinstance(meta, dict) else None


def progress(status: dict, meta: dict | None) -> float | None:
    """Percent 0..100: file-relative like Mainsail, else display_status, else virtual_sdcard."""
    sdcard = _obj(status, "virtual_sdcard")
    position = number(sdcard.get("file_position"))
    start, end = _meta(meta, "gcode_start_byte"), _meta(meta, "gcode_end_byte")
    if position is not None and start is not None and end is not None and end > start:
        return 100.0 * min(1.0, max(0.0, (position - start) / (end - start)))
    for value in (_obj(status, "display_status").get("progress"), sdcard.get("progress")):
        fraction = number(value)
        if fraction is not None:
            return clamp_progress(fraction * 100.0)
    return None


def remaining(status: dict, meta: dict | None, percent: float | None) -> int | None:
    """Seconds left: the mean of the slicer and the file estimate that are present."""
    duration = number(_obj(status, "print_stats").get("print_duration"))
    if duration is None:
        return None
    estimates = []
    estimated = _meta(meta, "estimated_time")
    if estimated is not None and estimated > 0:
        estimates.append(max(0.0, estimated - duration))
    # Klipper counts print_duration from the first extrusion: 0 (or -2.8e-14 after a pause)
    # before it, which would make the file estimate 0 s (Mainsail also needs > 0).
    if percent is not None and percent >= FILE_ESTIMATE_FROM and duration > 0:
        estimates.append(max(0.0, duration / (percent / 100.0) - duration))
    if not estimates:
        return None
    return round(sum(estimates) / len(estimates))


def _whole(value: object) -> int | None:
    result = number(value)
    return int(result) if result is not None and result >= 0 else None


def layer(status: dict, meta: dict | None) -> tuple[int, int | None] | None:
    """(current, total): print_stats.info, else from metadata and z like Mainsail."""
    info = _obj(_obj(status, "print_stats"), "info")
    first, height = _meta(meta, "first_layer_height"), _meta(meta, "layer_height")
    usable = first is not None and height is not None and height > 0

    total = _whole(info.get("total_layer")) or _whole(_meta(meta, "layer_count")) or None
    top = _meta(meta, "object_height")
    if total is None and usable and top is not None:
        total = max(0, math.ceil(round((top - first) / height + 1, 4)))

    current = _whole(info.get("current_layer"))
    if current is None and usable:
        duration = number(_obj(status, "print_stats").get("print_duration"))
        position = _obj(status, "gcode_move").get("gcode_position")
        z = number(position[2]) if isinstance(position, list) and len(position) > 2 else None
        if duration is not None and duration > 0 and z is not None:
            current = max(0, math.ceil(round((z - first) / height + 1, 4)))
    if current is None:
        return None
    if total is not None:
        current = min(current, total)
    return current, total


def pick_thumbnail(meta: dict | None) -> str | None:
    """relative_path of the largest PNG at most 300 px wide, else the smallest wider one.

    A path without an extension counts as PNG; JPEGs are only used when there is no PNG.
    """
    thumbs = meta.get("thumbnails") if isinstance(meta, dict) else None
    if not isinstance(thumbs, list):
        return None
    candidates = {".png": [], ".jpg": []}
    for thumb in thumbs:
        if not isinstance(thumb, dict):
            continue
        width, path = number(thumb.get("width")), thumb.get("relative_path")
        if width is None or not isinstance(path, str) or not path:
            continue
        ext = splitext(path)[1].lower() or ".png"
        if ext in (".jpg", ".jpeg"):
            ext = ".jpg"
        if ext in candidates:
            candidates[ext].append((width, path))
    for found in candidates.values():
        small = [c for c in found if c[0] <= THUMB_MAX_WIDTH]
        if small:
            return max(small, key=lambda c: c[0])[1]
        if found:
            return min(found, key=lambda c: c[0])[1]
    return None


def file_url(base: str, filename: str, relative_path: str) -> str:
    """Address of a file next to the G-code file ``filename``, every path part encoded."""
    parts = [p for p in dirname(filename).split("/") if p]
    parts += [p for p in relative_path.split("/") if p]
    encoded = "/".join(quote(p, safe="") for p in parts)
    return f"{base.rstrip('/')}/server/files/gcodes/{encoded}"


# --- per url memory --------------------------------------------------------------------

@dataclass
class _Job:
    filename: str | None = None
    meta: dict | None = None
    state: str | None = None       # last print_stats.state
    generation: int = 0            # counts new prints; part of the thumbnail cache key


_jobs: dict[str, _Job] = {}
_jobs_lock = threading.Lock()


def _job(url: str, filename: str | None, raw: str) -> _Job:
    """The memory of ``url``; metadata is dropped on a new file name or a new print."""
    with _jobs_lock:
        job = _jobs.setdefault(url, _Job())
        new_print = raw == "printing" and job.state not in ("printing", "paused")
        if filename != job.filename or new_print:
            job.filename, job.meta = filename, None
            job.generation += 1
        job.state = raw
        return job


# --- fetch ----------------------------------------------------------------------------

def _get(url: str, budget: Budget, headers: dict, params: dict | None = None):
    return http.get_json(url, params=params, headers=headers, timeout=budget.timeout())


def _optional(url: str, budget: Budget, headers: dict, params: dict | None = None):
    """The "result" object of an optional call, or None on any failure."""
    try:
        answer = _get(url, budget, headers, params)
    except (requests.RequestException, ValueError, SourceError):
        return None
    result = answer.get("result") if isinstance(answer, dict) else None
    return result if isinstance(result, dict) else None


def _query(base: str, budget: Budget, headers: dict) -> dict | None:
    """print status objects; None when Klippy is not connected (HTTP 503)."""
    url = f"{base}/printer/objects/query?{QUERY}"
    try:
        answer = _get(url, budget, headers)
    except requests.HTTPError as e:
        if e.response is not None and e.response.status_code == 503:
            return None
        raise source_error(e, url, direct=True) from e
    except (requests.RequestException, ValueError) as e:
        raise source_error(e, url, direct=True) from e
    result = answer.get("result") if isinstance(answer, dict) else None
    status = result.get("status") if isinstance(result, dict) else None
    if not isinstance(status, dict):
        raise SourceError("data", "no status in the answer", url=url)
    return status


def _last_job(base: str, budget: Budget, headers: dict, ctx) -> dict | None:
    """The newest history job as {filename, status, ended_at}, or None."""
    result = _optional(f"{base}/server/history/list", budget, headers,
                       {"limit": 1, "order": "desc"})
    jobs = result.get("jobs") if result else None
    if not isinstance(jobs, list) or not jobs or not isinstance(jobs[0], dict):
        return None
    job = jobs[0]
    end = number(job.get("end_time"))
    try:
        ended = None if end is None else datetime.fromtimestamp(end, ctx.now.tzinfo)
    except (OverflowError, OSError, ValueError):
        ended = None
    return {"filename": job.get("filename"), "status": job.get("status"), "ended_at": ended}


def _thumbnail(base: str, url: str, job: _Job, budget: Budget, headers: dict) -> Thumbnail | None:
    path = pick_thumbnail(job.meta)
    if path is None or not job.filename:
        return None
    address = file_url(base, job.filename, path)

    def load() -> Thumbnail:
        data, mime = http.get_bytes(address, headers=headers, timeout=budget.timeout(),
                                    max_bytes=MAX_IMAGE_BYTES)
        return Thumbnail(data, mime)

    key = ("moonraker", url, job.filename, path, job.generation)
    return _common.cached_thumbnail(key, load)


def fetch(options: dict, ctx) -> PrinterStatus:
    url = options["url"]
    base = url.rstrip("/")
    lang = options["lang"]
    headers = {"X-Api-Key": options["api_key"]} if options.get("api_key") else {}
    budget = Budget(clock=time.monotonic)

    status = _query(base, budget, headers)
    if status is None:
        return PrinterStatus("offline", message=_TEXT[lang]["disconnected"])
    nozzle = temp(_obj(status, "extruder").get("temperature"),
                  _obj(status, "extruder").get("target"))
    bed = temp(_obj(status, "heater_bed").get("temperature"),
               _obj(status, "heater_bed").get("target"))

    hooks = _obj(status, "webhooks")
    klippy = hooks.get("state", "ready")
    if klippy == "startup":
        return PrinterStatus("offline", message=_TEXT[lang]["startup"])
    if klippy != "ready":
        message = hooks.get("state_message")
        return PrinterStatus("error", nozzle=nozzle, bed=bed,
                             message=message if isinstance(message, str) and message
                             else str(klippy))

    stats = _obj(status, "print_stats")
    raw = stats.get("state")
    if not isinstance(raw, str) or not raw:
        raise SourceError("data", "no print_stats.state", url=url)
    state = _STATES.get(raw, "idle")
    filename = stats.get("filename") if isinstance(stats.get("filename"), str) else None
    filename = filename or None
    job = _job(url, filename, raw)

    if state == "idle":
        last = _last_job(base, budget, headers, ctx)
        last_job = None
        if last and last["status"] == "completed" and (name := clean_filename(
                last["filename"] if isinstance(last["filename"], str) else None)):
            last_job = (name, last["ended_at"])
        return PrinterStatus("idle", nozzle=nozzle, bed=bed, last_job=last_job,
                             message=None if raw in _STATES else raw)

    if raw in _JOB_STATES and filename and job.meta is None and budget.left() > 0:
        meta = _optional(f"{base}/server/files/metadata", budget, headers,
                         {"filename": filename})
        with _jobs_lock:
            if job.filename == filename:
                job.meta = meta
    meta = job.meta
    thumb = None
    if options.get("thumbnail", True) and budget.left() > 0:
        thumb = _thumbnail(base, url, job, budget, headers)

    percent = progress(status, meta)
    common = {"filename": clean_filename(filename), "nozzle": nozzle, "bed": bed,
              "thumbnail": thumb}
    if state == "finished":
        ended = None
        last = _last_job(base, budget, headers, ctx)
        if last and filename and last["filename"] == filename:
            ended = last["ended_at"]
        duration = number(stats.get("total_duration"))
        return PrinterStatus("finished", progress=100.0, ended_at=ended,
                             duration_s=None if duration is None else round(duration),
                             **common)
    if state == "error":
        message = stats.get("message")
        return PrinterStatus("error", progress=percent,
                             message=message if isinstance(message, str) and message else None,
                             **common)
    return PrinterStatus(state, progress=percent, remaining_s=remaining(status, meta, percent),
                         layer=layer(status, meta), **common)
