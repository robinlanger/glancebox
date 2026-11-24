"""Provider claude: Claude plan limits (5 hours, week), pushed from Claude Code in two formats.

Status line. Field names verified against https://code.claude.com/docs/en/statusline
(2026-11-15):
- rate_limits.five_hour.used_percentage, rate_limits.seven_day.used_percentage:
  percentage of the window used, 0 to 100 (a float, e.g. 23.5).
- rate_limits.five_hour.resets_at, rate_limits.seven_day.resets_at: Unix epoch seconds.
- rate_limits is present only for claude.ai Pro/Max/Ultra plans and only after the first API
  response of a session; each window may be absent on its own, and Claude Code drops a window
  once its resets_at has passed. (rate_limits.spend_limit exists behind a gateway; not shown.)

Usage report (`SDKUsageReport`, marked experimental by Anthropic), per
https://code.claude.com/docs/en/agent-sdk/typescript, verified 2026-11-24 with Claude Code
2.1.330: one line of `claude -p "/usage" --output-format stream-json` holds
- usage_report.rate_limits.limits: a list of {kind, group, percent, resets_at}.
- kind "session" is the 5-hour window, "weekly_all" the week over all models; other kinds
  (e.g. "weekly_scoped", one model only) are not shown.
- percent: percentage of the window used, 0 to 100. resets_at: ISO 8601 time with offset.
- usage_report appears only for claude.ai plans; rate_limits may be null.

tools/statusline/glancebox-statusline.sh posts the status-line JSON and
tools/statusline/glancebox-usage.sh (a Claude Code hook) the usage-report line to
/api/v1/push/claude; the server keeps only `rate_limits` and `usage_report` (PUSH_KEYS in
page.py). When a push holds `usage_report`, that format is read.
"""

from __future__ import annotations

from datetime import UTC, datetime

NAME = "Claude"
CHANNEL = "claude"

WINDOWS = (("five_hour", {"de": "5 Stunden", "en": "5 hours"}),
           ("seven_day", {"de": "Woche", "en": "Week"}))
REPORT_KINDS = {"session": "five_hour", "weekly_all": "seven_day"}  # usage_report kind -> window
WEEKDAYS = {"de": ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"),
            "en": ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")}
TEXT = {
    "de": {"nodata": "Noch keine Daten", "setup": "Statuszeilen-Skript einrichten",
           "nolimits": "Keine Limitdaten", "next": "Wartet auf die nächste Antwort",
           "reset": "zurückgesetzt", "asof": "Stand"},
    "en": {"nodata": "No data yet", "setup": "Set up the status-line script",
           "nolimits": "No limit data", "next": "Waiting for the next answer",
           "reset": "reset", "asof": "As of"},
}


def validate(options: dict) -> None:
    """No options beyond those of the page."""


def _number(value) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _iso_epoch(value) -> float | None:
    """Epoch seconds of an ISO 8601 time; no offset means UTC."""
    if not isinstance(value, str):
        return None
    try:
        at = datetime.fromisoformat(value)
    except ValueError:
        return None
    if at.tzinfo is None:
        at = at.replace(tzinfo=UTC)
    return at.timestamp()


def _windows(data: dict) -> list[tuple[str, float, float | None]]:
    """(window key of WINDOWS, percent used, resets_at as epoch seconds or None), in WINDOWS
    order. A push with `usage_report` is read in that format, otherwise `rate_limits`."""
    found: dict[str, tuple[float, float | None]] = {}
    if "usage_report" in data:
        report = data["usage_report"]
        limits = report.get("rate_limits") if isinstance(report, dict) else None
        entries = limits.get("limits") if isinstance(limits, dict) else None
        for entry in entries if isinstance(entries, list) else ():
            if not isinstance(entry, dict):
                continue
            kind = entry.get("kind")
            key = REPORT_KINDS.get(kind) if isinstance(kind, str) else None
            percent = _number(entry.get("percent"))
            if key is None or key in found or percent is None:
                continue
            found[key] = (percent, _iso_epoch(entry.get("resets_at")))
    else:
        limits = data.get("rate_limits")
        for key, _ in WINDOWS:
            window = limits.get(key) if isinstance(limits, dict) else None
            if not isinstance(window, dict):
                continue
            percent = _number(window.get("used_percentage"))
            if percent is not None:
                found[key] = (percent, _number(window.get("resets_at")))
    return [(key, *found[key]) for key, _ in WINDOWS if key in found]


def _reset_text(resets_at: float, now: datetime, lang: str) -> str:
    left = resets_at - now.timestamp()
    if left < 24 * 3600:
        minutes = int(left // 60)
        return f"in {minutes // 60}:{minutes % 60:02d}"
    at = datetime.fromtimestamp(resets_at, now.tzinfo)
    return f"{WEEKDAYS[lang][at.weekday()]} {at:%H:%M}"


def fetch(options: dict, ctx) -> dict:
    return {**_fetch(options, ctx), "theme": "claude"}  # the claude.ai look, notices too


def _fetch(options: dict, ctx) -> dict:
    lang = options["lang"]
    texts = TEXT[lang]
    pushed = ctx.pushed(CHANNEL)
    if pushed is None:
        return {"message": texts["nodata"], "sub": texts["setup"]}

    received = datetime.fromtimestamp(pushed.received_at, ctx.now.tzinfo)
    day = "" if received.date() == ctx.now.date() else f"{WEEKDAYS[lang][received.weekday()]} "
    stand = f"{texts['asof']} {day}{received:%H:%M}"  # weekday once the push is not from today
    labels = dict(WINDOWS)
    rows = []
    for key, percent, resets_at in _windows(pushed.data):
        if resets_at is None:
            reset = ""
        elif resets_at <= ctx.now.timestamp():
            percent, reset = 0.0, texts["reset"]
        else:
            reset = _reset_text(resets_at, ctx.now, lang)
        rows.append({"label": labels[key][lang], "reset": reset, "percent": percent,
                     "text": f"{round(percent)} %"})
    if not rows:
        return {"message": texts["nolimits"], "sub": texts["next"], "stand": stand}
    return {"rows": rows, "stand": stand}
