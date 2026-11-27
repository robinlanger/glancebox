"""Plain test values of the printer page tests: ``from printer_helpers import NOW, ctx``.

Not in conftest.py: with no __init__.py every conftest registers as the bare module name
``conftest``, so importing from it can pick up server/tests/conftest.py instead.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from glancebox.pages import PageContext

NOW = datetime(2026, 11, 25, 14, 32, tzinfo=ZoneInfo("Europe/Berlin"))  # a Wednesday


def ctx(lang="de"):
    return PageContext(NOW, lang, "Europe/Berlin")
