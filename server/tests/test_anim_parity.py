"""The device parser (firmware/lib/core/anim.h) must use the same limits as glancebox.anim."""

import re
from pathlib import Path

from glancebox import anim

HEADER = Path(__file__).resolve().parents[2] / "firmware" / "lib" / "core" / "anim.h"

NAMES = {
    "MaxTracks": anim.MAX_TRACKS,
    "MaxValueLen": anim.MAX_VALUE_LEN,
    "Screen": anim.SCREEN,
    "MinW": anim.MIN_W,
    "MaxW": anim.MAX_W,
    "MinH": anim.MIN_H,
    "MaxH": anim.MAX_H,
    "MinSpeed": anim.MIN_SPEED,
    "MaxSpeed": anim.MAX_SPEED,
    "LineThickness": anim.LINE_THICKNESS,
    "ArrowSpacing": anim.ARROW_SPACING,
    "ArrowHalfHeight": anim.ARROW_HALF_HEIGHT,
    "ArrowStroke": anim.ARROW_STROKE,
}


def test_firmware_anim_limits_match_server():
    found = {
        m.group(1): int(m.group(2))
        for m in re.finditer(r"kAnim(\w+)\s*=\s*(\d+)\s*;", HEADER.read_text(encoding="utf-8"))
    }
    for name, expected in NAMES.items():
        assert name in found, f"kAnim{name} not found in {HEADER}"
        assert found[name] == expected, f"kAnim{name}: firmware {found[name]}, server {expected}"
