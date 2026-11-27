"""Tests of the source prusalink (providers/prusalink.py) against documented answer shapes."""

import copy
import importlib
import io
import logging

import pytest
import requests
from PIL import Image
from printer_helpers import ctx

BASE = "http://drucker.local"
OPTS = {"source": "prusalink", "url": BASE, "lang": "de", "password": "geheim"}
KEY_OPTS = {"source": "prusalink", "url": BASE, "lang": "de", "api_key": "S3CRET"}
STATUS = "/api/v1/status"
JOB = "/api/v1/job"
THUMB = "/thumb/l/usb/BENCHY~1.BGC"


def _png():
    out = io.BytesIO()
    Image.new("RGB", (220, 124), (200, 120, 40)).save(out, "PNG")
    return out.getvalue()


PNG = (_png(), "image/png")


@pytest.fixture
def pl(printer):
    return importlib.import_module("glancebox_pages.printer.providers.prusalink")


def status_answer(load, state=None, *, job=True, **fields):
    """The status of a printing printer; ``state`` sets printer.state, ``job=False`` drops
    the job object (the firmware leaves it out when there is no job), keywords go into
    printer (temp_*, target_*) or job (everything else)."""
    answer = copy.deepcopy(load("prusalink_status_printing"))
    if state is not None:
        answer["printer"]["state"] = state
    if not job:
        del answer["job"]
    for name, value in fields.items():
        target = answer["printer"] if name.startswith(("temp_", "target_")) else answer["job"]
        target[name] = value
    return answer


def job_answer(load, **file):
    answer = copy.deepcopy(load("prusalink_job_printing"))
    answer["file"].update(file)
    return answer


def answers(load, **override):
    base = {STATUS: load("prusalink_status_printing"), JOB: load("prusalink_job_printing"),
            THUMB: PNG}
    names = {"status": STATUS, "job": JOB, "thumb": THUMB}
    for name, value in override.items():
        base[names[name]] = value
    return base


def paths(calls):
    return [c.url.removeprefix(BASE) for c in calls]


# --- states ----------------------------------------------------------------------------

@pytest.mark.parametrize(("word", "state"), [
    ("PRINTING", "printing"), ("PAUSED", "paused"), ("FINISHED", "finished"),
    ("STOPPED", "idle"), ("IDLE", "idle"), ("READY", "idle"), ("BUSY", "idle"),
    ("ERROR", "error"), ("ATTENTION", "paused"),
])
def test_state_map(pl, word, state):
    assert pl.STATE_MAP[word] == state


@pytest.mark.parametrize(("lang", "text"), [("de", "Eingriff nötig"), ("en", "Attention needed")])
def test_attention_is_paused_with_a_note(pl, load, route, lang, text):
    route(answers(load, status=status_answer(load, "ATTENTION")))
    s = pl.fetch({**OPTS, "lang": lang}, ctx(lang))
    assert s.state == "paused" and s.message == text
    assert s.filename == "benchy_0.2mm_PLA"


def test_unknown_word_is_idle_with_one_warning(pl, load, route, caplog):
    route({STATUS: status_answer(load, "SERVICE", job=False)})
    with caplog.at_level(logging.WARNING):
        first = pl.fetch(OPTS, ctx())
        second = pl.fetch(OPTS, ctx())
    assert first.state == second.state == "idle"
    assert first.message == "SERVICE"
    assert sum("SERVICE" in r.getMessage() for r in caplog.records) == 1


# --- fetch -------------------------------------------------------------------------------

def test_fetch_printing(pl, load, route):
    calls = route(answers(load))
    s = pl.fetch(OPTS, ctx())
    assert s.state == "printing"
    assert s.progress == 47.0 and s.remaining_s == 4980
    assert s.filename == "benchy_0.2mm_PLA"
    assert s.nozzle == (214.2, 215.0) and s.bed == (60.0, 60.0)
    assert s.layer is None and s.message is None
    assert s.thumbnail is not None and s.thumbnail.mime == "image/png"
    assert [c.url for c in calls] == [f"{BASE}{STATUS}", f"{BASE}{JOB}", f"{BASE}{THUMB}"]
    assert calls[2].max_bytes == 512 * 1024


def test_filename_falls_back_to_the_short_name(pl, load, route):
    route(answers(load, job=job_answer(load, display_name=None)))
    assert pl.fetch(OPTS, ctx()).filename == "BENCHY~1"


def test_job_204_means_no_job(pl, load, route):
    calls = route({STATUS: status_answer(load, "IDLE", job=False), JOB: None})
    s = pl.fetch(OPTS, ctx())
    assert s == pl.PrinterStatus("idle", nozzle=(214.2, 215.0), bed=(60.0, 60.0))
    assert paths(calls).count(JOB) <= 1
    # a printing printer whose job is gone between the two calls: no file, no image
    calls = route({STATUS: load("prusalink_status_printing"), JOB: None})
    s = pl.fetch(OPTS, ctx())
    assert s.state == "printing" and s.filename is None and s.thumbnail is None
    assert s.progress == 47.0
    assert paths(calls) == [STATUS, JOB]


@pytest.mark.parametrize("word", ["IDLE", "READY"])
def test_job_asked_at_most_once(pl, load, route, word):
    calls = route({STATUS: status_answer(load, word), JOB: None})
    pl.fetch(OPTS, ctx())
    assert paths(calls).count(JOB) <= 1
    calls = route(answers(load))
    pl.fetch({**OPTS, "thumbnail": False}, ctx())
    assert paths(calls) == [STATUS, JOB]


def test_finished_has_duration(pl, load, route):
    status = status_answer(load, "FINISHED", time_printing=11520, progress=100.0)
    route(answers(load, status=status))
    s = pl.fetch(OPTS, ctx())
    assert s.state == "finished" and s.progress == 100.0
    assert s.duration_s == 11520 and s.filename == "benchy_0.2mm_PLA"
    assert s.remaining_s is None and s.ended_at is None


def test_finished_without_job_keeps_the_last_print(pl, load, route):
    # Buddy firmware: at FINISHED has_job() is false, status has no job and /api/v1/job is 204
    route(answers(load, status=status_answer(load, time_printing=11500)))
    pl.fetch(OPTS, ctx())
    calls = route({STATUS: status_answer(load, "FINISHED", job=False), JOB: None, THUMB: PNG})
    s = pl.fetch(OPTS, ctx())
    assert s.state == "finished" and s.filename == "benchy_0.2mm_PLA"
    assert s.duration_s == 11500 and s.thumbnail is not None
    assert THUMB not in paths(calls)                     # from the cache
    # once idle the remembered print is forgotten
    route({STATUS: status_answer(load, "IDLE", job=False)})
    pl.fetch(OPTS, ctx())
    route({STATUS: status_answer(load, "FINISHED", job=False), JOB: None})
    s = pl.fetch(OPTS, ctx())
    assert s.state == "finished" and s.filename is None and s.duration_s is None


def test_error_keeps_the_job(pl, load, route):
    route(answers(load, status=status_answer(load, "ERROR")))
    s = pl.fetch(OPTS, ctx())
    assert s.state == "error" and s.filename == "benchy_0.2mm_PLA" and s.progress == 47.0


# --- authentication ---------------------------------------------------------------------

@pytest.mark.parametrize(("extra", "user"), [({}, "maker"), ({"user": "tester"}, "tester")])
def test_digest_auth_by_default(pl, load, route, extra, user):
    calls = route(answers(load))
    pl.fetch({**OPTS, **extra}, ctx())
    assert [c.kind for c in calls] == ["json", "json", "bytes"]
    for call in calls:
        assert isinstance(call.auth, requests.auth.HTTPDigestAuth)
        assert call.auth.username == user and call.auth.password == "geheim"
        assert "X-Api-Key" not in (call.headers or {})
    assert len({id(c.auth) for c in calls}) == 1
    calls_again = route(answers(load))
    pl.fetch({**OPTS, **extra}, ctx())
    assert calls_again[0].auth is not calls[0].auth        # a new handshake state per fetch


def test_api_key_instead_of_password(pl, load, route):
    calls = route(answers(load))
    pl.fetch(KEY_OPTS, ctx())
    assert [c.kind for c in calls] == ["json", "json", "bytes"]
    for call in calls:
        assert call.headers == {"X-Api-Key": "S3CRET"} and call.auth is None


# --- thumbnail --------------------------------------------------------------------------

def test_thumbnail_rules(pl, load, route):
    # no refs.thumbnail: no image, and the address is never built from the file name
    job = job_answer(load)
    del job["file"]["refs"]["thumbnail"]
    calls = route(answers(load, job=job))
    s = pl.fetch(OPTS, ctx())
    assert s.state == "printing" and s.thumbnail is None
    assert [c.kind for c in calls] == ["json", "json"]
    job = job_answer(load)
    del job["file"]["refs"]
    calls = route(answers(load, job=job))
    assert pl.fetch(OPTS, ctx()).thumbnail is None
    assert [c.kind for c in calls] == ["json", "json"]
    # a reference to another host is not fetched
    for ref in ("http://example.org/x.png", "//example.org/x.png"):
        calls = route(answers(load, job=job_answer(load, refs={"thumbnail": ref})))
        assert pl.fetch(OPTS, ctx()).thumbnail is None
        assert [c.kind for c in calls] == ["json", "json"]
    # QOI or any other type: get_bytes raises ValueError, the state stays
    route(answers(load, thumb=ValueError("image/qoi")))
    s = pl.fetch(OPTS, ctx())
    assert s.state == "printing" and s.thumbnail is None and s.filename == "benchy_0.2mm_PLA"
    route(answers(load, thumb=404))
    assert pl.fetch(OPTS, ctx()).thumbnail is None


def test_new_print_of_same_file_reloads_the_thumbnail(pl, load, route):  # Review Focus 5
    calls = route(answers(load))
    pl.fetch(OPTS, ctx())
    pl.fetch(OPTS, ctx())
    assert paths(calls).count(THUMB) == 1
    other = (_png(), "image/png")
    status = status_answer(load, id=13)
    calls = route(answers(load, status=status, thumb=other))
    pl.fetch(OPTS, ctx())
    assert paths(calls).count(THUMB) == 1


# --- missing fields and errors ----------------------------------------------------------

def test_missing_fields(pl, load, route):
    status = status_answer(load, job=False)
    del status["printer"]["temp_bed"]
    job = load("prusalink_job_printing")
    del job["progress"], job["time_remaining"]
    route(answers(load, status=status, job=job))
    s = pl.fetch(OPTS, ctx())
    assert s.state == "printing" and s.bed is None and s.nozzle == (214.2, 215.0)
    assert s.progress is None and s.remaining_s is None
    assert s.filename == "benchy_0.2mm_PLA"
    route(answers(load, status=status_answer(load, progress=None, time_remaining=None)))
    s = pl.fetch(OPTS, ctx())
    assert s.progress is None and s.remaining_s is None


def test_numbers_at_the_edges(pl, load, route):
    route(answers(load, status=status_answer(load, progress=104.2, time_remaining=-30)))
    s = pl.fetch(OPTS, ctx())
    assert s.progress == 100.0 and s.remaining_s is None
    route(answers(load, status=status_answer(load, progress="nan", time_remaining="soon")))
    s = pl.fetch(OPTS, ctx())
    assert s.progress is None and s.remaining_s is None


@pytest.mark.parametrize(("answer", "kind"), [
    (401, "auth"), (403, "auth"), (requests.ConnectionError("x"), "offline"),
    (requests.Timeout("x"), "offline"), (500, "data"), (["printer"], "data"), (None, "data"),
    ({"job": {}}, "data"), ({"printer": {"state": 5}}, "data"),
])
def test_wrong_password_is_auth(pl, common, load, route, answer, kind):    # Review Focus 2
    route({STATUS: answer, JOB: load("prusalink_job_printing")})
    with pytest.raises(common.SourceError) as err:
        pl.fetch(OPTS, ctx())
    assert err.value.kind == kind
    assert "geheim" not in str(err.value)


@pytest.mark.parametrize("answer", [403, requests.ConnectionError("x"), 500, ["x"]])
def test_failed_job_call_leaves_the_file_out(pl, load, route, answer):
    route({STATUS: load("prusalink_status_printing"), JOB: answer})
    s = pl.fetch(OPTS, ctx())
    assert s.state == "printing" and s.filename is None and s.progress == 47.0


# --- validation, registration and logs -----------------------------------------------------

@pytest.mark.parametrize(("options", "match"), [
    ({}, "password or api_key"),
    ({"password": "p", "api_key": "k"}, "not both"),
    ({"user": "tester"}, "user"),
    ({"user": "tester", "api_key": "k"}, "user"),
    ({"user": 5, "password": "p"}, "user"),
    ({"user": "", "password": "p"}, "user"),
    ({"password": 5}, "password"),
    ({"password": ""}, "password"),
    ({"api_key": ["k"]}, "api_key"),
])
def test_validate(pl, mod, options, match):
    full = {"source": "prusalink", "url": BASE, **options}
    with pytest.raises(ValueError, match=match):
        pl.validate(full)
    with pytest.raises(ValueError, match=match):
        mod.validate(full)


def test_validate_accepts(pl, mod):
    for extra in ({"password": "p"}, {"user": "tester", "password": "p"}, {"api_key": "k"}):
        mod.validate({"source": "prusalink", "url": BASE, **extra})
    with pytest.raises(ValueError, match="'token'.*'prusalink'"):
        mod.validate({"source": "prusalink", "url": BASE, "password": "p", "token": "t"})


def test_registered(mod, pl):
    assert mod.PROVIDERS["prusalink"] is pl
    assert list(mod.PROVIDERS) == ["moonraker", "octoprint", "prusalink", "hass"]
    assert (pl.NAME, pl.KEYS, pl.DEFAULT_USER) == ("PrusaLink", ("api_key", "user", "password"),
                                                   "maker")
    with pytest.raises(ValueError, match="moonraker, octoprint, prusalink, hass"):
        mod.validate({"source": "bambu", "url": BASE})


@pytest.mark.parametrize("opts", [OPTS, KEY_OPTS])
@pytest.mark.parametrize("exc", [401, 403, requests.ConnectionError("x")])
def test_password_never_logged(mod, load, route, caplog, opts, exc):
    route(answers(load, status=exc))
    with caplog.at_level(logging.DEBUG):
        d = mod.fetch(opts, ctx())
    assert d["view"] == "notice"
    assert "geheim" not in caplog.text and "S3CRET" not in caplog.text


def test_page_shows_the_print(mod, load, route):
    route(answers(load))
    d = mod.fetch(OPTS, ctx())
    assert (d["label"], d["big"], d["filename"]) == ("Druckt", "47", "benchy_0.2mm_PLA")
    assert d["main"] == "noch 1:23 h" and d["thumb"].startswith("data:image/png;base64,")


@pytest.mark.parametrize(("opts", "sub"), [(OPTS, "Passwort prüfen"),
                                           (KEY_OPTS, "API-Key prüfen")])
def test_page_auth_notice(mod, route, opts, sub):
    route({STATUS: 401})
    d = mod.fetch(opts, ctx())
    assert d["notice"]["message"] == "Zugang abgelehnt" and d["notice"]["sub"] == sub
