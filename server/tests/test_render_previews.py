import importlib.util
from pathlib import Path

from PIL import Image

from glancebox.anim import Anim, Track

SCRIPT = Path(__file__).resolve().parents[2] / "tools" / "render_previews.py"
BG = (0x0B, 0x0D, 0x12)
ARROW = (0xFF, 0xB0, 0x20)


def _load():
    spec = importlib.util.spec_from_file_location("render_previews", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _paint(direction: str) -> Image.Image:
    img = Image.new("RGB", (240, 240), BG)
    track = Track(64, 67, 85, 15, direction, "ffb020", 40)
    _load().paint_arrows(img, Anim("0b0d12", "232a38", (track,)))
    return img


def test_arrows_only_inside_the_track():
    img = _paint("r")
    inside = outside = 0
    for y in range(240):
        for x in range(240):
            if img.getpixel((x, y)) == ARROW:
                if 64 <= x < 64 + 85 and 67 <= y < 67 + 15:
                    inside += 1
                else:
                    outside += 1
    assert inside > 0
    assert outside == 0


def _leftmost(img: Image.Image, y: int, x0: int, x1: int) -> int:
    return min(x for x in range(x0, x1) if img.getpixel((x, y)) == ARROW)


def test_left_arrow_points_left():
    img = _paint("l")
    cy = 67 + 15 // 2
    # first chevron: tip at x + 9 = 73; look at that chevron only
    assert _leftmost(img, cy, 64, 82) < _leftmost(img, cy - 5, 64, 82)


def test_right_arrow_points_right():
    img = _paint("r")
    cy = 67 + 15 // 2
    assert _leftmost(img, cy, 64, 82) > _leftmost(img, cy - 5, 64, 82)
