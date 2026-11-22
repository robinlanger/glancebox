import io
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import requests
from PIL import Image

import glancebox.http
from glancebox.config import AppConfig, PageConfig
from glancebox.frames import render_page
from glancebox.pages import PageContext, load_page_types
from glancebox.render import Renderer

PAGES_DIR = Path(__file__).resolve().parents[1]
TZ = ZoneInfo("Europe/Berlin")
NOW = datetime(2026, 11, 14, 14, 5, tzinfo=TZ)
NOW_UTC = NOW.astimezone(UTC)
OPTIONS = {"url": "http://kuma.lan:3001", "slug": "home"}


def stamp(minutes_ago: float) -> str:
    """Kuma's time format: UTC, space separated, with milliseconds."""
    t = NOW_UTC - timedelta(minutes=minutes_ago)
    return t.strftime("%Y-%m-%d %H:%M:%S.") + f"{t.microsecond // 1000:03d}"


def beat(status: int, minutes_ago: float) -> dict:
    return {"status": status, "time": stamp(minutes_ago), "msg": "", "ping": 12}


def build(monitors: dict[int, tuple[str, list[dict], float]]):
    """monitors: id -> (name, beats oldest first, 24 h uptime). Shape per Uptime Kuma 2.0."""
    page = {
        "config": {"slug": "home", "title": "Homelab"},
        "incident": None,
        "maintenanceList": [],
        "publicGroupList": [{
            "id": 1, "name": "All", "weight": 1,
            "monitorList": [{"id": i, "name": n, "sendUrl": 0, "type": "http"}
                            for i, (n, _b, _u) in monitors.items()]}] if monitors else [],
    }
    heartbeat = {
        "heartbeatList": {str(i): b for i, (_n, b, _u) in monitors.items()},
        "uptimeList": {f"{i}_24": u for i, (_n, _b, u) in monitors.items()},
    }
    return page, heartbeat


@pytest.fixture
def kuma():
    return load_page_types([PAGES_DIR])["kuma"]


@pytest.fixture
def serve(monkeypatch):
    calls = []

    def install(page, heartbeat):
        def fake(url, *, params=None, headers=None, timeout=10):
            calls.append(url)
            return heartbeat if "/heartbeat/" in url else page
        monkeypatch.setattr(glancebox.http, "get_json", fake)
        return calls
    return install


def ctx(lang="de"):
    return PageContext(NOW, lang, "Europe/Berlin")


UP = [beat(1, 30), beat(1, 20), beat(1, 10)]


def test_all_up(kuma, serve):
    calls = serve(*build({
        1: ("Router", UP, 1.0), 2: ("NAS", UP, 1.0), 3: ("Pi-hole", UP, 0.997)}))
    data = kuma.fetch(OPTIONS, ctx())
    assert data["state"] == "ok"
    assert data["up"] == data["total"] == 3
    assert data["uptime"] == "99,9 %"
    assert data["down"] == [] and data["more"] == 0 and data["pending"] == 0
    assert data["title"] == "Homelab" and data["clock"] == "14:05"
    assert calls == ["http://kuma.lan:3001/api/status-page/home",
                     "http://kuma.lan:3001/api/status-page/heartbeat/home"]


def test_trailing_slash_and_title_option(kuma, serve):
    calls = serve(*build({1: ("Router", UP, 1.0)}))
    data = kuma.fetch({**OPTIONS, "url": "https://kuma.example/", "title": "Zuhause"}, ctx())
    assert data["title"] == "Zuhause"
    assert calls[0] == "https://kuma.example/api/status-page/home"


def test_english_uptime_format(kuma, serve):
    serve(*build({1: ("Router", UP, 0.999)}))
    assert kuma.fetch(OPTIONS, ctx("en"))["uptime"] == "99.9 %"


def test_two_down_sorted_with_since(kuma, serve):
    serve(*build({
        1: ("Router", UP, 1.0),
        2: ("NAS", [beat(1, 30), beat(0, 12), beat(0, 6)], 0.9),
        3: ("Pi-hole", [beat(1, 30), beat(0, 3)], 0.9),
    }))
    data = kuma.fetch(OPTIONS, ctx())
    assert data["state"] == "down"
    assert data["up"] == 1 and data["total"] == 3
    assert data["down"] == [{"name": "NAS", "since": "12 min"},
                            {"name": "Pi-hole", "since": "3 min"}]


def test_since_hours_and_days(kuma, serve):
    serve(*build({
        1: ("A", [beat(1, 600), beat(0, 3 * 60 + 5)], 0.9),
        2: ("B", [beat(1, 5000), beat(0, 2 * 24 * 60 + 30)], 0.9),
    }))
    data = kuma.fetch(OPTIONS, ctx())
    assert [d["since"] for d in data["down"]] == ["2 d", "3 h"]


def test_since_uses_first_down_after_last_up(kuma, serve):
    serve(*build({1: ("A", [beat(0, 50), beat(1, 40), beat(2, 20), beat(0, 15),
                            beat(0, 5)], 0.5)}))
    assert kuma.fetch(OPTIONS, ctx())["down"] == [{"name": "A", "since": "15 min"}]


def test_more_than_four_down(kuma, serve):
    monitors = {i: (f"M{i}", [beat(1, 60), beat(0, 10 + i)], 0.5) for i in range(1, 7)}
    serve(*build(monitors))
    data = kuma.fetch(OPTIONS, ctx())
    assert len(data["down"]) == 4 and data["more"] == 2
    assert [d["name"] for d in data["down"]] == ["M6", "M5", "M4", "M3"]


def test_pending_and_maintenance_not_down(kuma, serve):
    serve(*build({
        1: ("A", UP, 1.0),
        2: ("B", [beat(1, 30), beat(3, 5)], 1.0),
        3: ("C", [beat(1, 30), beat(2, 5)], 1.0),
    }))
    data = kuma.fetch(OPTIONS, ctx())
    assert data["state"] == "ok"
    assert data["pending"] == 1
    assert data["up"] == 2 and data["total"] == 3 and data["down"] == []


def test_monitor_without_beats_is_pending(kuma, serve):
    serve(*build({1: ("A", UP, 1.0), 2: ("New", [], 1.0)}))
    data = kuma.fetch(OPTIONS, ctx())
    assert data["state"] == "ok" and data["pending"] == 1 and data["up"] == 1


@pytest.mark.parametrize(("lang", "message"), [("de", "Wird geprüft"), ("en", "Being checked")])
def test_only_pending_is_not_ok(kuma, serve, lang, message):
    serve(*build({1: ("A", [beat(2, 5)], 1.0), 2: ("B", [], 1.0), 3: ("C", [beat(2, 1)], 1.0)}))
    data = kuma.fetch(OPTIONS, ctx(lang))
    assert data["state"] == "pending"
    assert data["message"] == message and data["sub"] == "0/3 OK"
    assert data["up"] == 0 and data["pending"] == 3 and data["down"] == []


def test_only_pending_template_orange_not_red():
    from glancebox.frames import _jinja_env

    html = _jinja_env([PAGES_DIR / "kuma"]).get_template("template.html").render(
        title="Homelab", clock="14:05", lang="de", state="pending", up=0, total=3,
        uptime=None, pending=3, down=[], more=0, message="Wird geprüft", sub="0/3 OK")
    assert "ui-tone-warn" in html and "Wird geprüft" in html and "0/3 OK" in html
    assert 'class="ui-hdr"' in html and "ui-hdr ui-alert" not in html  # header not red
    assert 'class="ok"' not in html  # no green check view


def test_down_without_up_beat_uses_ge(kuma, serve):
    serve(*build({1: ("A", [beat(0, 40), beat(0, 20), beat(0, 1)], 0.0)}))
    data = kuma.fetch(OPTIONS, ctx())
    assert data["state"] == "down" and data["up"] == 0
    assert data["down"] == [{"name": "A", "since": "≥ 40 min"}]
    assert data["uptime"] == "0,0 %"


def test_unreachable_gives_error_state(kuma, monkeypatch):
    def boom(*a, **k):
        raise requests.ConnectionError("no route")
    monkeypatch.setattr(glancebox.http, "get_json", boom)
    data = kuma.fetch(OPTIONS, ctx())
    assert data["state"] == "error"
    assert data["message"] == "Keine Verbindung zu Uptime Kuma"
    assert data["sub"] == "Stand 14:05"
    data = kuma.fetch(OPTIONS, ctx("en"))
    assert data["message"] == "Cannot reach Uptime Kuma" and data["sub"] == "As of 14:05"


def test_failure_is_logged(kuma, monkeypatch, caplog):
    def boom(*a, **k):
        raise requests.ConnectionError("no route")
    monkeypatch.setattr(glancebox.http, "get_json", boom)
    with caplog.at_level("WARNING"):
        kuma.fetch(OPTIONS, ctx())
    assert len(caplog.records) == 1
    assert "kuma: status page unavailable: ConnectionError: no route" in caplog.text


def test_failure_log_redacts_urls(kuma, monkeypatch, caplog):
    def boom(*a, **k):
        raise requests.HTTPError("401 for url: http://u:pw@kuma.lan/api/status-page/x?k=abc")
    monkeypatch.setattr(glancebox.http, "get_json", boom)
    with caplog.at_level("WARNING"):
        kuma.fetch(OPTIONS, ctx())
    assert "http://***@kuma.lan/api/status-page/x?***" in caplog.text
    assert "pw" not in caplog.text and "abc" not in caplog.text


def test_parse_error_is_logged(kuma, serve, caplog):
    page, hb = build({1: ("A", UP, 1.0)})
    del page["publicGroupList"][0]["monitorList"][0]["id"]
    serve(page, hb)
    with caplog.at_level("WARNING"):
        assert kuma.fetch(OPTIONS, ctx())["state"] == "error"
    assert "KeyError" in caplog.text


def test_second_request_failure_is_error(kuma, monkeypatch):
    page, _hb = build({1: ("A", UP, 1.0)})

    def fake(url, **k):
        if "/heartbeat/" in url:
            raise requests.HTTPError("502")
        return page
    monkeypatch.setattr(glancebox.http, "get_json", fake)
    assert kuma.fetch(OPTIONS, ctx())["state"] == "error"


def test_empty(kuma, serve):
    serve(*build({}))
    data = kuma.fetch(OPTIONS, ctx())
    assert data["state"] == "empty"
    assert data["message"] == "Keine Monitore auf der Statusseite"
    serve(*build({}))
    assert kuma.fetch(OPTIONS, ctx("en"))["message"] == "No monitors on this status page"


def test_time_formats(kuma, serve):
    """Kuma's space format and ISO 8601 (Z, offset, no zone = UTC) denote the same instant."""
    sinces = []
    for t in ("2026-11-14 13:00:00.000", "2026-11-14T13:00:00.000Z",
              "2026-11-14T14:00:00.000+01:00", "2026-11-14T13:00:00"):
        serve(*build({1: ("A", [beat(1, 90), {"status": 0, "time": t, "msg": ""}], 0.5)}))
        sinces.append(kuma.fetch(OPTIONS, ctx())["down"][0]["since"])
    assert sinces == ["5 min"] * 4


def test_validate(kuma):
    kuma.validate(OPTIONS)
    kuma.validate({"url": "https://kuma.example", "slug": "a-b-1", "title": "x", "lang": "en"})
    for bad in [{}, {"url": "http://k"}, {"slug": "home"},
                {"url": "kuma:3001", "slug": "home"},
                {"url": "ftp://kuma", "slug": "home"},
                {"url": "http://k", "slug": "Home"},
                {"url": "http://k", "slug": "a/b"},
                {"url": "http://k", "slug": ""},
                {**OPTIONS, "lang": "fr"}]:
        with pytest.raises(ValueError):
            kuma.validate(bad)


def test_no_min_refresh(kuma):
    assert kuma.min_refresh == 0


@pytest.mark.browser
async def test_template_renders_ok_and_down(kuma, serve, monkeypatch):
    cfg = AppConfig(interval=30, timezone="Europe/Berlin", lang="de",
                    pages=(), pages_dirs=(PAGES_DIR,))
    page = PageConfig(index=0, type="kuma", options=OPTIONS, duration=30, refresh=30)
    scenarios = {
        "ok": build({1: ("A", UP, 1.0), 2: ("B", UP, 1.0)}),
        "down": build({1: ("A", UP, 1.0),
                       2: ("Ein sehr langer Monitorname der abgeschnitten wird",
                           [beat(1, 30), beat(0, 12)], 0.9)}),
        "unreachable": None,
        "pending": build({1: ("A", [beat(2, 5)], 1.0)}),
    }
    frames = {}
    async with Renderer() as r:
        for name, sc in scenarios.items():
            if sc:
                serve(*sc)
            else:
                def boom(*a, **k):
                    raise requests.ConnectionError("x")
                monkeypatch.setattr(glancebox.http, "get_json", boom)
            out = await render_page(page, kuma, cfg, r, NOW.timestamp())
            img = Image.open(io.BytesIO(out)).convert("RGB")
            assert img.size == (240, 240)
            frames[name] = img
    ok_hdr, down_hdr = frames["ok"].getpixel((120, 4)), frames["down"].getpixel((120, 4))
    assert down_hdr[0] > 120 > down_hdr[2] and ok_hdr[2] > ok_hdr[0]  # red vs blue header
    assert frames["ok"].convert("L").getextrema()[1] > 150
    assert frames["unreachable"].convert("L").getextrema()[1] > 150
    pending_hdr = frames["pending"].getpixel((120, 4))
    assert pending_hdr[2] > pending_hdr[0]  # pending never turns the header red
