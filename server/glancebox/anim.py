"""Description of the device-side animation, sent in the ``X-Anim`` response header.

The limits below must equal those in ``firmware/lib/core/anim.h`` (a parity test
follows in a later task).
"""

import re
from dataclasses import dataclass
from itertools import pairwise

VERSION = 1
SCREEN = 240
MAX_TRACKS = 4
MAX_VALUE_LEN = 160
MIN_W, MAX_W = 16, 240
MIN_H, MAX_H = 8, 32
MIN_SPEED, MAX_SPEED = 1, 200
LINE_THICKNESS = 3
ARROW_SPACING = 18
ARROW_HALF_HEIGHT = 5
ARROW_STROKE = 2

_COLOR = re.compile(r"[0-9a-fA-F]{6}")


@dataclass(frozen=True)
class Track:
    x: int
    y: int
    w: int
    h: int
    direction: str  # "r" or "l" (screen direction)
    color: str  # "ffb020": 6 hex digits, no "#"
    speed: int  # px/s


@dataclass(frozen=True)
class Anim:
    background: str
    track_color: str
    tracks: tuple[Track, ...]


def line_top(y: int, h: int) -> int:
    """Top row of the track line, centred in the track rectangle."""
    return y + (h - LINE_THICKNESS) // 2


def _color(value: str, what: str) -> str:
    if not isinstance(value, str) or not _COLOR.fullmatch(value):
        raise ValueError(f"{what} color must be 6 hex digits without '#': {value!r}")
    return value.lower()


def _int(value: int, what: str) -> int:
    if type(value) is not int:
        raise ValueError(f"{what} must be an integer: {value!r}")
    return value


def _track(i: int, tr: Track) -> str:
    n = f"track {i}"
    x, y, w, h, speed = (
        _int(v, f"{n} {k}")
        for k, v in (("x", tr.x), ("y", tr.y), ("w", tr.w), ("h", tr.h), ("speed", tr.speed))
    )
    if not MIN_W <= w <= MAX_W:
        raise ValueError(f"{n} width {w} outside {MIN_W}..{MAX_W}")
    if not MIN_H <= h <= MAX_H:
        raise ValueError(f"{n} height {h} outside {MIN_H}..{MAX_H}")
    if x < 0 or y < 0 or x + w > SCREEN or y + h > SCREEN:
        raise ValueError(f"{n} outside the {SCREEN}x{SCREEN} screen")
    if tr.direction not in ("r", "l"):
        raise ValueError(f"{n} direction must be 'r' or 'l': {tr.direction!r}")
    if not MIN_SPEED <= speed <= MAX_SPEED:
        raise ValueError(f"{n} speed {speed} outside {MIN_SPEED}..{MAX_SPEED}")
    color = _color(tr.color, n)
    return f"{x},{y},{w},{h},{tr.direction},{color},{speed}"


def encode(anim: Anim) -> str:
    """Return the ``X-Anim`` header value; raise ValueError naming the broken limit."""
    if not 1 <= len(anim.tracks) <= MAX_TRACKS:
        raise ValueError(f"tracks: need 1..{MAX_TRACKS}, got {len(anim.tracks)}")
    parts = [
        str(VERSION),
        _color(anim.background, "background"),
        _color(anim.track_color, "track"),
    ]
    parts += [_track(i, tr) for i, tr in enumerate(anim.tracks)]
    spans = sorted((tr.y, tr.y + tr.h) for tr in anim.tracks)
    for (_, end), (start, _) in pairwise(spans):
        if start < end:
            raise ValueError("tracks overlap vertically")
    value = ";".join(parts)
    if len(value) > MAX_VALUE_LEN:
        raise ValueError(f"value length {len(value)} exceeds {MAX_VALUE_LEN}")
    return value
