"""Shared fixtures of the printer page tests.

NOW and ctx live in printer_helpers.py (``from printer_helpers import NOW, ctx``): never
import from conftest, the bare name ``conftest`` may be server/tests/conftest.py.
"""

import importlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit

import pytest
import requests

import glancebox.http
from glancebox.pages import load_page_types

PAGES_DIR = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _clear_module_state():
    page = sys.modules.get("glancebox_pages.printer")
    if page is not None and hasattr(page, "_memory"):
        page._memory.clear()
    common = sys.modules.get("glancebox_pages.printer.providers._common")
    if common is not None:
        common._thumbs.clear()
    moonraker = sys.modules.get("glancebox_pages.printer.providers.moonraker")
    if moonraker is not None:
        moonraker._jobs.clear()
    octoprint = sys.modules.get("glancebox_pages.printer.providers.octoprint")
    if octoprint is not None:
        octoprint._files.clear()
    hass = sys.modules.get("glancebox_pages.printer.providers.hass")
    if hass is not None:
        hass._warned.clear()


@pytest.fixture(autouse=True)
def _fresh_state():
    """Every test starts and ends with empty page memory, thumbnail cache and source caches.

    load_page_types re-executes page.py, so a new module normally starts empty anyway; this
    keeps tests independent of that and of their order.
    """
    _clear_module_state()
    yield
    _clear_module_state()


@pytest.fixture
def printer():
    return load_page_types([PAGES_DIR])["printer"]


@pytest.fixture
def mod(printer):
    return sys.modules["glancebox_pages.printer"]


@pytest.fixture
def common(printer):
    return importlib.import_module("glancebox_pages.printer.providers._common")


@pytest.fixture
def load():
    """load(name) -> the decoded JSON of fixtures/<name>.json."""
    def read(name):
        return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    return read


@pytest.fixture
def route(monkeypatch):
    """route({path_with_query_or_full_url: answer}) fakes glancebox.http.get_json/get_bytes.

    An answer that is an exception is raised, an int raises requests.HTTPError with that
    status, anything else is returned (get_bytes answers are ``(bytes, mime)``). Returns the
    list of calls (``kind`` "json"/"bytes", ``url``, ``params``, ``headers``, ``timeout``,
    ``auth``, ``max_bytes``); an address not in the dict fails with AssertionError.
    """
    def install(responses):
        calls = []

        def answer(kind, url, **kw):
            calls.append(SimpleNamespace(kind=kind, url=url, **kw))
            parts = urlsplit(url)
            path = parts.path + (f"?{parts.query}" if parts.query else "")
            for key in (url, path):
                if key in responses:
                    r = responses[key]
                    break
            else:
                raise AssertionError(f"unexpected {kind} request: {url}")
            if isinstance(r, Exception):
                raise r
            if isinstance(r, int):
                resp = requests.Response()
                resp.status_code = r
                raise requests.HTTPError(f"{r} error", response=resp)
            return r

        def get_json(url, *, params=None, headers=None, timeout=10, auth=None):
            return answer("json", url, params=params, headers=headers, timeout=timeout,
                          auth=auth, max_bytes=None)

        def get_bytes(url, *, headers=None, timeout=10, max_bytes, auth=None):
            return answer("bytes", url, params=None, headers=headers, timeout=timeout,
                          auth=auth, max_bytes=max_bytes)

        monkeypatch.setattr(glancebox.http, "get_json", get_json)
        monkeypatch.setattr(glancebox.http, "get_bytes", get_bytes)
        return calls
    return install
