"""Source hass: the printer through Home Assistant entities, with presets per integration.

Sources, read 2026-11-25: Home Assistant core dev components/octoprint 5f380806 and
components/prusalink 8dbdb49d, moonraker-home-assistant v1.14.0, ha-bambulab v2.4.1,
ha_creality_ws v0.9.10.
- GET /api/states/<entity_id> with "Authorization: Bearer <token>" -> {"entity_id", "state",
  "attributes": {"unit_of_measurement", "options", ...}, "last_changed"}; 404 when the
  entity does not exist (or is disabled). Values arrive as text; "unavailable"/"unknown"
  mean no value.
- Remaining time is a duration sensor in the unit it says (moonraker h, ha-bambulab usually
  h through suggested_unit_of_measurement, ha_creality_ws s); ETAs are ISO 8601 timestamps.
- Targets: sensors (octoprint, prusalink, ha-bambulab), number entities (moonraker) or the
  attribute "target" of the temperature sensor (ha_creality_ws).
- Images: GET /api/camera_proxy/<camera.x> or /api/image_proxy/<image.x>, same header.
  moonraker-home-assistant serves the thumbnail only while printing; OctoPrint's camera is
  the webcam, so its preset has no thumbnail.
- PrusaLink's temperature sensors are disabled by default (404 until enabled).
- moonraker-home-assistant also has sensor.{d}_printer_message (Klipper's state_message) and
  sensor.{d}_current_print_message (print_stats.message); the first is read only when
  sensor.{d}_printer_state is shutdown/error, the second only for a print error. A printer
  switched off while its Klipper host runs ("Lost communication with MCU") is "Printer off",
  as with the direct source. sensor.{d}_progress is 0.0 outside a print (seen while Klipper
  itself reported 1.0), so it counts only while printing or paused.

`device` is the entity prefix ({d} below); for octoprint it replaces the prefix "octoprint"
(a second instance is "octoprint_2"). `entities:` replaces single fields of the preset, a
value "sensor.x#attr" reads an attribute; `states:` maps raw words on top of the preset.

Derived from the integrations' source code. The moonraker preset was read on 2026-11-25 from a
Home Assistant instance (HA 2026.11.2, moonraker-home-assistant 1.14.0) with the printer
switched off only; the other presets are not checked against a Home Assistant instance.
"""

from __future__ import annotations

import dataclasses
import logging
import re
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import NamedTuple

import requests

from glancebox import hass, http

from . import _common
from ._common import (
    MAX_IMAGE_BYTES,
    STATES,
    Budget,
    PrinterStatus,
    SourceError,
    Thumbnail,
    clamp_progress,
    clean_filename,
    first_line,
    klipper_lost_mcu,
    number,
    source_error,
    temp,
)

log = logging.getLogger(__name__)

NAME = "Home Assistant"
KEYS = ("token", "integration", "device", "entities", "states")
FIELDS = ("state", "progress", "remaining", "eta", "filename", "nozzle", "nozzle_target",
          "bed", "bed_target", "layer", "layer_total", "thumbnail")

DEVICE_RE = re.compile(r"^[a-z0-9_]+$")
ATTRIBUTE_RE = re.compile(r"^[A-Za-z0-9_]+$")
NO_VALUE = ("unavailable", "unknown")
UNIT_SECONDS = {"s": 1, "min": 60, "h": 3600, "d": 86400}
IMAGE_MIN_LEFT_S = 2.0            # the image is skipped with less budget left (Decision 14)
_JOB_STATES = ("printing", "paused", "finished", "error")
_TEXT = {"de": {"missing": "Entität fehlt", "startup": "Klipper startet"},
         "en": {"missing": "Entity missing", "startup": "Klipper is starting"}}


@dataclass(frozen=True)
class Preset:
    entities: dict[str, str]             # field -> "sensor.{d}_progress" or "sensor.{d}_x#attr"
    states: dict[str, tuple[str, ...]]   # schema state -> raw words
    default_device: str | None = None    # "octoprint" for the octoprint preset
    klippy: str | None = None            # moonraker only: "sensor.{d}_printer_state"
    klippy_message: str | None = None    # moonraker: Klipper's state_message (optional)
    print_message: str | None = None     # moonraker: print_stats.message (optional)
    progress_while_printing: bool = False  # moonraker: the sensor says 0.0 outside a print
    slicer_remaining: str | None = None  # moonraker: time left before the file estimate counts
    finished_at_100: bool = False        # octoprint: operational + progress >= 100


PRESETS: dict[str, Preset] = {
    "moonraker": Preset(
        entities={
            "state": "sensor.{d}_current_print_state", "progress": "sensor.{d}_progress",
            "remaining": "sensor.{d}_print_time_left", "eta": "sensor.{d}_print_eta",
            "filename": "sensor.{d}_filename", "nozzle": "sensor.{d}_extruder_temperature",
            "nozzle_target": "number.{d}_extruder_target", "bed": "sensor.{d}_bed_temperature",
            "bed_target": "number.{d}_bed_target", "layer": "sensor.{d}_current_layer",
            "layer_total": "sensor.{d}_total_layer", "thumbnail": "camera.{d}_thumbnail"},
        states={"printing": ("printing",), "paused": ("paused",), "finished": ("complete",),
                "error": ("error",), "idle": ("standby", "cancelled")},
        klippy="sensor.{d}_printer_state", klippy_message="sensor.{d}_printer_message",
        print_message="sensor.{d}_current_print_message", progress_while_printing=True,
        slicer_remaining="sensor.{d}_slicer_print_time_left_estimate"),
    "octoprint": Preset(
        entities={
            "state": "sensor.{d}_current_state", "progress": "sensor.{d}_job_percentage",
            "eta": "sensor.{d}_estimated_finish_time", "filename": "sensor.{d}_current_file",
            "nozzle": "sensor.{d}_actual_tool0_temp",
            "nozzle_target": "sensor.{d}_target_tool0_temp",
            "bed": "sensor.{d}_actual_bed_temp", "bed_target": "sensor.{d}_target_bed_temp"},
        states={"printing": ("printing", "printing_sd", "printing_streaming", "starting",
                             "starting_sd", "starting_streaming", "resuming", "finishing"),
                "paused": ("paused", "pausing"), "error": ("error", "offline_after_error"),
                "idle": ("operational", "cancelling", "transferring_file"),
                "offline": ("offline", "open_serial", "detect_serial", "connecting")},
        default_device="octoprint", finished_at_100=True),
    "prusalink": Preset(
        entities={
            "state": "sensor.{d}", "progress": "sensor.{d}_progress",
            "eta": "sensor.{d}_print_finish", "filename": "sensor.{d}_filename",
            "nozzle": "sensor.{d}_nozzle_temperature",
            "nozzle_target": "sensor.{d}_nozzle_target_temperature",
            "bed": "sensor.{d}_heatbed_temperature",
            "bed_target": "sensor.{d}_heatbed_target_temperature",
            "thumbnail": "camera.{d}_preview"},
        states={"printing": ("printing",), "paused": ("paused", "attention"),
                "finished": ("finished",), "error": ("error",),
                "idle": ("idle", "ready", "stopped", "busy")}),
    "bambu_lab": Preset(
        entities={
            "state": "sensor.{d}_print_status", "progress": "sensor.{d}_print_progress",
            "remaining": "sensor.{d}_remaining_time", "eta": "sensor.{d}_end_time",
            "filename": "sensor.{d}_task_name", "nozzle": "sensor.{d}_nozzle_temperature",
            "nozzle_target": "sensor.{d}_nozzle_target_temperature",
            "bed": "sensor.{d}_bed_temperature", "bed_target": "sensor.{d}_bed_target_temperature",
            "layer": "sensor.{d}_current_layer", "layer_total": "sensor.{d}_total_layer_count",
            "thumbnail": "image.{d}_cover_image"},
        states={"printing": ("running", "prepare", "slicing", "init"), "paused": ("pause",),
                "finished": ("finish",), "error": ("failed",), "idle": ("idle",),
                "offline": ("offline",)}),
    "creality": Preset(
        entities={
            "state": "sensor.{d}_print_status", "progress": "sensor.{d}_print_progress",
            "remaining": "sensor.{d}_print_time_left", "filename": "sensor.{d}_print_status#file",
            "nozzle": "sensor.{d}_nozzle_temperature",
            "nozzle_target": "sensor.{d}_nozzle_temperature#target",
            "bed": "sensor.{d}_bed_temperature", "bed_target": "sensor.{d}_bed_temperature#target",
            "layer": "sensor.{d}_working_layer", "layer_total": "sensor.{d}_total_layers",
            "thumbnail": "image.{d}_current_print_preview"},
        states={"printing": ("printing", "processing", "self-testing"), "paused": ("paused",),
                "finished": ("completed",), "error": ("error",), "idle": ("idle", "stopped"),
                "offline": ("off",)}),
}
INTEGRATIONS = (*PRESETS, "custom")


class Ref(NamedTuple):
    entity: str
    attribute: str | None


def _ref(value: str) -> Ref:
    entity, _, attribute = value.partition("#")
    return Ref(entity, attribute or None)


def _device(options: dict, preset: Preset) -> str:
    return options.get("device") or preset.default_device or ""


def refs(options: dict) -> dict[str, Ref]:
    """field -> Ref: the preset with ``device`` filled in, then ``entities:`` on top."""
    out: dict[str, Ref] = {}
    preset = PRESETS.get(options.get("integration"))
    if preset is not None:
        device = _device(options, preset)
        out = {field: _ref(value.format(d=device)) for field, value in preset.entities.items()}
    for field, value in (options.get("entities") or {}).items():
        out[field] = _ref(value)
    return {field: out[field] for field in FIELDS if field in out}


def _preset_entity(options: dict, name: str) -> str | None:
    """The preset's extra entity ``name`` ("klippy", "klippy_message", "print_message")."""
    preset = PRESETS.get(options.get("integration"))
    value = getattr(preset, name) if preset is not None else None
    return value.format(d=_device(options, preset)) if value else None


def _klippy(options: dict) -> str | None:
    return _preset_entity(options, "klippy")


def _word(value: str) -> str:
    return value.strip().lower()


def words(options: dict) -> dict[str, str]:
    """raw word (lower case) -> schema state: schema words, the preset, then ``states:``."""
    out = {state: state for state in STATES}
    preset = PRESETS.get(options.get("integration"))
    for source in ((preset.states if preset else {}), options.get("states") or {}):
        for state, raw in source.items():
            for word in raw:
                out[_word(word)] = state
    return out


def seconds(value: float, unit: str | None) -> int | None:
    """A duration in whole seconds; None for an unknown unit or a negative value."""
    factor = UNIT_SECONDS.get(unit) if isinstance(unit, str) else None
    if factor is None or value < 0:
        return None
    return round(value * factor)


# --- reading states ------------------------------------------------------------------

_warned: set[str] = set()
_warned_lock = threading.Lock()


def _warn_once(word: str) -> None:
    with _warned_lock:
        if word in _warned:
            return
        _warned.add(word)
    log.warning("printer (hass): unknown state %r shown as idle; map it with states:", word)


def _value(states: dict, ref: Ref | None) -> object:
    """The state or attribute of ``ref``; None when missing, unavailable or unknown."""
    answer = states.get(ref.entity) if ref else None
    if not isinstance(answer, dict):
        return None
    if ref.attribute is None:
        value = answer.get("state")
    else:
        attributes = answer.get("attributes")
        value = attributes.get(ref.attribute) if isinstance(attributes, dict) else None
    if isinstance(value, str) and _word(value) in (*NO_VALUE, ""):
        return None
    return value


def _unit(states: dict, ref: Ref | None) -> str | None:
    """unit_of_measurement of the entity of ``ref``; None for an attribute (no unit known)."""
    if ref is None or ref.attribute is not None:
        return None
    attributes = (states.get(ref.entity) or {}).get("attributes")
    unit = attributes.get("unit_of_measurement") if isinstance(attributes, dict) else None
    return unit if isinstance(unit, str) else None


def _time(value: object, now: datetime) -> datetime | None:
    """An ISO 8601 text as an aware datetime in the zone of ``now``; naive counts as local."""
    if not isinstance(value, str):
        return None
    try:
        when = datetime.fromisoformat(value.strip())
        if when.tzinfo is None:
            when = when.replace(tzinfo=now.tzinfo)
        return when.astimezone(now.tzinfo)
    except (ValueError, OverflowError):
        return None


def _whole(value: object) -> int | None:
    result = number(value)
    return int(result) if result is not None and result >= 0 else None


def _layer(current: object, total: object) -> tuple[int, int | None] | None:
    now, top = _whole(current), _whole(total) or None
    if now is None:
        return None
    return (min(now, top) if top is not None else now), top


def _klippy_word(states: dict, options: dict) -> str | None:
    """Klippy's state (ready | startup | shutdown | error), lower case; None without one."""
    entity = _klippy(options)
    value = _value(states, Ref(entity, None)) if entity else None
    return _word(value) if isinstance(value, str) else None


def _job_word(states: dict, options: dict) -> str | None:
    """The schema state of the state entity's raw word; None when it has none."""
    raw = _value(states, refs(options)["state"])
    return words(options).get(_word(str(raw))) if raw is not None else None


def _messages(states: dict, options: dict) -> list[str]:
    """The message entities worth reading once state and Klippy state are known."""
    klippy = _klippy_word(states, options)
    if klippy in ("shutdown", "error"):
        entity = _preset_entity(options, "klippy_message")
    elif klippy in (None, "ready") and _job_word(states, options) == "error":
        entity = _preset_entity(options, "print_message")
    else:
        entity = None
    return [entity] if entity else []


def status_from(states: dict[str, dict | None], options: dict, now: datetime) -> PrinterStatus:
    """The status from the /api/states answers by entity id (None or absent = 404)."""
    ref = refs(options)
    lang = options.get("lang", "de")
    entity = ref["state"].entity
    answer = states.get(entity)
    if not isinstance(answer, dict):
        raise SourceError("config", f"{_TEXT[lang]['missing']}: {entity}")
    if ref["state"].attribute is None and not isinstance(answer.get("state"), str):
        raise SourceError("data", f"no state in {entity}")
    raw = _value(states, ref["state"])
    if raw is None:                      # unavailable, unknown (Decision 8) or no attribute
        return PrinterStatus("offline")
    raw = str(raw).strip()
    word = raw.lower()
    preset = PRESETS.get(options.get("integration"))

    def get(field: str) -> object:
        return _value(states, ref.get(field))

    progress = clamp_progress(get("progress"))
    message = None
    state = words(options).get(word)
    if state is None:
        _warn_once(word)
        state, message = "idle", raw
    if preset and preset.finished_at_100 and word == "operational" \
            and progress is not None and progress >= 100:
        state = "finished"
    klippy = _klippy_word(states, options)
    heaters = klippy in (None, "ready")      # else Klipper's heater values are frozen
    if klippy == "startup":
        return PrinterStatus("offline", message=_TEXT[lang]["startup"])
    if klippy in ("shutdown", "error"):
        # Klipper's own message, as the direct source reads it (moonraker.py)
        entity = _preset_entity(options, "klippy_message")
        text = _value(states, Ref(entity, None)) if entity else None
        if klipper_lost_mcu(text):
            filename = get("filename") if state == "finished" else None
            name = clean_filename(filename) if isinstance(filename, str) else None
            return PrinterStatus("offline", powered_off=True,
                                 last_job=(name, None) if name else None)
        return PrinterStatus("error", message=first_line(text))
    if state == "offline":
        return PrinterStatus("offline")
    if state == "error" and (entity := _preset_entity(options, "print_message")):
        message = first_line(_value(states, Ref(entity, None)))
    if preset and preset.progress_while_printing and state not in ("printing", "paused"):
        progress = None

    remaining = number(get("remaining"))
    remaining_s = None if remaining is None else seconds(remaining,
                                                         _unit(states, ref.get("remaining")))
    eta = _time(get("eta"), now)
    if state in ("printing", "paused") and (entity := _preset_entity(options, "slicer_remaining")) \
            and ((progress is not None and progress < 1) or remaining_s == 0):
        # The integration's time left is print_duration / progress - print_duration: 0.0 h
        # while print_duration is 0 (heating) and noise below 1 %; there the slicer's
        # estimate counts, as in Mainsail, Fluidd and the direct source (moonraker.py). The
        # integration's ETA comes from the same file estimate, so the page derives it instead.
        slicer = number(_value(states, Ref(entity, None)))
        unit = _unit(states, Ref(entity, None))
        remaining_s = seconds(slicer, unit) if slicer is not None and slicer > 0 else None
        eta = None
    filename = get("filename")
    return PrinterStatus(
        state, progress=progress,
        remaining_s=remaining_s,
        eta=eta if eta is not None and eta >= now else None,
        filename=clean_filename(filename) if isinstance(filename, str) else None,
        nozzle=temp(get("nozzle"), get("nozzle_target")) if heaters else None,
        bed=temp(get("bed"), get("bed_target")) if heaters else None,
        layer=_layer(get("layer"), get("layer_total")),
        message=message,
        state_since=_time(answer.get("last_changed"), now))


# --- fetch ---------------------------------------------------------------------------

def image_url(base_url: str, entity: str) -> str | None:
    domain = entity.partition(".")[0]
    kind = {"camera": "camera_proxy", "image": "image_proxy"}.get(domain)
    return f"{base_url.rstrip('/')}/api/{kind}/{entity}" if kind else None


def _thumbnail(options: dict, entity: str, filename: str | None, budget: Budget,
               headers: dict) -> Thumbnail | None:
    address = image_url(options["url"], entity)
    if address is None:
        return None

    def load() -> Thumbnail:
        data, mime = http.get_bytes(address, headers=headers, timeout=budget.timeout(),
                                    max_bytes=MAX_IMAGE_BYTES)
        return Thumbnail(data, mime)

    if filename:
        return _common.cached_thumbnail(("hass", options["url"], entity, filename), load)
    try:
        return load()
    except Exception as e:  # noqa: BLE001 - the image is optional, the status is not
        log.debug("printer thumbnail not loaded: %s", type(e).__name__)
        return None


def fetch(options: dict, ctx) -> PrinterStatus:
    ref = refs(options)
    state_entity = ref["state"].entity
    first = [state_entity]
    if klippy := _klippy(options):
        first.append(klippy)
    rest = [ref[field].entity for field in FIELDS
            if field not in ("state", "thumbnail") and field in ref]

    token = options["token"]
    budget = Budget(clock=time.monotonic)
    states: dict[str, dict | None] = {}

    def read(entities: list[str]) -> None:
        for entity in entities:
            if entity in states:
                continue
            url = hass.state_url(options["url"], entity)
            timeout = budget.timeout()
            try:
                states[entity] = hass.get_state(url, token, timeout)
            except (requests.RequestException, ValueError, TypeError) as e:
                if hass.status_of(e) != 404:
                    raise source_error(e, url, direct=False) from e
                if entity == state_entity:
                    missing = _TEXT[options.get("lang", "de")]["missing"]
                    raise SourceError("config", f"{missing}: {entity}", url=url) from e
                states[entity] = None

    read(first)
    read(_messages(states, options))      # only what the state and Klippy's state call for
    read(rest)
    if (slicer := _preset_entity(options, "slicer_remaining")) \
            and _job_word(states, options) in ("printing", "paused"):
        read([slicer])                    # only a print has a time left

    status = status_from(states, options, ctx.now)
    if (options.get("thumbnail", True) and status.state in _JOB_STATES and "thumbnail" in ref
            and _klippy_word(states, options) in (None, "ready")
            and budget.left() >= IMAGE_MIN_LEFT_S):
        headers = {"Authorization": f"Bearer {token}"}
        thumb = _thumbnail(options, ref["thumbnail"].entity, status.filename, budget, headers)
        status = dataclasses.replace(status, thumbnail=thumb)
    return status


# --- validation ----------------------------------------------------------------------

def _entity_value(field: str, value: object) -> None:
    entity, hash_, attribute = value.partition("#") if isinstance(value, str) else (value, "", "")
    try:
        hass.entity_id(entity)
    except ValueError as e:
        raise ValueError(f"entities.{field}: {e}") from None
    if hash_ and not ATTRIBUTE_RE.match(attribute):
        raise ValueError(f"entities.{field}: attribute after '#' must be a name "
                         "(letters, digits, _)")


def validate(options: dict) -> None:
    hass.validate_connection(options)
    integration = options.get("integration")
    if integration not in INTEGRATIONS:
        raise ValueError(f"integration must be one of: {', '.join(INTEGRATIONS)}")
    if "device" in options:
        device = options["device"]
        if not isinstance(device, str) or not DEVICE_RE.match(device):
            raise ValueError("device must be the entity prefix (a-z, 0-9, _), e.g. 'voron'")
    elif integration in PRESETS and PRESETS[integration].default_device is None:
        raise ValueError(f"device is required for integration {integration!r}")

    entities = options.get("entities", {})
    items = entities.items() if isinstance(entities, dict) else None
    if items is None:
        raise ValueError("entities must be a mapping of field: entity id")
    for field, value in items:
        if field not in FIELDS:
            raise ValueError(f"entities: unknown field {field!r}; allowed: {', '.join(FIELDS)}")
        _entity_value(field, value)
    if integration == "custom" and "state" not in entities:
        raise ValueError("integration 'custom' needs entities.state")

    mapping = options.get("states", {})
    items = mapping.items() if isinstance(mapping, dict) else None
    if items is None:
        raise ValueError("states must be a mapping of state: [raw words]")
    for state, raw in items:
        if state not in STATES:
            raise ValueError(f"states: unknown state {state!r}; allowed: {', '.join(STATES)}")
        if not isinstance(raw, list) or not all(isinstance(w, str) and w.strip() for w in raw):
            raise ValueError(f"states.{state} must be a list of non-empty texts")
