import importlib.util
import io
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


def test_sample_thumbnail_is_a_small_own_drawing():
    png = _load().sample_thumbnail()
    assert len(png) < 20000
    img = Image.open(io.BytesIO(png))
    assert img.format == "PNG"
    assert img.size == (300, 300)
    colors = {c for _, c in img.convert("RGB").getcolors(300 * 300)}
    assert (0xD9, 0x82, 0x2B) in colors
    assert (0xF2, 0xA2, 0x4A) in colors


PRINTER_VIEWS = {"printer-printing": ("job", "Printing"), "printer-finished": ("job", "Finished"),
                 "printer-error": ("job", "Error"), "printer-idle": ("idle", "Ready")}


def test_printer_samples_build():
    module = _load()
    for name, (view, text) in PRINTER_VIEWS.items():
        ptype, options, sample = module.SAMPLES[name]
        assert ptype == "printer"
        data = module._printer_data(options, sample)
        assert data["view"] == view, name
        assert data["clock"] == "14:32", name
        assert text in (data["label"], data["big"]), name
        if name != "printer-idle":
            assert data["thumb"].startswith("data:image/png;base64,"), name


def test_twelve_hour_clock_sample_exists():
    ptype, _, data = _load().SAMPLES["clock-12h"]
    assert ptype == "clock" and (data["time"], data["ampm"]) == ("2:32", "PM")


def test_every_clock_sample_has_the_ampm_key():
    assert all("ampm" in d for p, _, d in _load().SAMPLES.values() if p == "clock")
