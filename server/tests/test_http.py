import pytest
import requests

from glancebox import http


class FakeResponse:
    def __init__(self, fail=False, status_code=200, headers=None, chunks=(), on_chunk=None):
        self.fail = fail
        self.checked = False
        self.status_code = status_code
        self.headers = headers or {}
        self.chunks = list(chunks)
        self.on_chunk = on_chunk
        self.iterated = False
        self.chunks_read = 0
        self.chunk_size = None
        self.closed = False
        self.json_called = False

    def raise_for_status(self):
        self.checked = True
        if self.fail:
            raise requests.HTTPError("500")

    def json(self):
        self.json_called = True
        return {"ok": True}

    def iter_content(self, chunk_size):
        self.iterated = True
        self.chunk_size = chunk_size
        for chunk in self.chunks:
            self.chunks_read += 1
            if self.on_chunk:
                self.on_chunk()
            yield chunk

    def close(self):
        self.closed = True


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



def test_get_json_passes_auth_and_keeps_defaults(monkeypatch):
    calls = _patch(monkeypatch, FakeResponse())
    http.get_json("http://x", auth=("u", "p"))
    assert calls["auth"] == ("u", "p")
    calls = _patch(monkeypatch, FakeResponse())
    http.get_json("http://x")
    assert calls["auth"] is None


def test_get_json_204_is_none(monkeypatch):
    resp = FakeResponse(status_code=204)
    _patch(monkeypatch, resp)
    assert http.get_json("http://x") is None
    assert not resp.json_called


def test_get_bytes_ok(monkeypatch):
    resp = FakeResponse(headers={"Content-Type": "image/png; charset=binary"},
                        chunks=[b"\x89PNG", b"rest"])
    calls = _patch(monkeypatch, resp)
    auth = ("maker", "pw")
    assert http.get_bytes("http://x/img", headers={"X-Api-Key": "k"}, timeout=5,
                          max_bytes=1024, auth=auth) == (b"\x89PNGrest", "image/png")
    assert calls["stream"] is True
    assert calls["allow_redirects"] is False
    assert calls["timeout"] == 5
    assert calls["auth"] == auth
    assert calls["headers"]["User-Agent"].startswith("glancebox/")
    assert calls["headers"]["X-Api-Key"] == "k"
    assert resp.chunk_size == 8192
    assert resp.closed


@pytest.mark.parametrize("headers", [
    {"Content-Type": "text/html"},
    {"Content-Type": "image/qoi"},
    {"Content-Type": "image/svg+xml"},
    {},
])
def test_get_bytes_rejects_other_types(monkeypatch, headers):
    resp = FakeResponse(headers=headers, chunks=[b"x"])
    _patch(monkeypatch, resp)
    with pytest.raises(ValueError, match="type"):
        http.get_bytes("http://x", max_bytes=1024)
    assert not resp.iterated
    assert resp.closed


def test_get_bytes_stops_at_limit(monkeypatch):
    resp = FakeResponse(headers={"Content-Type": "image/jpeg", "Content-Length": "600000"},
                        chunks=[b"x" * 100_000] * 10)
    _patch(monkeypatch, resp)
    with pytest.raises(ValueError, match="large"):
        http.get_bytes("http://x", max_bytes=524288)
    assert resp.chunks_read == 0
    assert resp.closed

    resp = FakeResponse(headers={"Content-Type": "image/jpeg"}, chunks=[b"x" * 100_000] * 10)
    _patch(monkeypatch, resp)
    with pytest.raises(ValueError, match="large"):
        http.get_bytes("http://x", max_bytes=524288)
    assert resp.chunks_read <= 6
    assert resp.closed


def test_get_bytes_total_time_is_bounded(monkeypatch):
    clock = [1000.0]

    def tick():
        clock[0] += 3

    monkeypatch.setattr(http.time, "monotonic", lambda: clock[0])
    resp = FakeResponse(headers={"Content-Type": "image/png"}, chunks=[b"x"] * 10, on_chunk=tick)
    _patch(monkeypatch, resp)
    with pytest.raises(ValueError, match="slow"):
        http.get_bytes("http://x", timeout=5, max_bytes=1024)
    assert resp.chunks_read < 10
    assert resp.closed


def test_get_bytes_redirect_is_an_error(monkeypatch):
    resp = FakeResponse(status_code=302, headers={"Content-Type": "image/png",
                                                  "Location": "http://elsewhere/"})
    _patch(monkeypatch, resp)
    with pytest.raises(requests.HTTPError):
        http.get_bytes("http://x", max_bytes=1024)
    assert not resp.iterated
    assert resp.closed

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
    assert "ss" not in out and out.startswith("http://***")


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


@pytest.mark.parametrize("text,expected,leaks", [
    ("http://h/x?email=me@mail.example.org&k=SECRET", "http://***",
     ("SECRET", "mail.example.org", "email")),
    ("http://h/x?token=abc@def", "http://***", ("abc", "def")),
    ("http://h/x#frag@tail", "http://***", ("frag", "tail")),
    ("see http://h/x?e=a@b&k=SECRET.", "see http://***.", ("SECRET", "a@b", "&k")),
])
def test_redact_urls_at_in_query_or_fragment(text, expected, leaks):
    out = http.redact_urls(text)
    assert out == expected
    assert not any(leak in out for leak in leaks)
