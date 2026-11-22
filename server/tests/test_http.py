import pytest
import requests

from glancebox import http


class FakeResponse:
    def __init__(self, fail=False):
        self.fail = fail
        self.checked = False

    def raise_for_status(self):
        self.checked = True
        if self.fail:
            raise requests.HTTPError("500")

    def json(self):
        return {"ok": True}


def _patch(monkeypatch, resp):
    calls = {}

    def fake_get(url, **kwargs):
        calls["url"] = url
        calls.update(kwargs)
        return resp

    monkeypatch.setattr(requests, "get", fake_get)
    return calls


def test_get_json_defaults(monkeypatch):
    resp = FakeResponse()
    calls = _patch(monkeypatch, resp)
    assert http.get_json("http://x", params={"a": 1}, headers={"X-Key": "k"}) == {"ok": True}
    assert calls["timeout"] == 10
    assert calls["params"] == {"a": 1}
    assert calls["headers"]["User-Agent"].startswith("glancebox/")
    assert calls["headers"]["X-Key"] == "k"
    assert resp.checked


def test_get_json_propagates_http_error(monkeypatch):
    _patch(monkeypatch, FakeResponse(fail=True))
    with pytest.raises(requests.HTTPError):
        http.get_json("http://x")


@pytest.mark.parametrize("text,expected", [
    ("Page.goto: net::ERR at http://h:3000/d/x?token=abc&kiosk",
     "Page.goto: net::ERR at http://h:3000/d/x?***"),
    ("401 for url: https://user:pw@example.org/api/states/sensor.a",
     "401 for url: https://***@example.org/api/states/sensor.a"),
    ("see http://a/x#secret and https://b/?k=1.", "see http://a/x?*** and https://b/?***."),
    ("no url here", "no url here"),
    ("broken http://[ and ?a=b", "broken http://[ and ?a=b"),
    ("", ""),
])
def test_redact_urls(text, expected):
    assert http.redact_urls(text) == expected


@pytest.mark.parametrize("text,expected", [
    ("(at https://u@h/p?q=1)", "(at https://***@h/p?***)"),
    ("got 'http://h/x?token=abc'", "got 'http://h/x?***'"),
    ("HTTPS://user:pw@h:1/?a", "HTTPS://***@h:1/?***"),
    ("http://h/x", "http://h/x"),
])
def test_redact_urls_edge_cases(text, expected):
    assert http.redact_urls(text) == expected


@pytest.mark.parametrize("text,expected", [
    ("[http://u:pw@h/?a=1]", "[http://***@h/?***]"),
    ("<http://h/x?a=1>", "<http://h/x?***>"),
    ("with url: /api/x?apikey=SECRET (Caused by X)", "with url: /api/x?*** (Caused by X)"),
    ("with url: /api/x (Caused by X)", "with url: /api/x (Caused by X)"),
])
def test_redact_urls_brackets_and_schemeless(text, expected):
    assert http.redact_urls(text) == expected


@pytest.mark.parametrize("text", ["http://user:pa/ss@h/x", "http://user:p?ss@h/x",
                                  "http://user:p#ss@h/x"])
def test_redact_urls_odd_userinfo(text):
    out = http.redact_urls(text)
    assert "ss" not in out and out.startswith("http://***@h")


def _closed_port() -> int:
    import socket
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_redact_urls_real_requests_connection_error():
    with pytest.raises(requests.ConnectionError) as err:
        http.get_json(f"http://127.0.0.1:{_closed_port()}/api/x", params={"apikey": "SECRET"},
                      timeout=2)
    assert "SECRET" in str(err.value)  # precondition: requests quotes the query
    out = http.redact_urls(str(err.value))
    assert "SECRET" not in out and "url: /api/x?***" in out
