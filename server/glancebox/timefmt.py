"""Time-of-day formatting in 24 or 12 hours.

This is the only place that formats a time of day. Durations and countdowns
("in 2:13", "12 min") are not its business and must never go through it.
"""

from __future__ import annotations

import re
from datetime import datetime, time

TIME_FORMATS: tuple[str, str] = ("24h", "12h")

_HHMM = re.compile(r"([0-9]{1,2}):([0-9]{2})")
_SUFFIXES = ("AM", "PM")


def _check(time_format: str) -> None:
    if time_format not in TIME_FORMATS:
        raise ValueError(f"time_format must be '24h' or '12h', got {time_format!r}")


def _h12(hour: int) -> tuple[int, str]:
    return hour % 12 or 12, "AM" if hour < 12 else "PM"


def format_time(when: datetime | time, time_format: str = "24h") -> str:
    """Return "14:05" in 24h or "2:05 PM" in 12h."""
    _check(time_format)
    if time_format == "24h":
        return f"{when.hour:02d}:{when.minute:02d}"
    hour, suffix = _h12(when.hour)
    return f"{hour}:{when.minute:02d} {suffix}"


def format_hour(when: datetime | time, time_format: str = "24h") -> str:
    """Return the hour alone: "15" in 24h or "3 PM" in 12h."""
    _check(time_format)
    if time_format == "24h":
        return f"{when.hour:02d}"
    hour, suffix = _h12(when.hour)
    return f"{hour} {suffix}"


def split_suffix(text: str) -> tuple[str, str]:
    """Split a trailing " AM" / " PM" off: ("2:05", "PM"), or (text, "") if there is none."""
    head, sep, tail = text.rpartition(" ")
    if sep and head and tail in _SUFFIXES:
        return head, tail
    return text, ""


def convert_hhmm(text: str, time_format: str = "24h") -> str:
    """Convert an "H:MM" / "HH:MM" text to the given format; anything else is returned as is."""
    _check(time_format)
    if time_format == "24h":
        return text
    match = _HHMM.fullmatch(text)
    if match is None:
        return text
    hour, minute = int(match[1]), int(match[2])
    if hour > 23 or minute > 59:
        return text
    return format_time(time(hour, minute), time_format)
