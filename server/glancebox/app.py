"""HTTP API polled by the device, plus the preview UI."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import secrets
import time
from collections.abc import Callable
from datetime import datetime
from zoneinfo import ZoneInfo

import jinja2
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse

from . import __version__
from .config import AppConfig
from .frames import TEMPLATES_DIR, Frame, FrameStore, run_worker
from .pages import PageType, load_page_types, merge_push_keys
from .push import CHANNEL_RE, MAX_BODY, PushInbox
from .render import Renderer
from .schedule import clamp_next_in, select

log = logging.getLogger(__name__)

ERROR_NEXT_IN = 10
_env = jinja2.Environment(loader=jinja2.FileSystemLoader(str(TEMPLATES_DIR)), autoescape=True)


def _etag_matches(header: str | None, etag: str) -> bool:
    if not header:
        return False
    for part in header.split(","):
        part = part.strip()
        part = part.removeprefix("W/")
        if part.strip('"') == etag:
            return True
    return False


def on_worker_done(task: asyncio.Task, exit_process: Callable[[int], object] = os._exit) -> None:
    """Done callback of the render worker: a dead worker means no page is ever refreshed
    again, so log why and exit non-zero; the container restart policy brings us back.
    Cancellation is the normal shutdown path and is ignored."""
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        log.critical("render worker died, exiting", exc_info=exc)
    else:
        log.critical("render worker died (returned), exiting")
    exit_process(1)


def _bearer_ok(header: str | None, key: str) -> bool:
    """True if ``header`` is ``Bearer <key>``; constant-time in the key comparison."""
    scheme, _, token = (header or "").partition(" ")
    # Compare even on a bad scheme so the timing does not tell the two apart.
    match = secrets.compare_digest(token.encode("utf-8"), key.encode("utf-8"))
    return scheme == "Bearer" and match


async def _read_limited(request: Request, limit: int) -> bytes | None:
    """The request body, or None as soon as it grows beyond ``limit`` bytes."""
    buf = bytearray()
    async for chunk in request.stream():
        buf += chunk
        if len(buf) > limit:
            return None
    return bytes(buf)


INGRESS_PEER = "172.30.32.2"  # the Supervisor; Ingress requests come only from here
SEEN_FRESH_S = 120  # a display that fetched within this time counts as connected


class DisplaySeen:
    """When a display last fetched a frame (RAM only), shown on the add-on page."""

    def __init__(self) -> None:
        self.last: float | None = None

    def mark(self, now: float) -> None:
        self.last = now


def _ago(seconds: int) -> str:
    if seconds < 90:
        return f"{seconds} s ago"
    if seconds < 5400:
        return f"{round(seconds / 60)} min ago"
    return f"{round(seconds / 3600)} h ago"


def _overview_csp(nonce: str, framable: bool) -> str:
    """CSP of the overview: inline styles, previews from this origin, and only the one inline
    script that carries ``nonce``. Home Assistant shows the add-on page in an iframe, so
    ``framable`` leaves out ``frame-ancestors``."""
    csp = (f"default-src 'none'; img-src 'self'; style-src 'unsafe-inline'; "
           f"script-src 'nonce-{nonce}'; base-uri 'none'; form-action 'none'")
    return csp if framable else csp + "; frame-ancestors 'none'"


def _add_overview(app: FastAPI, cfg: AppConfig, store: FrameStore, clock: Callable[[], float],
                  seen: DisplaySeen | None = None, *, framable: bool = False,
                  **page_vars) -> None:
    """Routes ``/`` (overview) and ``/preview/{index}.jpg``. URLs in the page are relative so
    they also work under the Ingress path prefix."""

    @app.get("/preview/{index}.jpg")
    def preview(index: int) -> Response:
        current = store.get(index, clock())
        if current is None:
            raise HTTPException(404, "not rendered yet")
        return Response(current.jpeg, media_type="image/jpeg",
                        headers={"Cache-Control": "no-store",
                                 "X-Content-Type-Options": "nosniff"})

    @app.get("/", response_class=HTMLResponse)
    def index() -> HTMLResponse:
        now = clock()
        rows = []
        for p in cfg.pages:
            current = store.get(p.index, now)
            rows.append({
                "index": p.index, "type": p.type, "error": store.last_error(p.index),
                "age": None if current is None else int(now - current.rendered_at),
                "has_frame": current is not None,
            })
        seen_age = None if seen is None or seen.last is None else max(0, int(now - seen.last))
        nonce = secrets.token_urlsafe(16)
        html = _env.get_template("index.html").render(
            pages=rows, version=__version__, seen_fresh=seen_age is not None
            and seen_age <= SEEN_FRESH_S, seen_ago=None if seen_age is None else _ago(seen_age),
            nonce=nonce, **page_vars)
        return HTMLResponse(html, headers={
            "Content-Security-Policy": _overview_csp(nonce, framable),
            "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer"})


def create_ingress_app(cfg: AppConfig, store: FrameStore, clock: Callable[[], float] = time.time,
                       *, connect: str | None, config_note: str | None,
                       starter_yaml: str | None = None,
                       seen: DisplaySeen | None = None) -> FastAPI:
    """Overview for the Home Assistant sidebar (Ingress), with the display address to copy.
    Answers only the Supervisor; HA has already checked the user's login."""
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware("http")
    async def only_supervisor(request: Request, call_next):
        if request.client is None or request.client.host != INGRESS_PEER:
            return Response("forbidden", status_code=403)
        return await call_next(request)

    _add_overview(app, cfg, store, clock, seen, framable=True, addon=True, connect=connect,
                  config_note=config_note, starter_yaml=starter_yaml)
    return app


def create_app(cfg: AppConfig, store: FrameStore, clock: Callable[[], float] = time.time, *,
               types: dict[str, PageType] | None = None, start_worker: bool = True,
               ui: bool = True, seen: DisplaySeen | None = None) -> FastAPI:
    """The LAN app. ``ui=False`` (add-on mode) leaves out the overview and previews; the add-on
    serves those only through Ingress (see ``create_ingress_app``)."""
    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI):
        if not start_worker:
            yield
            return
        page_types = types if types is not None else load_page_types(cfg.pages_dirs)
        async with Renderer() as renderer:
            await store.build_error_frame(renderer)
            task = asyncio.create_task(
                run_worker(cfg, page_types, renderer, store, app.state.inbox))
            task.add_done_callback(on_worker_done)
            app.state.renderer, app.state.worker_task = renderer, task
            try:
                yield
            finally:
                task.remove_done_callback(on_worker_done)
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.renderer = app.state.worker_task = None  # set by lifespan when the worker runs
    # Pushed data lives in RAM only. The allowlist comes from the page types' PUSH_KEYS;
    # without explicit types (tests) nothing can be pushed.
    app.state.inbox = inbox = PushInbox()
    push_allow = merge_push_keys(types) if types is not None else {}
    durations = [p.duration for p in cfg.pages]
    tz = ZoneInfo(cfg.timezone)

    def jpeg_response(request: Request, frame: Frame, next_in: int) -> Response:
        headers = {"ETag": f'"{frame.etag}"', "X-Next-In": str(next_in),
                   "Cache-Control": "no-store",
                   # Device clock for night mode: local wall time in the configured zone.
                   "X-Local-Time": datetime.fromtimestamp(clock(), tz).strftime("%H:%M:%S")}
        if _etag_matches(request.headers.get("if-none-match"), frame.etag):
            return Response(status_code=304, headers=headers)
        return Response(frame.jpeg, media_type="image/jpeg", headers=headers)

    @app.get("/api/v1/frame")
    def frame(request: Request, id: str = "", fw: str = "") -> Response:
        log.debug("frame request id=%s fw=%s", id, fw)
        now = clock()
        if seen is not None:
            seen.mark(now)
        index, to_switch = select(durations, store.available(now), now)
        if index is None:
            return jpeg_response(request, store.error_frame, ERROR_NEXT_IN)
        current = store.get(index, now)
        if current is None:  # went stale between the two calls
            return jpeg_response(request, store.error_frame, ERROR_NEXT_IN)
        last = store.last_attempt(index)
        until_refresh = 0.0 if last is None else max(
            0.0, last + cfg.pages[index].refresh - now)
        return jpeg_response(request, current, clamp_next_in(min(to_switch, until_refresh)))

    if ui:
        _add_overview(app, cfg, store, clock)

    @app.post("/api/v1/push/{channel}", status_code=204)
    async def push(channel: str, request: Request) -> Response:
        # Order matters: never reveal more than needed to an unauthenticated client.
        # The body and the key are never logged.
        if not cfg.push_key:
            raise HTTPException(404)
        allowed = push_allow.get(channel)
        if allowed is None or not CHANNEL_RE.fullmatch(channel):
            raise HTTPException(404)
        if not _bearer_ok(request.headers.get("authorization"), cfg.push_key):
            raise HTTPException(401, headers={"WWW-Authenticate": "Bearer"})
        declared = request.headers.get("content-length", "")
        if declared.isascii() and declared.isdigit() and int(declared) > MAX_BODY:
            raise HTTPException(413)
        raw = await _read_limited(request, MAX_BODY)
        if raw is None:
            raise HTTPException(413)
        try:
            body = json.loads(raw)
        except (ValueError, RecursionError):
            body = None
        if not isinstance(body, dict):
            raise HTTPException(422, "body must be a JSON object")
        inbox.put(channel, {k: body[k] for k in allowed if k in body}, clock())
        return Response(status_code=204)

    @app.get("/healthz")
    def healthz() -> JSONResponse:
        task, renderer = app.state.worker_task, app.state.renderer
        worker_ok = task is None or not task.done()
        browser_ok = renderer is None or renderer.healthy()
        body = {"version": __version__, "pages_ok": sum(store.available(clock())),
                "worker_ok": worker_ok, "browser_ok": browser_ok}
        return JSONResponse(body, status_code=200 if worker_ok and browser_ok else 503)

    return app
