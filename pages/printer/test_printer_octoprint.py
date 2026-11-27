"""Tests of the source octoprint (providers/octoprint.py) against documented answer shapes."""

import copy
import importlib
import io
import logging

import pytest
import requests
from PIL import Image
from printer_helpers import ctx

BASE = "http://drucker.local"
OPTS = {"source": "octoprint", "url": BASE, "lang": "de", "api_key": "S3CRET"}
HEADERS = {"X-Api-Key": "S3CRET"}
PRINTER = "/api/printer"
JOB = "/api/job"
FILE = "/api/files/local/Teile/benchy_0.2mm_PLA.gcode"
THUMB_V1 = "/plugin/prusaslicerthumbnails/thumbnail/Teile/benchy_0.2mm_PLA.png?20261125140500"
THUMB_V2 = "/downloads/thumbs/local/Teile/benchy_0.2mm_PLA.gcode?_cb=1795536300"
FLAGS = ("operational", "printing", "cancelling", "pausing", "resuming", "finishing",
         "closedOrError", "error", "paused", "ready", "sdReady")


def _png():
    out = io.BytesIO()
    Image.new("RGB", (220, 124), (200, 120, 40)).save(out, "PNG")
    return out.getvalue()


PNG = (_png(), "image/png")


@pytest.fixture
def op(printer):
    return importlib.import_module("glancebox_pages.printer.providers.octoprint")


def flags(*on):
    return {name: name in on for name in FLAGS}


def printer_answer(load, *on, **temperature):
    answer = copy.deepcopy(load("octoprint_printer_printing"))
    if on:
        answer["state"]["flags"] = flags(*on)
    answer["temperature"].update(temperature)
    return answer


def job_answer(load, *, file=None, error=None, state=None, **progress):
    answer = copy.deepcopy(load("octoprint_job_printing"))
    answer["progress"].update(progress)
    if file is not None:
        answer["job"]["file"].update(file)
    if error is not None:
        answer["error"] = error
    if state is not None:
        answer["state"] = state
    return answer


def answers(load, **override):
    """All endpoints of a printing printer (OctoPrint 2.0 thumbnails); keywords replace one."""
    base = {PRINTER: load("octoprint_printer_printing"), JOB: load("octoprint_job_printing"),
            FILE: load("octoprint_file_v2"), THUMB_V2: PNG}
    names = {"printer": PRINTER, "job": JOB, "file": FILE, "thumb": THUMB_V2}
    for name, value in override.items():
        base[names[name]] = value
    return base


def paths(calls):
    return [c.url.removeprefix(BASE) for c in calls]


# --- states ----------------------------------------------------------------------------

@pytest.mark.parametrize(("on", "completion", "has_file", "state"), [
    (("operational", "error"), None, True, "error"),
    (("closedOrError",), None, True, "error"),
    (("error", "printing", "operational"), 50.0, True, "error"),
    (("operational", "paused"), 50.0, True, "paused"),
    (("operational", "pausing", "printing"), 50.0, True, "paused"),
    (("operational", "cancelling", "printing"), 50.0, True, "idle"),
    (("operational", "printing"), 50.0, True, "printing"),
    (("operational", "finishing"), 100.0, True, "printing"),
    (("operational", "resuming"), 50.0, True, "printing"),
    (("operational", "ready"), 100.0, True, "finished"),
    (("operational",), 100.0, True, "finished"),
    (("operational", "ready"), 100.0, False, "idle"),
    (("operational", "ready"), 47.0, True, "idle"),
    (("operational", "ready"), None, True, "idle"),
    (("ready",), None, False, "idle"),
    ((), None, False, "offline"),
    (("sdReady",), None, False, "offline"),
])
def test_state_of(op, on, completion, has_file, state):
    assert op.state_of(flags(*on), completion, has_file) == state


def test_state_of_ignores_non_true_values(op):
    assert op.state_of({"printing": "yes", "operational": 1}, None, False) == "offline"
    assert op.state_of({}, None, False) == "offline"


# --- fetch -------------------------------------------------------------------------------

def test_fetch_printing(op, load, route):
    calls = route(answers(load))
    s = op.fetch(OPTS, ctx())
    assert s.state == "printing"
    assert s.progress == 47.0 and s.remaining_s == 4980
    assert s.filename == "benchy_0.2mm_PLA"
    assert s.nozzle == (214.2, 215.0) and s.bed == (60.0, 60.0)
    assert s.layer is None and s.message is None
    assert s.thumbnail is not None and s.thumbnail.mime == "image/png"
    assert paths(calls) == [PRINTER, JOB, FILE, THUMB_V2]
    assert calls[0].params == {"exclude": "sd"}
    assert all(c.headers == HEADERS for c in calls)
    assert not any("X-OctoPrint-Api-Version" in c.headers for c in calls)


def test_printer_409_is_offline(op, load, route):
    # OctoPrint: abort(409, "Printer is not operational") when nothing is connected
    calls = route({PRINTER: 409, JOB: job_answer(load, state="Offline", completion=None)})
    s = op.fetch(OPTS, ctx())
    assert s == op.PrinterStatus("offline")
    assert paths(calls) == [PRINTER, JOB]


@pytest.mark.parametrize("answer", [requests.ConnectionError("x"), 500, ["x"]])
def test_printer_409_and_no_job_is_offline(op, route, answer):
    route({PRINTER: 409, JOB: answer})
    assert op.fetch(OPTS, ctx()) == op.PrinterStatus("offline")


@pytest.mark.parametrize(("text", "error", "message"), [
    ("Error", "Too many consecutive timeouts", "Too many consecutive timeouts"),
    ("Offline after error", "Too many consecutive timeouts", "Too many consecutive timeouts"),
    ("Offline after error", None, None),
])
def test_printer_409_after_an_error_is_error(op, load, route, text, error, message):
    # An error state is not operational, so /api/printer answers 409; /api/job tells why.
    route({PRINTER: 409, JOB: job_answer(load, state=text, error=error)})
    s = op.fetch(OPTS, ctx())
    assert (s.state, s.message) == ("error", message)


def test_finished_has_duration(op, load, route):
    route(answers(load, printer=printer_answer(load, "operational", "ready"),
                  job=job_answer(load, completion=100.0, printTime=11520, printTimeLeft=0)))
    s = op.fetch(OPTS, ctx())
    assert s.state == "finished" and s.progress == 100.0
    assert s.duration_s == 11520 and s.ended_at is None
    assert s.filename == "benchy_0.2mm_PLA" and s.thumbnail is not None


def test_error_message(op, load, route):
    route(answers(load, printer=printer_answer(load, "operational", "error"),
                  job=job_answer(load, error="Too many consecutive timeouts")))
    s = op.fetch(OPTS, ctx())
    assert (s.state, s.message) == ("error", "Too many consecutive timeouts")
    route(answers(load, printer=printer_answer(load, "operational", "error")))
    assert op.fetch(OPTS, ctx()).message is None


def test_paused_keeps_the_job(op, load, route):
    route(answers(load, printer=printer_answer(load, "operational", "paused")))
    s = op.fetch(OPTS, ctx())
    assert s.state == "paused" and s.progress == 47.0 and s.remaining_s == 4980
    assert s.filename == "benchy_0.2mm_PLA" and s.thumbnail is not None


def test_idle_shows_no_job(op, load, route):
    calls = route(answers(load, printer=printer_answer(load, "operational", "ready"),
                          job=job_answer(load, completion=None, printTime=None,
                                         printTimeLeft=None)))
    s = op.fetch(OPTS, ctx())
    assert s.state == "idle" and s.filename is None and s.thumbnail is None
    assert s.nozzle == (214.2, 215.0)
    assert paths(calls) == [PRINTER, JOB]


def test_thumbnail_v1_and_v2(op, load, route):
    calls = route(answers(load, file=load("octoprint_file_v1"), thumb=None) | {THUMB_V1: PNG})
    assert op.fetch(OPTS, ctx()).thumbnail is not None
    assert paths(calls) == [PRINTER, JOB, FILE, THUMB_V1]
    assert calls[3].kind == "bytes" and calls[3].max_bytes == 524288
    assert calls[3].headers == HEADERS
    op._files.clear()
    calls = route(answers(load))
    assert op.fetch(OPTS, ctx()).thumbnail is not None
    assert calls[3].url == BASE + THUMB_V2
    assert calls[3].kind == "bytes" and calls[3].max_bytes == 524288
    assert calls[3].headers == HEADERS


def test_file_path_parts_are_encoded(op, load, route):
    name = "Teile/Halter #2 groß.gcode"
    calls = route({PRINTER: load("octoprint_printer_printing"),
                   JOB: job_answer(load, file={"name": "Halter #2 groß.gcode", "path": name}),
                   "/api/files/local/Teile/Halter%20%232%20gro%C3%9F.gcode": {"refs": {}}})
    s = op.fetch(OPTS, ctx())
    assert calls[2].url == BASE + "/api/files/local/Teile/Halter%20%232%20gro%C3%9F.gcode"
    assert s.filename == "Halter #2 groß" and s.thumbnail is None


@pytest.mark.parametrize("case", ["no_fields", "sdcard", "404", "image_fails", "off"])
def test_no_thumbnail(op, load, route, case):
    override, opts = {}, OPTS
    if case == "no_fields":
        override["file"] = {k: v for k, v in load("octoprint_file_v1").items()
                            if k not in ("thumbnail", "thumbnail_src")}
    elif case == "sdcard":
        override["job"] = job_answer(load, file={"origin": "sdcard",
                                                 "path": "benchy~1.gco"})
    elif case == "404":
        override["file"] = 404
    elif case == "image_fails":
        override["thumb"] = 404
    else:
        opts = {**OPTS, "thumbnail": False}
    calls = route(answers(load, **override))
    s = op.fetch(opts, ctx())
    assert s.state == "printing" and s.progress == 47.0 and s.thumbnail is None
    if case in ("sdcard", "off"):
        assert paths(calls) == [PRINTER, JOB]


@pytest.mark.parametrize("ref", ["http://example.org/x.png", "//example.org/x.png",
                                 "https://drucker.local/x.png", "http://drucker.local:5000/x.png"])
def test_thumbnail_reference_must_stay_on_the_printer(op, load, route, ref):
    calls = route(answers(load, file={"refs": {"thumbnail": ref}}))
    s = op.fetch(OPTS, ctx())
    assert s.thumbnail is None and all(c.kind == "json" for c in calls)


def test_thumbnail_reference_on_the_same_host_is_allowed(op, load, route):
    calls = route(answers(load, file={"refs": {"thumbnail": "http://drucker.local:80/t.png"}})
                  | {"http://drucker.local:80/t.png": PNG})
    assert op.fetch(OPTS, ctx()).thumbnail is not None
    assert calls[-1].url == "http://drucker.local:80/t.png"


def test_thumbnail_once_per_file(op, load, route):
    calls = route(answers(load))
    first = op.fetch(OPTS, ctx())
    second = op.fetch(OPTS, ctx())
    assert paths(calls) == [PRINTER, JOB, FILE, THUMB_V2, PRINTER, JOB]
    assert second.thumbnail == first.thumbnail


def test_file_without_thumbnail_is_asked_once(op, load, route):
    calls = route(answers(load, file={"refs": {}}))
    op.fetch(OPTS, ctx())
    op.fetch(OPTS, ctx())
    assert paths(calls) == [PRINTER, JOB, FILE, PRINTER, JOB]


def test_failed_file_call_is_tried_again(op, load, route):
    route(answers(load, file=requests.Timeout("x")))
    assert op.fetch(OPTS, ctx()).thumbnail is None
    calls = route(answers(load))
    assert op.fetch(OPTS, ctx()).thumbnail is not None
    assert paths(calls) == [PRINTER, JOB, FILE, THUMB_V2]


def test_new_upload_of_same_path_reloads_the_thumbnail(op, load, route):
    route(answers(load))
    op.fetch(OPTS, ctx())
    newer = copy.deepcopy(load("octoprint_file_v2"))
    newer["refs"]["thumbnail"] = BASE + "/downloads/thumbs/local/x.gcode?_cb=1795540000"
    other = (b"\x89PNG-new", "image/png")
    calls = route(answers(load, job=job_answer(load, file={"date": 1795540000}), file=newer)
                  | {"/downloads/thumbs/local/x.gcode?_cb=1795540000": other})
    s = op.fetch(OPTS, ctx())
    assert paths(calls)[2:] == [FILE, "/downloads/thumbs/local/x.gcode?_cb=1795540000"]
    assert s.thumbnail.data == other[0]


def test_null_fields(op, load, route):
    job = job_answer(load, completion=None, printTimeLeft=None, file={"name": None})
    printer = printer_answer(load, bed=None)
    route(answers(load, job=job, printer=printer))
    s = op.fetch(OPTS, ctx())
    assert s.state == "printing"
    assert s.progress is None and s.remaining_s is None and s.filename == "benchy_0.2mm_PLA"
    assert s.bed is None and s.nozzle == (214.2, 215.0)
    job = job_answer(load)
    del job["progress"], job["job"]["file"]
    printer = load("octoprint_printer_printing")
    del printer["temperature"]
    route({PRINTER: printer, JOB: job})
    s = op.fetch(OPTS, ctx())
    assert s.state == "printing" and s.filename is None and s.thumbnail is None
    assert s.progress is None and s.nozzle is None and s.bed is None


def test_numbers_at_the_edges(op, load, route):
    route(answers(load, job=job_answer(load, completion=104.2, printTimeLeft=-30)))
    s = op.fetch(OPTS, ctx())
    assert s.progress == 100.0 and s.remaining_s is None
    route(answers(load, job=job_answer(load, completion="nan", printTimeLeft="soon")))
    s = op.fetch(OPTS, ctx())
    assert s.progress is None and s.remaining_s is None


@pytest.mark.parametrize(("answer", "kind"), [
    (401, "auth"), (403, "auth"), (requests.ConnectionError("x"), "offline"),
    (requests.Timeout("x"), "offline"), (500, "data"), (["state"], "data"), (None, "data"),
    ({"temperature": {}}, "data"), ({"state": {"text": "Printing"}}, "data"),
])
def test_wrong_key_is_auth(op, common, load, route, answer, kind):          # Review Focus 2
    route({PRINTER: answer, JOB: load("octoprint_job_printing")})
    with pytest.raises(common.SourceError) as err:
        op.fetch(OPTS, ctx())
    assert err.value.kind == kind
    assert "S3CRET" not in str(err.value)


@pytest.mark.parametrize(("answer", "kind"), [
    (403, "auth"), (requests.ConnectionError("x"), "offline"), (500, "data"), ("x", "data"),
])
def test_job_errors(op, common, load, route, answer, kind):
    route({PRINTER: load("octoprint_printer_printing"), JOB: answer})
    with pytest.raises(common.SourceError) as err:
        op.fetch(OPTS, ctx())
    assert err.value.kind == kind


# --- validation, registration and logs -----------------------------------------------------

@pytest.mark.parametrize("key", [5, "", None, ["k"]])
def test_validate(op, mod, key):
    with pytest.raises(ValueError, match="api_key"):
        op.validate({"source": "octoprint", "url": BASE, "api_key": key})
    with pytest.raises(ValueError, match="api_key"):
        op.validate({"source": "octoprint", "url": BASE})
    with pytest.raises(ValueError, match="api_key"):
        mod.validate({"source": "octoprint", "url": BASE})
    op.validate({"source": "octoprint", "url": BASE, "api_key": "k"})
    with pytest.raises(ValueError, match="'token'.*'octoprint'"):
        mod.validate({"source": "octoprint", "url": BASE, "api_key": "k", "token": "t"})
    mod.validate({"source": "octoprint", "url": BASE, "api_key": "k", "thumbnail": False})


def test_registered(mod, op):
    assert mod.PROVIDERS["octoprint"] is op
    assert list(mod.PROVIDERS)[:2] == ["moonraker", "octoprint"]
    assert (op.NAME, op.KEYS) == ("OctoPrint", ("api_key",))


@pytest.mark.parametrize("exc", [401, 403, requests.ConnectionError("x"),
                                 requests.exceptions.InvalidHeader("X-Api-Key: S3CRET")])
def test_key_never_logged(mod, load, route, caplog, exc):
    route(answers(load, printer=exc))
    with caplog.at_level(logging.DEBUG):
        d = mod.fetch(OPTS, ctx())
    assert d["view"] == "notice"
    assert "S3CRET" not in caplog.text


def test_page_shows_the_print(mod, load, route):
    route(answers(load))
    d = mod.fetch(OPTS, ctx())
    assert (d["label"], d["big"], d["filename"]) == ("Druckt", "47", "benchy_0.2mm_PLA")
    assert d["main"] == "noch 1:23 h" and d["thumb"].startswith("data:image/png;base64,")
