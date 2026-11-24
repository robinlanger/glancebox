import logging

import pytest
import requests

import glancebox.http
from glancebox import hass


def test_format_number_scales_watts_and_localizes():
    assert hass.format_number(2310, "W", None, "de") == ("2,3", "kW")
    assert hass.format_number(-1100, "W", None, "en") == ("−1.1", "kW")
    assert hass.format_number(21.0, "°C", None, "de") == ("21", "°C")


def test_number_is_finite_or_none():
    assert hass.number("nan") is None
    assert hass.number("1e400") is None
    assert hass.number("abc") is None
    assert hass.number("3200.000001") == 3200.000001


def test_state_url_strips_trailing_slash():
    assert hass.state_url("http://ha.lan:8123/", "sensor.a").endswith(
        ":8123/api/states/sensor.a")
    assert hass.state_url("http://ha.lan:8123", "sensor.a") == (
        "http://ha.lan:8123/api/states/sensor.a")


def test_get_state_passes_bearer_and_timeout(monkeypatch):
    seen = {}

    def fake(url, headers=None, timeout=None, **kw):
        seen.update(url=url, headers=headers, timeout=timeout)
        return {"state": "1"}

    monkeypatch.setattr(glancebox.http, "get_json", fake)
    assert hass.get_state("http://x/api/states/a.b", "tok", 4.5) == {"state": "1"}
    assert seen["headers"] == {"Authorization": "Bearer tok"}
    assert seen["timeout"] == 4.5


def test_get_state_rejects_non_dict(monkeypatch):
    monkeypatch.setattr(glancebox.http, "get_json", lambda *a, **k: [1])
    with pytest.raises(TypeError):
        hass.get_state("http://x/api/states/a.b", "tok", 1)


GOOD = {"url": "http://ha.lan:8123", "token": "abc"}


def test_validate_connection_accepts_good_options():
    hass.validate_connection({**GOOD, "lang": "en", "title": "T"})
    hass.validate_connection(GOOD)


@pytest.mark.parametrize("bad", [
    {"token": "abc"},
    {"url": "ftp://ha.lan", "token": "abc"},
    {**GOOD, "token": ""},
    {**GOOD, "token": "a b"},
    {**GOOD, "lang": "fr"},
    {**GOOD, "title": 3},
])
def test_validate_connection_rejects(bad):
    with pytest.raises(ValueError):
        hass.validate_connection(bad)


def test_entity_id():
    assert hass.entity_id("sensor.a_1") == "sensor.a_1"
    with pytest.raises(ValueError):
        hass.entity_id("Sensor.A")


def test_log_failure_never_logs_the_token(caplog):
    with caplog.at_level(logging.DEBUG):
        hass.log_failure("energy", "http://ha.lan:8123/api/states/sensor.a",
                         requests.exceptions.InvalidHeader("Bearer t0ken"))
    assert "energy:" in caplog.text
    assert "t0ken" not in caplog.text and "Bearer" not in caplog.text
