"""Departure board page (bahn)."""

from __future__ import annotations

import logging

from glancebox.http import redact_urls

from . import departures

DEFAULT_DBF_URL = "https://dbf.finalrewind.org"
DEFAULT_LIMIT = 4
MIN_REFRESH = 60  # DB Fahrplan rule: poll at most once a minute


log = logging.getLogger(__name__)


def validate(options: dict) -> None:
    station = options.get("station")
    if not isinstance(station, str) or not station.strip():
        raise ValueError("station is required")
    limit = options.get("limit")
    if limit is not None and (isinstance(limit, bool) or not isinstance(limit, int)
                              or not 1 <= limit <= 6):
        raise ValueError("limit must be an integer between 1 and 6")


def _joined(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        value = ",".join(str(v).strip() for v in value if str(v).strip())
    return str(value).strip() or None


def _badge(train: str) -> str:
    t = train.upper()
    if t.startswith("S"):
        return "s"
    if t.startswith(("ICE", "IC", "EC", "FLX", "NJ")):
        return "long"
    if t.startswith(("RE", "RB", "RS", "IRE")):
        return "regional"
    return "other"


def _row(dep, now) -> dict:
    unit = ""
    right_class = ""
    if dep.cancelled:
        right, right_class = "fällt aus", "cancelled"
    else:
        mins = dep.minutes_until(now)
        if mins <= 0:
            right = "jetzt"
        elif mins < 60:
            right, unit = str(mins), "min"
        else:
            right = dep.realtime(now).strftime("%H:%M")
        if mins <= 3:
            right_class = "soon"
    delay = dep.delay if not dep.cancelled and dep.delay and dep.delay > 0 else None
    return {
        "train": dep.train,
        "badge": _badge(dep.train),
        "destination": dep.destination,
        "right": right,
        "unit": unit,
        "right_class": right_class,
        "scheduled": dep.scheduled,
        "delay": delay,
        "delay_class": "minor" if delay is not None and delay < 6 else "major",
        "platform": f"Gl. {dep.platform}" if dep.platform else "",
        "platform_changed": dep.platform_changed,
        "cancelled": dep.cancelled,
    }


def fetch(options: dict, ctx) -> dict:
    station = options["station"].strip()
    limit = options.get("limit", DEFAULT_LIMIT)
    clock = ctx.now.strftime("%H:%M")
    data = {"title": options.get("title") or station, "clock": clock, "rows": [],
            "message": None, "sub": None}
    try:
        deps = departures.fetch(
            options.get("dbf_url", DEFAULT_DBF_URL).rstrip("/"), station,
            via=_joined(options.get("via")), platforms=_joined(options.get("platforms")),
            limit=limit, tz=ctx.timezone)
    except Exception as exc:  # noqa: BLE001  network error, DBF down, unknown station ...
        log.warning("departures unavailable: %s", redact_urls(str(exc)))
        data["message"], data["sub"] = "Keine Daten", f"Stand {clock}"
        return data
    if not deps:
        data["message"] = "Keine Abfahrten"
        return data
    data["rows"] = [_row(d, ctx.now) for d in deps[:limit]]
    return data
