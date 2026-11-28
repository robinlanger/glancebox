#!/usr/bin/env python3
"""Render the preview images of the template catalog to docs/img/templates/<name>.png.

Each entry of SAMPLES maps a preview name to (page type, options, data). `data` is the dict the
page's fetch() would return; it goes straight into the page's template.html, so no network is
needed. Later template pages add their entries here. For `energy`, `data` holds the Home
Assistant states instead; the page's own build() turns them into the template data, and
paint_arrows() draws one still position of the arrows the device would animate. For `printer`,
`data` holds the fields of a PrinterStatus; the page's build() turns them into the template data
at PRINTER_NOW, with sample_thumbnail() as the slicer preview.

Run it locally (uses the server's virtualenv, which has Chromium):

    server/.venv/bin/python tools/render_previews.py

or inside the image (tools/ is not copied into it, so mount it):

    docker run --rm -v "$PWD/docs/img:/app/docs/img" -v "$PWD/tools:/app/tools:ro" \
        glancebox:dev python /app/tools/render_previews.py
"""
import asyncio
import io
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))

from glancebox import anim as anim_format
from glancebox.anim import Anim
from glancebox.frames import ANIM_KEY, _jinja_env
from glancebox.pages import load_page_types
from glancebox.render import Renderer

OUT = ROOT / "docs" / "img" / "templates"
PAGES = ROOT / "pages"

# Fixed time of the printer previews (a Wednesday) and the job they show. "thumbnail": True
# stands for sample_thumbnail(), our own drawing; never a third-party model picture.
PRINTER_NOW = datetime(2026, 11, 25, 14, 32, tzinfo=ZoneInfo("Europe/Berlin"))
PRINTER_OPTIONS = {"source": "moonraker", "url": "http://drucker.local:7125", "lang": "en"}
_PRINTER_FILE = "benchy_0.2mm_PLA_MK4"

SAMPLES: dict[str, tuple[str, dict, dict]] = {
    "clock": ("clock", {"lang": "en"},
              {"time": "14:32", "ampm": "", "weekday": "Thursday", "date": "2026-11-12"}),
    "clock-12h": ("clock", {"lang": "en"},
                  {"time": "2:32", "ampm": "PM", "weekday": "Thursday", "date": "2026-11-12"}),
    "weather": ("weather", {"location": "Frankfurt am Main", "lang": "en"}, {
        "title": "Frankfurt am Main", "clock": "14:32", "icon": "partly", "temp": 11,
        "desc": "Partly cloudy", "high": 15, "low": 6,
        "hours": [{"hour": "15", "temp": 12, "rain": 10}, {"hour": "16", "temp": 12, "rain": 20},
                  {"hour": "17", "temp": 10, "rain": 55}, {"hour": "18", "temp": 9, "rain": 70}]}),
    "kuma-ok": ("kuma", {"url": "http://kuma.lan:3001", "slug": "home", "lang": "en"}, {
        "title": "Homelab", "clock": "14:32", "lang": "en", "state": "ok", "up": 14,
        "total": 14, "uptime": "99.9 %", "pending": 0, "down": [], "more": 0,
        "message": None, "sub": None}),
    "kuma-down": ("kuma", {"url": "http://kuma.lan:3001", "slug": "home", "lang": "en"}, {
        "title": "Homelab", "clock": "14:32", "lang": "en", "state": "down", "up": 12,
        "total": 14, "uptime": "97.1 %", "pending": 0,
        "down": [{"name": "Nextcloud", "since": "12 min"},
                 {"name": "Backup server with a very long host name", "since": "3 h"}],
        "more": 0, "message": None, "sub": None}),
    "homeassistant-tiles": ("homeassistant", {"url": "http://homeassistant.lan:8123",
                                              "token": "${HA_TOKEN}", "lang": "en"}, {
        "title": "Solar", "clock": "14:32", "lang": "en", "layout": "tiles", "state": "ok",
        "message": None, "sub": None,
        "items": [{"label": "PV", "value": "3.2", "unit": "kW", "tone": "", "size": "l"},
                  {"label": "Grid", "value": "−1.1", "unit": "kW", "tone": "", "size": "l"},
                  {"label": "House", "value": "2.1", "unit": "kW", "tone": "", "size": "l"},
                  {"label": "Battery", "value": "78", "unit": "%", "tone": "", "size": "l"}]}),
    "homeassistant-list": ("homeassistant", {"url": "http://homeassistant.lan:8123",
                                             "token": "${HA_TOKEN}", "lang": "en"}, {
        "title": "Home", "clock": "14:32", "lang": "en", "layout": "list", "state": "ok",
        "message": None, "sub": None,
        "items": [{"label": "Living room", "value": "21.4", "unit": "°C", "tone": "", "size": "m"},
                  {"label": "Outside", "value": "8.1", "unit": "°C", "tone": "", "size": "m"},
                  {"label": "Humidity", "value": "54", "unit": "%", "tone": "", "size": "m"},
                  {"label": "Front door", "value": "closed", "unit": None, "tone": "",
                   "size": "m"},
                  {"label": "Bathroom window", "value": "open", "unit": None, "tone": "open",
                   "size": "m"},
                  {"label": "Kitchen light", "value": "on", "unit": None, "tone": "on",
                   "size": "m"}]}),
    "ai-claude": ("ai", {"provider": "claude", "lang": "en"}, {
        "title": "Claude", "clock": "14:05", "big": None, "stand": "As of 13:58",
        "message": None, "sub": None, "theme": "claude",
        "rows": [{"label": "5 hours", "reset": "in 2:13", "percent": 42.0, "text": "42 %"},
                 {"label": "Week", "reset": "Thu 09:00", "percent": 81.0, "text": "81 %"}]}),
    "ai-cost": ("ai", {"provider": "openai-api", "key": "${OPENAI_ADMIN_KEY}", "budget": 50,
                       "lang": "en"}, {
        "title": "OpenAI API", "clock": "14:05", "stand": "As of 14:05", "message": None,
        "sub": None, "alert": False, "big": {"label": "This month", "value": "$18.40"},
        "rows": [{"label": "Budget", "reset": "Dec 1", "percent": 36.8, "text": "37 %"}]}),
    "bahn": ("bahn", {"station": "Musterstadt"}, {
        "title": "Musterstadt", "clock": "10:42", "message": None, "sub": None,
        "rows": [
            {"train": "RB 1", "badge": "regional", "destination": "Ostdorf", "right": "5",
             "unit": "min", "right_class": "", "scheduled": "10:47", "delay": 4,
             "delay_class": "minor", "platform": "Gl. 1", "platform_changed": False,
             "cancelled": False},
            {"train": "S 3", "badge": "s", "destination": "Westhafen", "right": "9",
             "unit": "min", "right_class": "", "scheduled": "10:51", "delay": None,
             "delay_class": "major", "platform": "Gl. 2", "platform_changed": True,
             "cancelled": False},
            {"train": "ICE 599", "badge": "long", "destination": "Nord Hbf", "right": "fällt aus",
             "unit": "", "right_class": "cancelled", "scheduled": "10:55", "delay": None,
             "delay_class": "major", "platform": "Gl. 3", "platform_changed": False,
             "cancelled": True},
            {"train": "RE 20", "badge": "regional", "destination": "Südstadt", "right": "2",
             "unit": "min", "right_class": "soon", "scheduled": "10:44", "delay": 8,
             "delay_class": "major", "platform": "Gl. 4", "platform_changed": False,
             "cancelled": False},
        ]}),
    "energy": ("energy", {"url": "http://homeassistant.lan:8123", "token": "${HA_TOKEN}",
                          "lang": "en", "title": "Power",
                          "rows": [{"type": "grid", "entity": "sensor.grid_power"},
                                   {"type": "pv", "entity": "sensor.pv_power"},
                                   {"type": "battery", "entity": "sensor.battery_power",
                                    "soc": "sensor.battery_level"}]}, {
        # Home Assistant states given to the page's build(); battery negative = charging.
        "sensor.grid_power": {"state": "-1100", "attributes": {"unit_of_measurement": "W"}},
        "sensor.pv_power": {"state": "3200", "attributes": {"unit_of_measurement": "W"}},
        "sensor.battery_power": {"state": "-900", "attributes": {"unit_of_measurement": "W"}},
        "sensor.battery_level": {"state": "64", "attributes": {"unit_of_measurement": "%"}}}),
    # printer: the fields of a PrinterStatus, turned into template data by the page's build().
    "printer-printing": ("printer", PRINTER_OPTIONS, {
        "state": "printing", "progress": 47.0, "remaining_s": 4980, "filename": _PRINTER_FILE,
        "nozzle": (214.0, 215.0), "bed": (60.0, 60.0), "layer": (112, 240), "thumbnail": True}),
    "printer-finished": ("printer", PRINTER_OPTIONS, {
        "state": "finished", "progress": 100.0, "filename": _PRINTER_FILE, "duration_s": 11520,
        "ended_at": PRINTER_NOW - timedelta(minutes=4), "nozzle": (48.0, None),
        "bed": (41.0, None), "thumbnail": True}),
    "printer-error": ("printer", PRINTER_OPTIONS, {
        "state": "error", "progress": 47.0, "filename": _PRINTER_FILE,
        "message": "Heater extruder not heating at expected rate", "nozzle": (162.0, None),
        "bed": (58.0, None), "thumbnail": True}),
    "printer-idle": ("printer", PRINTER_OPTIONS, {
        "state": "idle", "nozzle": (142.0, 215.0), "bed": (23.0, None),
        "last_job": (_PRINTER_FILE,
                     (PRINTER_NOW - timedelta(days=1)).replace(hour=21, minute=14))}),
}
ENERGY_CLOCK = "14:32"


def paint_arrows(img: Image.Image, anim: Anim) -> None:
    """Draw fixed chevrons into each track like the firmware does (tips at x + 9 + k * 18).

    Same shape as drawChevron() in firmware/src/display.cpp: tip on the track's middle row,
    ARROW_HALF_HEIGHT px up and down, ARROW_STROKE px wide towards the open side, clipped to the
    track rectangle.
    """
    half, spacing = anim_format.ARROW_HALF_HEIGHT, anim_format.ARROW_SPACING
    for tr in anim.tracks:
        mask = Image.new("L", (tr.w, tr.h), 0)
        draw = ImageDraw.Draw(mask)
        left = tr.direction == "l"
        d, step = (half, 1) if left else (-half, -1)
        cy = tr.h // 2
        for tx in range(spacing // 2, tr.w + spacing, spacing):
            for s in range(anim_format.ARROW_STROKE):
                x = tx + s * step
                draw.line([(x + d, cy - half), (x, cy)], fill=255)
                draw.line([(x + d, cy + half), (x, cy)], fill=255)
        img.paste("#" + tr.color, (tr.x, tr.y), mask)


def _energy_data(options: dict, states: dict) -> tuple[dict, Anim | None]:
    """Template data and animation from the energy page's own build()."""
    load_page_types([PAGES])
    build = sys.modules["glancebox_pages.energy"].build
    data = build(options, states, options["lang"], ENERGY_CLOCK)
    return data, data.pop(ANIM_KEY, None)


def sample_thumbnail() -> bytes:
    """A 300×300 PNG slicer preview drawn here: the cube of the printer mockup (symbol
    `thumbimg` in docs/superpowers/specs/assets/2026-11-25-printer-mockup.html), its 100×100
    coordinates times 3."""
    def pts(*xy: int) -> list[tuple[int, int]]:
        return [(xy[i] * 3, xy[i + 1] * 3) for i in range(0, len(xy), 2)]

    img = Image.new("RGB", (300, 300), "#141922")
    draw = ImageDraw.Draw(img)
    draw.polygon(pts(22, 70, 50, 82, 80, 68, 80, 44, 52, 32, 22, 46), fill="#d9822b")
    draw.polygon(pts(22, 46, 52, 32, 80, 44, 50, 57), fill="#f2a24a")
    draw.polygon(pts(50, 57, 50, 82, 80, 68, 80, 44), fill="#b8661c")
    draw.polygon(pts(40, 40, 40, 22, 58, 16, 58, 36), fill="#f2a24a", outline="#b8661c",
                 width=6)
    draw.ellipse((49 * 3 - 12, 26 * 3 - 12, 49 * 3 + 12, 26 * 3 + 12), fill="#141922")
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def _printer_data(options: dict, sample: dict) -> dict:
    """Template data from the printer page's own build(), at PRINTER_NOW."""
    load_page_types([PAGES])
    page = sys.modules["glancebox_pages.printer"]
    common = sys.modules["glancebox_pages.printer.providers._common"]
    fields = dict(sample)
    if fields.pop("thumbnail", False):
        fields["thumbnail"] = common.Thumbnail(sample_thumbnail(), "image/png")
    status = page.PrinterStatus(**fields)
    return page.build(status, options, options["lang"], PRINTER_NOW)


def _homeassistant_sizes(data: dict) -> None:
    """Set each item's size class with the page's own size_class, so previews match real output."""
    load_page_types([PAGES])
    size_class = sys.modules["glancebox_pages.homeassistant"].size_class
    items = data["items"]
    for item in items:
        item["size"] = size_class(item["value"], item["unit"], data["layout"], len(items))


async def render_all(names: list[str]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    async with Renderer() as renderer:
        for name in names:
            ptype, options, data = SAMPLES[name]
            anim = None
            if ptype == "homeassistant":
                _homeassistant_sizes(data)
            elif ptype == "energy":
                data, anim = _energy_data(options, data)
            elif ptype == "printer":
                data = _printer_data(options, data)
            page_dir = PAGES / ptype
            html = _jinja_env([page_dir]).get_template("template.html").render(**data)
            jpeg = await renderer.render_html(html)
            img = Image.open(io.BytesIO(jpeg)).convert("RGB")
            if anim is not None:
                paint_arrows(img, anim)
            buf = io.BytesIO()
            img.quantize(256, method=Image.Quantize.FASTOCTREE, dither=Image.Dither.NONE).save(buf, "PNG", optimize=True)
            (OUT / f"{name}.png").write_bytes(buf.getvalue())
            print(f"{name}.png  {buf.tell()} bytes")


def main(argv: list[str]) -> int:
    names = argv[1:] or list(SAMPLES)
    unknown = [n for n in names if n not in SAMPLES]
    if unknown:
        print(f"unknown sample(s): {', '.join(unknown)}; known: {', '.join(SAMPLES)}",
              file=sys.stderr)
        return 1
    asyncio.run(render_all(names))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
