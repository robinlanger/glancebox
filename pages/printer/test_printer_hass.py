"""Tests of the source hass (providers/hass.py) against answer shapes from the integrations."""

import copy
import importlib
import io
import logging
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
import requests
from PIL import Image
from printer_helpers import NOW, ctx

HA = "http://homeassistant.lan:8123"
OPT = {"source": "hass", "url": HA, "token": "t0ken"}
MOON = {**OPT, "integration": "moonraker", "device": "voron"}
DEVICES = {"moonraker": "voron", "octoprint": None, "prusalink": "mk4", "bambu_lab": "x1c",
           "creality": "k1"}
STATE = {"moonraker": "sensor.voron_current_print_state",
         "octoprint": "sensor.octoprint_current_state", "prusalink": "sensor.mk4",
         "bambu_lab": "sensor.x1c_print_status", "creality": "sensor.k1_print_status"}


def _png():
    out = io.BytesIO()
    Image.new("RGB", (120, 120), (200, 120, 40)).save(out, "PNG")
    return out.getvalue()


PNG = (_png(), "image/png")


@pytest.fixture
def ha(printer):
    return importlib.import_module("glancebox_pages.printer.providers.hass")


def options(integration, **extra):
    device = DEVICES[integration]
    return {**OPT, "integration": integration, **({"device": device} if device else {}), **extra}


def states(load, integration, **changes):
    """The running-print fixture; ``changes`` maps entity ids (dots as __) to a new state,
    None for a missing entity (404) or a dict that is merged into the answer."""
    data = copy.deepcopy(load(f"hass_{integration}"))
    for key, value in changes.items():
        eid = key.replace("__", ".")
        if value is None:
            data[eid] = None
        elif isinstance(value, dict):
            data[eid] = {**data.get(eid, {"entity_id": eid, "attributes": {}}), **value}
        else:
            data[eid] = {**data[eid], "state": value}
    return data


def set_state(data, eid, value):
    data[eid] = None if value is None else {**data[eid], "state": value}
    return data


# --- presets ---------------------------------------------------------------------------

@pytest.mark.parametrize(("integration", "device", "expect"), [
    ("moonraker", "voron", {"remaining_s": 4968, "layer": (112, 240), "nozzle": (214.2, 215.0)}),
    ("octoprint", None, {"remaining_s": None, "layer": None, "nozzle": (214.2, 215.0)}),
    ("prusalink", "mk4", {"remaining_s": None, "layer": None, "nozzle": (214.2, 215.0)}),
    ("bambu_lab", "x1c", {"remaining_s": 4968, "layer": (112, 240), "nozzle": (214.2, 215.0)}),
    ("creality", "k1", {"remaining_s": 4980, "layer": (112, 240), "nozzle": (214.2, 215.0)}),
])
def test_presets_read_a_running_print(ha, load, integration, device, expect):
    options = {**OPT, "integration": integration, **({"device": device} if device else {})}
    status = ha.status_from(load(f"hass_{integration}"), options, NOW)
    assert (status.state, status.progress, status.filename) == ("printing", 47.0, "benchy_0.2mm_PLA")
    assert status.bed == (60.0, 60.0)
    for name, value in expect.items():
        assert getattr(status, name) == value


def test_eta_of_a_running_print(ha, load):
    for integration in ("moonraker", "octoprint", "prusalink", "bambu_lab"):
        status = ha.status_from(load(f"hass_{integration}"), options(integration), NOW)
        assert status.eta == datetime.fromisoformat("2026-11-25T14:55:00+00:00")
    assert ha.status_from(load("hass_creality"), options("creality"), NOW).eta is None


def test_seconds(ha):
    assert [ha.seconds(1.38, "h"), ha.seconds(83, "min"), ha.seconds(4980, "s"),
            ha.seconds(1.5, "d")] == [4968, 4980, 4980, 129600]
    assert ha.seconds(83, None) is None and ha.seconds(83, "%") is None
    assert ha.seconds(-5, "min") is None


# The template table of the spec, field by field ("–" = not in the template).
SPEC_TABLE = {
    "moonraker": {
        "state": "sensor.voron_current_print_state", "progress": "sensor.voron_progress",
        "remaining": "sensor.voron_print_time_left", "eta": "sensor.voron_print_eta",
        "filename": "sensor.voron_filename", "nozzle": "sensor.voron_extruder_temperature",
        "nozzle_target": "number.voron_extruder_target", "bed": "sensor.voron_bed_temperature",
        "bed_target": "number.voron_bed_target", "layer": "sensor.voron_current_layer",
        "layer_total": "sensor.voron_total_layer", "thumbnail": "camera.voron_thumbnail"},
    "octoprint": {
        "state": "sensor.octoprint_2_current_state",
        "progress": "sensor.octoprint_2_job_percentage",
        "eta": "sensor.octoprint_2_estimated_finish_time",
        "filename": "sensor.octoprint_2_current_file",
        "nozzle": "sensor.octoprint_2_actual_tool0_temp",
        "nozzle_target": "sensor.octoprint_2_target_tool0_temp",
        "bed": "sensor.octoprint_2_actual_bed_temp",
        "bed_target": "sensor.octoprint_2_target_bed_temp"},
    "prusalink": {
        "state": "sensor.mk4", "progress": "sensor.mk4_progress",
        "eta": "sensor.mk4_print_finish", "filename": "sensor.mk4_filename",
        "nozzle": "sensor.mk4_nozzle_temperature",
        "nozzle_target": "sensor.mk4_nozzle_target_temperature",
        "bed": "sensor.mk4_heatbed_temperature",
        "bed_target": "sensor.mk4_heatbed_target_temperature",
        "thumbnail": "camera.mk4_preview"},
    "bambu_lab": {
        "state": "sensor.x1c_print_status", "progress": "sensor.x1c_print_progress",
        "remaining": "sensor.x1c_remaining_time", "eta": "sensor.x1c_end_time",
        "filename": "sensor.x1c_task_name", "nozzle": "sensor.x1c_nozzle_temperature",
        "nozzle_target": "sensor.x1c_nozzle_target_temperature",
        "bed": "sensor.x1c_bed_temperature", "bed_target": "sensor.x1c_bed_target_temperature",
        "layer": "sensor.x1c_current_layer", "layer_total": "sensor.x1c_total_layer_count",
        "thumbnail": "image.x1c_cover_image"},
    "creality": {
        "state": "sensor.k1_print_status", "progress": "sensor.k1_print_progress",
        "remaining": "sensor.k1_print_time_left", "filename": "sensor.k1_print_status#file",
        "nozzle": "sensor.k1_nozzle_temperature",
        "nozzle_target": "sensor.k1_nozzle_temperature#target",
        "bed": "sensor.k1_bed_temperature", "bed_target": "sensor.k1_bed_temperature#target",
        "layer": "sensor.k1_working_layer", "layer_total": "sensor.k1_total_layers",
        "thumbnail": "image.k1_current_print_preview"},
}


@pytest.mark.parametrize("integration", list(SPEC_TABLE))
def test_preset_entity_ids(ha, integration):
    opts = options(integration)
    if integration == "octoprint":
        opts["device"] = "octoprint_2"
    refs = ha.refs(opts)
    want = {field: ha.Ref(*value.split("#")) if "#" in value else ha.Ref(value, None)
            for field, value in SPEC_TABLE[integration].items()}
    assert refs == want
    assert set(refs) <= set(ha.FIELDS)


def test_octoprint_default_prefix(ha):
    assert ha.refs(options("octoprint"))["state"] == ha.Ref("sensor.octoprint_current_state", None)


def test_creality_attribute_refs(ha):
    refs = ha.refs(options("creality"))
    assert refs["filename"] == ha.Ref("sensor.k1_print_status", "file")
    assert refs["nozzle_target"] == ha.Ref("sensor.k1_nozzle_temperature", "target")


# The state word table of the spec, every cell (finished of octoprint and the Klippy/
# unavailable cells of offline have tests of their own).
WORDS = {
    "moonraker": {"printing": ["printing"], "paused": ["paused"], "finished": ["complete"],
                  "error": ["error"], "idle": ["standby", "cancelled"]},
    "octoprint": {"printing": ["printing", "printing_sd", "printing_streaming", "starting",
                               "starting_sd", "starting_streaming", "resuming", "finishing"],
                  "paused": ["paused", "pausing"], "error": ["error", "offline_after_error"],
                  "idle": ["operational", "cancelling", "transferring_file"],
                  "offline": ["offline", "open_serial", "detect_serial", "connecting"]},
    "prusalink": {"printing": ["printing"], "paused": ["paused", "attention"],
                  "finished": ["finished"], "error": ["error"],
                  "idle": ["idle", "ready", "stopped", "busy"]},
    "bambu_lab": {"printing": ["running", "prepare", "slicing", "init"], "paused": ["pause"],
                  "finished": ["finish"], "error": ["failed"], "idle": ["idle"],
                  "offline": ["offline"]},
    "creality": {"printing": ["printing", "processing", "self-testing"], "paused": ["paused"],
                 "finished": ["completed"], "error": ["error"], "idle": ["idle", "stopped"],
                 "offline": ["off"]},
}
WORD_CASES = [(i, word, schema) for i, table in WORDS.items()
              for schema, words in table.items() for word in words]


@pytest.mark.parametrize(("integration", "word", "schema"), WORD_CASES)
def test_state_words(ha, load, integration, word, schema):
    data = states(load, integration)
    for raw in (word, f" {word.upper()} ", word.capitalize()):
        set_state(data, STATE[integration], raw)
        if integration == "octoprint":
            set_state(data, "sensor.octoprint_job_percentage", "47.0")
        assert ha.status_from(data, options(integration), NOW).state == schema
        assert ha.words(options(integration))[word] == schema


def test_octoprint_finished_is_operational_at_100(ha, load):
    data = states(load, "octoprint", sensor__octoprint_current_state="operational",
                  sensor__octoprint_job_percentage="100")
    assert ha.status_from(data, options("octoprint"), NOW).state == "finished"
    set_state(data, "sensor.octoprint_job_percentage", "47")
    assert ha.status_from(data, options("octoprint"), NOW).state == "idle"
    set_state(data, "sensor.octoprint_job_percentage", None)
    assert ha.status_from(data, options("octoprint"), NOW).state == "idle"
    del data["sensor.octoprint_job_percentage"]
    assert ha.status_from(data, options("octoprint"), NOW).state == "idle"


@pytest.mark.parametrize(("klippy", "state"), [
    ("shutdown", "error"), ("error", "error"), ("startup", "offline"), (" Shutdown ", "error"),
    ("ready", "printing"), (None, "printing"), ("unavailable", "printing"),
])
def test_moonraker_klippy_overrides(ha, load, klippy, state):
    data = set_state(states(load, "moonraker"), "sensor.voron_printer_state", klippy)
    assert ha.status_from(data, MOON, NOW).state == state
    data = set_state(data, "sensor.voron_current_print_state", "paused")
    assert ha.status_from(data, MOON, NOW).state == ("paused" if state == "printing" else state)


def test_moonraker_klippy_startup_says_so(ha, load):
    data = set_state(states(load, "moonraker"), "sensor.voron_printer_state", "startup")
    assert ha.status_from(data, {**MOON, "lang": "en"}, NOW).message == "Klipper is starting"


@pytest.mark.parametrize("integration", list(STATE))
@pytest.mark.parametrize("word", ["unavailable", "unknown", "Unavailable "])
def test_unavailable_and_unknown_state_is_offline(ha, load, integration, word):
    data = set_state(states(load, integration), STATE[integration], word)
    status = ha.status_from(data, options(integration), NOW)
    assert status.state == "offline" and status.message is None


def test_unknown_word_is_idle_with_the_raw_word(ha, load, caplog):
    data = set_state(states(load, "bambu_lab"), STATE["bambu_lab"], "calibrating_extrusion")
    with caplog.at_level(logging.WARNING):
        for _ in range(3):
            status = ha.status_from(data, options("bambu_lab"), NOW)
            assert (status.state, status.message) == ("idle", "calibrating_extrusion")
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1 and "calibrating_extrusion" in warnings[0].getMessage()


def test_states_option_adds_and_overrides(ha, load):
    opts = options("bambu_lab", states={"printing": ["calibrating_extrusion"], "idle": ["finish"]})
    data = states(load, "bambu_lab")
    for word, state in (("calibrating_extrusion", "printing"), ("finish", "idle"),
                        ("running", "printing"), ("Calibrating_Extrusion", "printing")):
        set_state(data, STATE["bambu_lab"], word)
        assert ha.status_from(data, opts, NOW).state == state


def test_custom_integration(ha):
    opts = {**OPT, "integration": "custom",
            "entities": {"state": "sensor.mein_status", "progress": "sensor.mein_fortschritt"}}
    assert ha.refs(opts) == {"state": ha.Ref("sensor.mein_status", None),
                             "progress": ha.Ref("sensor.mein_fortschritt", None)}

    def run(word, o=opts):
        data = {"sensor.mein_status": {"entity_id": "sensor.mein_status", "state": word,
                                       "attributes": {}, "last_changed": "bad"},
                "sensor.mein_fortschritt": {"entity_id": "sensor.mein_fortschritt",
                                            "state": "12.5", "attributes": {}}}
        return ha.status_from(data, o, NOW)

    for word in ("printing", "paused", "finished", "error", "idle", "offline"):
        assert run(word).state == word
    assert run("printing").progress == 12.5
    assert (run("running").state, run("running").message) == ("idle", "running")
    mapped = {**opts, "states": {"printing": ["running", "busy"], "finished": ["done"]}}
    assert [run(w, mapped).state for w in ("running", "busy", "done", "paused")] == \
        ["printing", "printing", "finished", "paused"]


def test_entities_override_one_field(ha):
    refs = ha.refs({**MOON, "entities": {"nozzle_target": "sensor.voron_ziel#temperature"}})
    assert refs["nozzle_target"] == ha.Ref("sensor.voron_ziel", "temperature")
    others = {k: v for k, v in refs.items() if k != "nozzle_target"}
    assert others == {k: v for k, v in ha.refs(MOON).items() if k != "nozzle_target"}


def test_entity_override_reads_the_attribute(ha, load):
    data = states(load, "moonraker", sensor__voron_ziel={"state": "on",
                                                        "attributes": {"temperature": 230}})
    opts = {**MOON, "entities": {"nozzle_target": "sensor.voron_ziel#temperature"}}
    assert ha.status_from(data, opts, NOW).nozzle == (214.2, 230.0)


OPTIONAL = {  # field -> (entity of the moonraker fixture, attribute on the status, value)
    "progress": ("sensor.voron_progress", "progress"),
    "remaining": ("sensor.voron_print_time_left", "remaining_s"),
    "eta": ("sensor.voron_print_eta", "eta"),
    "filename": ("sensor.voron_filename", "filename"),
    "nozzle": ("sensor.voron_extruder_temperature", "nozzle"),
    "bed": ("sensor.voron_bed_temperature", "bed"),
    "layer": ("sensor.voron_current_layer", "layer"),
}


@pytest.mark.parametrize("field", list(OPTIONAL))
@pytest.mark.parametrize("value", [None, "unavailable", "unknown"])
def test_optional_fields_missing_or_unavailable(ha, load, field, value):
    eid, attr = OPTIONAL[field]
    status = ha.status_from(set_state(states(load, "moonraker"), eid, value), MOON, NOW)
    assert status.state == "printing"
    assert getattr(status, attr) is None


@pytest.mark.parametrize("value", [None, "unavailable", "unknown"])
def test_missing_targets_and_total_only_drop_that_part(ha, load, value):
    data = states(load, "moonraker")
    for eid in ("number.voron_extruder_target", "number.voron_bed_target",
                "sensor.voron_total_layer"):
        set_state(data, eid, value)
    status = ha.status_from(data, MOON, NOW)
    assert (status.nozzle, status.bed, status.layer) == ((214.2, None), (60.0, None), (112, None))


def test_prusalink_disabled_temperature_sensors(ha, load):
    data = states(load, "prusalink")
    for eid in ("sensor.mk4_nozzle_temperature", "sensor.mk4_nozzle_target_temperature",
                "sensor.mk4_heatbed_temperature", "sensor.mk4_heatbed_target_temperature"):
        del data[eid]
    status = ha.status_from(data, options("prusalink"), NOW)
    assert (status.state, status.nozzle, status.bed) == ("printing", None, None)


def test_creality_attributes_missing(ha, load):
    data = states(load, "creality")
    data["sensor.k1_print_status"]["attributes"] = {}
    data["sensor.k1_nozzle_temperature"]["attributes"].pop("target")
    status = ha.status_from(data, options("creality"), NOW)
    assert (status.state, status.filename, status.nozzle) == ("printing", None, (214.2, None))


@pytest.mark.parametrize("integration", ["octoprint", "prusalink"])
def test_stale_eta_is_dropped(ha, load, integration):            # Review Focus 4
    eta = {"octoprint": "sensor.octoprint_estimated_finish_time",
           "prusalink": "sensor.mk4_print_finish"}[integration]
    data = states(load, integration)
    for value in ("2026-11-25T11:00:00+00:00", "unknown", "morgen", "", "2026-13-45T99:00",
                  "0001-01-01T00:00:00+05:00"):
        status = ha.status_from(set_state(data, eta, value), options(integration), NOW)
        assert (status.eta, status.remaining_s) == (None, None), value
    status = ha.status_from(set_state(data, eta, "2026-11-25T16:10:00"), options(integration), NOW)
    assert status.eta == NOW.replace(hour=16, minute=10)


def test_stale_eta_with_remaining_keeps_remaining(ha, load):
    data = set_state(states(load, "moonraker"), "sensor.voron_print_eta",
                     "2026-11-25T11:00:00+00:00")
    status = ha.status_from(data, MOON, NOW)
    assert (status.eta, status.remaining_s) == (None, 4968)


@pytest.mark.parametrize("unit", [None, "", "%", "Stunden"])
def test_remaining_without_unit_is_not_used(ha, load, unit):
    data = states(load, "moonraker")
    attributes = data["sensor.voron_print_time_left"]["attributes"]
    if unit is None:
        attributes.pop("unit_of_measurement")
    else:
        attributes["unit_of_measurement"] = unit
    assert ha.status_from(data, MOON, NOW).remaining_s is None


@pytest.mark.parametrize(("value", "want"), [("104", 100.0), ("-1", 0.0), ("nan", None),
                                             ("inf", None), ("viel", None), ("47.5", 47.5)])
def test_progress_garbage(ha, load, value, want):
    data = set_state(states(load, "moonraker"), "sensor.voron_progress", value)
    assert ha.status_from(data, MOON, NOW).progress == want


@pytest.mark.parametrize(("value", "want"), [("-3", None), ("x", None), ("nan", None),
                                             ("112.0", (112, 240)), ("1500", (240, 240))])
def test_layer_garbage(ha, load, value, want):
    data = set_state(states(load, "moonraker"), "sensor.voron_current_layer", value)
    assert ha.status_from(data, MOON, NOW).layer == want


def test_state_since_is_last_changed(ha, load):
    data = states(load, "moonraker", sensor__voron_current_print_state={
        "last_changed": "2026-11-25T13:05:00+00:00"})
    since = ha.status_from(data, MOON, NOW).state_since
    assert since == NOW.replace(hour=14, minute=5) and since.tzinfo == NOW.tzinfo
    data["sensor.voron_current_print_state"]["last_changed"] = "gestern"
    assert ha.status_from(data, MOON, NOW).state_since is None
    del data["sensor.voron_current_print_state"]["last_changed"]
    assert ha.status_from(data, MOON, NOW).state_since is None


def test_image_url(ha):
    assert ha.image_url(HA + "/", "camera.voron_thumbnail") == \
        HA + "/api/camera_proxy/camera.voron_thumbnail"
    assert ha.image_url(HA, "image.x1c_cover_image") == HA + "/api/image_proxy/image.x1c_cover_image"
    assert ha.image_url(HA, "sensor.voron_thumbnail") is None


# --- fetch -----------------------------------------------------------------------------

def served(load, integration, **extra):
    """route() answers: every fixture entity under /api/states/, None as 404, plus extra."""
    answers = {}
    for eid, answer in load(f"hass_{integration}").items():
        answers[f"/api/states/{eid}"] = 404 if answer is None else answer
    answers.update(extra)
    return answers


def test_fetch_calls_each_entity_once_then_the_image(ha, load, route):
    calls = route(served(load, "moonraker", **{"/api/camera_proxy/camera.voron_thumbnail": PNG}))
    status = ha.fetch({**MOON, "lang": "de"}, ctx())
    assert status.state == "printing" and status.thumbnail == ha.Thumbnail(*PNG)
    reads = [c for c in calls if c.kind == "json"]
    assert [c.url.removeprefix(HA + "/api/states/") for c in reads] == [
        "sensor.voron_current_print_state", "sensor.voron_printer_state",
        "sensor.voron_progress", "sensor.voron_print_time_left", "sensor.voron_print_eta",
        "sensor.voron_filename", "sensor.voron_extruder_temperature",
        "number.voron_extruder_target", "sensor.voron_bed_temperature",
        "number.voron_bed_target", "sensor.voron_current_layer", "sensor.voron_total_layer"]
    assert all(c.headers == {"Authorization": "Bearer t0ken"} for c in calls)
    assert [(c.kind, c.url) for c in calls[len(reads):]] == [
        ("bytes", HA + "/api/camera_proxy/camera.voron_thumbnail")]
    assert calls[-1].max_bytes == 512 * 1024


def test_fetch_reads_shared_entities_once(ha, load, route):
    calls = route(served(load, "creality",
                         **{"/api/image_proxy/image.k1_current_print_preview": PNG}))
    status = ha.fetch({**options("creality"), "lang": "de"}, ctx())
    assert (status.filename, status.nozzle) == ("benchy_0.2mm_PLA", (214.2, 215.0))
    urls = [c.url for c in calls if c.kind == "json"]
    assert len(urls) == len(set(urls)) == 7
    assert calls[-1].url == HA + "/api/image_proxy/image.k1_current_print_preview"


def test_fetch_bambu_image_and_octoprint_none(ha, load, route):
    calls = route(served(load, "bambu_lab", **{"/api/image_proxy/image.x1c_cover_image": PNG}))
    assert ha.fetch({**options("bambu_lab"), "lang": "de"}, ctx()).thumbnail is not None
    assert calls[-1].url == HA + "/api/image_proxy/image.x1c_cover_image"
    calls = route(served(load, "octoprint"))
    status = ha.fetch({**options("octoprint"), "lang": "de"}, ctx())
    assert status.thumbnail is None and all(c.kind == "json" for c in calls)


@pytest.mark.parametrize("answer", [500, ValueError("type"), requests.ConnectionError("x")])
def test_image_failure_gives_status_without_image(ha, load, route, answer):
    route(served(load, "moonraker", **{"/api/camera_proxy/camera.voron_thumbnail": answer}))
    status = ha.fetch({**MOON, "lang": "de"}, ctx())
    assert status.state == "printing" and status.thumbnail is None and status.progress == 47.0


def test_image_is_cached_per_file(ha, load, route):
    calls = route(served(load, "moonraker", **{"/api/camera_proxy/camera.voron_thumbnail": PNG}))
    ha.fetch({**MOON, "lang": "de"}, ctx())
    ha.fetch({**MOON, "lang": "de"}, ctx())
    assert sum(c.kind == "bytes" for c in calls) == 1


def test_image_without_filename_is_not_cached(ha, load, route):
    answers = served(load, "moonraker", **{"/api/camera_proxy/camera.voron_thumbnail": PNG,
                                           "/api/states/sensor.voron_filename": 404})
    calls = route(answers)
    ha.fetch({**MOON, "lang": "de"}, ctx())
    ha.fetch({**MOON, "lang": "de"}, ctx())
    assert sum(c.kind == "bytes" for c in calls) == 2


@pytest.mark.parametrize(("word", "extra"), [("standby", {}), ("unavailable", {}),
                                             ("printing", {"thumbnail": False})])
def test_no_image_when_idle_or_disabled(ha, load, route, word, extra):
    answers = served(load, "moonraker")
    answers["/api/states/sensor.voron_current_print_state"] = {
        **answers["/api/states/sensor.voron_current_print_state"], "state": word}
    calls = route(answers)
    ha.fetch({**MOON, "lang": "de", **extra}, ctx())
    assert all(c.kind == "json" for c in calls)


@pytest.mark.parametrize(("lang", "detail"), [
    ("de", "Entität fehlt: sensor.voron_current_print_state"),
    ("en", "Entity missing: sensor.voron_current_print_state"),
])
def test_missing_state_entity_is_a_config_error(ha, common, load, route, lang, detail):
    calls = route(served(load, "moonraker",
                         **{"/api/states/sensor.voron_current_print_state": 404}))
    with pytest.raises(common.SourceError) as err:
        ha.fetch({**MOON, "lang": lang}, ctx())
    assert (err.value.kind, err.value.detail) == ("config", detail)
    assert len(calls) == 1


def test_missing_state_entity_page_notice(mod, load, route):
    route(served(load, "moonraker", **{"/api/states/sensor.voron_current_print_state": 404}))
    data = mod.fetch(MOON, ctx())
    assert data["notice"]["message"] == "Entität fehlt: sensor.voron_current_print_state"


@pytest.mark.parametrize(("answer", "kind"), [
    (401, "auth"), (403, "auth"), (requests.ConnectionError("x"), "unreachable"),
    (requests.Timeout("x"), "unreachable"), (500, "unreachable"), ([1, 2], "unreachable"),
])
@pytest.mark.parametrize("entity", ["sensor.voron_current_print_state", "sensor.voron_progress"])
def test_token_rejected_and_unreachable(ha, common, load, route, answer, kind, entity):
    route(served(load, "moonraker", **{f"/api/states/{entity}": answer}))
    with pytest.raises(common.SourceError) as err:
        ha.fetch({**MOON, "lang": "de"}, ctx())
    assert err.value.kind == kind
    assert "t0ken" not in str(err.value)


def test_state_answer_without_state_is_unreadable(ha, common, load, route):
    answers = served(load, "moonraker")
    answers["/api/states/sensor.voron_current_print_state"] = {"entity_id": "x", "attributes": {}}
    route(answers)
    with pytest.raises(common.SourceError) as err:
        ha.fetch({**MOON, "lang": "de"}, ctx())
    assert err.value.kind == "data"


def test_page_notices(mod, load, route):
    route(served(load, "moonraker", **{"/api/states/sensor.voron_progress": 401}))
    assert mod.fetch(MOON, ctx())["notice"]["message"] == "Token abgelehnt"
    route(served(load, "moonraker", **{"/api/states/sensor.voron_progress": 500}))
    assert mod.fetch(MOON, ctx())["notice"]["message"] == "Keine Verbindung zu Home Assistant"


def test_page_shows_the_print(mod, load, route):
    route(served(load, "moonraker", **{"/api/camera_proxy/camera.voron_thumbnail": PNG}))
    data = mod.fetch(MOON, ctx())
    assert (data["view"], data["label"], data["big"]) == ("job", "Druckt", "47")
    assert data["main"] == "noch 1:22 h" and data["filename"] == "benchy_0.2mm_PLA"
    assert data["thumb"].startswith("data:image/png;base64,")


def _timed(monkeypatch, ha, responses, step):
    """Fake http calls that record timeouts; the fake clock advances ``step`` s per call."""
    clock = [0.0]
    calls = []

    def fake(url, *, params=None, headers=None, timeout=10, auth=None, max_bytes=None):
        calls.append(SimpleNamespace(url=url, timeout=timeout))
        clock[0] += step
        answer = responses[url.removeprefix(HA)]
        if isinstance(answer, int):
            resp = requests.Response()
            resp.status_code = answer
            raise requests.HTTPError(f"{answer} error", response=resp)
        return answer

    monkeypatch.setattr(ha, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    monkeypatch.setattr(ha.http, "get_json", fake)
    monkeypatch.setattr(ha.http, "get_bytes", fake)
    return calls


def test_budget_like_energy(ha, common, load, monkeypatch):
    answers = served(load, "moonraker", **{"/api/camera_proxy/camera.voron_thumbnail": PNG})
    calls = _timed(monkeypatch, ha, answers, step=2.0)
    with pytest.raises(common.SourceError) as err:
        ha.fetch({**MOON, "lang": "de"}, ctx())
    assert err.value.kind == "unreachable"
    assert len(calls) == 8 and all(0 < c.timeout <= 5 for c in calls)

    calls = _timed(monkeypatch, ha, answers, step=1.1)
    status = ha.fetch({**MOON, "lang": "de"}, ctx())
    assert len(calls) == 12 and all(0 < c.timeout <= 5 for c in calls)
    assert status.state == "printing" and status.thumbnail is None

    calls = _timed(monkeypatch, ha, answers, step=0.5)
    assert ha.fetch({**MOON, "lang": "de"}, ctx()).thumbnail is not None
    assert len(calls) == 13


# --- validation and logs -----------------------------------------------------------------

@pytest.mark.parametrize("opts", [
    MOON,
    {**OPT, "integration": "octoprint"},
    {**OPT, "integration": "octoprint", "device": "octoprint_2"},
    options("prusalink"), options("bambu_lab"), options("creality"),
    {**OPT, "integration": "custom", "entities": {"state": "sensor.mein_status"}},
    {**OPT, "integration": "custom", "device": "egal", "entities": {"state": "sensor.s"}},
    {**MOON, "entities": {"nozzle_target": "sensor.voron_ziel#temperature",
                          "filename": "sensor.voron_x#file_name"}},
    {**MOON, "states": {"printing": ["running", "Busy"], "finished": []}},
    {**MOON, "thumbnail": False, "lang": "en", "title": "Voron"},
])
def test_validate_ok(ha, mod, opts):
    ha.validate(opts)
    mod.validate(opts)


@pytest.mark.parametrize(("opts", "match"), [
    ({k: v for k, v in MOON.items() if k != "token"}, "token"),
    ({k: v for k, v in MOON.items() if k != "integration"}, "integration"),
    ({**MOON, "integration": "elegoo"}, "integration"),
    ({**OPT, "integration": "moonraker"}, "device"),
    ({**OPT, "integration": "prusalink"}, "device"),
    ({**OPT, "integration": "bambu_lab"}, "device"),
    ({**OPT, "integration": "creality"}, "device"),
    ({**MOON, "device": "Voron 2"}, "device"),
    ({**MOON, "device": ""}, "device"),
    ({**MOON, "device": 5}, "device"),
    ({**MOON, "entities": ["sensor.x"]}, "entities"),
    ({**MOON, "entities": {"temp": "sensor.x"}}, "nozzle_target"),
    ({**MOON, "entities": {"state": "Sensor.X"}}, "entity id"),
    ({**MOON, "entities": {"state": "sensor.x#"}}, "attribute"),
    ({**MOON, "entities": {"state": "sensor.x#a b"}}, "attribute"),
    ({**MOON, "entities": {"state": 5}}, "entity id"),
    ({**OPT, "integration": "custom"}, "entities.state"),
    ({**OPT, "integration": "custom", "entities": {"progress": "sensor.p"}}, "entities.state"),
    ({**MOON, "states": ["printing"]}, "states"),
    ({**MOON, "states": {"done": ["x"]}}, "states"),
    ({**MOON, "states": {"printing": "running"}}, "states"),
    ({**MOON, "states": {"printing": ["running", 5]}}, "states"),
    ({**MOON, "states": {"printing": [""]}}, "states"),
])
def test_validate_rejects(ha, opts, match):
    with pytest.raises(ValueError, match=match):
        ha.validate(opts)


def test_page_accepts_only_hass_keys(mod):
    with pytest.raises(ValueError, match="unknown key 'api_key'"):
        mod.validate({**MOON, "api_key": "x"})


@pytest.mark.parametrize("exc", [requests.ConnectionError("x"), 401, 404,
                                 requests.exceptions.InvalidHeader("Bearer t0ken")])
def test_token_never_logged(mod, load, route, caplog, exc):
    route(served(load, "moonraker", **{"/api/states/sensor.voron_current_print_state": exc}))
    with caplog.at_level(logging.DEBUG):
        data = mod.fetch(MOON, ctx())
    assert data["view"] == "notice"
    assert "t0ken" not in caplog.text and "Bearer" not in caplog.text


def test_status_since_feeds_finished(mod, load, route):
    answers = served(load, "moonraker")
    answers["/api/states/sensor.voron_current_print_state"] = {
        **answers["/api/states/sensor.voron_current_print_state"], "state": "complete",
        "last_changed": (NOW - timedelta(minutes=4)).isoformat()}
    route(answers)
    data = mod.fetch(MOON, ctx())
    assert (data["label"], data["big"]) == ("Fertig", "14:28")
