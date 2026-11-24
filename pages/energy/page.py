"""Energy flow page (energy): up to four rows (grid, PV, battery, gas, water, wallbox), each with
a track whose moving arrows the device draws from the X-Anim description in ``_anim``.

Reads GET /api/states/<entity_id> like the homeassistant page (see glancebox.hass).
"""

from __future__ import annotations

import logging
import math
import time
from typing import NamedTuple

import requests

from glancebox import hass
from glancebox.anim import Anim, Track, line_top
from glancebox.hass import LANGS, MISSING, NA, entity_id
from glancebox.render import text_width

log = logging.getLogger(__name__)

MIN_REFRESH = 2
DEFAULT_REFRESH = 5
SKIP_UNCHANGED = True
KINDS = ("grid", "pv", "battery", "gas", "water", "wallbox")
POWER_KINDS = ("grid", "pv", "battery", "wallbox")   # compared in W
# Sign before `invert`: grid positive = import, battery positive = discharging. Both follow the
# Home Assistant energy dashboard's power sensors ("Standard" type), checked 2026-11-23 in the
# frontend text of the battery power field: "Positive values indicate discharging the battery,
# negative values indicate charging the battery." and of the inverted grid type: "Positive values
# indicate exporting to the grid" (so standard grid positive = import).
# https://github.com/home-assistant/frontend/blob/dev/src/translations/en.json
# (ui.panel.config.energy). The prose docs (home-assistant.io/docs/energy/battery/) name no sign.
TWO_WAY = ("grid", "battery")                        # others: wrong sign counts as 0
FULL = {"grid": 5000, "pv": 5000, "battery": 3000, "wallbox": 11000, "gas": 2, "water": 15}
SPEED_MIN, SPEED_MAX = 10, 80
BG, TRACK, INACTIVE = "#0b0d12", "#232a38", "#6b7280"
COLOR = {"import": "#ffb020", "export": "#34d399", "pv": "#ffd040", "battery": "#2ec4b6",
         "gas": "#ff6b4a", "water": "#4da3ff", "wallbox": "#a78bfa"}
TRACK_X, TRACK_W, TRACK_H = 64, 85, 15
VALUE_LEFT, VALUE_RIGHT = 156, 226
DEFAULT_TITLE = {"de": "Energie", "en": "Energy"}
MAX_ROWS = 4
ROW_KEYS = ("type", "entity", "soc", "invert", "full", "min")
# Header 28 px, rows share the 198 px from y = 41 down (see geometry()).
_ROWS_TOP, _ROWS_SPAN = 41, 198

# Value font sizes, as in template.html: {class: (value px, unit px, unit margin px)}.
SIZES = {"l": (24, 13, 3), "m": (19, 12, 3), "s": (15, 11, 2)}
_SAFETY_PX = 1  # rounding of the layout box
# The server gives a page FETCH_TIMEOUT_S = 20 s; stay well below it for all entities together.
_BUDGET_S = 15.0
_CALL_TIMEOUT_S = 5.0

TEXT = {
    "de": {"import": "Bezug", "export": "Einspeisung", "pv": "Erzeugung", "charge": "lädt",
           "discharge": "entlädt", "usage": "Verbrauch",
           "error": "Keine Verbindung zu Home Assistant", "asof": "Stand",
           "token": "Token abgelehnt", "token_sub": "Long-Lived Access Token prüfen"},
    "en": {"import": "Import", "export": "Export", "pv": "Producing", "charge": "charging",
           "discharge": "discharging", "usage": "Usage",
           "error": "Cannot reach Home Assistant", "asof": "As of",
           "token": "Token rejected", "token_sub": "Check the long-lived access token"},
}


class RowConfig(NamedTuple):
    kind: str
    entity: str
    soc: str | None
    invert: bool
    full: float
    min: float


def _is_number(value: object) -> bool:
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value))


def _row(item: object) -> RowConfig:
    unknown = [k for k in item if k not in ROW_KEYS] if isinstance(item, dict) else None
    if unknown is None:
        raise ValueError("each row must be a mapping with 'type' and 'entity'")
    if unknown:
        raise ValueError(f"row: unknown key {unknown[0]!r}; allowed: {', '.join(ROW_KEYS)}")
    kind = item.get("type")
    if kind not in KINDS:
        raise ValueError(f"row type must be one of {', '.join(KINDS)}: {kind!r}")
    if "entity" not in item:
        raise ValueError("row: entity is required")
    entity = entity_id(item["entity"])
    soc = item.get("soc")
    if soc is not None:
        if kind != "battery":
            raise ValueError("row: soc is only allowed for type 'battery'")
        soc = entity_id(soc)
    invert = item.get("invert", False)
    if type(invert) is not bool:
        raise ValueError("row: invert must be true or false")
    full = item.get("full", FULL[kind])
    if not _is_number(full) or full <= 0:
        raise ValueError("row: full must be a number above 0")
    minimum = item.get("min", 0)
    if not _is_number(minimum) or minimum < 0:
        raise ValueError("row: min must be a number of at least 0")
    return RowConfig(kind, entity, soc, invert, full, minimum)


def rows(options: dict) -> list[RowConfig]:
    return [_row(item) for item in options["rows"]]


def validate(options: dict) -> None:
    hass.validate_connection(options)
    items = options.get("rows")
    if not isinstance(items, list) or not items:
        raise ValueError("rows is required and must be a non-empty list")
    if len(items) > MAX_ROWS:
        raise ValueError(f"rows: at most {MAX_ROWS} entries")
    rows(options)
    if "animate" in options and not isinstance(options["animate"], bool):
        raise ValueError("animate must be true or false")


class Box(NamedTuple):
    cy: int
    x: int
    y: int
    w: int
    h: int
    line_y: int


def geometry(n: int) -> list[Box]:
    boxes = []
    for i in range(n):
        cy = _ROWS_TOP + (2 * i + 1) * _ROWS_SPAN // (2 * n)
        y = cy - TRACK_H // 2
        boxes.append(Box(cy, TRACK_X, y, TRACK_W, TRACK_H, line_top(y, TRACK_H)))
    return boxes


class Flow(NamedTuple):
    value: str
    unit: str | None
    active: bool
    direction: str | None        # "r" (away from the icon), "l" (towards it), None when inactive
    color: str
    status: str
    speed: int


def _soc_text(soc: dict | None, lang: str) -> str | None:
    if soc is None:
        return None
    level = hass.number(str(soc.get("state", "")))
    if level is None:
        return None
    text, _ = hass.format_number(level, None, 0, lang)
    return f"{text} %"


def _arrow(kind: str, v: float) -> tuple[str, str, str]:
    """(direction, color key, status key) for an active row with comparison value v."""
    if kind == "grid":
        return ("r", "import", "import") if v > 0 else ("l", "export", "export")
    if kind == "battery":
        return ("r", "battery", "discharge") if v > 0 else ("l", "battery", "charge")
    if kind == "wallbox":
        return "l", "wallbox", "charge"
    if kind == "pv":
        return "r", "pv", "pv"
    return "r", kind, "usage"


def flow(row: RowConfig, state: dict | None, soc: dict | None, lang: str) -> Flow:
    level = _soc_text(soc, lang) if row.kind == "battery" else None
    idle_status = level or ""
    if state is None:
        return Flow(MISSING[lang], None, False, None, INACTIVE, idle_status, 0)
    raw = str(state.get("state", ""))
    number = None if raw in ("unavailable", "unknown") else hass.number(raw)
    if number is None:
        return Flow(NA[lang], None, False, None, INACTIVE, idle_status, 0)
    unit = (state.get("attributes") or {}).get("unit_of_measurement") or None
    scale = 1000 if row.kind in POWER_KINDS and unit == "kW" else 1
    if row.invert:
        number = -number
    if row.kind not in TWO_WAY and number < 0:
        number = 0.0
    if abs(number * scale) < row.min:
        number = 0.0
    v = number * scale
    text, shown_unit = hass.format_number(abs(number), unit, None, lang)
    if not any(c in "123456789" for c in text):
        return Flow(text, shown_unit, False, None, INACTIVE, idle_status, 0)
    direction, color, status = _arrow(row.kind, v)
    status = TEXT[lang][status]
    if level:
        status = f"{status} · {level}"
    speed = round(SPEED_MIN + (SPEED_MAX - SPEED_MIN) * min(1, abs(v) / row.full))
    return Flow(text, shown_unit, True, direction, COLOR[color], status, speed)


def size_class(value: str, unit: str | None) -> str:
    """Largest value size class whose estimated width fits between VALUE_LEFT and VALUE_RIGHT."""
    available = VALUE_RIGHT - VALUE_LEFT
    for name, sizes in SIZES.items():
        if text_width(value, unit, sizes) <= available - _SAFETY_PX:
            return name
    return "s"


def _base(options: dict, lang: str, clock: str, state: str, **extra) -> dict:
    data = {"title": options.get("title") or DEFAULT_TITLE[lang], "clock": clock, "lang": lang,
            "state": state, "message": None, "sub": None, "bg": BG, "track": TRACK, "value_left": VALUE_LEFT,
            "value_right": VALUE_RIGHT, "rows": []}
    data.update(extra)
    return data


def build(options: dict, states: dict[str, dict | None], lang: str, clock: str) -> dict:
    parsed = rows(options)
    out_rows, tracks = [], []
    for cfg, box in zip(parsed, geometry(len(parsed)), strict=True):
        f = flow(cfg, states.get(cfg.entity), states.get(cfg.soc) if cfg.soc else None, lang)
        out_rows.append({"kind": cfg.kind, **box._asdict(), "value": f.value, "unit": f.unit,
                         "size": size_class(f.value, f.unit), "status": f.status,
                         "color": f.color, "active": f.active})
        if f.active:
            tracks.append(Track(box.x, box.y, box.w, box.h, f.direction, f.color[1:], f.speed))
    data = _base(options, lang, clock, "ok", rows=out_rows)
    if tracks and options.get("animate") is not False:
        data["_anim"] = Anim(BG[1:], TRACK[1:], tuple(tracks))
    return data


def fetch(options: dict, ctx) -> dict:
    lang = options.get("lang", ctx.lang if ctx.lang in LANGS else "de")
    clock = ctx.now.strftime("%H:%M")
    texts = TEXT[lang]
    wanted = []
    for cfg in rows(options):
        for eid in (cfg.entity, cfg.soc):
            if eid and eid not in wanted:
                wanted.append(eid)

    def error() -> dict:
        return _base(options, lang, clock, "error", message=texts["error"],
                     sub=f"{texts['asof']} {clock}")

    states: dict[str, dict | None] = {}
    deadline = time.monotonic() + _BUDGET_S
    for eid in wanted:
        url = hass.state_url(options["url"], eid)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            log.warning("energy: time budget used up before %s", eid)
            return error()
        try:
            states[eid] = hass.get_state(url, options["token"], min(_CALL_TIMEOUT_S, remaining))
        except (requests.RequestException, ValueError, TypeError) as exc:
            status = hass.status_of(exc)
            if status == 404:
                states[eid] = None
                continue
            hass.log_failure("energy", url, exc)
            if status in (401, 403):
                return _base(options, lang, clock, "token", message=texts["token"],
                             sub=texts["token_sub"])
            return error()
    return build(options, states, lang, clock)
