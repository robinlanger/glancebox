import importlib.util
import io
import sys
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from PIL import Image

from glancebox.config import AppConfig, PageConfig
from glancebox.frames import render_page
from glancebox.pages import PageContext, load_page_types
from glancebox.render import Renderer

# Load by file path: pages/bahn is not an installed package, and the top-level
# name `departures` must not leak into sys.modules.
_NAME = "glancebox_pages_bahn_departures"
_spec = importlib.util.spec_from_file_location(_NAME, Path(__file__).parent / "departures.py")
departures = importlib.util.module_from_spec(_spec)
sys.modules[_NAME] = departures  # dataclasses looks the module up here
_spec.loader.exec_module(departures)

Departure = departures.Departure
_clean_train = departures._clean_train
matches = departures.matches
parse = departures.parse
parse_directions = departures.parse_directions

# The route also contains stops BEFORE our own station; those must not match.
DIRECTIONS = {
    "departures": [
        {"train": "XY RB1", "destination": "Ost", "scheduledDeparture": "10:00",
         "route": [{"name": "West Hbf"}, {"name": "Musterstadt"}, {"name": "Ost"}]},
        {"train": "XY RB1", "destination": "West Hbf", "scheduledDeparture": "10:05",
         "route": [{"name": "Ost"}, {"name": "Musterstadt"}, {"name": "Mitte"},
                   {"name": "West Hbf"}]},
        {"train": "XY RB2", "destination": "Nord(Main)Hbf", "scheduledDeparture": "10:10",
         "route": [{"name": "Musterstadt"}, {"name": "Nord(Main)Hbf"}]},
    ]
}


def test_direction_filter_ignores_previous_stops():
    deps = parse(DIRECTIONS, "Musterstadt")
    dirs = parse_directions("West, nord")
    assert [d.destination for d in deps if matches(d, dirs)] == ["West Hbf", "Nord Hbf"]
    assert [d.destination for d in deps if matches(d, parse_directions("Mitte"))] == ["West Hbf"]
    assert all(matches(d, []) for d in deps)


SAMPLE = {
    "departures": [
        {"train": "HLB RB75", "destination": "Wiesbaden Hbf", "scheduledDeparture": "19:50",
         "delayDeparture": 4, "platform": "9", "scheduledPlatform": "9", "isCancelled": 0},
        {"train": "VIA RB66", "destination": "Darmstadt Hbf", "scheduledArrival": "19:53",
         "scheduledDeparture": None, "delayDeparture": None, "platform": "6", "isCancelled": 0},
        {"train": "S 3", "destination": "Bad Soden(Taunus)", "scheduledDeparture": "19:58",
         "delayDeparture": 0, "platform": "2", "scheduledPlatform": "1", "isCancelled": 0},
        {"train": "ICE 1234", "destination": "Hamburg-Altona", "scheduledDeparture": "20:05",
         "delayDeparture": None, "platform": "3", "scheduledPlatform": "3", "isCancelled": 1},
    ]
}

TZ = ZoneInfo("Europe/Berlin")


def test_clean_train():
    assert _clean_train("HLB RB75") == "RB75"
    assert _clean_train("S 1") == "S1"
    assert _clean_train("RE 60") == "RE60"
    assert _clean_train("ICE 123") == "ICE 123"


def test_parse_skips_arrivals_only():
    deps = parse(SAMPLE)
    assert [d.train for d in deps] == ["RB75", "S3", "ICE 1234"]
    assert deps[1].platform_changed is True
    assert deps[2].cancelled is True
    assert deps[1].destination == "Bad Soden"


def test_minutes_until_with_delay_and_midnight():
    now = datetime(2026, 11, 12, 19, 45, tzinfo=TZ)
    d = Departure("RB75", "X", "19:50", 4, None, False, False)
    assert d.minutes_until(now) == 9
    late = datetime(2026, 11, 12, 23, 55, tzinfo=TZ)
    d2 = Departure("S1", "X", "00:05", 0, None, False, False)
    assert d2.minutes_until(late) == 10


# --- page.py (fetch + template) ---------------------------------------------------------

PAGES_DIR = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 11, 12, 19, 49, tzinfo=TZ)


@pytest.fixture
def bahn(monkeypatch):
    ptype = load_page_types([PAGES_DIR])["bahn"]
    module = sys.modules["glancebox_pages.bahn"]
    calls = []

    def fake(base_url, station, **kw):
        calls.append((base_url, station, kw))
        return parse(SAMPLE, station)

    monkeypatch.setattr(module.departures, "fetch", fake)
    return ptype, module, calls


def _ctx(now=NOW):
    return PageContext(now=now, lang="de", timezone="Europe/Berlin")


def test_fetch_rows_from_sample(bahn):
    ptype, _, calls = bahn
    data = ptype.fetch({"station": "Musterstadt", "via": ["West", "Nord"], "platforms": "1,2"},
                       _ctx())
    assert data["title"] == "Musterstadt"
    assert data["clock"] == "19:49"
    assert data["message"] is None
    rows = data["rows"]
    assert [r["right"] for r in rows] == ["5", "9", "fällt aus"]
    assert rows[0]["unit"] == "min"
    assert rows[0]["badge"] == "regional"
    assert rows[0]["delay"] == 4 and rows[0]["delay_class"] == "minor"
    assert rows[1]["badge"] == "s" and rows[1]["platform_changed"] is True
    assert rows[1]["platform"] == "Gl. 2"
    assert rows[2]["right_class"] == "cancelled" and rows[2]["cancelled"] is True
    assert rows[2]["badge"] == "long" and rows[2]["unit"] == ""
    base_url, station, kw = calls[0]
    assert base_url == "https://dbf.finalrewind.org" and station == "Musterstadt"
    assert kw["via"] == "West,Nord" and kw["platforms"] == "1,2"
    assert kw["limit"] == 4 and kw["tz"] == "Europe/Berlin"


def test_fetch_dbf_error_gives_message(bahn, monkeypatch):
    ptype, module, _ = bahn

    def boom(*a, **kw):
        raise RuntimeError("DBF down")

    monkeypatch.setattr(module.departures, "fetch", boom)
    data = ptype.fetch({"station": "X", "title": "Mein Bahnhof"}, _ctx())
    assert data["message"] == "Keine Daten" and data["sub"] == "Stand 19:49"
    assert data["rows"] == [] and data["title"] == "Mein Bahnhof"


def test_fetch_error_log_redacts_urls(bahn, monkeypatch, caplog):
    ptype, module, _ = bahn

    def boom(*a, **kw):
        raise RuntimeError("cannot reach https://u:pw@dbf.example.org/X.json?token=abc")

    monkeypatch.setattr(module.departures, "fetch", boom)
    with caplog.at_level("WARNING"):
        ptype.fetch({"station": "X"}, _ctx())
    assert "https://***@dbf.example.org/X.json?***" in caplog.text
    assert "pw" not in caplog.text and "abc" not in caplog.text


def test_fetch_empty_list(bahn, monkeypatch):
    ptype, module, _ = bahn
    monkeypatch.setattr(module.departures, "fetch", lambda *a, **kw: [])
    data = ptype.fetch({"station": "X"}, _ctx())
    assert data["message"] == "Keine Abfahrten" and data["rows"] == []


def test_right_soon_and_hours(bahn):
    _, module, _ = bahn
    soon = Departure("S1", "X", "19:50", 0, None, False, False)
    later = Departure("S1", "X", "21:10", 0, None, False, False)
    r1, r2 = (module._row(d, NOW) for d in (soon, later))
    assert (r1["right"], r1["unit"], r1["right_class"]) == ("1", "min", "soon")
    assert (r2["right"], r2["unit"], r2["right_class"]) == ("21:10", "", "")
    now = Departure("S1", "X", "19:49", 0, None, False, False)
    assert module._row(now, NOW)["right"] == "jetzt"



def test_twelve_hour_rows(bahn):
    _, module, _ = bahn
    soon = Departure("S1", "X", "19:50", 0, None, False, False)
    later = Departure("S1", "X", "21:10", 5, None, False, False)
    r1, r2 = (module._row(d, NOW, "12h") for d in (soon, later))
    assert (r1["right"], r1["unit"], r1["scheduled"]) == ("1", "min", "7:50 PM")
    assert (r2["right"], r2["unit"], r2["scheduled"]) == ("9:15", "PM", "9:10 PM")
    assert module._row(later, NOW)["scheduled"] == "21:10"          # default unchanged
    assert module._row(later, NOW, "24h")["right"] == "21:15"


def test_twelve_hour_keeps_odd_scheduled_text(bahn):
    _, module, _ = bahn
    # DBF always sends HH:MM; a cancelled row never calls realtime(), so odd text gets this far
    odd = Departure("S1", "X", "--:--", None, None, False, True)
    assert module._row(odd, NOW, "12h")["scheduled"] == "--:--"


def test_twelve_hour_header_and_error_subtitle(bahn, monkeypatch):
    ptype, module, _ = bahn
    ctx12 = replace(_ctx(), time_format="12h")
    assert ptype.fetch({"station": "X"}, ctx12)["clock"] == "7:49 PM"

    def boom(*a, **k):
        raise RuntimeError("down")

    monkeypatch.setattr(module.departures, "fetch", boom)
    assert ptype.fetch({"station": "X"}, ctx12)["sub"] == "Stand 7:49 PM"

@pytest.mark.browser
async def test_template_renders_sample(bahn):
    ptype, _, _ = bahn
    cfg = AppConfig(interval=30, timezone="Europe/Berlin", lang="de",
                    pages=(), pages_dirs=(PAGES_DIR,))
    page = PageConfig(index=0, type="bahn", options={"station": "Musterstadt"},
                      duration=30, refresh=60)
    async with Renderer() as r:
        out = await render_page(page, ptype, cfg, r, NOW.timestamp())
    img = Image.open(io.BytesIO(out))
    assert img.format == "JPEG" and img.size == (240, 240)


@pytest.mark.browser
async def test_template_twelve_hours_fits():
    from playwright.async_api import async_playwright

    from glancebox.frames import _jinja_env

    row = {"train": "ICE 1234", "badge": "long", "destination": "Frankfurt (Main) Flughafen Fernbf",
           "right": "12:59", "unit": "PM", "right_class": "", "scheduled": "12:59 PM",
           "delay": 12, "delay_class": "major", "platform": "Gl. 102",
           "platform_changed": False, "cancelled": False}
    data = {"title": "Frankfurt (Main) Flughafen Fernbf", "clock": "12:59 PM",
            "rows": [dict(row) for _ in range(6)], "message": None, "sub": None}
    html = _jinja_env([PAGES_DIR / "bahn"]).get_template("template.html").render(**data)
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 240, "height": 240})
        await page.set_content(html, wait_until="load")
        boxes = await page.evaluate(
            "[...document.querySelectorAll('.right, .right *, .l2 > *')].map(e => {"
            " const r = e.getBoundingClientRect();"
            " return {cls: e.className, text: e.textContent,"
            " overflow: e.scrollWidth > e.clientWidth, left: r.left, right: r.right}; })")
        ampm = await page.evaluate("document.querySelectorAll('.hdr .clock .ui-ampm').length")
        await browser.close()
    assert len(boxes) == 6 * 6, boxes   # per row: .right, .val, .unit, .sched, .delay, .plat
    for b in boxes:
        assert not b["overflow"] and b["left"] >= 0 and b["right"] <= 240, b
    assert ampm == 1
