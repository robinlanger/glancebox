"""Uptime Kuma page (kuma): state of one Uptime Kuma status page.

Response shape verified against Uptime Kuma 2.0.2 (louislam/uptime-kuma, tag 2.0.2):
- server/routers/status-page-router.js, GET /api/status-page/heartbeat/:slug answers
  {"heartbeatList": {"<monitorId>": [beat, ...oldest first, max 100]},
   "uptimeList": {"<monitorId>_24": <24 h uptime, fraction 0..1>}}, cached 1 minute server side.
- server/model/heartbeat.js toPublicJSON(): {status, time, msg: "" (hidden), ping}.
  `time` is stored via R.isoDateTimeMillis(dayjs.utc()): "YYYY-MM-DD HH:MM:SS.sss" in UTC.
- server/model/status_page.js getStatusPageData(): {config, incident, publicGroupList,
  maintenanceList}; config.title is the page title (config.toPublicJSON).
- server/model/group.js: publicGroupList[] = {id, name, weight, monitorList};
  server/model/monitor.js toPublicJSON(): monitorList[] = {id, name, sendUrl, type, ...}.
Status codes: 0 down, 1 up, 2 pending, 3 maintenance. The parser also accepts ISO 8601.
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from urllib.parse import urlparse

from glancebox import http

log = logging.getLogger(__name__)

LANGS = ("de", "en")
SLUG_RE = re.compile(r"^[a-z0-9-]+$")
DEFAULT_TITLE = "Uptime Kuma"
MAX_ROWS = 4

DOWN, UP, PENDING, MAINTENANCE = 0, 1, 2, 3

TEXT = {
    "de": {"error": "Keine Verbindung zu Uptime Kuma", "asof": "Stand",
           "empty": "Keine Monitore auf der Statusseite", "pending": "Wird geprüft"},
    "en": {"error": "Cannot reach Uptime Kuma", "asof": "As of",
           "empty": "No monitors on this status page", "pending": "Being checked"},
}


def validate(options: dict) -> None:
    url = options.get("url")
    if not isinstance(url, str) or not url:
        raise ValueError("url is required")
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("url must start with http:// or https://")
    slug = options.get("slug")
    if not isinstance(slug, str) or not SLUG_RE.match(slug):
        raise ValueError("slug is required and may only contain a-z, 0-9 and -")
    if options.get("lang", "de") not in LANGS:
        raise ValueError("lang must be 'de' or 'en'")


def _parse_time(value: str) -> datetime:
    """Kuma 1.x/2.x write 'YYYY-MM-DD HH:MM:SS.sss' (UTC); also accept ISO 8601."""
    text = value.strip().replace(" ", "T", 1)
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    t = datetime.fromisoformat(text)
    return t.replace(tzinfo=UTC) if t.tzinfo is None else t.astimezone(UTC)


def _duration(seconds: float) -> str:
    minutes = max(int(seconds // 60), 0)
    if minutes < 60:
        return f"{minutes} min"
    if minutes < 24 * 60:
        return f"{minutes // 60} h"
    return f"{minutes // (24 * 60)} d"


def _down_since(beats: list[dict]) -> tuple[datetime, bool]:
    """Start of the current outage and whether it is only a lower bound (no up beat seen)."""
    last_up = max((i for i, b in enumerate(beats) if b["status"] == UP), default=-1)
    for b in beats[last_up + 1:]:
        if b["status"] == DOWN:
            return _parse_time(b["time"]), last_up < 0
    return _parse_time(beats[-1]["time"]), True  # not reached for a down monitor


def _uptime_text(values: list[float], lang: str) -> str | None:
    if not values:
        return None
    text = f"{sum(values) / len(values) * 100:.1f}"
    return (text.replace(".", ",") if lang == "de" else text) + " %"


def fetch(options: dict, ctx) -> dict:
    lang = options.get("lang", ctx.lang if ctx.lang in LANGS else "de")
    clock = ctx.clock()
    title = options.get("title") or DEFAULT_TITLE
    texts = TEXT[lang]
    base = f"{options['url'].rstrip('/')}/api/status-page"
    slug = options["slug"]

    def result(state: str, **extra) -> dict:
        data = {"title": title, "clock": clock, "lang": lang, "state": state, "up": 0, "total": 0,
                "uptime": None, "pending": 0, "down": [], "more": 0,
                "message": None, "sub": None}
        data.update(extra)
        return data

    try:
        page = http.get_json(f"{base}/{slug}")
        beats_data = http.get_json(f"{base}/heartbeat/{slug}")
        title = options.get("title") or (page.get("config") or {}).get("title") or DEFAULT_TITLE
        monitors = [m for g in page.get("publicGroupList") or [] for m in g["monitorList"]]
        heartbeats = beats_data.get("heartbeatList") or {}
        uptimes = beats_data.get("uptimeList") or {}

        now_utc = ctx.now.astimezone(UTC)
        up = pending = 0
        down = []
        values = []
        for m in monitors:
            beats = heartbeats.get(str(m["id"])) or []
            value = uptimes.get(f"{m['id']}_24")
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                values.append(float(value))
            status = beats[-1]["status"] if beats else PENDING
            if status in (UP, MAINTENANCE):
                up += 1
            elif status == DOWN:
                since, lower_bound = _down_since(beats)
                down.append((since, m["name"], lower_bound))
            else:
                pending += 1
        down.sort(key=lambda d: d[0])
        rows = [{"name": name,
                 "since": ("≥ " if lb else "") + _duration((now_utc - since).total_seconds())}
                for since, name, lb in down]
    except Exception as exc:  # noqa: BLE001 - any failure must show the notice, never a stale "all OK"
        log.warning("kuma: status page unavailable: %s: %s", type(exc).__name__,
                    http.redact_urls(str(exc)))
        return result("error", message=texts["error"], sub=f"{texts['asof']} {clock}")

    if not monitors:
        return result("empty", message=texts["empty"])
    if not rows and up == 0:  # only pending monitors: not an "all OK" (and not red either)
        return result("pending", up=0, total=len(monitors), pending=pending,
                      message=texts["pending"], sub=f"0/{len(monitors)} OK")
    return result("down" if rows else "ok", up=up, total=len(monitors), pending=pending,
                  uptime=_uptime_text(values, lang), down=rows[:MAX_ROWS],
                  more=max(len(rows) - MAX_ROWS, 0))
