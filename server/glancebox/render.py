"""Render HTML or URLs to a 240x240 baseline JPEG using one shared Chromium."""

import asyncio
import base64
import contextlib
import io
import logging
import os
from collections.abc import Mapping
from functools import cache
from pathlib import Path
from typing import Self

from PIL import Image
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import async_playwright

MAX_JPEG_BYTES = 24576  # must equal kMaxFrameBytes in firmware/lib/core/poll_timing.h
QUALITY_STEPS = (85, 75, 65, 55, 45, 40)
SIZE = 240

log = logging.getLogger(__name__)

# Chromium gets only these variables (plus the prefixes below), never tokens or keys.
BROWSER_ENV_NAMES = frozenset(
    {"PATH", "HOME", "USER", "LOGNAME", "LANG", "LANGUAGE", "TZ", "TMPDIR"})
BROWSER_ENV_PREFIXES = ("LC_", "XDG_", "FONTCONFIG_")

FONTS_DIR = Path(__file__).parent / "fonts"
_FONTS = (
    ("DejaVuSans.ttf", "normal", "normal"),
    ("DejaVuSans-Bold.ttf", "bold", "normal"),
    ("DejaVuSansCondensed.ttf", "normal", "condensed"),
    ("DejaVuSansCondensed-Bold.ttf", "bold", "condensed"),
)


class RenderError(Exception):
    """Rendering failed (browser error, timeout, or image too large)."""


def browser_env(environ: Mapping[str, str]) -> dict[str, str]:
    """The part of ``environ`` Chromium may see (allowlist, so secrets never reach it)."""
    return {k: v for k, v in environ.items()
            if k in BROWSER_ENV_NAMES or k.startswith(BROWSER_ENV_PREFIXES)}


@cache
def font_face_css() -> str:
    """Inline @font-face rules for the bundled DejaVu fonts (built once)."""
    rules = []
    for filename, weight, variant in _FONTS:
        data = base64.b64encode((FONTS_DIR / filename).read_bytes()).decode("ascii")
        family = "DejaVu Sans Condensed" if variant == "condensed" else "DejaVu Sans"
        rules.append(
            f"@font-face{{font-family:'{family}';font-weight:{weight};font-style:normal;"
            f"src:url(data:font/ttf;base64,{data}) format('truetype');}}"
        )
    return "\n".join(rules)


@cache
def serif_face_css() -> str:
    """@font-face rule for DejaVu Serif Bold; only the pages that use it embed it (~470 KB)."""
    data = base64.b64encode((FONTS_DIR / "DejaVuSerif-Bold.ttf").read_bytes()).decode("ascii")
    return ("@font-face{font-family:'DejaVu Serif';font-weight:bold;font-style:normal;"
            f"src:url(data:font/ttf;base64,{data}) format('truetype');}}")


def encode_jpeg(png: bytes) -> bytes:
    """Encode PNG bytes as baseline JPEG, lowering quality until it fits."""
    img = Image.open(io.BytesIO(png)).convert("RGB")
    for quality in QUALITY_STEPS:
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=quality, progressive=False, optimize=True)
        if buf.tell() <= MAX_JPEG_BYTES:
            return buf.getvalue()
    raise RenderError(f"JPEG larger than {MAX_JPEG_BYTES} bytes even at quality {QUALITY_STEPS[-1]}")


class Renderer:
    """Async context manager holding one Chromium instance."""

    def __init__(self) -> None:
        self._pw = None
        self._browser = None
        self._lock = asyncio.Lock()
        self.sandboxed: bool | None = None  # None until Chromium first started

    async def __aenter__(self) -> Self:
        try:
            self._pw = await async_playwright().start()
            await self._launch()
        except Exception as exc:
            await self.__aexit__(None, None, None)
            raise RenderError(f"cannot start Chromium: {exc}") from exc
        return self

    async def __aexit__(self, *exc) -> None:
        browser, pw = self._browser, self._pw
        self._browser = self._pw = None
        try:
            if browser:
                await browser.close()
        finally:
            if pw:
                await pw.stop()

    async def _launch(self) -> None:
        """Start Chromium with a clean environment; try the sandbox once, remember the outcome."""
        env = browser_env(os.environ)
        if self.sandboxed is None:
            try:
                self._browser = await self._pw.chromium.launch(env=env, chromium_sandbox=True)
            except PlaywrightError:
                log.warning("Chromium sandbox not available in this container; running without it")
                self.sandboxed = False
            else:
                log.info("Chromium sandbox enabled")
                self.sandboxed = True
                return
        self._browser = await self._pw.chromium.launch(env=env, chromium_sandbox=self.sandboxed)

    def healthy(self) -> bool:
        """True while the shared Chromium is running and connected."""
        return self._browser is not None and self._browser.is_connected()

    async def _relaunch(self) -> None:
        # Chromium died (crash, OOM kill): start a fresh one instead of failing forever.
        old, self._browser = self._browser, None
        if old is not None:
            with contextlib.suppress(Exception):
                await old.close()
        try:
            await self._launch()
        except Exception as exc:
            raise RenderError(f"cannot restart Chromium: {exc}") from exc

    async def render_html(self, html: str, timeout_s: float = 10) -> bytes:
        async def load(page):
            await page.set_content(html, wait_until="load", timeout=timeout_s * 1000)

        return await self._render(load, timeout_s)

    async def render_url(
        self, url: str, wait_ms: int, wait_for: str | None, timeout_s: float
    ) -> bytes:
        async def load(page):
            await page.goto(url, wait_until="load", timeout=timeout_s * 1000)
            if wait_for:
                await page.wait_for_selector(wait_for, timeout=timeout_s * 1000)
            if wait_ms:
                await page.wait_for_timeout(wait_ms)

        return await self._render(load, timeout_s + wait_ms / 1000)

    async def _render(self, load, budget_s: float) -> bytes:
        if self._pw is None:
            raise RenderError("renderer not started")
        async with self._lock:
            if not self.healthy():
                await self._relaunch()
            context = page = None
            try:
                async with asyncio.timeout(budget_s + 2):
                    context = await self._browser.new_context(
                        viewport={"width": SIZE, "height": SIZE}, device_scale_factor=1
                    )
                    page = await context.new_page()
                    await load(page)
                    png = await page.screenshot(
                        type="png", clip={"x": 0, "y": 0, "width": SIZE, "height": SIZE}
                    )
            except (PlaywrightError, TimeoutError) as exc:
                raise RenderError(f"render failed: {exc}") from exc
            finally:
                for obj in (page, context):
                    if obj is not None:
                        with contextlib.suppress(PlaywrightError):
                            await obj.close()
        return encode_jpeg(png)
