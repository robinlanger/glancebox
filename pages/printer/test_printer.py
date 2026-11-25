"""Tests of the printer page: validation, state rules (finished_for) and display data."""

import io
import logging
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from PIL import Image
from printer_helpers import NOW, ctx

from glancebox.config import AppConfig, ConfigError, PageConfig
from glancebox.pages import validate_config

URL = "http://drucker.local:7125"
OPTS = {"source": "fake", "url": URL}
PRINTING = {"state": "printing", "progress": 47.6, "remaining_s": 4980,
            "filename": "benchy_0.2mm_PLA", "nozzle": (214.2, 215.0), "bed": (60.0, 60.0),
            "layer": (112, 240)}
KEY = ("fake", URL, None, None)


@pytest.fixture
def fake(mod, monkeypatch):
    """A fake source in PROVIDERS; set ``.result`` to a PrinterStatus or an exception."""
    provider = SimpleNamespace(NAME="Fake", KEYS=("api_key",), validated=[], calls=[],
                               result=None)
    provider.validate = provider.validated.append

    def fetch(options, _ctx):
        provider.calls.append(options)
        if isinstance(provider.result, Exception):
            raise provider.result
        return provider.result

    provider.fetch = fetch
    monkeypatch.setitem(mod.PROVIDERS, "fake", provider)
    return provider


def png(size=300):
    out = io.BytesIO()
    Image.new("RGB", (size, size), "orange").save(out, "PNG")
    return out.getvalue()


# --- build: job views -----------------------------------------------------------

def test_build_printing(mod, common):
    d = mod.build(common.PrinterStatus(**PRINTING), {}, "de", NOW)
    assert (d["view"], d["tone"], d["label"], d["alert"]) == ("job", "green", "Druckt", False)
    assert (d["big"], d["big_unit"], d["bar"]) == ("47", "%", 47)
    assert (d["main"], d["main_muted"]) == ("noch 1:23 h", False)
    assert d["lines"] == ["fertig 15:55", "Schicht 112/240"]
    assert d["temps"] == [
        {"kind": "nozzle", "actual": "214°", "target": "215", "label": "Düse", "on": True},
        {"kind": "bed", "actual": "60°", "target": "60", "label": "Bett", "on": True}]
    assert (d["title"], d["clock"], d["filename"], d["thumb"]) == (
        "Drucker", "14:32", "benchy_0.2mm_PLA", None)
    assert (d["lang"], d["message"], d["notice"]) == ("de", None, None)


def test_build_en(mod, common):
    d = mod.build(common.PrinterStatus(**PRINTING), {"title": "Voron"}, "en", NOW)
    assert (d["title"], d["label"], d["main"]) == ("Voron", "Printing", "1:23 h left")
    assert d["lines"] == ["done 15:55", "Layer 112/240"]
    assert [t["label"] for t in d["temps"]] == ["Nozzle", "Bed"]


def test_only_the_state_is_required(mod, common):            # anti-goal of the spec
    for state in common.STATES:
        d = mod.build(common.PrinterStatus(state), {}, "de", NOW)
        assert d["temps"] == [] and d["thumb"] is None and d["filename"] is None
    d = mod.build(common.PrinterStatus("printing"), {}, "de", NOW)
    assert (d["big"], d["bar"], d["main"], d["lines"]) == (None, None, None, [])


def test_eta_and_remaining_complete_each_other(mod, common):
    S = common.PrinterStatus
    d = mod.build(S("printing", remaining_s=4980), {}, "de", NOW)
    assert (d["main"], d["lines"]) == ("noch 1:23 h", ["fertig 15:55"])
    d = mod.build(S("printing", eta=NOW + timedelta(minutes=83)), {}, "de", NOW)
    assert (d["main"], d["lines"]) == ("noch 1:23 h", ["fertig 15:55"])
    monday = datetime(2026, 11, 30, 7, 40, tzinfo=NOW.tzinfo)
    d = mod.build(S("printing", eta=monday), {}, "de", NOW)
    assert d["lines"] == ["fertig Mo 07:40"]
    d = mod.build(S("printing", layer=(112, None)), {}, "de", NOW)
    assert d["lines"] == ["Schicht 112"]


def test_eta_in_the_past_and_negative_remaining_are_dropped(mod, common):
    S = common.PrinterStatus
    d = mod.build(S("printing", eta=NOW - timedelta(minutes=5)), {}, "de", NOW)
    assert (d["main"], d["lines"]) == (None, [])
    d = mod.build(S("printing", remaining_s=-300), {}, "de", NOW)
    assert (d["main"], d["lines"]) == (None, [])


def test_build_paused(mod, common):
    S = common.PrinterStatus
    d = mod.build(S("paused", progress=47, remaining_s=4980, layer=(112, 240),
                    state_since=NOW - timedelta(minutes=27), message="Eingriff nötig"),
                  {}, "de", NOW)
    assert (d["view"], d["tone"], d["label"]) == ("job", "orange", "Pausiert")
    assert (d["main"], d["main_muted"]) == ("noch 1:23 h", True)
    assert d["lines"] == ["seit 14:05", "Schicht 112/240"]
    assert d["message"] == "Eingriff nötig"
    d = mod.build(S("paused", layer=(112, 240)), {}, "en", NOW)
    assert (d["label"], d["lines"]) == ("Paused", ["Layer 112/240"])


def test_build_finished(mod, common):
    S = common.PrinterStatus
    d = mod.build(S("finished", progress=100, ended_at=NOW - timedelta(minutes=4),
                    duration_s=11520), {}, "de", NOW)
    assert (d["view"], d["label"], d["tone"]) == ("job", "Fertig", "green")
    assert (d["big"], d["big_unit"], d["main"]) == ("14:28", None, "Dauer 3:12 h")
    assert (d["lines"], d["bar"]) == (["vor 4 min"], 100)
    d = mod.build(S("finished", ended_at=NOW - timedelta(minutes=4)), {}, "en", NOW)
    assert (d["label"], d["main"], d["lines"], d["bar"]) == ("Finished", None, ["4 min ago"], 100)


def test_build_error(mod, common):
    S = common.PrinterStatus
    d = mod.build(S("error", progress=47, remaining_s=4980,
                    message="Heater extruder not heating at expected rate"), {}, "de", NOW)
    assert (d["alert"], d["tone"], d["label"], d["view"]) == (True, "red", "Fehler", "job")
    assert (d["big"], d["bar"]) == ("47", 47)
    assert d["message"] == "Heater extruder not heating at expected rate"
    assert (d["lines"], d["main"]) == ([], None)
    assert mod.build(S("error"), {}, "en", NOW)["message"] is None
    assert mod.build(S("error"), {}, "en", NOW)["label"] == "Error"


def test_build_idle(mod, common):
    S = common.PrinterStatus
    yesterday = datetime(2026, 11, 24, 21, 14, tzinfo=NOW.tzinfo)
    d = mod.build(S("idle", last_job=("benchy_0.2mm_PLA", yesterday), nozzle=(142.0, 215.0),
                    bed=(23.0, None)), {}, "de", NOW)
    assert (d["view"], d["big"], d["label"], d["alert"]) == ("idle", "Bereit", "", False)
    assert d["lines"] == ["Zuletzt: benchy_0.2mm_PLA", "fertig gestern 21:14"]
    assert d["temps"] == [
        {"kind": "nozzle", "actual": "142°", "target": "215", "label": "Düse heizt", "on": True},
        {"kind": "bed", "actual": "23°", "target": None, "label": "Bett", "on": False}]
    assert (d["bar"], d["main"], d["filename"]) == (None, None, None)
    d = mod.build(S("idle", last_job=("benchy_0.2mm_PLA", None)), {}, "en", NOW)
    assert (d["big"], d["lines"]) == ("Ready", ["Last: benchy_0.2mm_PLA"])
    assert mod.build(S("idle"), {}, "de", NOW)["lines"] == []
    assert mod.build(S("idle", message="busy_unknown"), {}, "de", NOW)["message"] == "busy_unknown"


def test_heating_needs_more_than_five_degrees_below_target(mod, common):
    d = mod.build(common.PrinterStatus("idle", nozzle=(210.0, 215.0), bed=(54.9, 60.0)),
                  {}, "en", NOW)
    assert [t["label"] for t in d["temps"]] == ["Nozzle", "Bed heating"]


def test_build_offline(mod, common):
    d = mod.build(common.PrinterStatus("offline"), {}, "de", NOW)
    assert (d["view"], d["alert"], d["label"], d["big"]) == ("notice", False, "", None)
    assert d["notice"] == {"message": "Drucker nicht erreichbar", "sub": None, "tone": "muted"}
    d = mod.build(common.PrinterStatus("offline", message="Klipper startet"), {}, "de", NOW)
    assert d["notice"]["sub"] == "Klipper startet"
    d = mod.build(common.PrinterStatus("offline"), {}, "en", NOW)
    assert d["notice"]["message"] == "Printer not reachable"


def test_thumbnail_option(mod, common):
    S = common.PrinterStatus
    thumb = common.Thumbnail(png(), "image/png")
    d = mod.build(S("printing", thumbnail=thumb), {}, "de", NOW)
    assert d["thumb"].startswith("data:image/png;base64,")
    assert mod.build(S("printing", thumbnail=thumb), {"thumbnail": False}, "de", NOW)["thumb"] \
        is None
    for state in ("idle", "offline"):
        assert mod.build(S(state, thumbnail=thumb), {}, "de", NOW)["thumb"] is None


def test_same_status_gives_equal_data(mod, common):
    status = common.PrinterStatus(**PRINTING)
    assert mod.build(status, {}, "de", NOW) == mod.build(status, {}, "de", NOW)
    a = mod.build(common.PrinterStatus(**{**PRINTING, "progress": 47.1}), {}, "de", NOW)
    b = mod.build(common.PrinterStatus(**{**PRINTING, "progress": 47.9}), {}, "de", NOW)
    assert a == b


# --- notice ----------------------------------------------------------------------

NOTICES = [
    ("fake", {}, "auth", None,
     ("Zugang abgelehnt", "API-Key prüfen"), ("Access denied", "Check the API key")),
    ("prusalink", {}, "auth", None,
     ("Zugang abgelehnt", "Passwort prüfen"), ("Access denied", "Check the password")),
    ("prusalink", {"api_key": "k"}, "auth", None,
     ("Zugang abgelehnt", "API-Key prüfen"), ("Access denied", "Check the API key")),
    ("hass", {}, "auth", None,
     ("Token abgelehnt", "Long-Lived Access Token prüfen"),
     ("Token rejected", "Check the long-lived access token")),
    ("hass", {}, "unreachable", None,
     ("Keine Verbindung zu Home Assistant", "Stand 14:32"),
     ("Cannot reach Home Assistant", "As of 14:32")),
    ("hass", {}, "config", "Entität fehlt: sensor.voron_current_print_state",
     ("Entität fehlt: sensor.voron_current_print_state", None),
     ("Entität fehlt: sensor.voron_current_print_state", None)),
    ("fake", {}, "data", None,
     ("Antwort nicht lesbar", "Stand 14:32"), ("Unexpected answer", "As of 14:32")),
    ("fake", {}, "offline", None,
     ("Drucker nicht erreichbar", None), ("Printer not reachable", None)),
]


@pytest.mark.parametrize(("source", "extra", "kind", "detail", "de", "en"), NOTICES)
def test_notice_kinds(mod, common, source, extra, kind, detail, de, en):
    options = {"source": source, "url": URL, **extra}
    for lang, (message, sub) in (("de", de), ("en", en)):
        d = mod.notice(options, lang, NOW, common.SourceError(kind, detail))
        assert (d["view"], d["alert"], d["label"]) == ("notice", False, "")
        assert d["notice"] == {"message": message, "sub": sub,
                               "tone": "muted" if kind == "offline" else "warn"}
        assert (d["clock"], d["lang"]) == ("14:32", lang)


def test_unreachable_of_a_direct_source_is_not_home_assistant(mod, common):
    d = mod.notice(OPTS, "de", NOW, common.SourceError("unreachable", "time budget used up"))
    assert d["notice"] == {"message": "Drucker nicht erreichbar", "sub": None, "tone": "muted"}


# --- settle (finished_for) -----------------------------------------------------------

def finished(common, **kw):
    return common.PrinterStatus(**{"state": "finished", "progress": 100.0,
                                   "filename": "benchy_0.2mm_PLA", **kw})


def test_finished_becomes_idle_after_finished_for(mod, common):
    ended = NOW - timedelta(minutes=119)
    s = mod.settle(finished(common, ended_at=ended), KEY, 120, NOW)
    assert (s.state, s.ended_at) == ("finished", ended)
    ended = NOW - timedelta(minutes=121)
    thumb = common.Thumbnail(png(), "image/png")
    s = mod.settle(finished(common, ended_at=ended, remaining_s=0, thumbnail=thumb,
                            nozzle=(30.0, None)), KEY, 120, NOW)
    assert (s.state, s.last_job) == ("idle", ("benchy_0.2mm_PLA", ended))
    assert (s.progress, s.remaining_s, s.thumbnail, s.filename) == (None, None, None, None)
    assert s.nozzle == (30.0, None)
    since = NOW - timedelta(minutes=121)
    s = mod.settle(finished(common, state_since=since), ("fake", "other", None, None), 120, NOW)
    assert (s.state, s.last_job) == ("idle", ("benchy_0.2mm_PLA", since))


def test_finished_first_seen_is_remembered(mod, common):
    s = mod.settle(finished(common), KEY, 120, NOW)
    assert (s.state, s.ended_at) == ("finished", NOW)
    assert mod.settle(finished(common), KEY, 120, NOW + timedelta(minutes=119)).state == "finished"
    assert mod.settle(finished(common), KEY, 120, NOW + timedelta(minutes=121)).state == "idle"
    other = ("fake", "http://drucker2.local:7125", None, None)
    later = NOW + timedelta(minutes=121)
    assert mod.settle(finished(common), other, 120, later).state == "finished"
    mod.settle(common.PrinterStatus("printing"), KEY, 120, NOW + timedelta(minutes=122))
    s = mod.settle(finished(common), KEY, 120, NOW + timedelta(minutes=200))
    assert (s.state, s.ended_at) == ("finished", NOW + timedelta(minutes=200))


def test_finished_for_zero_never_shows_finished(mod, common):
    s = mod.settle(finished(common, ended_at=NOW), KEY, 0, NOW)
    assert (s.state, s.last_job) == ("idle", ("benchy_0.2mm_PLA", NOW))
    assert mod.settle(finished(common), ("fake", "x", None, None), 0, NOW).state == "idle"


def test_finished_for_large_value(mod, common):
    s = mod.settle(finished(common, ended_at=NOW - timedelta(days=6)), KEY, 10080, NOW)
    assert s.state == "finished"


def test_last_finished_job_survives_the_printer_going_idle(mod, common):
    ended = NOW - timedelta(minutes=10)
    mod.settle(finished(common, filename="A", ended_at=ended), KEY, 120, NOW)
    s = mod.settle(common.PrinterStatus("idle"), KEY, 120, NOW + timedelta(minutes=1))
    assert (s.state, s.last_job) == ("idle", ("A", ended))
    own = ("B", NOW - timedelta(days=2))
    s = mod.settle(common.PrinterStatus("idle", last_job=own), KEY, 120, NOW)
    assert s.last_job == own


def test_memory_key(mod):
    assert mod.memory_key({"source": "hass", "url": "http://homeassistant.lan:8123",
                           "integration": "moonraker", "device": "voron"}) == (
        "hass", "http://homeassistant.lan:8123", "moonraker", "voron")
    assert mod.memory_key(OPTS) == KEY


# --- validate --------------------------------------------------------------------

def test_validate_ok(mod, fake):
    mod.validate(OPTS)
    mod.validate({**OPTS, "title": "Voron", "lang": "en", "thumbnail": False,
                  "finished_for": 0, "api_key": "k"})
    mod.validate({**OPTS, "finished_for": 10080})
    assert len(fake.validated) == 3


@pytest.mark.parametrize(("options", "match"), [
    ({"url": URL}, "source must be one of"),
    ({"source": "bambu", "url": URL}, "source must be one of"),
    ({"source": "fake"}, "url is required"),
    ({"source": "fake", "url": "drucker.local"}, "http:// or https://"),
    ({**OPTS, "lang": "fr"}, "lang"),
    ({**OPTS, "title": 5}, "title"),
    ({**OPTS, "thumbnail": "no"}, "thumbnail"),
    ({**OPTS, "finished_for": -1}, "finished_for"),
    ({**OPTS, "finished_for": True}, "finished_for"),
    ({**OPTS, "finished_for": 1.5}, "finished_for"),
    ({**OPTS, "finished_for": "120"}, "finished_for"),
    ({**OPTS, "finish_for": 60}, "finish_for"),
    ({**OPTS, "token": "t"}, "'token'.*'fake'"),
])
def test_validate_rejects(mod, fake, options, match):
    with pytest.raises(ValueError, match=match):
        mod.validate(options)
    assert fake.validated == []


def _cfg(extra):
    page = PageConfig(0, "printer", OPTS, 30, extra.get("refresh", 30), "refresh" in extra)
    return AppConfig(30, "Europe/Berlin", "de", (page,), ())


def test_refresh_default_and_floor(printer, fake):
    types = {"printer": printer}
    assert validate_config(_cfg({}), types).pages[0].refresh == 10
    assert validate_config(_cfg({"refresh": 5}), types).pages[0].refresh == 5
    with pytest.raises(ConfigError, match="at least 5"):
        validate_config(_cfg({"refresh": 4}), types)


# --- fetch -----------------------------------------------------------------------

def test_fetch_uses_lang_and_provider(mod, common, fake):
    fake.result = finished(common, ended_at=NOW - timedelta(minutes=121))
    d = mod.fetch(OPTS, ctx("en"))
    assert fake.calls[0] == {**OPTS, "lang": "en"}
    assert (d["view"], d["big"], d["lines"][0]) == ("idle", "Ready", "Last: benchy_0.2mm_PLA")
    fake.result = common.PrinterStatus(**PRINTING)
    d = mod.fetch({**OPTS, "lang": "de"}, ctx("en"))
    assert fake.calls[1]["lang"] == "de"
    assert d == mod.build(common.PrinterStatus(**PRINTING), OPTS, "de", NOW)
    mod.fetch(OPTS, ctx("fr"))
    assert fake.calls[2]["lang"] == "de"


def test_auth_rejected_is_its_own_state(mod, common, fake):
    fake.result = common.SourceError("auth", url=f"{URL}/printer/info")
    d = mod.fetch(OPTS, ctx())
    assert d["view"] == "notice"
    assert d["notice"]["message"] == "Zugang abgelehnt"
    assert d["notice"]["message"] != "Drucker nicht erreichbar"


@pytest.mark.parametrize("exc", [KeyError("result"), TypeError("x"), ValueError("x"),
                                 AttributeError("x")])
def test_unexpected_exception_is_a_data_notice(mod, fake, exc):
    fake.result = exc
    d = mod.fetch(OPTS, ctx())
    assert (d["view"], d["notice"]["message"]) == ("notice", "Antwort nicht lesbar")


def test_offline_is_logged_once_and_without_secrets(mod, common, fake, caplog):
    caplog.set_level(logging.DEBUG)

    def down():
        return common.SourceError("offline", url=f"{URL}/x?apikey=S3CRET",
                                  cause=ConnectionError(f"refused {URL}/x?apikey=S3CRET"))

    def warnings():
        return [r for r in caplog.records if r.levelno >= logging.WARNING]

    for _ in range(3):
        fake.result = down()
        assert mod.fetch(OPTS, ctx())["notice"]["message"] == "Drucker nicht erreichbar"
    assert len(warnings()) == 1
    assert all("S3CRET" not in r.getMessage() for r in caplog.records)
    fake.result = common.PrinterStatus("idle")
    mod.fetch(OPTS, ctx())
    fake.result = down()
    mod.fetch(OPTS, ctx())
    assert len(warnings()) == 2
    assert "S3CRET" not in caplog.text
