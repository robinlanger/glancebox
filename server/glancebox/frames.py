"""In-memory frame cache and the background worker that keeps it fresh."""

from __future__ import annotations

import asyncio
import hashlib
import io
import logging
import secrets
import time
import traceback
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import jinja2
from PIL import Image

from .anim import Anim, encode
from .config import AppConfig, PageConfig
from .http import redact_urls
from .pages import PageContext, PageType
from .push import PushInbox
from .render import SIZE, font_face_css, serif_face_css

log = logging.getLogger(__name__)

STALE_AFTER_S = 600
FETCH_TIMEOUT_S = 20
TEMPLATES_DIR = Path(__file__).parent / "templates"
ANIM_KEY = "_anim"  # reserved key in a page's fetch() result: the animation description


@dataclass(frozen=True)
class Frame:
    jpeg: bytes
    etag: str
    rendered_at: float
    anim: str | None = None  # finished, checked X-Anim header value; not part of the ETag
    data: dict | None = None  # fetch() result without ANIM_KEY, for SKIP_UNCHANGED


def _static_error_jpeg() -> bytes:
    """Plain dark 240x240 JPEG, used until the rendered error frame exists."""
    buf = io.BytesIO()
    Image.new("RGB", (SIZE, SIZE), (24, 24, 28)).save(buf, "JPEG", quality=85, progressive=False)
    return buf.getvalue()


class FrameStore:
    def __init__(self, page_count: int) -> None:
        self._page_count = page_count
        # Random per store (= per process start) so a restarted server never answers 304
        # for a frame the device cached from a previous run.
        self._nonce = secrets.token_hex(4)
        self._frames: dict[int, Frame] = {}
        self._last_attempt: dict[int, float] = {}
        self._last_error: dict[int, str | None] = {}
        self.error_frame: Frame = self._make_frame(_static_error_jpeg(), 0.0)

    def _make_frame(self, jpeg: bytes, now: float) -> Frame:
        etag = hashlib.sha1(jpeg).hexdigest()[:16] + self._nonce
        return Frame(jpeg, etag, now)

    def put(self, index: int, jpeg: bytes, now: float, anim: str | None = None,
            data: dict | None = None) -> None:
        self._frames[index] = replace(self._make_frame(jpeg, now), anim=anim, data=data)

    def get(self, index: int, now: float) -> Frame | None:
        frame = self._frames.get(index)
        if frame is None or now - frame.rendered_at > STALE_AFTER_S:
            return None
        return frame

    def available(self, now: float) -> list[bool]:
        return [self.get(i, now) is not None for i in range(self._page_count)]

    def last_attempt(self, index: int) -> float | None:
        return self._last_attempt.get(index)

    def last_error(self, index: int) -> str | None:
        return self._last_error.get(index)

    def mark_attempt(self, index: int, now: float, error: str | None) -> None:
        self._last_attempt[index] = now
        self._last_error[index] = error

    async def build_error_frame(self, renderer) -> None:
        """Replace the static fallback with the rendered error.html; keep it on failure."""
        try:
            html = _jinja_env([]).get_template("error.html").render(
                message="Keine Daten", sub=None)
            jpeg = await renderer.render_html(html)
        except Exception:
            log.exception("cannot render error frame; keeping static fallback")
            return
        self.error_frame = self._make_frame(jpeg, 0.0)


def _jinja_env(extra_dirs: list) -> jinja2.Environment:
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader([*map(str, extra_dirs), str(TEMPLATES_DIR)]),
        autoescape=True,
    )
    env.globals["font_face_css"] = font_face_css()  # base.html uses it as a string
    env.globals["serif_face_css"] = serif_face_css  # a function: only called where needed
    return env


async def fetch_page_data(page: PageConfig, ptype: PageType, cfg: AppConfig, now: float,
                          inbox: PushInbox | None = None) -> dict:
    """Run the page type's fetch(); the result may still carry ANIM_KEY."""
    ctx = PageContext(
        now=datetime.fromtimestamp(now, ZoneInfo(cfg.timezone)),
        lang=page.options.get("lang", cfg.lang),
        timezone=cfg.timezone,
        **({} if inbox is None else {"pushed": inbox.get}),
    )
    return await asyncio.wait_for(
        asyncio.to_thread(ptype.fetch, page.options, ctx), FETCH_TIMEOUT_S)


async def render_data(ptype: PageType, data: dict, renderer) -> bytes:
    path = ptype.template_path
    if path is None or not path.is_file():
        raise FileNotFoundError(f"template not found: {path}")
    data = {k: v for k, v in data.items() if k != ANIM_KEY}
    html = _jinja_env([path.parent]).get_template(path.name).render(**data)
    return await renderer.render_html(html)


async def render_page(page: PageConfig, ptype: PageType, cfg: AppConfig, renderer,
                       now: float, inbox: PushInbox | None = None) -> bytes:
    if ptype.kind == "url":
        o = page.options
        return await renderer.render_url(
            o["url"], o.get("wait_ms", 0), o.get("wait_for"), o.get("timeout_s", 15))
    path = ptype.template_path
    if path is None or not path.is_file():
        raise FileNotFoundError(f"template not found: {path}")
    data = await fetch_page_data(page, ptype, cfg, now, inbox)
    return await render_data(ptype, data, renderer)


def _encode_anim(value, label: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, Anim):
        log.warning("%s: X-Anim dropped: not an Anim: %s", label, type(value).__name__)
        return None
    try:
        return encode(value)
    except ValueError as e:
        log.warning("%s: X-Anim dropped: %s", label, e)
        return None


async def refresh_once(cfg: AppConfig, types: dict[str, PageType], renderer,
                       store: FrameStore, now: float, inbox: PushInbox | None = None) -> None:
    for page in cfg.pages:
        last = store.last_attempt(page.index)
        if last is not None and now - last < page.refresh:
            continue
        label = f"pages[{page.index}] ({page.type})"
        try:
            ptype = types.get(page.type)
            if ptype is None:
                raise LookupError(f"unknown page type {page.type!r}")
            anim = None
            data = None
            if ptype.kind == "url":
                jpeg = await render_page(page, ptype, cfg, renderer, now, inbox)
            else:
                raw = await fetch_page_data(page, ptype, cfg, now, inbox)
                data = {k: v for k, v in raw.items() if k != ANIM_KEY}
                anim = _encode_anim(raw.get(ANIM_KEY), label)
                old = store.get(page.index, now)
                if ptype.skip_unchanged and old is not None and old.data == data:
                    store.put(page.index, old.jpeg, now, anim=anim, data=data)
                    store.mark_attempt(page.index, now, None)
                    continue
                jpeg = await render_data(ptype, data, renderer)
        except Exception as e:  # noqa: BLE001 - any page may fail; logged with traceback below
            error = redact_urls(f"{type(e).__name__}: {e}")
            # One record: the short error, then the traceback, both without URL secrets.
            log.warning("%s: refresh failed: %s\n%s", label, error,
                        redact_urls(traceback.format_exc()).rstrip())
            store.mark_attempt(page.index, now, error)
            continue
        store.put(page.index, jpeg, now, anim=anim, data=data)
        store.mark_attempt(page.index, now, None)


async def run_worker(cfg: AppConfig, types: dict[str, PageType], renderer,
                     store: FrameStore, inbox: PushInbox | None = None) -> None:
    await store.build_error_frame(renderer)
    while True:
        await refresh_once(cfg, types, renderer, store, time.time(), inbox)
        await asyncio.sleep(1)
