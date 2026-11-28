import io
import logging
import os
import sys
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import requests
from PIL import Image

import glancebox.http
from glancebox.config import AppConfig, PageConfig
from glancebox.frames import render_page
from glancebox.pages import PageContext, load_page_types
from glancebox.render import Renderer

PAGES_DIR = Path(__file__).resolve().parents[1]
OPTIONS = {"url": "http://homeassistant.lan:8123", "token": "t0ken", "entities": ["sensor.a"]}


@pytest.fixture
def ha():
    return load_page_types([PAGES_DIR])["homeassistant"]


@pytest.fixture
def mod(ha):
    return sys.modules["glancebox_pages.homeassistant"]


def test_validate_ok_minimal(ha):
    ha.validate(OPTIONS)


def test_validate_ok_full(ha):
    ha.validate({**OPTIONS, "layout": "list", "lang": "en", "title": "X",
                 "entities": ["sensor.a", {"entity": "sensor.b", "label": "B", "decimals": 2}]})


def _opts(**kw):
    return {**OPTIONS, **kw}


def _without(key):
    return {k: v for k, v in OPTIONS.items() if k != key}


@pytest.mark.parametrize(("options", "match"), [
    (_without("url"), "url"),
    (_opts(url="ftp://x"), "http"),
    (_without("token"), "token"),
    (_opts(token=""), "token"),
    (_opts(token="abc\r"), "token"),
    (_opts(token="ab\ncd"), "token"),
    (_opts(token="ab cd"), "token"),
    (_without("entities"), "entities"),
    (_opts(entities=[]), "entities"),
    (_opts(entities=[f"sensor.s{i}" for i in range(7)], layout="list"), "at most 6"),
    (_opts(entities=["Sensor.A"]), "entity id"),
    (_opts(entities=[{"label": "x"}]), "entity"),
    (_opts(entities=[{"entity": "sensor.a", "decimals": 4}]), "decimals"),
    (_opts(entities=[{"entity": "sensor.a", "decimals": True}]), "decimals"),
    (_opts(entities=[{"entity": "sensor.a", "label": 5}]), "label"),
    (_opts(layout="grid"), "layout"),
    (_opts(layout="tiles", entities=[f"sensor.s{i}" for i in range(5)]), "at most 4"),
    (_opts(lang="fr"), "lang"),
    (_opts(title=3), "title"),
])
def test_validate_rejects(ha, options, match):
    with pytest.raises(ValueError, match=match):
        ha.validate(options)


def test_entries_normalizes(mod):
    result = mod.entries({"entities": ["sensor.a",
                                       {"entity": "sensor.b", "label": "B", "decimals": 0}]})
    assert result == [mod.Entry("sensor.a", None, None), mod.Entry("sensor.b", "B", 0)]


def test_default_layout(mod):
    assert [mod.default_layout(n) for n in (1, 4, 5, 6)] == ["tiles", "tiles", "list", "list"]


def test_no_min_refresh(ha):
    assert ha.min_refresh == 0


# --- Task 3: format values ---------------------------------------------------

def st(state, entity_id="sensor.x", **attrs):
    return {"entity_id": entity_id, "state": state, "attributes": attrs}


def test_number_with_unit_de_en(mod):
    s = st("21.37", unit_of_measurement="°C")
    assert mod.format_state(s, None, "de") == mod.Cell("21,4", "°C", "")
    assert mod.format_state(s, None, "en") == mod.Cell("21.4", "°C", "")


def test_integer_stays_integer(mod):
    assert mod.format_state(st("54", unit_of_measurement="%"), None, "de").value == "54"
    assert mod.format_state(st("54.0", unit_of_measurement="%"), None, "de").value == "54"


def test_decimals_option(mod):
    assert mod.format_state(st("21.37"), 2, "de").value == "21,37"
    assert mod.format_state(st("21.37"), 0, "de").value == "21"


def test_watts_to_kilowatts(mod):
    w = {"unit_of_measurement": "W"}
    assert mod.format_state(st("3200", **w), None, "de") == mod.Cell("3,2", "kW", "")
    assert mod.format_state(st("999", **w), None, "de") == mod.Cell("999", "W", "")
    assert mod.format_state(st("-1100", **w), None, "de") == mod.Cell("−1,1", "kW", "")
    assert mod.format_state(st("12500", unit_of_measurement="Wh"), None, "de") == mod.Cell(
        "12,5", "kWh", "")


def test_negative_uses_minus_sign(mod):
    assert mod.format_state(st("-3.5", unit_of_measurement="°C"), None, "de").value == "−3,5"


@pytest.mark.parametrize(("lang", "text"), [("de", "n. v."), ("en", "n/a")])
@pytest.mark.parametrize("state", ["unavailable", "unknown", "nan", "inf", "-inf"])
def test_unavailable_unknown_nan_inf(mod, lang, text, state):
    assert mod.format_state(st(state), None, lang) == mod.Cell(text, None, "warn")


def test_format_number_rounding_edge_cases(mod):
    assert mod.format_state(st("1.0e-05"), None, "de").value == "0"
    c = mod.format_state(st("3200.000001", unit_of_measurement="W"), None, "de")
    assert (c.value, c.unit) == ("3,2", "kW")


@pytest.mark.parametrize(("entity", "dc", "state", "de", "en", "tone"), [
    *[("binary_sensor.x", d, "on", "offen", "open", "open")
      for d in ("window", "door", "opening", "garage_door")],
    *[("binary_sensor.x", d, "off", "zu", "closed", "")
      for d in ("window", "door", "opening", "garage_door")],
    *[("binary_sensor.x", d, "on", "erkannt", "detected", "")
      for d in ("motion", "occupancy", "presence")],
    *[("binary_sensor.x", d, "off", "frei", "clear", "")
      for d in ("motion", "occupancy", "presence")],
    ("binary_sensor.x", None, "on", "an", "on", ""),
    ("binary_sensor.x", None, "off", "aus", "off", ""),
    ("light.x", None, "on", "an", "on", "on"),
    ("light.x", None, "off", "aus", "off", ""),
    ("switch.x", None, "on", "an", "on", "on"),
    ("input_boolean.x", None, "on", "an", "on", ""),
    ("fan.x", None, "on", "an", "on", ""),
])
def test_binary_words(mod, entity, dc, state, de, en, tone):
    attrs = {"device_class": dc} if dc else {}
    s = st(state, entity_id=entity, **attrs)
    assert mod.format_state(s, None, "de") == mod.Cell(de, None, tone)
    assert mod.format_state(s, None, "en") == mod.Cell(en, None, tone)


def test_other_text_passthrough(mod):
    assert mod.format_state(st("heat", entity_id="climate.x"), None, "de") == mod.Cell(
        "heat", None, "")


def test_size_class(mod):
    sc = mod.size_class
    assert sc("21,4", "°C", "tiles", 4) == "l"
    assert sc("−10,4", "kW", "tiles", 4) in ("m", "s")
    assert sc("−10234,5", "kWh", "tiles", 4) == "s"
    assert sc("21,4", "°C", "tiles", 1) == "l"
    assert sc("Langer Zustandstext hier", None, "list", 6) == "s"
    # common values pick a class whose width fits, so the template never needs an ellipsis
    assert sc("−1.1", "kW", "tiles", 4) == "l"
    assert sc("100", "%", "tiles", 4) == "l"
    assert sc("100,0", "%", "tiles", 4) == "m"
    assert sc("closed", None, "tiles", 4) == "m"
    assert sc("erkannt", None, "tiles", 4) == "m"
    assert sc("detected", None, "tiles", 4) == "s"
    assert sc("Abwesend", None, "tiles", 4) == "s"
    assert sc("Abwesend", None, "tiles", 1) == "m"
    assert sc("21,4", "°C", "list", 6) == "m"


def test_text_width_grows_with_font_and_unit(mod):
    w = mod.text_width
    assert w("100", None, (30, 15, 3)) < w("100", "%", (30, 15, 3)) < w("100", "%", (44, 15, 3))
    assert w("mmm", None, (20, 10, 2)) > w("iii", None, (20, 10, 2))


def test_kw_switch_after_rounding(mod):
    assert mod.format_state(st("999.96", unit_of_measurement="W"), None, "de") == \
        mod.Cell("1", "kW", "")
    assert mod.format_state(st("-999.96", unit_of_measurement="W"), None, "de") == \
        mod.Cell("−1", "kW", "")


@pytest.mark.parametrize("lang,text", [("de", "n. v."), ("en", "n/a")])
def test_overflow_float_is_not_a_number(mod, lang, text):
    assert mod.format_state(st("1e400"), None, lang) == mod.Cell(text, None, "warn")


# --- fetch ---

NOW = datetime(2026, 11, 14, 14, 5, tzinfo=ZoneInfo("Europe/Berlin"))


def ctx(lang="de"):
    return PageContext(NOW, lang, "Europe/Berlin")


def ent(entity_id, state, **attrs):
    return {"entity_id": entity_id, "state": state, "attributes": attrs}


@pytest.fixture
def serve(monkeypatch):
    def install(responses):
        calls = []

        def fake(url, *, params=None, headers=None, timeout=10):
            calls.append((url, headers))
            r = responses[url]
            if isinstance(r, Exception):
                raise r
            if isinstance(r, int):
                resp = requests.Response()
                resp.status_code = r
                raise requests.HTTPError(response=resp)
            return r

        monkeypatch.setattr(glancebox.http, "get_json", fake)
        return calls
    return install


BASE = "http://homeassistant.lan:8123/api/states/"
TWO = {**OPTIONS, "entities": ["sensor.a", "sensor.b"]}


def two_ok():
    return {BASE + "sensor.a": ent("sensor.a", "21.4", unit_of_measurement="°C",
                                   friendly_name="Wohnzimmer"),
            BASE + "sensor.b": ent("sensor.b", "off", friendly_name="Fenster",
                                   device_class="window")}


def test_ok_tiles(ha, serve):
    serve(two_ok())
    data = ha.fetch(TWO, ctx())
    assert data["state"] == "ok" and data["layout"] == "tiles"
    assert data["title"] == "Home Assistant" and data["clock"] == "14:05"
    assert [i["label"] for i in data["items"]] == ["Wohnzimmer", "Fenster"]
    assert data["items"][0] == {"label": "Wohnzimmer", "value": "21,4", "unit": "°C",
                                "tone": "", "size": "l"}


def test_twelve_hour_clock(ha, serve):
    serve(two_ok())
    data = ha.fetch(TWO, replace(ctx(), time_format="12h"))
    assert data["state"] == "ok" and data["clock"] == "2:05 PM"


def test_label_option_wins(ha, serve):
    serve({BASE + "sensor.a": ent("sensor.a", "1", friendly_name="FN")})
    opts = {**OPTIONS, "entities": [{"entity": "sensor.a", "label": "Mine"}]}
    assert ha.fetch(opts, ctx())["items"][0]["label"] == "Mine"


@pytest.mark.parametrize("body", [{"entity_id": "sensor.a", "state": "1"},
                                  {"entity_id": "sensor.a", "state": "1", "attributes": {}}])
def test_label_falls_back_to_entity_id(ha, serve, body):
    serve({BASE + "sensor.a": body})
    item = ha.fetch(OPTIONS, ctx())["items"][0]
    assert item["label"] == "sensor.a" and item["unit"] is None


def test_auth_header_and_urls(ha, serve):
    calls = serve(two_ok())
    ha.fetch(TWO, ctx())
    assert calls[0] == (BASE + "sensor.a", {"Authorization": "Bearer t0ken"})
    assert [c[0] for c in calls] == [BASE + "sensor.a", BASE + "sensor.b"]


def test_url_trailing_slash(ha, serve):
    calls = serve(two_ok())
    ha.fetch({**TWO, "url": "http://homeassistant.lan:8123/"}, ctx())
    assert calls[0][0] == BASE + "sensor.a"


@pytest.mark.parametrize("lang,word", [("de", "fehlt"), ("en", "missing")])
def test_missing_entity_404_keeps_others(ha, serve, lang, word):
    responses = two_ok()
    responses[BASE + "sensor.a"] = 404
    serve(responses)
    data = ha.fetch(TWO, ctx(lang))
    assert data["state"] == "ok"
    assert data["items"][0]["label"] == "sensor.a"
    assert data["items"][0]["value"] == word and data["items"][0]["tone"] == "warn"
    assert data["items"][1]["label"] == "Fenster"


def test_missing_entity_uses_configured_label(ha, serve):
    serve({BASE + "sensor.a": 404})
    for label, expected in (("Mine", "Mine"), ("", "sensor.a")):
        opts = {**OPTIONS, "entities": [{"entity": "sensor.a", "label": label}]}
        assert ha.fetch(opts, ctx())["items"][0]["label"] == expected


@pytest.mark.parametrize("code", [401, 403])
@pytest.mark.parametrize("lang,msg,sub", [
    ("de", "Token abgelehnt", "Long-Lived Access Token prüfen"),
    ("en", "Token rejected", "Check the long-lived access token")])
def test_token_rejected(ha, serve, code, lang, msg, sub):
    serve({BASE + "sensor.a": code})
    data = ha.fetch(OPTIONS, ctx(lang))
    assert (data["state"], data["message"], data["sub"], data["items"]) == ("token", msg, sub, [])


@pytest.mark.parametrize("exc", [requests.ConnectionError("x"), requests.Timeout("x"), 500,
                                 ValueError("bad json")])
def test_unreachable(ha, serve, exc):
    serve({BASE + "sensor.a": exc})
    data = ha.fetch(OPTIONS, ctx())
    assert data["state"] == "error" and data["items"] == []
    assert data["message"] == "Keine Verbindung zu Home Assistant"
    assert data["sub"] == "Stand 14:05"
    en = ha.fetch(OPTIONS, ctx("en"))
    assert (en["message"], en["sub"]) == ("Cannot reach Home Assistant", "As of 14:05")


def test_twelve_hour_error_subtitle(ha, serve):
    serve({BASE + "sensor.a": requests.ConnectionError("x")})
    data = ha.fetch(OPTIONS, replace(ctx(), time_format="12h"))
    assert data["state"] == "error" and data["sub"] == "Stand 2:05 PM"
    en = ha.fetch(OPTIONS, replace(ctx("en"), time_format="12h"))
    assert en["sub"] == "As of 2:05 PM"


def _timed(monkeypatch, mod, responses, step):
    """Fake get_json that records timeouts; the fake clock advances `step` s per call."""
    from types import SimpleNamespace
    clock = [0.0]
    timeouts = []

    def fake(url, *, params=None, headers=None, timeout=10):
        timeouts.append(timeout)
        clock[0] += step
        return responses[url]

    monkeypatch.setattr(mod, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    monkeypatch.setattr(glancebox.http, "get_json", fake)
    return timeouts


SIX = {**OPTIONS, "entities": [f"sensor.s{n}" for n in range(6)]}


def test_calls_have_short_timeouts(ha, mod, monkeypatch):
    responses = {BASE + f"sensor.s{n}": ent(f"sensor.s{n}", "1") for n in range(6)}
    timeouts = _timed(monkeypatch, mod, responses, step=1.0)
    assert ha.fetch(SIX, ctx())["state"] == "ok"
    assert len(timeouts) == 6 and all(0 < t <= 5 for t in timeouts)


def test_exhausted_budget_is_error(ha, mod, monkeypatch):
    responses = {BASE + f"sensor.s{n}": ent(f"sensor.s{n}", "1") for n in range(6)}
    timeouts = _timed(monkeypatch, mod, responses, step=5.0)  # 3 calls use the 15 s budget
    data = ha.fetch(SIX, ctx())
    assert data["state"] == "error" and data["items"] == []
    assert data["message"] == "Keine Verbindung zu Home Assistant"
    assert len(timeouts) == 3 and all(t <= 5 for t in timeouts)


def test_error_on_second_entity_drops_first(ha, serve):
    responses = two_ok()
    responses[BASE + "sensor.b"] = requests.ConnectionError("x")
    serve(responses)
    data = ha.fetch(TWO, ctx())
    assert data["state"] == "error" and data["items"] == []


def test_token_never_logged_via_leaky_exception(ha, monkeypatch, caplog):
    """A library error quoting the Authorization header (like InvalidHeader) must not be logged."""
    def leaky(url, *, params=None, headers=None, timeout=10):
        raise requests.exceptions.InvalidHeader(f"Invalid return character in {headers}")

    monkeypatch.setattr(glancebox.http, "get_json", leaky)
    with caplog.at_level(logging.DEBUG):
        data = ha.fetch(OPTIONS, ctx())
    assert data["state"] == "error"
    assert "t0ken" not in caplog.text and "Bearer" not in caplog.text


def test_token_never_logged_real_header_validation(ha, caplog):
    """Bypass validate: real requests header validation rejects the CR in the token."""
    with caplog.at_level(logging.DEBUG):
        data = ha.fetch({**OPTIONS, "token": "t0ken\r"}, ctx())
    assert data["state"] == "error"
    assert "t0ken" not in caplog.text


@pytest.mark.parametrize("exc", [requests.ConnectionError("x"), 401])
def test_token_never_logged(ha, serve, caplog, exc):
    serve({BASE + "sensor.a": exc})
    with caplog.at_level(logging.DEBUG):
        ha.fetch(OPTIONS, ctx())
    assert "t0ken" not in caplog.text


@pytest.mark.parametrize("body", [[], None, "text", 5])
def test_non_dict_response_is_error(ha, serve, body):
    serve({BASE + "sensor.a": body})
    data = ha.fetch(OPTIONS, ctx())
    assert data["state"] == "error" and data["items"] == []


def test_layout_default_and_option(ha, serve):
    five = [f"sensor.s{i}" for i in range(5)]
    serve({BASE + e: ent(e, "1") for e in five} | two_ok())
    assert ha.fetch({**OPTIONS, "entities": five}, ctx())["layout"] == "list"
    assert ha.fetch({**TWO, "layout": "list"}, ctx())["layout"] == "list"


def test_lang_from_ctx(ha, serve):
    serve({BASE + "sensor.a": 500})
    assert ha.fetch(OPTIONS, ctx("en"))["message"] == "Cannot reach Home Assistant"


def _cfg():
    return AppConfig(interval=30, timezone="Europe/Berlin", lang="de",
                     pages=(), pages_dirs=(PAGES_DIR,))


def _states(*specs):
    """specs: (entity_id, state, attrs) | HTTP status | exception -> (entity ids, responses)."""
    ids = [f"sensor.s{n}" if isinstance(v, (int, Exception)) else v[0]
           for n, v in enumerate(specs)]
    return ids, {BASE + i: (v if isinstance(v, (int, Exception)) else ent(v[0], v[1], **v[2]))
                 for i, v in zip(ids, specs, strict=True)}


def _has(img, box, test):
    crop = img.crop(box).convert("RGB")
    px = crop.load()
    return any(test(*px[x, y]) for y in range(crop.height) for x in range(crop.width))


def yellow(r, g, b):
    return r > 200 and g > 205 and b < 80


def orange(r, g, b):
    return r > 200 and 100 < g < 200 and b < 100


def tile_box(layout, count, k):
    """Pixel box of cell k (tiles grid starts at y=34, list rows are 34 px)."""
    if layout == "list":
        return (0, 34 + 34 * k, 240, 68 + 34 * k)
    if count == 3 and k == 0:
        return (0, 34, 240, 137)
    if count == 3:
        return ((k - 1) * 120, 137, (k - 1) * 120 + 120, 240)
    if count == 4:
        return ((k % 2) * 120, 34 + (k // 2) * 103, (k % 2) * 120 + 120, 34 + (k // 2) * 103 + 103)
    h = 206 // count
    return (0, 34 + k * h, 240, 34 + (k + 1) * h)


@pytest.mark.browser
async def test_template_renders_all_layouts(ha, serve):
    temp = ("sensor.temp", "21.4", {"friendly_name": "Wohnzimmer", "unit_of_measurement": "°C"})
    big = ("sensor.grid", "-10.4", {"friendly_name": "Netzbezug", "unit_of_measurement": "kW"})
    huge = ("sensor.energy", "-10234.5",
            {"friendly_name": "Zähler", "unit_of_measurement": "kWh"})
    win = ("binary_sensor.fenster", "on", {"friendly_name": "Fenster", "device_class": "window"})
    lamp = ("light.kueche", "on", {"friendly_name": "Licht"})
    longname = ("sensor.long", "21.4", {
        "friendly_name": "Wohnzimmer Fensterkontakt links oben", "unit_of_measurement": "°C"})
    nope = ("sensor.nope", "unavailable", {"friendly_name": "Tür"})
    scenarios = {
        "tiles1": ("tiles", [temp]),
        "tiles2": ("tiles", [temp, win]),
        "tiles3": ("tiles", [temp, big, lamp]),
        "tiles4": ("tiles", [big, temp, win, lamp]),
        "tiles4_huge": ("tiles", [huge, temp, win, lamp]),
        "tiles4_long": ("tiles", [longname, temp, win, lamp]),
        "list6": ("list", [temp, big, win, lamp, temp, big]),
        "list_long": ("list", [longname, win, lamp]),
        "list_missing": ("list", [temp, 404, nope]),
        "error": ("tiles", [requests.ConnectionError("x")]),
        "token": ("tiles", [401]),
    }
    frames = {}
    # Set HA_SHOT_DIR to a directory to also write each rendered frame there as <scenario>.png.
    shots = os.environ.get("HA_SHOT_DIR")
    async with Renderer() as r:
        for name, (layout, specs) in scenarios.items():
            ids, responses = _states(*specs)
            serve(responses)
            options = {**OPTIONS, "entities": ids, "layout": layout}
            page = PageConfig(index=0, type="homeassistant", options=options,
                              duration=30, refresh=30)
            out = await render_page(page, ha, _cfg(), r, NOW.timestamp())
            if shots:
                Path(shots, f"{name}.png").write_bytes(out)
            img = Image.open(io.BytesIO(out)).convert("RGB")
            assert img.size == (240, 240), name
            hdr = img.getpixel((120, 4))
            assert hdr[2] > hdr[0], name
            assert img.convert("L").getextrema()[1] > 150, name
            frames[name] = img
    for name in ("error", "token"):
        assert _has(frames[name], (0, 100, 240, 140), lambda r, g, b: r > 200 and b < 100), name
    # tones: light "an" is yellow, window "offen" orange, fehlt / n. v. orange
    for name, layout, count, win_k, lamp_k in [
            ("tiles2", "tiles", 2, 1, None), ("tiles3", "tiles", 3, None, 2),
            ("tiles4", "tiles", 4, 2, 3), ("list6", "list", 6, 2, 3)]:
        if lamp_k is not None:
            assert _has(frames[name], tile_box(layout, count, lamp_k), yellow), name
        if win_k is not None:
            assert _has(frames[name], tile_box(layout, count, win_k), orange), name
            assert not _has(frames[name], tile_box(layout, count, win_k), yellow), name
    for k in (1, 2):
        assert _has(frames["list_missing"], tile_box("list", 3, k), orange), k
    assert not _has(frames["list_missing"], tile_box("list", 3, 0), orange)
    # long labels are ellipsised, the value stays readable at the right edge
    assert _has(frames["tiles4_long"], (0, 34, 120, 137), lambda r, g, b: r > 200 and g > 200)
    assert _has(frames["list_long"], (170, 35, 240, 67), lambda r, g, b: r > 200 and g > 200)
    assert not _has(frames["list_long"], (232, 35, 240, 67), lambda r, g, b: g > 120)
    # "-10,4 kW" and "-10234,5 kWh" stay inside their tile (stripe between the columns is free)
    for name in ("tiles4", "tiles4_huge"):
        strip = frames[name].crop((116, 40, 125, 110)).convert("L")
        assert strip.getextrema()[1] < 120, name


@pytest.mark.browser
async def test_long_text_state_is_ellipsised(ha, serve):
    """A long text state (input_select) never runs out of its tile or row."""
    mode = ("input_select.modus", "Abwesend lange Urlaubsreise Modus", {"friendly_name": "Modus"})
    temp = ("sensor.temp", "21.4", {"friendly_name": "Wohnzimmer", "unit_of_measurement": "°C"})
    lamp = ("light.kueche", "on", {"friendly_name": "Licht"})
    bright = lambda r, g, b: r > 200 and g > 200 and b > 200
    frames = {}
    async with Renderer() as r:
        for name, layout, specs in [("tiles4", "tiles", [mode, temp, lamp, temp]),
                                    ("list", "list", [mode, temp, lamp])]:
            ids, responses = _states(*specs)
            serve(responses)
            options = {**OPTIONS, "entities": ids, "layout": layout}
            page = PageConfig(index=0, type="homeassistant", options=options,
                              duration=30, refresh=30)
            out = await render_page(page, ha, _cfg(), r, NOW.timestamp())
            frames[name] = Image.open(io.BytesIO(out)).convert("RGB")
    # tiles: the value is shortened inside its tile. The content box ends at x 118 (120 px tile,
    # 2 px right padding); where exactly the "…" ends depends on the font rasteriser, so only
    # the padding, the divider and the neighbour tile's left padding (x 118-128) must stay dark.
    assert _has(frames["tiles4"], (0, 34, 118, 137), bright)
    assert not _has(frames["tiles4"], (118, 34, 128, 137), bright)
    # list: the label stays visible and nothing reaches the right edge
    assert _has(frames["list"], (8, 35, 60, 67), bright)
    assert not _has(frames["list"], (236, 35, 240, 67), bright)


@pytest.mark.browser
async def test_common_values_fit_without_ellipsis(ha, mod, serve):
    """Values like "detected", "100 %", "100,0 %", "−10,4 kW" fit their cell in every layout."""
    from playwright.async_api import async_playwright

    from glancebox.frames import _jinja_env

    motion = ("binary_sensor.flur", "on", {"friendly_name": "Hall", "device_class": "motion"})
    door = ("binary_sensor.door", "off", {"friendly_name": "Door", "device_class": "door"})
    full = ("sensor.akku", "100", {"friendly_name": "Battery", "unit_of_measurement": "%"})
    full1 = ("sensor.akku1", "100.0", {"friendly_name": "Battery", "unit_of_measurement": "%"})
    grid = ("sensor.grid", "-10.4", {"friendly_name": "Grid", "unit_of_measurement": "kW"})
    pv = ("sensor.pv", "3200", {"friendly_name": "PV", "unit_of_measurement": "W"})
    word = ("input_select.modus", "Abwesend", {"friendly_name": "Mode"})
    cases = [
        ("tiles", [grid, motion, pv, full]), ("tiles", [word, motion, door, full1]),
        ("tiles", [motion, full1, word]), ("tiles", [motion, word]), ("tiles", [word]),
        ("list", [motion, door, full, full1, grid, word]),
    ]
    env = _jinja_env([PAGES_DIR / "homeassistant"])
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 240, "height": 240})
        for lang in ("en", "de"):
            for layout, specs in cases:
                ids, responses = _states(*specs)
                serve(responses)
                options = {**OPTIONS, "entities": ids, "layout": layout, "lang": lang}
                data = ha.fetch(options, ctx(lang))
                await page.set_content(env.get_template("template.html").render(**data))
                cut = await page.evaluate(
                    "[...document.querySelectorAll('.val,.v')]"
                    ".filter(e => e.scrollWidth > e.clientWidth).map(e => e.textContent)")
                assert cut == [], (lang, layout, [i["value"] for i in data["items"]])
        await browser.close()


def test_failure_log_redacts_url_credentials(ha, serve, caplog):
    base = "http://user:pw@homeassistant.lan:8123/api/states/"
    serve({base + "sensor.a": requests.ConnectionError(f"cannot reach {base}sensor.a?x=1")})
    with caplog.at_level(logging.DEBUG):
        ha.fetch({**OPTIONS, "url": "http://user:pw@homeassistant.lan:8123"}, ctx())
    assert "http://***@homeassistant.lan:8123/api/states/sensor.a" in caplog.text
    assert "pw" not in caplog.text and "x=1" not in caplog.text
