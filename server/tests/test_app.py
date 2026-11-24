import asyncio
import logging
import re
import subprocess
import sys
import time

from fastapi import FastAPI
from fastapi.testclient import TestClient

from glancebox.__main__ import uvicorn_config
from glancebox.app import create_app, on_worker_done
from glancebox.config import AppConfig, PageConfig
from glancebox.frames import FrameStore

NOW = 1_000_000.0


def make_cfg() -> AppConfig:
    pages = (PageConfig(0, "url", {}, 30, 30), PageConfig(1, "url", {}, 30, 30))
    return AppConfig(30, "Europe/Berlin", "de", pages, ())


def make_client(store=None, now=NOW):
    cfg = make_cfg()
    store = store or FrameStore(2)
    return TestClient(create_app(cfg, store, lambda: now, start_worker=False)), store


def filled_store_at(t: float) -> FrameStore:
    store = FrameStore(2)
    store.put(0, b"jpeg0", t - 1)
    store.put(1, b"jpeg1", t - 1)
    store.mark_attempt(0, t - 1, None)
    store.mark_attempt(1, t - 1, None)
    return store


def filled_store() -> FrameStore:
    return filled_store_at(NOW)


def test_frame_200_with_headers():
    client, _ = make_client(filled_store())
    r = client.get("/api/v1/frame?id=abc&fw=0.1.0")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/jpeg"
    assert r.headers["etag"]
    assert 2 <= int(r.headers["x-next-in"]) <= 30
    assert r.headers["cache-control"] == "no-store"


def test_frame_304_on_matching_etag():
    client, _ = make_client(filled_store())
    first = client.get("/api/v1/frame")
    r = client.get("/api/v1/frame", headers={"If-None-Match": first.headers["etag"]})
    assert r.status_code == 304
    assert r.headers["etag"] == first.headers["etag"]
    assert 2 <= int(r.headers["x-next-in"]) <= 30


def test_stale_etag_after_restart_gets_200():
    client, _ = make_client(filled_store())
    other, _ = make_client(filled_store())
    etag = other.get("/api/v1/frame").headers["etag"]
    assert client.get("/api/v1/frame", headers={"If-None-Match": etag}).status_code == 200


def test_frame_all_pages_down_returns_error_frame():
    client, _ = make_client(FrameStore(2))
    r = client.get("/api/v1/frame")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/jpeg"
    assert r.headers["x-next-in"] == "10"


def test_preview_and_healthz_and_index():
    client, store = make_client(filled_store())
    store.mark_attempt(1, NOW - 1, "RuntimeError: boom")
    assert client.get("/preview/0.jpg").content == b"jpeg0"
    assert client.get("/preview/5.jpg").status_code == 404
    h = client.get("/healthz").json()
    assert h["pages_ok"] == 2 and h["version"]
    html = client.get("/").text
    assert "preview/0.jpg" in html and "boom" in html


def test_cli_bad_config_exits_2(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text("pages:\n  - type: nonexistent\n")
    r = subprocess.run([sys.executable, "-m", "glancebox", "render", "0", "-o",
                        str(tmp_path / "o.png"), "--config", str(cfg)],
                       check=False, capture_output=True, text=True)
    assert r.returncode == 2
    assert "pages[0]" in r.stderr


class _FakeTask:
    def __init__(self, done=False, cancelled=False, exc=None):
        self._done, self._cancelled, self._exc = done, cancelled, exc

    def done(self):
        return self._done

    def cancelled(self):
        return self._cancelled

    def exception(self):
        return self._exc


class _FakeRenderer:
    def __init__(self, ok):
        self.ok = ok

    def healthy(self):
        return self.ok


def test_healthz_503_when_worker_dead():
    client, _ = make_client(filled_store())
    client.app.state.worker_task = _FakeTask(done=True, exc=RuntimeError("boom"))
    client.app.state.renderer = _FakeRenderer(True)
    r = client.get("/healthz")
    assert r.status_code == 503
    assert r.json()["worker_ok"] is False


def test_healthz_503_when_browser_disconnected():
    client, _ = make_client(filled_store())
    client.app.state.worker_task = _FakeTask()
    client.app.state.renderer = _FakeRenderer(False)
    r = client.get("/healthz")
    assert r.status_code == 503
    assert r.json()["browser_ok"] is False


def test_healthz_200_when_worker_and_browser_alive():
    client, _ = make_client(filled_store())
    client.app.state.worker_task = _FakeTask()
    client.app.state.renderer = _FakeRenderer(True)
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["worker_ok"] is True and r.json()["browser_ok"] is True


def test_worker_death_logs_and_exits_nonzero(caplog):
    codes = []
    on_worker_done(_FakeTask(done=True, exc=RuntimeError("boom")), exit_process=codes.append)
    assert codes == [1]
    assert "render worker died" in caplog.text and "boom" in caplog.text


def test_worker_cancelled_at_shutdown_does_not_exit():
    codes = []
    on_worker_done(_FakeTask(done=True, cancelled=True), exit_process=codes.append)
    assert codes == []


def test_worker_returning_is_also_fatal(caplog):
    codes = []
    on_worker_done(_FakeTask(done=True), exit_process=codes.append)
    assert codes == [1]


def test_frame_has_local_time_header():
    # NOW = 1970-01-12 13:46:40 UTC -> 14:46:40 Europe/Berlin (CET)
    client, _ = make_client(filled_store())
    assert client.get("/api/v1/frame").headers["x-local-time"] == "14:46:40"


def test_local_time_on_304_and_error_frame():
    client, _ = make_client(filled_store())
    etag = client.get("/api/v1/frame").headers["etag"]
    r = client.get("/api/v1/frame", headers={"If-None-Match": etag})
    assert r.status_code == 304
    assert r.headers["x-local-time"] == "14:46:40"
    empty, _ = make_client(FrameStore(2))
    assert empty.get("/api/v1/frame").headers["x-local-time"] == "14:46:40"


def test_local_time_respects_dst():
    # 2026-07-01 00:30:00 UTC -> 02:30:00 CEST
    t = 1782865800.0
    client, _ = make_client(filled_store_at(t), now=t)
    assert client.get("/api/v1/frame").headers["x-local-time"] == "02:30:00"


def test_lifespan_passes_push_inbox_to_worker(monkeypatch):
    from glancebox import app as app_mod

    seen = {}

    class NoBrowser:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

    async def fake_worker(cfg, types, renderer, store, inbox):
        seen["inbox"] = inbox
        await asyncio.Event().wait()

    async def no_error_frame(renderer):
        return None

    monkeypatch.setattr(app_mod, "Renderer", NoBrowser)
    monkeypatch.setattr(app_mod, "run_worker", fake_worker)
    store = FrameStore(2)
    monkeypatch.setattr(store, "build_error_frame", no_error_frame)
    application = create_app(make_cfg(), store, lambda: NOW, types={})
    with TestClient(application):
        for _ in range(100):
            if "inbox" in seen:
                break
            time.sleep(0.01)
    assert seen["inbox"] is application.state.inbox


def test_push_never_logs_body_or_key(caplog):
    from glancebox.pages import PageType

    caplog.set_level(logging.DEBUG)
    key = "secret-key-123456789"
    t = PageType("ai", "script", push_keys={"claude": ("rate_limits",)})
    cfg = AppConfig(30, "Europe/Berlin", "de", (), (), key)
    client = TestClient(create_app(cfg, FrameStore(0), lambda: NOW, types={"ai": t},
                                   start_worker=False))
    for auth in (key, "wrong-key-0000000000"):
        client.post("/api/v1/push/claude", json={"rate_limits": "sensitive-body"},
                    headers={"Authorization": f"Bearer {auth}"})
    assert "sensitive-body" not in caplog.text
    assert key not in caplog.text


def ingress_client(peer="172.30.32.2", connect="http://192.168.1.5:8090", note=None,
                   starter=None):
    from glancebox.app import create_ingress_app
    app = create_ingress_app(make_cfg(), filled_store(), lambda: NOW, connect=connect,
                             config_note=note, starter_yaml=starter)
    return TestClient(app, client=(peer, 5000))


def test_ui_false_hides_overview():
    client = TestClient(create_app(make_cfg(), filled_store(), lambda: NOW, start_worker=False,
                                   ui=False))
    assert client.get("/").status_code == 404
    assert client.get("/preview/0.jpg").status_code == 404
    assert client.get("/api/v1/frame").status_code == 200


def test_overview_uses_relative_preview_urls():
    client, _ = make_client(filled_store())
    html = client.get("/").text
    assert 'src="preview/0.jpg"' in html and 'src="/preview' not in html


def test_ingress_rejects_other_peers():
    assert ingress_client(peer="192.168.1.9").get("/").status_code == 403
    assert ingress_client(peer="192.168.1.9").get("/preview/0.jpg").status_code == 403


def test_ingress_shows_connect_box():
    client = ingress_client()
    r = client.get("/")
    assert r.status_code == 200 and "http://192.168.1.5:8090" in r.text
    assert client.get("/preview/0.jpg").content == b"jpeg0"


def test_ingress_without_address_and_with_note():
    html = ingress_client(connect=None, note="starter playlist could not be saved").get("/").text
    assert "could not be determined" in html
    assert "starter playlist could not be saved" in html


def test_ingress_has_no_frame_or_push():
    client = ingress_client()
    assert client.get("/api/v1/frame").status_code == 404
    assert client.post("/api/v1/push/claude", json={}).status_code in (404, 405)


def test_ingress_shows_starter_yaml_to_copy_when_not_saved():
    html = ingress_client(note="could not be saved", starter="pages:\n  - type: clock\n").get("/").text
    assert '<pre id="starter">' in html and "type: clock" in html


def test_copy_works_without_clipboard_api():
    # navigator.clipboard is missing on plain-http pages (HA is often opened over http).
    html = ingress_client().get("/").text
    assert "navigator.clipboard" in html and "getSelection" in html


def test_display_seen_tracks_frame_requests_for_ingress():
    from glancebox.app import DisplaySeen, create_ingress_app
    seen = DisplaySeen()
    store = filled_store()
    lan = TestClient(create_app(make_cfg(), store, lambda: NOW, start_worker=False, ui=False,
                                seen=seen))
    ingress = TestClient(create_ingress_app(make_cfg(), store, lambda: NOW + 4, connect="http://x:8090",
                                            config_note=None, seen=seen),
                         client=("172.30.32.2", 5000))
    assert "Waiting for your display" in ingress.get("/").text
    lan.get("/api/v1/frame")
    html = ingress.get("/").text
    assert "Display connected" in html and "4 s ago" in html


def test_display_seen_goes_stale():
    from glancebox.app import DisplaySeen, create_ingress_app
    seen = DisplaySeen()
    seen.mark(NOW - 600)
    ingress = TestClient(create_ingress_app(make_cfg(), filled_store(), lambda: NOW,
                                            connect="http://x:8090", config_note=None, seen=seen),
                         client=("172.30.32.2", 5000))
    html = ingress.get("/").text
    assert "Waiting for your display" in html and "10 min ago" in html


def test_uvicorn_config_ignores_proxy_headers():
    cfg = uvicorn_config(FastAPI(), "0.0.0.0", 8080)
    assert cfg.proxy_headers is False and cfg.server_header is False


def test_serve_ctrl_c_exits_cleanly(monkeypatch, tmp_path):
    import argparse

    import uvicorn

    from glancebox import __main__ as cli
    from glancebox import addon

    class InterruptedServer:
        def __init__(self, config):
            pass

        def run(self):
            raise KeyboardInterrupt

    monkeypatch.setattr(uvicorn, "Server", InterruptedServer)
    monkeypatch.setattr(addon, "is_addon", lambda environ: False)
    config = tmp_path / "config.yaml"
    config.write_text("pages:\n  - type: url\n    url: http://example.org/\n")
    args = argparse.Namespace(config=str(config), host="127.0.0.1", port=0)
    assert cli._serve(args) == 0


def test_overview_security_headers():   # Docker mode
    client, _ = make_client(filled_store())
    r = client.get("/")
    csp = r.headers["content-security-policy"]
    assert "default-src 'none'" in csp and "frame-ancestors 'none'" in csp
    assert "'unsafe-inline'" not in csp.split("script-src")[1].split(";")[0]
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["referrer-policy"] == "no-referrer"


def test_preview_sends_nosniff():
    client, _ = make_client(filled_store())
    assert client.get("/preview/0.jpg").headers["x-content-type-options"] == "nosniff"


def test_ingress_csp_allows_framing_by_home_assistant():
    ingress = ingress_client()
    first, second = ingress.get("/"), ingress.get("/")
    csp = first.headers["content-security-policy"]
    assert "frame-ancestors" not in csp
    nonce = re.search(r"script-src 'nonce-([^']+)'", csp).group(1)
    assert f'<script nonce="{nonce}">' in first.text
    assert nonce not in second.headers["content-security-policy"]  # fresh per response


ANIM = "1;0b0d12;232a38;64,67,85,15,r,ffb020,48"


def anim_store() -> FrameStore:
    store = filled_store()
    store.put(1, b"jpeg1", NOW - 1, anim=ANIM)
    return store


def test_x_anim_on_200_and_304_only_for_its_frame():
    client, _ = make_client(anim_store(), now=NOW)          # NOW % 60 == 40: page 1
    first = client.get("/api/v1/frame")
    assert first.status_code == 200 and first.headers["x-anim"] == ANIM
    again = client.get("/api/v1/frame", headers={"If-None-Match": first.headers["etag"]})
    assert again.status_code == 304 and again.headers["x-anim"] == ANIM
    other, _ = make_client(anim_store(), now=NOW + 30)      # page 0 has no description
    assert "x-anim" not in other.get("/api/v1/frame").headers


def test_no_x_anim_on_the_error_frame():
    client, _ = make_client(FrameStore(2))
    assert "x-anim" not in client.get("/api/v1/frame").headers


def test_anim_does_not_change_the_etag():
    store = FrameStore(2)
    store.put(0, b"jpeg0", NOW)
    plain = store.get(0, NOW).etag
    store.put(0, b"jpeg0", NOW, anim=ANIM)
    assert store.get(0, NOW).etag == plain


def test_response_head_stays_below_the_device_limit():
    store = filled_store()
    store.put(1, b"jpeg1", NOW - 1, anim="1" * 160)         # as long as the limit allows
    r = make_client(store)[0].get("/api/v1/frame")
    head = 17 + sum(len(k) + len(v) + 4 for k, v in r.headers.items()) + 2
    assert head + 60 <= 1024                                # 60: date and server from uvicorn
