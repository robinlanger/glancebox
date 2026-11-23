import logging
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
import requests

import glancebox.anim
import glancebox.http
from glancebox.anim import Anim, Track
from glancebox.config import AppConfig, ConfigError, PageConfig
from glancebox.pages import PageContext, load_page_types, validate_config
from glancebox.render import text_width

PAGES_DIR = Path(__file__).resolve().parents[1]
OPTIONS = {"url": "http://homeassistant.lan:8123", "token": "t0ken",
           "rows": [{"type": "grid", "entity": "sensor.grid_power"}]}
BASE = "http://homeassistant.lan:8123/api/states/"
NOW = datetime(2026, 11, 23, 14, 5, tzinfo=ZoneInfo("Europe/Berlin"))


@pytest.fixture
def energy():
    return load_page_types([PAGES_DIR])["energy"]


@pytest.fixture
def mod(energy):
    return sys.modules["glancebox_pages.energy"]


def ctx(lang="de"):
    return PageContext(NOW, lang, "Europe/Berlin")


def ent(entity_id, state, unit="W"):
    attrs = {"unit_of_measurement": unit} if unit else {}
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


# --- flow rule ---------------------------------------------------------------

def row(mod, kind="grid", **kw):
    base = {"type": kind, "entity": "sensor.x", **kw}
    return mod.rows({"rows": [base]})[0]


def st(state, unit="W"):
    return {"entity_id": "sensor.x", "state": state,
            "attributes": {"unit_of_measurement": unit}}


@pytest.mark.parametrize(("kind", "state", "kw", "expect"), [
    ("grid", "2310", {}, ("2,3", "kW", True, "r", "#ffb020", "Bezug", 42)),
    ("grid", "-1100", {}, ("1,1", "kW", True, "l", "#34d399", "Einspeisung", 25)),
    ("grid", "1100", {"invert": True}, ("1,1", "kW", True, "l", "#34d399", "Einspeisung", 25)),
    ("grid", "15", {"min": 20}, ("0", "W", False, None, "#6b7280", "", 0)),
    ("grid", "9000", {"full": 3000}, ("9", "kW", True, "r", "#ffb020", "Bezug", 80)),
    ("pv", "3200", {}, ("3,2", "kW", True, "r", "#ffd040", "Erzeugung", 55)),
    ("pv", "-50", {}, ("0", "W", False, None, "#6b7280", "", 0)),
    ("wallbox", "11000", {}, ("11", "kW", True, "l", "#a78bfa", "lädt", 80)),
    ("wallbox", "-300", {}, ("0", "W", False, None, "#6b7280", "", 0)),
])
def test_flow_rule_de(mod, kind, state, kw, expect):
    assert mod.flow(row(mod, kind, **kw), st(state), None, "de") == mod.Flow(*expect)


def test_flow_gas_and_water_use_the_sensor_unit(mod):
    gas = mod.flow(row(mod, "gas"), st("1.0", "m³/h"), None, "en")
    assert gas == mod.Flow("1", "m³/h", True, "r", "#ff6b4a", "Usage", 45)
    water = mod.flow(row(mod, "water"), st("3", "L/min"), None, "de")
    assert (water.value, water.direction, water.status, water.speed) == ("3", "r", "Verbrauch", 24)


def test_flow_battery_with_level(mod):
    # Home Assistant convention: positive = discharging, negative = charging.
    soc = st("64.4", "%")
    b = row(mod, "battery", soc="sensor.level")
    assert mod.flow(b, st("-1500"), soc, "de")[3:] == ("l", "#2ec4b6", "lädt · 64 %", 45)
    assert mod.flow(b, st("1500"), soc, "en")[3:] == ("r", "#2ec4b6", "discharging · 64 %", 45)
    idle = mod.flow(b, st("0"), soc, "de")
    assert (idle.active, idle.status, idle.color) == (False, "64 %", "#6b7280")


def test_flow_battery_without_level_and_invert(mod):
    b = row(mod, "battery")
    assert mod.flow(b, st("1500"), None, "de")[3:] == ("r", "#2ec4b6", "entlädt", 45)
    inv = row(mod, "battery", invert=True)
    assert mod.flow(inv, st("1500"), None, "en")[3:] == ("l", "#2ec4b6", "charging", 45)
    assert mod.flow(b, st("0"), None, "de").status == ""


def test_flow_power_in_kilowatts(mod):                      # Review Focus 1
    f = mod.flow(row(mod, "grid"), st("2.31", "kW"), None, "de")
    assert (f.value, f.unit, f.speed) == ("2,3", "kW", 42)
    assert mod.flow(row(mod, "grid"), st("2310.000001"), None, "de").value == "2,3"


def test_flow_tiny_negative_is_zero(mod):                   # Review Focus 3
    for state in ("-0.04", "-0.0", "0.04"):
        f = mod.flow(row(mod, "grid"), st(state), None, "de")
        assert (f.value, f.active, f.direction, f.speed) == ("0", False, None, 0)


@pytest.mark.parametrize(("lang", "na", "missing"), [("de", "n. v.", "fehlt"),
                                                     ("en", "n/a", "missing")])
def test_flow_unavailable_and_missing(mod, lang, na, missing):
    for state in ("unavailable", "unknown", "nan", "text"):
        f = mod.flow(row(mod), st(state), None, lang)
        assert (f.value, f.unit, f.active) == (na, None, False)
    assert mod.flow(row(mod), None, None, lang).value == missing


def test_geometry(mod):
    assert [b.cy for b in mod.geometry(1)] == [140]
    assert [b.cy for b in mod.geometry(2)] == [90, 189]
    assert [b.cy for b in mod.geometry(4)] == [65, 115, 164, 214]
    assert mod.geometry(3) == [mod.Box(74, 64, 67, 85, 15, 73), mod.Box(140, 64, 133, 85, 15, 139),
                               mod.Box(206, 64, 199, 85, 15, 205)]


# --- validate ----------------------------------------------------------------

def _opts(**kw):
    return {**OPTIONS, **kw}


def _without(key):
    return {k: v for k, v in OPTIONS.items() if k != key}


def _row(**kw):
    return _opts(rows=[{"type": "grid", "entity": "sensor.grid_power", **kw}])


def test_validate_ok(energy):
    energy.validate(OPTIONS)
    energy.validate(_opts(title="Strom", lang="en", animate=False, rows=[
        {"type": "grid", "entity": "sensor.grid_power", "invert": True, "full": 2.5, "min": 0},
        {"type": "pv", "entity": "sensor.pv_1"},
        {"type": "pv", "entity": "sensor.pv_2"},
        {"type": "battery", "entity": "sensor.battery_power", "soc": "sensor.battery_level"}]))
    energy.validate(_opts(rows=[{"type": "gas", "entity": "sensor.gas_flow"},
                                {"type": "water", "entity": "sensor.water_flow"},
                                {"type": "wallbox", "entity": "sensor.wallbox_power"}]))


@pytest.mark.parametrize(("options", "match"), [
    (_without("rows"), "rows"),
    (_opts(rows=[]), "rows"),
    (_opts(rows=[{"type": "pv", "entity": f"sensor.p{i}"} for i in range(5)]), "at most 4"),
    (_opts(rows=["sensor.a"]), "mapping"),
    (_opts(rows=[{"type": "heatpump", "entity": "sensor.a"}]), "type"),
    (_opts(rows=[{"type": "grid"}]), "entity"),
    (_row(entity="Sensor.A"), "entity id"),
    (_row(soc="sensor.level"), "soc"),
    (_opts(rows=[{"type": "battery", "entity": "sensor.b", "soc": "x"}]), "entity id"),
    (_row(invert="yes"), "invert"),
    (_row(full=0), "full"),
    (_row(full=True), "full"),
    (_row(min=-1), "min"),
    (_row(inverted=True), "inverted"),
    (_opts(rows=[{"typ": "grid", "entity": "sensor.a"}]), "unknown key 'typ'"),
    (_opts(animate="false"), "animate"),
    (_without("url"), "url"),
    (_opts(url="ftp://x"), "http"),
    (_without("token"), "token"),
    (_opts(token="ab\ncd"), "token"),
    (_opts(lang="fr"), "lang"),
    (_opts(title=3), "title"),
])
def test_validate_rejects(energy, options, match):
    with pytest.raises(ValueError, match=match):
        energy.validate(options)


def _cfg(extra):
    page = PageConfig(0, "energy", OPTIONS, 30, extra.get("refresh", 30), "refresh" in extra)
    return AppConfig(30, "Europe/Berlin", "de", (page,), (PAGES_DIR,))


def test_refresh_default_and_floor(energy):
    types = {"energy": energy}
    assert validate_config(_cfg({}), types).pages[0].refresh == 5
    assert validate_config(_cfg({"refresh": 2}), types).pages[0].refresh == 2
    with pytest.raises(ConfigError, match="at least 2"):
        validate_config(_cfg({"refresh": 1}), types)


# --- build -------------------------------------------------------------------

THREE = _opts(rows=[{"type": "grid", "entity": "sensor.grid_power"},
                    {"type": "pv", "entity": "sensor.pv_power"},
                    {"type": "battery", "entity": "sensor.battery_power",
                     "soc": "sensor.battery_level"}])


def three_states(grid="-1100", pv="3200", battery="0"):
    return {"sensor.grid_power": ent("sensor.grid_power", grid),
            "sensor.pv_power": ent("sensor.pv_power", pv),
            "sensor.battery_power": ent("sensor.battery_power", battery),
            "sensor.battery_level": ent("sensor.battery_level", "64", "%")}


def test_build_ok_three_rows(mod):
    data = mod.build(THREE, three_states(), "de", "14:05")
    assert (data["state"], data["title"], data["clock"], data["lang"]) == \
        ("ok", "Energie", "14:05", "de")
    assert (data["bg"], data["track"]) == ("#0b0d12", "#232a38")
    assert data["message"] is None and data["sub"] is None
    boxes = mod.geometry(3)
    for r, b in zip(data["rows"], boxes, strict=True):
        assert (r["cy"], r["x"], r["y"], r["w"], r["h"], r["line_y"]) == tuple(b)
    assert [r["kind"] for r in data["rows"]] == ["grid", "pv", "battery"]
    assert data["rows"][0] == {"kind": "grid", "cy": 74, "x": 64, "y": 67, "w": 85, "h": 15,
                               "line_y": 73, "value": "1,1", "unit": "kW", "size": "l",
                               "status": "Einspeisung", "color": "#34d399", "active": True}
    assert (data["rows"][2]["status"], data["rows"][2]["active"]) == ("64 %", False)
    assert data["_anim"] == Anim("0b0d12", "232a38", (
        Track(64, 67, 85, 15, "l", "34d399", 25), Track(64, 133, 85, 15, "r", "ffd040", 55)))
    glancebox.anim.encode(data["_anim"])


def test_build_title_option_and_en(mod):
    assert mod.build(THREE, three_states(), "en", "14:05")["title"] == "Energy"
    assert mod.build({**THREE, "title": "Strom"}, three_states(), "en", "x")["title"] == "Strom"


def test_no_anim_when_nothing_flows_or_animate_false(mod):
    idle = mod.build(THREE, three_states("0", "0", "0"), "de", "14:05")
    assert "_anim" not in idle and idle["state"] == "ok"
    with_anim = mod.build(THREE, three_states(), "de", "14:05")
    still = mod.build({**THREE, "animate": False}, three_states(), "de", "14:05")
    assert "_anim" not in still
    assert still == {k: v for k, v in with_anim.items() if k != "_anim"}


def test_same_states_give_equal_data(mod):
    a = mod.build(OPTIONS, {"sensor.grid_power": ent("sensor.grid_power", "2310")}, "de", "14:05")
    b = mod.build(OPTIONS, {"sensor.grid_power": ent("sensor.grid_power", "2330")}, "de", "14:05")
    anim_a, anim_b = a.pop("_anim"), b.pop("_anim")
    assert a == b
    assert (anim_a.tracks[0].speed, anim_b.tracks[0].speed) == (42, 43)


def test_four_rows_encode(mod):
    opts = _opts(rows=[{"type": "grid", "entity": "sensor.a"}, {"type": "pv", "entity": "sensor.b"},
                       {"type": "battery", "entity": "sensor.c"},
                       {"type": "wallbox", "entity": "sensor.d"}])
    states = {e: ent(e, "-11000" if e == "sensor.a" else "11000")
              for e in ("sensor.a", "sensor.b", "sensor.c", "sensor.d")}
    data = mod.build(opts, states, "de", "14:05")
    assert len(data["_anim"].tracks) == 4
    assert len(glancebox.anim.encode(data["_anim"])) <= glancebox.anim.MAX_VALUE_LEN


# --- fetch -------------------------------------------------------------------

def three_responses(**kw):
    return {BASE + k: v for k, v in three_states(**kw).items()}


@pytest.mark.parametrize("soc", [404, ent("sensor.battery_level", "unavailable", None)])
def test_soc_missing_or_unavailable_keeps_row(energy, serve, soc):
    responses = three_responses(battery="-1500")
    responses[BASE + "sensor.battery_level"] = soc
    serve(responses)
    data = energy.fetch(THREE, ctx())
    assert data["state"] == "ok"
    assert data["rows"][2]["status"] == "lädt" and data["rows"][2]["active"]
    assert len(data["_anim"].tracks) == 3


def test_fetch_ok_calls_each_entity(energy, serve):
    calls = serve(three_responses())
    data = energy.fetch(THREE, ctx())
    assert data["state"] == "ok" and data["clock"] == "14:05"
    assert [c[0] for c in calls] == [BASE + e for e in (
        "sensor.grid_power", "sensor.pv_power", "sensor.battery_power", "sensor.battery_level")]
    assert calls[0][1] == {"Authorization": "Bearer t0ken"}


@pytest.mark.parametrize(("lang", "word"), [("de", "fehlt"), ("en", "missing")])
def test_missing_entity_keeps_others(energy, serve, lang, word):
    responses = three_responses()
    responses[BASE + "sensor.grid_power"] = 404
    serve(responses)
    data = energy.fetch(THREE, ctx(lang))
    assert data["state"] == "ok"
    assert (data["rows"][0]["value"], data["rows"][0]["active"]) == (word, False)
    assert data["rows"][1]["active"]
    assert [t.color for t in data["_anim"].tracks] == ["ffd040"]


@pytest.mark.parametrize("code", [401, 403])
@pytest.mark.parametrize(("lang", "msg", "sub"), [
    ("de", "Token abgelehnt", "Long-Lived Access Token prüfen"),
    ("en", "Token rejected", "Check the long-lived access token")])
def test_token_rejected(energy, serve, code, lang, msg, sub):
    serve({BASE + "sensor.grid_power": code})
    data = energy.fetch(OPTIONS, ctx(lang))
    assert (data["state"], data["message"], data["sub"], data["rows"]) == ("token", msg, sub, [])
    assert "_anim" not in data


@pytest.mark.parametrize("exc", [requests.ConnectionError("x"), requests.Timeout("x"), 500, []])
def test_unreachable(energy, serve, exc):
    serve({BASE + "sensor.grid_power": exc})
    data = energy.fetch(OPTIONS, ctx())
    assert data["state"] == "error" and data["rows"] == [] and "_anim" not in data
    assert (data["message"], data["sub"]) == ("Keine Verbindung zu Home Assistant", "Stand 14:05")
    en = energy.fetch(OPTIONS, ctx("en"))
    assert (en["message"], en["sub"]) == ("Cannot reach Home Assistant", "As of 14:05")


def test_error_on_later_entity_drops_all(energy, serve):
    responses = three_responses()
    responses[BASE + "sensor.battery_level"] = requests.ConnectionError("x")
    serve(responses)
    data = energy.fetch(THREE, ctx())
    assert data["state"] == "error" and data["rows"] == [] and "_anim" not in data


FOUR = _opts(rows=[{"type": "grid", "entity": "sensor.s0"}, {"type": "pv", "entity": "sensor.s1"},
                   {"type": "wallbox", "entity": "sensor.s2"},
                   {"type": "battery", "entity": "sensor.s3", "soc": "sensor.s4"}])
FIVE = {BASE + f"sensor.s{n}": ent(f"sensor.s{n}", "100") for n in range(5)}


def _timed(monkeypatch, mod, responses, step):
    """Fake get_json that records timeouts; the fake clock advances `step` s per call."""
    clock = [0.0]
    timeouts = []

    def fake(url, *, params=None, headers=None, timeout=10):
        timeouts.append(timeout)
        clock[0] += step
        return responses[url]

    monkeypatch.setattr(mod, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    monkeypatch.setattr(glancebox.http, "get_json", fake)
    return timeouts


def test_calls_have_short_timeouts(energy, mod, monkeypatch):
    timeouts = _timed(monkeypatch, mod, FIVE, step=1.0)
    assert energy.fetch(FOUR, ctx())["state"] == "ok"
    assert len(timeouts) == 5 and all(0 < t <= 5 for t in timeouts)


def test_exhausted_budget_is_error(energy, mod, monkeypatch):
    timeouts = _timed(monkeypatch, mod, FIVE, step=5.0)  # 3 calls use the 15 s budget
    data = energy.fetch(FOUR, ctx())
    assert data["state"] == "error" and data["rows"] == [] and "_anim" not in data
    assert len(timeouts) == 3 and all(t <= 5 for t in timeouts)


@pytest.mark.parametrize("exc", [requests.ConnectionError("x"), 401,
                                 requests.exceptions.InvalidHeader("Bearer t0ken")])
def test_token_never_logged(energy, serve, caplog, exc):
    serve({BASE + "sensor.grid_power": exc})
    with caplog.at_level(logging.DEBUG):
        data = energy.fetch(OPTIONS, ctx())
    assert data["state"] in ("error", "token")
    assert "t0ken" not in caplog.text and "Bearer" not in caplog.text


@pytest.mark.parametrize(("value", "unit"), [("2,3", "kW"), ("11", "kW"), ("n. v.", None),
                                             ("1234,5", "m³/h")])
def test_value_size_keeps_the_value_out_of_the_track(mod, value, unit):
    size = mod.size_class(value, unit)
    assert size in mod.SIZES
    assert (text_width(value, unit, mod.SIZES[size]) <= mod.VALUE_RIGHT - mod.VALUE_LEFT - 1
            or size == "s")


def test_common_values_get_the_large_size(mod):
    assert mod.size_class("2,3", "kW") == "l"
