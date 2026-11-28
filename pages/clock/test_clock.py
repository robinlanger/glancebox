import io
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from PIL import Image

from glancebox.config import AppConfig, PageConfig
from glancebox.frames import render_page
from glancebox.pages import PageContext, load_page_types
from glancebox.render import Renderer

PAGES_DIR = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 11, 14, 9, 5, tzinfo=ZoneInfo("Europe/Berlin"))  # a Saturday


@pytest.fixture
def clock():
    return load_page_types([PAGES_DIR])["clock"]


def test_fetch_german(clock):
    data = clock.fetch({}, PageContext(NOW, "de", "Europe/Berlin"))
    assert data == {"time": "09:05", "ampm": "", "weekday": "Samstag", "date": "14.11.2026"}


def test_fetch_english_option_overrides_ctx(clock):
    data = clock.fetch({"lang": "en"}, PageContext(NOW, "de", "Europe/Berlin"))
    assert data == {"time": "09:05", "ampm": "", "weekday": "Saturday", "date": "2026-11-14"}


def test_fetch_twelve_hours(clock):
    ctx = PageContext(NOW, "en", "Europe/Berlin", time_format="12h")
    assert clock.fetch({}, ctx) == {"time": "9:05", "ampm": "AM", "weekday": "Saturday",
                                    "date": "2026-11-14"}
    noon = PageContext(NOW.replace(hour=12, minute=59), "de", "Europe/Berlin", time_format="12h")
    assert (clock.fetch({}, noon)["time"], clock.fetch({}, noon)["ampm"]) == ("12:59", "PM")


def test_validate_rejects_unknown_lang(clock):
    with pytest.raises(ValueError, match="lang"):
        clock.validate({"lang": "fr"})


@pytest.mark.browser
async def test_template_renders(clock):
    cfg = AppConfig(interval=30, timezone="Europe/Berlin", lang="de",
                    pages=(), pages_dirs=(PAGES_DIR,))
    page = PageConfig(index=0, type="clock", options={}, duration=30, refresh=60)
    async with Renderer() as r:
        out = await render_page(page, clock, cfg, r, NOW.timestamp())
    img = Image.open(io.BytesIO(out))
    assert img.format == "JPEG" and img.size == (240, 240)
    assert img.convert("L").getextrema()[1] > 150  # bright text on the dark background


async def _measure(time: str, ampm: str) -> dict:
    from playwright.async_api import async_playwright

    from glancebox.frames import _jinja_env

    html = _jinja_env([PAGES_DIR / "clock"]).get_template("template.html").render(
        time=time, ampm=ampm, weekday="Saturday", date="2026-11-14")
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 240, "height": 240})
        await page.set_content(html)
        info = await page.evaluate(
            "(() => { const t = document.querySelector('.time');"
            " const s = document.querySelector('.ampm');"
            " const r = t.getBoundingClientRect();"
            " const right = s ? Math.max(r.right, s.getBoundingClientRect().right) : r.right;"
            " const all = [...document.querySelectorAll('.clock *')];"
            " return {left: r.left, right: right, size: getComputedStyle(t).fontSize,"
            " suffix: s ? s.textContent : null,"
            " overflow: all.some(e => e.scrollWidth > e.clientWidth)"
            "   || document.documentElement.scrollWidth > 240}; })()")
        await browser.close()
    return info


@pytest.mark.browser
async def test_template_twelve_hours_fits():
    info = await _measure("12:59", "PM")
    assert info["suffix"] == "PM"
    assert 4 <= info["left"] and info["right"] <= 236, info
    assert not info["overflow"], info
    plain = await _measure("12:59", "")
    assert plain["suffix"] is None
    assert plain["size"] == "72px"
