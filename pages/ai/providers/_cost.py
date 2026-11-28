"""Shared code of the API providers anthropic-api, openai-api, xai-api and copilot.

Cost and usage data change slowly, so each successful result is kept for CACHE_S seconds per
process, keyed by (provider, sha256(key), and the CACHE_SCOPE options). A failure is kept for
FAIL_CACHE_S, so a bad or revoked key does not hit the provider on every refresh; meanwhile the
page shows the "No data" notice, never a stale amount. MIN_REFRESH of the page stays 0 because
the claude provider needs a short refresh.

Keys only ever travel in request headers. A failure is logged with the exception type and the
HTTP status only, never with the exception text, so no key or URL detail can reach the log.
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Callable
from datetime import UTC, datetime

log = logging.getLogger(__name__)

CACHE_S = 300
FAIL_CACHE_S = 60
MAX_PAGES = 20
# Options besides the key that change what a provider requests, so they are part of the cache key.
CACHE_SCOPE = ("team_id", "username", "unit")

TEXT = {
    "de": {"month": "Diesen Monat", "balance": "Guthaben", "nodata": "Keine Daten",
           "asof": "Stand", "budget": "Budget"},
    "en": {"month": "This month", "balance": "Balance", "nodata": "No data",
           "asof": "As of", "budget": "Budget"},
}
MONTHS_EN = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
             "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")

# (provider, sha256 of the key, *CACHE_SCOPE values) -> (fetched at, (amount, data as of or None))
_cache: dict[tuple, tuple[float, tuple[float, datetime | None]]] = {}
# Same key -> (failed at, the exception), re-raised until FAIL_CACHE_S has passed.
_failures: dict[tuple, tuple[float, Exception]] = {}


def require_text(options: dict, name: str) -> None:
    value = options.get(name)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} is required (use ${{VAR}} and .env for secrets)")


def validate_budget(options: dict) -> None:
    budget = options.get("budget")
    if budget is None:
        return
    if isinstance(budget, bool) or not isinstance(budget, (int, float)) or budget <= 0:
        raise ValueError("budget must be a positive number (USD)")


def month_start(now: datetime) -> datetime:
    """Start of the current calendar month in UTC (the providers bill in UTC)."""
    return now.astimezone(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def paginate(get_page: Callable[[str | None], dict]) -> list[dict]:
    """Calls get_page(cursor) while the API reports has_more; at most MAX_PAGES pages."""
    pages, cursor = [], None
    for _ in range(MAX_PAGES):
        page = get_page(cursor)
        pages.append(page)
        if not page["has_more"]:
            return pages
        cursor = page["next_page"]
    raise RuntimeError(f"more than {MAX_PAGES} pages")


def usd(amount: float, lang: str) -> str:
    """18.4 -> '18,40 $' (de) or '$18.40' (en); thousands separated."""
    text = f"{abs(amount):,.2f}"
    sign = "-" if round(amount, 2) < 0 else ""
    if lang == "de":
        return sign + text.replace(",", " ").replace(".", ",").replace(" ", ".") + " $"
    return f"{sign}${text}"


def next_month(now: datetime, lang: str) -> str:
    """First day of the next UTC month: '1.12.' (de) or 'Dec 1' (en)."""
    start = month_start(now)
    month = start.month % 12 + 1
    return f"1.{month}." if lang == "de" else f"{MONTHS_EN[month - 1]} 1"


def cached(provider: str, options: dict, now: float,
           load: Callable[[], tuple[float, datetime | None]]):
    """(fetched at, load()) from the cache if younger than CACHE_S, else calls load().

    A failure of load() is re-raised without a new call until it is FAIL_CACHE_S old.
    """
    cache_key = (provider, hashlib.sha256(options["key"].encode()).hexdigest(),
                 *(options.get(name) for name in CACHE_SCOPE))
    failed = _failures.get(cache_key)
    if failed is not None and 0 <= now - failed[0] < FAIL_CACHE_S:
        raise failed[1].with_traceback(None)
    hit = _cache.get(cache_key)
    if hit is not None and 0 <= now - hit[0] < CACHE_S:
        return hit
    try:
        entry = (now, load())
    except Exception as exc:
        _failures[cache_key] = (now, exc)
        raise
    _failures.pop(cache_key, None)
    _cache[cache_key] = entry
    return entry


def no_data(provider: str, exc: Exception, ctx, lang: str) -> dict:
    """Logs the failure without key or URL detail and returns the 'No data' notice (red)."""
    texts = TEXT[lang]
    status = getattr(getattr(exc, "response", None), "status_code", None)
    log.warning("ai %s: no data: %s%s", provider, type(exc).__name__,
                f" (HTTP {status})" if status else "")
    return {"message": texts["nodata"], "sub": f"{texts['asof']} {ctx.clock()}",
            "alert": True}


def show(provider: str, options: dict, ctx, label: str,
         load: Callable[[], tuple[float, datetime | None]]) -> dict:
    """Runs load() (through the cache) and builds the page data, or the 'No data' notice.

    load() returns (amount in USD, time the provider's data is as of, or None for "now").
    """
    lang = options["lang"]
    texts = TEXT[lang]
    try:
        fetched_at, (amount, as_of) = cached(provider, options, ctx.now.timestamp(), load)
    except Exception as exc:  # noqa: BLE001 - every failure shows the notice, never stale data
        return no_data(provider, exc, ctx, lang)

    stand = (as_of or datetime.fromtimestamp(fetched_at, UTC)).astimezone(ctx.now.tzinfo)
    data = {"big": {"label": texts[label], "value": usd(amount, lang)},
            "stand": f"{texts['asof']} {ctx.clock(stand)}"}
    budget = options.get("budget")
    if budget:
        percent = amount / budget * 100
        data["rows"] = [{"label": texts["budget"], "reset": next_month(ctx.now, lang),
                         "percent": percent, "text": f"{round(percent)} %"}]
    return data
