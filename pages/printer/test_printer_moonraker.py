"""Tests of the source moonraker (providers/moonraker.py) against documented answer shapes."""

import copy
import importlib
import io
import logging
from datetime import datetime
from types import SimpleNamespace

import pytest
import requests
from PIL import Image
from printer_helpers import NOW, ctx

BASE = "http://drucker.local:7125"
OPTS = {"source": "moonraker", "url": BASE, "lang": "de"}
QUERY = "webhooks&print_stats&virtual_sdcard&display_status&extruder&heater_bed&gcode_move"
Q = f"/printer/objects/query?{QUERY}"
META = "/server/files/metadata"
HIST = "/server/history/list"
THUMB = "/server/files/gcodes/.thumbs/benchy_0.2mm_PLA-300x300.png"
END = datetime(2026, 11, 24, 21, 14, tzinfo=NOW.tzinfo)


def _png():
    out = io.BytesIO()
    Image.new("RGB", (300, 300), (200, 120, 40)).save(out, "PNG")
    return out.getvalue()


PNG = (_png(), "image/png")


@pytest.fixture
def mk(printer):
    return importlib.import_module("glancebox_pages.printer.providers.moonraker")


def query(load, *, webhooks=None, drop=(), **print_stats):
    """The printing fixture with print_stats fields replaced and status objects dropped."""
    answer = copy.deepcopy(load("moonraker_query_printing"))
    status = answer["result"]["status"]
    status["print_stats"].update(print_stats)
    if webhooks:
        status["webhooks"].update(webhooks)
    for name in drop:
        del status[name]
    return answer


def history(load, **job):
    answer = copy.deepcopy(load("moonraker_history"))
    answer["result"]["jobs"][0].update(job)
    return answer


def answers(load, **override):
    """All endpoints of a printing printer; keyword names q, meta, hist, thumb replace one."""
    base = {Q: query(load), META: load("moonraker_metadata"), HIST: load("moonraker_history"),
            THUMB: PNG}
    names = {"q": Q, "meta": META, "hist": HIST, "thumb": THUMB}
    for name, value in override.items():
        base[names[name]] = value
    return base


def paths(calls):
    return [c.url.removeprefix(BASE) for c in calls]


# --- pure computation ----------------------------------------------------------------

def test_progress_is_file_relative(mk, load):
    st = load("moonraker_query_printing")["result"]["status"]
    meta = load("moonraker_metadata")["result"]
    assert mk.progress(st, meta) == pytest.approx(47.0)          # (95000-1000)/(201000-1000)
    assert mk.progress(st, None) == pytest.approx(46.0)          # display_status
    del st["display_status"]
    assert mk.progress(st, None) == pytest.approx(45.0)          # virtual_sdcard


def test_progress_is_clamped_and_needs_sane_bytes(mk, load):
    st = load("moonraker_query_printing")["result"]["status"]
    meta = load("moonraker_metadata")["result"]
    st["virtual_sdcard"]["file_position"] = 500                  # still in the header
    assert mk.progress(st, meta) == 0.0
    st["virtual_sdcard"]["file_position"] = 209000               # in the footer
    assert mk.progress(st, meta) == 100.0
    assert mk.progress(st, {**meta, "gcode_end_byte": 1000}) == pytest.approx(46.0)
    assert mk.progress({}, None) is None


def test_remaining_is_the_mean_of_both_estimates(mk, load):
    st = load("moonraker_query_printing")["result"]["status"]
    meta = load("moonraker_metadata")["result"]
    assert mk.remaining(st, meta, 47.0) == 5306      # mean of 5200 (slicer) and 5412.77 (file)
    assert mk.remaining(st, None, 47.0) == 5413      # file estimate only
    assert mk.remaining(st, meta, 0.5) == 5200       # below 1 %: slicer only
    assert mk.remaining(st, None, 0.5) is None
    assert mk.remaining(st, {"estimated_time": 0}, None) is None


def test_remaining_never_below_zero(mk, load):
    st = load("moonraker_query_printing")["result"]["status"]
    assert mk.remaining(st, {"estimated_time": 3000}, None) == 0      # slicer overrun
    assert mk.remaining(st, None, 100.0) == 0


def test_layer_fallback_like_mainsail(mk, load):
    st = load("moonraker_query_printing")["result"]["status"]
    meta = load("moonraker_metadata")["result"]
    assert mk.layer(st, meta) == (112, 240)
    st["print_stats"]["info"] = {"current_layer": 7, "total_layer": 90}
    assert mk.layer(st, meta) == (7, 90)
    assert mk.layer(load("moonraker_query_printing")["result"]["status"], None) is None


def test_layer_count_and_bounds(mk, load):
    st = load("moonraker_query_printing")["result"]["status"]
    meta = load("moonraker_metadata")["result"]
    assert mk.layer(st, {**meta, "layer_count": 241}) == (112, 241)
    st["gcode_move"]["gcode_position"][2] = 80.0                  # z hop after the last layer
    assert mk.layer(st, meta) == (240, 240)
    st["print_stats"]["print_duration"] = 0.0                     # still heating: z is no layer
    assert mk.layer(st, meta) is None


def test_pick_thumbnail(mk):
    t = lambda w, p: {"width": w, "height": w, "size": 1, "relative_path": p}
    assert mk.pick_thumbnail({"thumbnails": [t(32, "a"), t(300, "b"), t(400, "c")]}) == "b"
    assert mk.pick_thumbnail({"thumbnails": [t(400, "c"), t(640, "d")]}) == "c"
    assert mk.pick_thumbnail({"thumbnails": [t(48, "x.jpg"), t(32, "a.png")]}) == "a.png"
    assert mk.pick_thumbnail({"thumbnails": []}) is None and mk.pick_thumbnail(None) is None


def test_pick_thumbnail_takes_a_jpg_only_without_png(mk):
    t = lambda w, p: {"width": w, "height": w, "size": 1, "relative_path": p}
    assert mk.pick_thumbnail({"thumbnails": [t(220, "x.jpg")]}) == "x.jpg"
    assert mk.pick_thumbnail({"thumbnails": [{"width": "big"}, t(300, None)]}) is None


def test_file_url(mk):
    assert (mk.file_url(BASE + "/", "benchy.gcode", ".thumbs/benchy-300x300.png")
            == f"{BASE}/server/files/gcodes/.thumbs/benchy-300x300.png")
    assert (mk.file_url(BASE, "Teile/Halter #2 groß.gcode", ".thumbs/Halter #2 groß-300x300.png")
            == f"{BASE}/server/files/gcodes/Teile/.thumbs/Halter%20%232%20gro%C3%9F-300x300.png")


# --- fetch -------------------------------------------------------------------------

def test_fetch_printing(mk, load, route):
    calls = route(answers(load))
    s = mk.fetch(OPTS, ctx())
    assert s.state == "printing"
    assert s.progress == pytest.approx(47.0)
    assert s.remaining_s == 5306
    assert s.filename == "benchy_0.2mm_PLA"
    assert s.nozzle == (214.2, 215.0) and s.bed == (60.0, 60.0)
    assert s.layer == (112, 240)
    assert s.thumbnail is not None and s.thumbnail.mime == "image/png"
    assert paths(calls) == [Q, META, THUMB]
    assert calls[1].params == {"filename": "benchy_0.2mm_PLA.gcode"}
    assert calls[2].kind == "bytes" and calls[2].max_bytes == 524288


def test_metadata_and_thumbnail_once_per_file(mk, load, route):
    calls = route(answers(load))
    first = mk.fetch(OPTS, ctx())
    second = mk.fetch(OPTS, ctx())
    assert paths(calls) == [Q, META, THUMB, Q]
    assert second.thumbnail == first.thumbnail and second.remaining_s == 5306


def test_new_print_of_same_filename_reloads_metadata(mk, load, route):   # Review Focus 5
    calls = route(answers(load))
    assert mk.fetch(OPTS, ctx()).remaining_s == 5306
    route_done = answers(load, q=query(load, state="complete"))
    calls = route(route_done)
    assert mk.fetch(OPTS, ctx()).state == "finished"
    assert META not in paths(calls) and THUMB not in paths(calls)       # same print, cached
    meta = load("moonraker_metadata")
    meta["result"]["estimated_time"] = 20000
    meta["result"]["modified"] += 600
    other = (b"\x89PNG-new", "image/png")
    calls = route(answers(load, meta=meta, thumb=other))
    s = mk.fetch(OPTS, ctx())
    assert paths(calls) == [Q, META, THUMB]
    assert s.remaining_s == round(((20000 - 4800) + 5412.77) / 2)
    assert s.thumbnail.data == other[0]


def test_new_file_name_loads_its_own_metadata(mk, load, route):
    route(answers(load))
    mk.fetch(OPTS, ctx())
    meta = load("moonraker_metadata")
    meta["result"]["thumbnails"] = []
    calls = route(answers(load, q=query(load, filename="deckel.gcode"), meta=meta))
    s = mk.fetch(OPTS, ctx())
    assert paths(calls) == [Q, META] and calls[1].params == {"filename": "deckel.gcode"}
    assert s.filename == "deckel" and s.thumbnail is None


def test_filename_with_space_hash_umlaut_and_folder(mk, load, route):    # Review Focus 1
    name = "Teile/Halter #2 groß.gcode"
    meta = load("moonraker_metadata")
    meta["result"]["thumbnails"] = [{"width": 300, "height": 300, "size": 1,
                                     "relative_path": ".thumbs/Halter #2 groß-300x300.png"}]
    thumb = "/server/files/gcodes/Teile/.thumbs/Halter%20%232%20gro%C3%9F-300x300.png"
    calls = route({Q: query(load, filename=name), META: meta, thumb: PNG})
    s = mk.fetch(OPTS, ctx())
    assert calls[1].params == {"filename": name}
    assert calls[2].url == BASE + thumb
    assert s.filename == "Halter #2 groß" and s.thumbnail is not None


@pytest.mark.parametrize(("raw", "state", "message"), [
    ("standby", "idle", None), ("paused", "paused", None), ("complete", "finished", None),
    ("cancelled", "idle", None),
    ("error", "error", "Heater extruder not heating at expected rate"),
])
def test_print_states(mk, load, route, raw, state, message):
    msg = "Heater extruder not heating at expected rate" if raw == "error" else ""
    route(answers(load, q=query(load, state=raw, message=msg)))
    s = mk.fetch(OPTS, ctx())
    assert (s.state, s.message) == (state, message)


def test_unknown_print_state_is_idle_with_the_word(mk, load, route):
    route(answers(load, q=query(load, state="calibrating")))
    s = mk.fetch(OPTS, ctx())
    assert (s.state, s.message) == ("idle", "calibrating")


def test_paused_keeps_the_job(mk, load, route):
    route(answers(load, q=query(load, state="paused")))
    s = mk.fetch(OPTS, ctx())
    assert s.progress == pytest.approx(47.0) and s.remaining_s == 5306
    assert s.filename == "benchy_0.2mm_PLA" and s.thumbnail is not None


@pytest.mark.parametrize(("webhooks", "state", "de", "en"), [
    ("shutdown", "error", "MCU 'mcu' shutdown: Timer too close", None),
    ("error", "error", "MCU 'mcu' shutdown: Timer too close", None),
    ("startup", "offline", "Klipper startet", "Klipper is starting"),
])
def test_klippy_not_ready(mk, load, route, webhooks, state, de, en):
    hooks = {"state": webhooks, "state_message": "MCU 'mcu' shutdown: Timer too close"}
    route({Q: query(load, webhooks=hooks)})
    s = mk.fetch(OPTS, ctx())
    assert (s.state, s.message) == (state, de)
    assert mk.fetch({**OPTS, "lang": "en"}, ctx("en")).message == (en or de)


def test_klippy_host_not_connected_is_offline(mk, route):
    route({Q: 503})                      # Moonraker: ServerError("Klippy Host not connected", 503)
    s = mk.fetch(OPTS, ctx())
    assert (s.state, s.message) == ("offline", "Klipper nicht verbunden")
    assert mk.fetch({**OPTS, "lang": "en"}, ctx("en")).message == "Klipper not connected"


def test_finished_reads_history(mk, load, route):
    calls = route(answers(load, q=query(load, state="complete")))
    s = mk.fetch(OPTS, ctx())
    assert HIST in paths(calls)
    assert calls[paths(calls).index(HIST)].params == {"limit": 1, "order": "desc"}
    assert s.state == "finished" and s.ended_at == END
    assert s.ended_at.tzinfo == NOW.tzinfo
    assert s.duration_s == 4925 and s.progress == 100.0
    assert s.filename == "benchy_0.2mm_PLA" and s.thumbnail is not None
    route(answers(load, q=query(load, state="complete"),
                  hist=history(load, filename="deckel.gcode")))
    assert mk.fetch(OPTS, ctx()).ended_at is None


def test_history_not_read_while_printing(mk, load, route):
    for raw in ("printing", "paused"):
        calls = route(answers(load, q=query(load, state=raw)))
        mk.fetch(OPTS, ctx())
        assert HIST not in paths(calls)


def test_idle_shows_last_completed_job(mk, load, route):
    standby = query(load, state="standby", filename="")
    calls = route({Q: standby, HIST: load("moonraker_history")})
    s = mk.fetch(OPTS, ctx())
    assert s.last_job == ("benchy_0.2mm_PLA", END)
    assert paths(calls) == [Q, HIST]
    route({Q: standby, HIST: history(load, status="cancelled")})
    assert mk.fetch(OPTS, ctx()).last_job is None
    route({Q: standby, HIST: {"result": {"count": 0, "jobs": []}}})
    assert mk.fetch(OPTS, ctx()).last_job is None


@pytest.mark.parametrize("answer", [404, requests.ConnectionError("x"), ["x"],
                                    {"result": {"jobs": [{"end_time": "soon"}]}}])
def test_history_component_off(mk, load, route, answer):
    route(answers(load, q=query(load, state="complete"), hist=answer))
    s = mk.fetch(OPTS, ctx())
    assert s.state == "finished" and s.ended_at is None
    route({Q: query(load, state="standby", filename=""), HIST: answer})
    s = mk.fetch(OPTS, ctx())
    assert s.state == "idle" and s.last_job is None


@pytest.mark.parametrize("missing", ["drop", "empty"])
def test_missing_objects_do_not_break(mk, load, route, missing):
    q = query(load)
    status = q["result"]["status"]
    for name in ("heater_bed", "display_status", "gcode_move"):
        if missing == "drop":
            del status[name]
        else:
            status[name] = {}
    route(answers(load, q=q))
    s = mk.fetch(OPTS, ctx())
    assert s.state == "printing" and s.bed is None
    assert s.nozzle == (214.2, 215.0) and s.progress == pytest.approx(47.0)
    assert s.remaining_s == 5306 and s.layer is None


@pytest.mark.parametrize(("meta", "thumb", "progress"), [
    (404, PNG, 46.0), ({"result": "x"}, PNG, 46.0),
    ("ok", 404, 47.0), ("ok", ValueError("unexpected content type"), 47.0),
])
def test_missing_metadata_or_image(mk, load, route, meta, thumb, progress):
    meta = load("moonraker_metadata") if meta == "ok" else meta
    route(answers(load, meta=meta, thumb=thumb))
    s = mk.fetch(OPTS, ctx())
    assert s.state == "printing" and s.thumbnail is None
    assert s.progress == pytest.approx(progress)


def test_failed_metadata_is_tried_again(mk, load, route):
    route(answers(load, meta=404))
    mk.fetch(OPTS, ctx())
    calls = route(answers(load))
    assert mk.fetch(OPTS, ctx()).remaining_s == 5306
    assert paths(calls) == [Q, META, THUMB]


def test_thumbnail_false_skips_the_download(mk, load, route):
    calls = route(answers(load))
    s = mk.fetch({**OPTS, "thumbnail": False}, ctx())
    assert s.thumbnail is None and all(c.kind == "json" for c in calls)


@pytest.mark.parametrize(("extra", "headers"), [({"api_key": "S3CRET"}, {"X-Api-Key": "S3CRET"}),
                                                ({}, {})])
def test_api_key_header(mk, load, route, extra, headers):
    calls = route(answers(load, q=query(load, state="complete")))
    mk.fetch({**OPTS, **extra}, ctx())
    assert paths(calls) == [Q, META, THUMB, HIST]
    assert all(c.headers == headers for c in calls)


@pytest.mark.parametrize(("answer", "kind"), [
    (401, "auth"), (403, "auth"), (requests.ConnectionError("x"), "offline"),
    (requests.Timeout("x"), "offline"), (500, "data"), (["status"], "data"),
    ({"result": {"status": {"webhooks": {"state": "ready"}}}}, "data"),
    ({"result": {"status": {"print_stats": {"state": None}}}}, "data"), (None, "data"),
])
def test_wrong_key_is_auth(mk, common, route, answer, kind):            # Review Focus 2
    route({Q: answer})
    with pytest.raises(common.SourceError) as err:
        mk.fetch({**OPTS, "api_key": "S3CRET"}, ctx())
    assert err.value.kind == kind
    assert "S3CRET" not in str(err.value)


def _timed(monkeypatch, mk, responses, step):
    """Fake http calls that record timeouts; the fake clock advances ``step`` s per call."""
    clock = [0.0]
    timeouts = []

    def fake(url, *, params=None, headers=None, timeout=10, auth=None, max_bytes=None):
        timeouts.append(timeout)
        clock[0] += step
        return responses[url.removeprefix(BASE)]

    monkeypatch.setattr(mk, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    monkeypatch.setattr(mk.http, "get_json", fake)
    monkeypatch.setattr(mk.http, "get_bytes", fake)
    return timeouts


def test_calls_share_the_time_budget(mk, load, monkeypatch):
    timeouts = _timed(monkeypatch, mk, answers(load), step=1.0)
    assert mk.fetch(OPTS, ctx()).thumbnail is not None
    assert len(timeouts) == 3 and all(0 < t <= 5 for t in timeouts)
    mk._jobs.clear()
    timeouts = _timed(monkeypatch, mk, answers(load), step=15.0)
    s = mk.fetch(OPTS, ctx())
    assert len(timeouts) == 1 and timeouts[0] <= 5
    assert s.state == "printing" and s.thumbnail is None
    assert s.progress == pytest.approx(46.0) and s.remaining_s == 5635


# --- validation and logs -------------------------------------------------------------

@pytest.mark.parametrize("key", [5, "", None, ["k"]])
def test_validate(mk, mod, key):
    with pytest.raises(ValueError, match="api_key"):
        mk.validate({"source": "moonraker", "url": BASE, "api_key": key})
    mk.validate({"source": "moonraker", "url": BASE})
    mk.validate({"source": "moonraker", "url": BASE, "api_key": "k"})
    with pytest.raises(ValueError, match="'token'.*'moonraker'"):
        mod.validate({"source": "moonraker", "url": BASE, "token": "t"})
    mod.validate({"source": "moonraker", "url": BASE, "api_key": "k", "thumbnail": False})


def test_registered(mod, mk):
    assert mod.PROVIDERS["moonraker"] is mk
    assert (mk.NAME, mk.KEYS, mk.QUERY) == ("Moonraker", ("api_key",), QUERY)


@pytest.mark.parametrize("exc", [401, requests.ConnectionError("x"),
                                 requests.exceptions.InvalidHeader("X-Api-Key: S3CRET")])
def test_key_never_logged(mod, load, route, caplog, exc):
    route(answers(load, q=exc))
    with caplog.at_level(logging.DEBUG):
        d = mod.fetch({"source": "moonraker", "url": BASE, "api_key": "S3CRET"}, ctx())
    assert d["view"] == "notice"
    assert "S3CRET" not in caplog.text


def test_page_shows_the_print(mod, load, route):
    route(answers(load))
    d = mod.fetch({"source": "moonraker", "url": BASE}, ctx())
    assert (d["label"], d["big"], d["filename"]) == ("Druckt", "47", "benchy_0.2mm_PLA")
    assert d["main"] == "noch 1:28 h" and d["thumb"].startswith("data:image/png;base64,")
