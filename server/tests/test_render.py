import io
import random
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from PIL import Image
from playwright.async_api import Error as PlaywrightError

from glancebox.render import MAX_JPEG_BYTES, Renderer, RenderError, browser_env, encode_jpeg


def test_encode_jpeg_baseline_and_size():
    rnd = random.Random(1)
    img = Image.frombytes("RGB", (240, 240), bytes(rnd.randrange(256) for _ in range(240 * 240 * 3)))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    out = encode_jpeg(buf.getvalue())
    assert len(out) <= MAX_JPEG_BYTES
    res = Image.open(io.BytesIO(out))
    assert not res.info.get("progressive")
    assert res.size == (240, 240)


@pytest.mark.browser
async def test_render_html_umlauts():
    async with Renderer() as r:
        out = await r.render_html("<p>Grüße</p>")
    img = Image.open(io.BytesIO(out))
    assert img.format == "JPEG"
    assert img.size == (240, 240)


@pytest.mark.browser
async def test_render_url_timeout_raises():
    class Slow(BaseHTTPRequestHandler):
        def do_GET(self):
            time.sleep(5)
            self.send_response(200)
            self.end_headers()

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), Slow)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        async with Renderer() as r:
            t0 = time.monotonic()
            with pytest.raises(RenderError):
                await r.render_url(f"http://127.0.0.1:{srv.server_port}/", 0, None, 1)
            assert time.monotonic() - t0 < 3
    finally:
        srv.shutdown()


@pytest.mark.browser
async def test_render_url_wait_ms_exceeds_timeout_succeeds():
    class Fast(BaseHTTPRequestHandler):
        def do_GET(self):
            body = b"<p>ok</p>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), Fast)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        async with Renderer() as r:
            out = await r.render_url(f"http://127.0.0.1:{srv.server_port}/", 4000, None, 1)
        assert Image.open(io.BytesIO(out)).size == (240, 240)
    finally:
        srv.shutdown()


@pytest.mark.browser
async def test_render_relaunches_dead_browser():
    async with Renderer() as r:
        await r._browser.close()  # simulates a crashed Chromium
        assert not r.healthy()
        out = await r.render_html("<p>again</p>")
        assert r.healthy()
    assert Image.open(io.BytesIO(out)).format == "JPEG"


def _serve(body: bytes, content_type: str, seen: list[str]) -> HTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            seen.append(self.path)
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


@pytest.mark.browser
async def test_render_url_blocks_internal_target():
    internal_seen: list[str] = []
    internal = _serve(b"", "image/png", internal_seen)
    page_seen: list[str] = []
    html = f'<img src="http://localhost:{internal.server_port}/x.png"><p>hi</p>'.encode()
    page = _serve(html, "text/html", page_seen)
    try:
        async with Renderer() as r:
            out = await r.render_url(f"http://127.0.0.1:{page.server_port}/", 0, None, 5)
        assert Image.open(io.BytesIO(out)).format == "JPEG"
        assert page_seen  # the page's own host stays reachable
        assert internal_seen == []
    finally:
        page.shutdown()
        internal.shutdown()


@pytest.mark.browser
async def test_render_html_blocks_loopback():
    seen: list[str] = []
    srv = _serve(b"", "image/png", seen)
    try:
        async with Renderer() as r:
            await r.render_html(f'<img src="http://127.0.0.1:{srv.server_port}/x.png">')
        assert seen == []
    finally:
        srv.shutdown()


class _DeadBrowser:
    def is_connected(self):
        return False

    async def close(self):
        pass


class _FailingChromium:
    async def launch(self, **kwargs):
        raise RuntimeError("no chromium")


class _FakePlaywright:
    chromium = _FailingChromium()


def test_browser_env_is_allowlist():
    env = browser_env({"PATH": "/usr/bin", "HOME": "/home/pwuser", "TZ": "Europe/Berlin",
                       "LC_ALL": "C.UTF-8", "XDG_CACHE_HOME": "/tmp/c", "FONTCONFIG_PATH": "/f",
                       "SUPERVISOR_TOKEN": "tok", "ANTHROPIC_ADMIN_KEY": "sk", "LD_PRELOAD": "x",
                       "GLANCEBOX_PUSH_KEY": "p"})
    assert set(env) == {"PATH", "HOME", "TZ", "LC_ALL", "XDG_CACHE_HOME", "FONTCONFIG_PATH"}
    assert env["PATH"] == "/usr/bin"


class _LiveBrowser:
    def is_connected(self):
        return True

    async def close(self):
        pass


class _SandboxlessChromium:
    def __init__(self, sandbox_works=False):
        self.calls = []
        self.sandbox_works = sandbox_works

    async def launch(self, **kwargs):
        self.calls.append(kwargs)
        if kwargs["chromium_sandbox"] and not self.sandbox_works:
            raise PlaywrightError("No usable sandbox!")
        return _LiveBrowser()


class _SandboxlessPlaywright:
    def __init__(self, sandbox_works=False):
        self.chromium = _SandboxlessChromium(sandbox_works)


async def test_sandbox_falls_back_once(caplog, monkeypatch):
    monkeypatch.setenv("SUPERVISOR_TOKEN", "tok")
    r = Renderer()
    r._pw = _SandboxlessPlaywright()
    assert r.sandboxed is None
    await r._launch()
    assert r.sandboxed is False
    assert [k["chromium_sandbox"] for k in r._pw.chromium.calls] == [True, False]
    assert all("SUPERVISOR_TOKEN" not in k["env"] for k in r._pw.chromium.calls)
    assert sum("sandbox" in rec.message.lower() for rec in caplog.records) == 1
    await r._launch()  # relaunch does not retry the sandbox, no second warning
    assert r._pw.chromium.calls[-1]["chromium_sandbox"] is False
    assert len(r._pw.chromium.calls) == 3
    assert sum("sandbox" in rec.message.lower() for rec in caplog.records) == 1


async def test_sandbox_used_when_available(caplog, monkeypatch):
    caplog.set_level("INFO")
    r = Renderer()
    r._pw = _SandboxlessPlaywright(sandbox_works=True)
    await r._launch()
    assert r.sandboxed is True
    assert [k["chromium_sandbox"] for k in r._pw.chromium.calls] == [True]
    await r._launch()
    assert [k["chromium_sandbox"] for k in r._pw.chromium.calls] == [True, True]


async def test_render_relaunch_failure_is_render_error():
    r = Renderer()
    r._pw, r._browser = _FakePlaywright(), _DeadBrowser()
    with pytest.raises(RenderError, match="cannot restart Chromium"):
        await r.render_html("<p>x</p>")
    assert not r.healthy()
