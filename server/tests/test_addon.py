import logging

import pytest
import requests

from glancebox.addon import (
    STARTER_CONFIG,
    AddonError,
    HaInfo,
    addon_setup,
    connect_url,
    ensure_config,
    fetch_ha_info,
    ha_defaults,
    is_addon,
    lang_from_ha,
    secrets_env,
)
from glancebox.config import load_config
from glancebox.pages import load_page_types, validate_config


def test_is_addon_needs_both(tmp_path):
    opts = tmp_path / "options.json"
    opts.write_text("{}")
    assert is_addon({"SUPERVISOR_TOKEN": "t"}, opts)
    assert not is_addon({}, opts)
    assert not is_addon({"SUPERVISOR_TOKEN": "t"}, tmp_path / "missing.json")


def test_secrets_env_fixed_and_extra(caplog):
    caplog.set_level(logging.WARNING)
    env = secrets_env({"push_key": "p" * 16, "openai_admin_key": "",
                       "extra_secrets": [{"name": "MY_API", "value": "s3cret"},
                                         {"name": "PATH", "value": "evil"},
                                         {"name": "GLANCEBOX_PUSH_KEY", "value": "x"},
                                         {"name": "bad-name", "value": "x"}]},
                      {"PATH": "/usr/bin"})
    assert env == {"GLANCEBOX_PUSH_KEY": "p" * 16, "MY_API": "s3cret"}
    assert "evil" not in caplog.text and "s3cret" not in caplog.text
    assert "PATH" in caplog.text


def test_secrets_env_skips_missing_and_none():
    assert secrets_env({"push_key": None, "extra_secrets": None}, {}) == {}
    assert secrets_env({}, {}) == {}


def test_ensure_config_writes_once(tmp_path):
    p = tmp_path / "config.yaml"
    assert ensure_config(p, tmp_path / "fb") == (p, True)
    text = p.read_text()
    assert "type: weather" in text and "latitude" not in text
    p.write_text("pages:\n  - type: clock\n")
    assert ensure_config(p, tmp_path / "fb") == (p, True)
    assert p.read_text() == "pages:\n  - type: clock\n"


def test_ensure_config_falls_back_when_not_writable(tmp_path):
    ro = tmp_path / "ro"
    ro.mkdir()
    ro.chmod(0o500)
    try:
        path, own = ensure_config(ro / "config.yaml", tmp_path / "fb")
    finally:
        ro.chmod(0o700)
    assert own is False
    assert path == tmp_path / "fb" / "config.yaml" and path.exists()


def test_lang_from_ha():
    assert lang_from_ha("de") == "de"
    assert lang_from_ha("en-GB") == "en"
    assert lang_from_ha("fr") == "en"
    assert lang_from_ha(None) == "en"


def test_ha_defaults_fill_only_missing():
    info = HaInfo("America/New_York", "en-GB", 40.7, -74.0)
    hook = ha_defaults(info, {"SUPERVISOR_TOKEN": "sup", "GLANCEBOX_PUSH_KEY": "k" * 16})
    data = {"pages": [{"type": "weather"}, {"type": "weather", "location": "Paris"},
                      {"type": "homeassistant", "entities": ["sensor.a"]},
                      {"type": "homeassistant", "url": "http://other:8123", "token": "t",
                       "entities": ["sensor.a"]}]}
    out = hook(data)
    assert out["timezone"] == "America/New_York" and out["lang"] == "en"
    assert out["push_key"] == "k" * 16
    assert out["pages"][0]["latitude"] == 40.7 and out["pages"][0]["longitude"] == -74.0
    assert "latitude" not in out["pages"][1]
    assert out["pages"][2]["url"] == "http://supervisor/core"
    assert out["pages"][2]["token"] == "sup"
    assert out["pages"][3]["url"] == "http://other:8123" and out["pages"][3]["token"] == "t"
    assert data["pages"][0] == {"type": "weather"}  # input not mutated


def test_ha_defaults_fill_energy_like_homeassistant():
    hook = ha_defaults(HaInfo("Europe/Berlin", "de", 1.0, 2.0), {"SUPERVISOR_TOKEN": "sup"})
    rows = [{"type": "grid", "entity": "sensor.grid_power"}]
    out = hook({"pages": [{"type": "energy", "rows": rows},
                          {"type": "energy", "url": "http://other:8123", "token": "t",
                           "rows": rows}]})
    assert (out["pages"][0]["url"], out["pages"][0]["token"]) == ("http://supervisor/core", "sup")
    assert (out["pages"][1]["url"], out["pages"][1]["token"]) == ("http://other:8123", "t")


def test_ha_defaults_yaml_wins():
    hook = ha_defaults(HaInfo("America/New_York", "en", 1.0, 2.0), {"SUPERVISOR_TOKEN": "s"})
    out = hook({"timezone": "Europe/Berlin", "lang": "de", "pages": [{"type": "clock"}]})
    assert (out["timezone"], out["lang"]) == ("Europe/Berlin", "de")
    assert "push_key" not in out


def test_starter_config_validates(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text(STARTER_CONFIG)
    hook = ha_defaults(HaInfo("Europe/Berlin", "de", 50.0, 8.0), {"SUPERVISOR_TOKEN": "s"})
    cfg = load_config(p, defaults=hook)
    validate_config(cfg, load_page_types(cfg.pages_dirs))
    assert [pg.type for pg in cfg.pages] == ["clock", "weather"]
    assert cfg.pages[1].options["latitude"] == 50.0


class FakeResp:
    def __init__(self, data, status=200):
        self.data, self.status_code = data, status

    def json(self):
        return self.data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}")


def fake_get(routes, calls=None):
    def get(url, headers=None, timeout=None, **kw):
        if calls is not None:
            calls.append((url, headers, timeout))
        hit = routes[url]
        if isinstance(hit, Exception):
            raise hit
        return hit
    return get


CONFIG_URL = "http://supervisor/core/api/config"
NETWORK_URL = "http://supervisor/network/info"
SELF_URL = "http://supervisor/addons/self/info"


def test_fetch_ha_info_parses():
    calls = []
    get = fake_get({CONFIG_URL: FakeResp({"time_zone": "Europe/Berlin", "latitude": 50.1,
                                          "longitude": 8.6, "language": "de"})}, calls)
    assert fetch_ha_info("tok", get=get) == HaInfo("Europe/Berlin", "de", 50.1, 8.6)
    assert calls[0][1]["Authorization"] == "Bearer tok"
    assert calls[0][2] == 5


def test_fetch_ha_info_without_language():
    get = fake_get({CONFIG_URL: FakeResp({"time_zone": "UTC", "latitude": 1, "longitude": 2})})
    assert fetch_ha_info("tok", get=get).language is None


def test_fetch_ha_info_retries_then_fails():
    sleeps = []
    get = fake_get({CONFIG_URL: requests.ConnectionError("refused tok")})
    with pytest.raises(AddonError) as err:
        fetch_ha_info("tok", get=get, sleep=sleeps.append, attempts=3)
    assert len(sleeps) == 2
    assert "tok" not in str(err.value)


def test_fetch_ha_info_retries_on_5xx_then_succeeds():
    answers = iter([FakeResp({}, 502), FakeResp({"time_zone": "UTC", "latitude": 1,
                                                  "longitude": 2})])
    info = fetch_ha_info("tok", get=lambda *a, **k: next(answers), sleep=lambda s: None)
    assert info.time_zone == "UTC"


NETWORK = {"result": "ok", "data": {"interfaces": [
    {"interface": "docker0", "primary": False, "ipv4": {"address": ["172.30.32.1/23"]}},
    {"interface": "eth0", "primary": True, "ipv4": {"address": ["192.168.1.5/24"]}}]}}


def test_connect_url():
    get = fake_get({NETWORK_URL: FakeResp(NETWORK),
                    SELF_URL: FakeResp({"result": "ok", "data": {"network": {"8080/tcp": 8090}}})})
    assert connect_url("tok", get=get) == "http://192.168.1.5:8090"


def test_connect_url_port_disabled():
    get = fake_get({NETWORK_URL: FakeResp(NETWORK),
                    SELF_URL: FakeResp({"result": "ok", "data": {"network": {"8080/tcp": None}}})})
    assert connect_url("tok", get=get) is None


def test_connect_url_supervisor_error():
    get = fake_get({NETWORK_URL: requests.ConnectionError("x"), SELF_URL: FakeResp({})})
    assert connect_url("tok", get=get) is None


OPTIONS_URL = "http://supervisor/addons/self/options/config"


def setup_routes(options=None):
    return fake_get({
        OPTIONS_URL: FakeResp({"result": "ok", "data": options if options is not None else {}}),
        CONFIG_URL: FakeResp({"time_zone": "Europe/Berlin", "latitude": 50.1, "longitude": 8.6,
                              "language": "de"}),
        NETWORK_URL: FakeResp(NETWORK),
        SELF_URL: FakeResp({"result": "ok", "data": {"network": {"8080/tcp": 8090}}}),
    })


def test_addon_setup_end_to_end(tmp_path):
    import json
    opts = tmp_path / "options.json"
    opts.write_text(json.dumps({"push_key": "wrong-source"}))
    opts.chmod(0o000)  # the Supervisor writes it root-only (0600); we must not read it
    environ = {"SUPERVISOR_TOKEN": "sup"}
    try:
        setup = addon_setup(environ, tmp_path / "config" / "config.yaml", tmp_path / "fb",
                            get=setup_routes({"push_key": "p" * 16, "extra_secrets": []}),
                            sleep=lambda s: None)
    finally:
        opts.chmod(0o600)
    assert setup.config_path == tmp_path / "config" / "config.yaml"
    assert setup.config_path.exists() and setup.config_note is None
    assert setup.environ["GLANCEBOX_PUSH_KEY"] == "p" * 16
    assert environ == {}
    assert setup.connect == "http://192.168.1.5:8090"
    cfg = load_config(setup.config_path, defaults=setup.defaults, environ=setup.environ)
    assert [pg.type for pg in cfg.pages] == ["clock", "weather"]
    assert cfg.pages[1].options["latitude"] == 50.1
    assert cfg.push_key == "p" * 16 and cfg.timezone == "Europe/Berlin" and cfg.lang == "de"


def test_addon_setup_keeps_secrets_out_of_process_env(tmp_path):
    environ = {"SUPERVISOR_TOKEN": "tok", "PATH": "/usr/bin"}
    setup = addon_setup(environ, tmp_path / "config.yaml", tmp_path / "fb",
                        get=setup_routes({"anthropic_admin_key": "sk-secret"}),
                        sleep=lambda s: None)
    assert "ANTHROPIC_ADMIN_KEY" not in environ
    assert "SUPERVISOR_TOKEN" not in environ
    assert setup.environ["ANTHROPIC_ADMIN_KEY"] == "sk-secret"
    assert setup.environ["SUPERVISOR_TOKEN"] == "tok"  # only for ${NAME} lookups
    assert setup.environ["PATH"] == "/usr/bin"


def test_addon_setup_supervisor_token_resolves_in_config(tmp_path):
    environ = {"SUPERVISOR_TOKEN": "tok"}
    config = tmp_path / "config.yaml"
    config.write_text("pages:\n  - type: homeassistant\n    url: http://supervisor/core\n"
                      "    token: ${SUPERVISOR_TOKEN}\n")
    setup = addon_setup(environ, config, tmp_path / "fb", get=setup_routes(),
                        sleep=lambda s: None)
    assert "SUPERVISOR_TOKEN" not in environ
    cfg = load_config(setup.config_path, defaults=setup.defaults, environ=setup.environ)
    assert cfg.pages[0].options["token"] == "tok"


def test_addon_setup_homeassistant_page_still_gets_supervisor_token(tmp_path):
    environ = {"SUPERVISOR_TOKEN": "tok"}
    config = tmp_path / "config.yaml"
    config.write_text("pages:\n  - type: homeassistant\n")
    setup = addon_setup(environ, config, tmp_path / "fb", get=setup_routes(),
                        sleep=lambda s: None)
    assert "SUPERVISOR_TOKEN" not in environ
    cfg = load_config(setup.config_path, defaults=setup.defaults, environ=setup.environ)
    assert cfg.pages[0].options["url"] == "http://supervisor/core"
    assert cfg.pages[0].options["token"] == "tok"


def test_addon_setup_extra_secret_cannot_take_the_supervisor_token_name(tmp_path, caplog):
    extra = [{"name": "SUPERVISOR_TOKEN", "value": "mine"}]
    setup = addon_setup({"SUPERVISOR_TOKEN": "tok"}, tmp_path / "config.yaml", tmp_path / "fb",
                        get=setup_routes({"extra_secrets": extra}), sleep=lambda s: None)
    assert setup.environ["SUPERVISOR_TOKEN"] == "tok"
    assert "already in use" in caplog.text


def test_addon_setup_note_when_config_not_writable(tmp_path):
    opts = tmp_path / "options.json"
    opts.write_text("{}")
    ro = tmp_path / "ro"
    ro.mkdir()
    ro.chmod(0o500)
    try:
        setup = addon_setup({"SUPERVISOR_TOKEN": "sup"}, ro / "config.yaml",
                            tmp_path / "fb", get=setup_routes(), sleep=lambda s: None)
    finally:
        ro.chmod(0o700)
    assert setup.config_path == tmp_path / "fb" / "config.yaml"
    assert setup.config_note and "could not" in setup.config_note


def test_addon_setup_options_api_unreachable_is_clear_error(tmp_path):
    opts = tmp_path / "options.json"
    opts.write_text("{}")
    get = fake_get({OPTIONS_URL: requests.ConnectionError("tok")})
    with pytest.raises(AddonError) as err:
        addon_setup({"SUPERVISOR_TOKEN": "tok"}, tmp_path / "c.yaml", tmp_path / "fb",
                    get=get, sleep=lambda s: None)
    assert "options" in str(err.value) and "tok" not in str(err.value)


def test_connect_url_odd_shapes_do_not_crash():
    odd = {"result": "ok", "data": {"interfaces": [{"primary": True, "ipv4": "x"}]}}
    get = fake_get({NETWORK_URL: FakeResp(odd),
                    SELF_URL: FakeResp({"result": "ok", "data": {"network": "x"}})})
    assert connect_url("tok", get=get) is None


def test_fetch_ha_info_refused_fails_fast():
    sleeps = []
    get = fake_get({CONFIG_URL: FakeResp({}, 401)})
    with pytest.raises(AddonError) as err:
        fetch_ha_info("tok", get=get, sleep=sleeps.append, attempts=5)
    assert "refused" in str(err.value) and "401" in str(err.value)
    assert sleeps == []


def test_secrets_env_duplicate_extra_name_warns_first_wins(caplog):
    caplog.set_level(logging.WARNING)
    env = secrets_env({"extra_secrets": [{"name": "MY_API", "value": "one"},
                                         {"name": "MY_API", "value": "two"}]}, {})
    assert env == {"MY_API": "one"}
    assert "MY_API" in caplog.text and "two" not in caplog.text


def test_ha_defaults_fill_null_values():
    hook = ha_defaults(HaInfo("America/New_York", "en", 1.0, 2.0), {"SUPERVISOR_TOKEN": "s"})
    out = hook({"timezone": None, "lang": None, "pages": [{"type": "clock"}]})
    assert (out["timezone"], out["lang"]) == ("America/New_York", "en")
