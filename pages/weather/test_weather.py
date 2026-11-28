import io
import itertools
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from PIL import Image

import glancebox.http
from glancebox.config import AppConfig, PageConfig
from glancebox.frames import render_page
from glancebox.pages import PageContext, load_page_types
from glancebox.render import Renderer

PAGES_DIR = Path(__file__).resolve().parents[1]
TZ = ZoneInfo("Europe/Berlin")
NOW = datetime(2026, 11, 14, 14, 5, tzinfo=TZ)

_START = datetime(2026, 11, 14, 0, 0)
HOURLY = {  # 48 hourly slots, temperature = 10 + 0.5 * slot index
    "time": [(_START + timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M") for i in range(48)],
    "temperature_2m": [10 + 0.5 * i for i in range(48)],
    "precipitation_probability": [i % 100 for i in range(48)],
    "weather_code": [3] * 48,
    "is_day": [1] * 48,
}
FORECAST = {
    "current": {"time": "2026-11-14T14:00", "temperature_2m": 12.5, "weather_code": 2,
                "is_day": 1},
    "hourly": HOURLY,
    "daily": {"temperature_2m_max": [14.5, 9.0], "temperature_2m_min": [5.5, 3.0]},
}
GEO = {"results": [{"name": "Frankfurt am Main", "latitude": 50.11, "longitude": 8.68}]}


@pytest.fixture
def weather():
    mod = load_page_types([PAGES_DIR])["weather"]
    return mod


@pytest.fixture
def calls(monkeypatch):
    made = []

    def fake(url, *, params=None, headers=None, timeout=10):
        made.append((url, params))
        return GEO if "geocoding" in url else FORECAST

    monkeypatch.setattr(glancebox.http, "get_json", fake)
    return made


def ctx(now=NOW, lang="de"):
    return PageContext(now, lang, "Europe/Berlin")


def test_validate_location_xor_coordinates(weather):
    weather.validate({"location": "Frankfurt"})
    weather.validate({"latitude": 50.1, "longitude": 8.7})
    with pytest.raises(ValueError):
        weather.validate({"location": "x", "latitude": 50.1, "longitude": 8.7})
    with pytest.raises(ValueError):
        weather.validate({})
    with pytest.raises(ValueError):
        weather.validate({"latitude": 50.1})
    with pytest.raises(ValueError):
        weather.validate({"latitude": 91, "longitude": 8.7})


def test_min_refresh(weather):
    assert weather.min_refresh == 60


def forecast_calls(calls):
    return [c for c in calls if "geocoding" not in c[0]]


def test_forecast_cached_for_900_s(weather, calls):
    opts = {"latitude": 50.1, "longitude": 8.7}
    weather.fetch(opts, ctx())
    data = weather.fetch(opts, ctx(NOW + timedelta(seconds=299)))
    assert len(forecast_calls(calls)) == 1
    assert data["clock"] == "14:09"  # clock and hours follow ctx.now, not the cached answer
    weather.fetch(opts, ctx(NOW + timedelta(seconds=899)))
    assert len(forecast_calls(calls)) == 1
    weather.fetch(opts, ctx(NOW + timedelta(seconds=901)))
    assert len(forecast_calls(calls)) == 2


def test_forecast_cache_keyed_by_coordinates(weather, calls):
    weather.fetch({"latitude": 50.1, "longitude": 8.7}, ctx())
    weather.fetch({"latitude": 48.1, "longitude": 11.6}, ctx())
    assert len(forecast_calls(calls)) == 2


def test_failed_forecast_not_cached_and_raises_after_expiry(weather, calls, monkeypatch):
    opts = {"latitude": 50.1, "longitude": 8.7}
    weather.fetch(opts, ctx())

    def boom(url, *, params=None, headers=None, timeout=10):
        calls.append((url, params))
        raise RuntimeError("down")

    monkeypatch.setattr(glancebox.http, "get_json", boom)
    weather.fetch(opts, ctx(NOW + timedelta(seconds=600)))  # still cached
    for seconds in (901, 961):  # expired: every attempt asks again and raises
        with pytest.raises(RuntimeError):
            weather.fetch(opts, ctx(NOW + timedelta(seconds=seconds)))
    assert len(forecast_calls(calls)) == 3


def test_fetch_maps_current_and_hours(weather, calls):
    data = weather.fetch({"latitude": 50.1, "longitude": 8.7}, ctx())
    assert data["title"] == "Wetter"
    assert data["clock"] == "14:05"
    assert data["icon"] == "partly"
    assert data["temp"] == 13  # 12.5 rounds half-up
    assert data["desc"] == "Leicht bewölkt"
    assert data["high"] == 15 and data["low"] == 6
    # Slots 15..18 (index 15..18): temp 17.5 -> 18, 18, 18.5 -> 19, 19
    assert data["hours"] == [
        {"hour": "15", "temp": 18, "rain": 15},
        {"hour": "16", "temp": 18, "rain": 16},
        {"hour": "17", "temp": 19, "rain": 17},
        {"hour": "18", "temp": 19, "rain": 18},
    ]
    url, params = calls[0]
    assert url == "https://api.open-meteo.com/v1/forecast"
    assert params["timezone"] == "Europe/Berlin" and params["forecast_days"] == 2


def test_hours_cross_midnight(weather, calls):
    now = datetime(2026, 11, 14, 22, 30, tzinfo=TZ)
    data = weather.fetch({"latitude": 50.1, "longitude": 8.7}, ctx(now))
    assert [h["hour"] for h in data["hours"]] == ["23", "00", "01", "02"]
    assert data["hours"][1]["temp"] == 22  # slot 24 -> 22.0


def test_night_icon(weather, calls, monkeypatch):
    forecast = {**FORECAST, "current": {**FORECAST["current"], "weather_code": 0, "is_day": 0}}
    monkeypatch.setattr(glancebox.http, "get_json", lambda *a, **k: forecast)
    data = weather.fetch({"latitude": 1, "longitude": 1}, ctx())
    assert data["icon"] == "clear-night"


def test_icon_keys(weather, calls, monkeypatch):
    longitudes = itertools.count(1)

    def icon(code, is_day=1):
        forecast = {**FORECAST, "current": {**FORECAST["current"], "weather_code": code,
                                            "is_day": is_day}}
        monkeypatch.setattr(glancebox.http, "get_json", lambda *a, **k: forecast)
        # distinct coordinates per call so the forecast cache does not answer
        return weather.fetch({"latitude": 1, "longitude": next(longitudes)}, ctx())["icon"]

    for code, key in [(0, "clear"), (1, "partly"), (3, "cloudy"), (45, "fog"), (61, "rain"),
                      (81, "rain"), (73, "snow"), (86, "snow"), (96, "thunder"), (42, "cloudy")]:
        assert icon(code) == key
    assert icon(2, 0) == "partly-night"


def test_geocode_cached(weather, calls):
    for _ in range(2):
        data = weather.fetch({"location": "Frankfurt am Main"}, ctx())
    assert data["title"] == "Frankfurt am Main"
    geo = [c for c in calls if "geocoding" in c[0]]
    assert len(geo) == 1
    assert geo[0][1] == {"name": "Frankfurt am Main", "count": 1, "language": "de",
                         "format": "json"}
    forecast = [c for c in calls if "geocoding" not in c[0]]
    assert forecast[0][1]["latitude"] == 50.11


def test_title_option_wins(weather, calls):
    data = weather.fetch({"location": "Frankfurt", "title": "Zuhause"}, ctx())
    assert data["title"] == "Zuhause"


def test_location_not_found(weather, calls, monkeypatch):
    monkeypatch.setattr(glancebox.http, "get_json", lambda *a, **k: {})
    with pytest.raises(ValueError, match="location not found: Nirgendwo"):
        weather.fetch({"location": "Nirgendwo"}, ctx())


def test_english_texts(weather, calls):
    data = weather.fetch({"latitude": 50.1, "longitude": 8.7}, ctx(lang="en"))
    assert data["title"] == "Weather"
    assert data["desc"] == "Partly cloudy"


def test_twelve_hour_clock_and_hours(weather, calls):
    data = weather.fetch({"latitude": 50.1, "longitude": 8.7}, replace(ctx(), time_format="12h"))
    assert data["clock"] == "2:05 PM"
    assert [h["hour"] for h in data["hours"]] == ["3 PM", "4 PM", "5 PM", "6 PM"]


def test_twelve_hour_hours_cross_midnight(weather, calls):
    late = datetime(2026, 11, 14, 22, 30, tzinfo=TZ)
    data = weather.fetch({"latitude": 50.1, "longitude": 8.7},
                         replace(ctx(now=late), time_format="12h"))
    assert [h["hour"] for h in data["hours"]] == ["11 PM", "12 AM", "1 AM", "2 AM"]


@pytest.mark.browser
async def test_template_renders(weather, calls):
    cfg = AppConfig(interval=30, timezone="Europe/Berlin", lang="de",
                    pages=(), pages_dirs=(PAGES_DIR,))
    page = PageConfig(index=0, type="weather", options={"latitude": 50.1, "longitude": 8.7},
                      duration=30, refresh=60)
    async with Renderer() as r:
        out = await render_page(page, weather, cfg, r, NOW.timestamp())
    img = Image.open(io.BytesIO(out))
    assert img.format == "JPEG" and img.size == (240, 240)
    assert img.convert("L").getextrema()[1] > 150


@pytest.mark.browser
async def test_twelve_hour_hours_fit_their_columns(weather, calls):
    from playwright.async_api import async_playwright

    from glancebox.frames import _jinja_env

    data = weather.fetch({"latitude": 50.1, "longitude": 8.7}, replace(ctx(), time_format="12h"))
    texts = ["10 PM", "11 PM", "12 AM", "1 AM"]
    for h, text in zip(data["hours"], texts, strict=True):
        h["hour"] = text
    html = _jinja_env([PAGES_DIR / "weather"]).get_template("template.html").render(**data)
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 240, "height": 240})
        await page.set_content(html)
        boxes = await page.evaluate(
            "[...document.querySelectorAll('.h')].map(h => { const t = h.querySelector('.t');"
            " const c = h.getBoundingClientRect(), r = t.getBoundingClientRect();"
            " return {text: t.textContent, overflow: t.scrollWidth > t.clientWidth,"
            " width: c.width, inside: r.left >= c.left && r.right <= c.right}; })")
        await browser.close()
    assert [b["text"] for b in boxes] == texts
    for b in boxes:
        assert not b["overflow"] and b["inside"], b
        assert 59 <= b["width"] <= 61, b


def dst_forecast(stamps: list[str]) -> dict:
    """Open-Meteo answer with timezone=Europe/Berlin: local wall-clock strings, temp = index."""
    n = len(stamps)
    return {**FORECAST, "hourly": {"time": stamps, "temperature_2m": list(range(n)),
                                   "precipitation_probability": [0] * n,
                                   "weather_code": [3] * n, "is_day": [1] * n}}


def day_stamps(day: str, hours: list[int]) -> list[str]:
    return [f"{day}T{h:02d}:00" for h in hours]


# 2026-10-25: clocks go back 03:00 CEST -> 02:00 CET, so the 02:00 slot occurs twice (25 slots).
FALL_BACK = day_stamps("2026-10-25", [0, 1, 2, 2, *range(3, 24)])
# 2026-03-29: clocks go forward 02:00 CET -> 03:00 CEST, there is no 02:00 slot (23 slots).
SPRING_FORWARD = day_stamps("2026-03-29", [0, 1, *range(3, 24)])


@pytest.mark.parametrize(("now", "stamps", "hours", "temps"), [
    # 01:30 CEST: both 02:00 slots, then 03 and 04
    (datetime(2026, 10, 25, 1, 30, tzinfo=TZ), FALL_BACK, ["02", "02", "03", "04"], [2, 3, 4, 5]),
    # 02:30 CEST (first pass): the second 02:00 (CET) is still ahead
    (datetime(2026, 10, 25, 2, 30, tzinfo=TZ), FALL_BACK, ["02", "03", "04", "05"], [3, 4, 5, 6]),
    # 02:30 CET (second pass, fold=1)
    (datetime(2026, 10, 25, 2, 30, fold=1, tzinfo=TZ), FALL_BACK,
     ["03", "04", "05", "06"], [4, 5, 6, 7]),
    # 01:30 CET: next slot is 03:00 CEST
    (datetime(2026, 3, 29, 1, 30, tzinfo=TZ), SPRING_FORWARD, ["03", "04", "05", "06"],
     [2, 3, 4, 5]),
    # 03:30 CEST
    (datetime(2026, 3, 29, 3, 30, tzinfo=TZ), SPRING_FORWARD, ["04", "05", "06", "07"],
     [3, 4, 5, 6]),
])
def test_hours_across_dst(weather, monkeypatch, now, stamps, hours, temps):
    forecast = dst_forecast(stamps)
    monkeypatch.setattr(glancebox.http, "get_json", lambda *a, **k: forecast)
    data = weather.fetch({"latitude": 50.1, "longitude": 8.7}, ctx(now))
    assert [h["hour"] for h in data["hours"]] == hours
    assert [h["temp"] for h in data["hours"]] == temps
