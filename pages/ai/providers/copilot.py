"""Provider copilot: GitHub Copilot usage of the current month against your own allowance.

Verified 2026-11-15 against https://docs.github.com/en/rest/billing/usage (API version
2026-03-10):
- GET https://api.github.com/users/{username}/settings/billing/ai_credit/usage (usage-based
  billing, since 1 June 2026) or .../premium_request/usage (annual Pro/Pro+ plans that stayed
  on request-based billing).
- Headers: Authorization: Bearer <token>, Accept: application/vnd.github+json,
  X-GitHub-Api-Version: 2026-03-10.
- Token: fine-grained personal access token (or GitHub App user token) with the user
  permission "Plan" (read), per the endpoint reference and
  https://docs.github.com/en/rest/authentication/permissions-required-for-fine-grained-personal-access-tokens
  ("User permissions for Plan"). Conflict: the tutorial
  https://docs.github.com/en/billing/tutorials/automate-usage-reporting says the billing usage
  endpoints need a classic PAT and do not support fine-grained ones, and no doc names the
  classic scope. The user docs recommend fine-grained first and a classic token on HTTP 403.
  Only covers a Copilot plan the user bought personally; seats billed
  through an organisation or enterprise are not included.
- Query: year, month (default: the current month). The included allowance resets on the 1st at
  00:00 UTC, so the month is the UTC month.
- Response: {"timePeriod": {...}, "user": ..., "usageItems": [{"unitType": "ai-credits" or
  "requests", "grossQuantity": number, "discountQuantity", "netQuantity", ...}]}; usage =
  sum of grossQuantity. No pagination.

None of GitHub's documented endpoints returns the entitlement (the Copilot SDK's
account.getQuota is a JSON-RPC call into a running Copilot CLI, not an HTTP API), so the user
supplies it as monthly_allowance.
"""

from __future__ import annotations

from datetime import UTC, datetime
from urllib.parse import quote

from glancebox import http

from . import _cost

NAME = "GitHub Copilot"
URL = "https://api.github.com/users/{user}/settings/billing/{meter}/usage"
API_VERSION = "2026-03-10"
UNITS = {"ai-credits": "ai_credit", "premium-requests": "premium_request"}

TEXT = {
    "de": {"ai-credits": "AI-Credits", "premium-requests": "Premium-Requests", "left": "Übrig"},
    "en": {"ai-credits": "AI credits", "premium-requests": "Premium requests", "left": "Left"},
}


def validate(options: dict) -> None:
    _cost.require_text(options, "key")
    _cost.require_text(options, "username")
    allowance = options.get("monthly_allowance")
    if isinstance(allowance, bool) or not isinstance(allowance, (int, float)) or allowance <= 0:
        raise ValueError("monthly_allowance is required: your plan's monthly allowance, "
                         "a positive number (for example 1500 AI credits)")
    if options.get("unit", "ai-credits") not in UNITS:
        raise ValueError(f"unit must be one of: {', '.join(UNITS)}")
    if "budget" in options:
        raise ValueError("budget is not supported for copilot (use monthly_allowance)")


def _count(value: float, lang: str) -> str:
    """1234.4 -> '1.234' (de) or '1,234' (en)."""
    text = f"{round(value):,}"
    return text.replace(",", ".") if lang == "de" else text


def fetch(options: dict, ctx) -> dict:
    lang = options["lang"]
    unit = options.get("unit", "ai-credits")
    options = {**options, "unit": unit}

    def load():
        start = _cost.month_start(ctx.now)
        url = URL.format(user=quote(options["username"], safe=""), meter=UNITS[unit])
        report = http.get_json(url, params={"year": start.year, "month": start.month},
                               headers={"Authorization": f"Bearer {options['key']}",
                                        "Accept": "application/vnd.github+json",
                                        "X-GitHub-Api-Version": API_VERSION})
        return sum(float(item["grossQuantity"]) for item in report["usageItems"]), None

    try:
        fetched_at, (used, _) = _cost.cached("copilot", options, ctx.now.timestamp(), load)
    except Exception as exc:  # noqa: BLE001 - every failure shows the notice, never stale data
        return _cost.no_data("copilot", exc, ctx, lang)

    allowance = options["monthly_allowance"]
    texts = TEXT[lang]
    stand = datetime.fromtimestamp(fetched_at, UTC).astimezone(ctx.now.tzinfo)
    return {
        "rows": [{"label": texts[unit], "reset": _cost.next_month(ctx.now, lang),
                  "percent": used / allowance * 100,
                  "text": f"{_count(used, lang)} / {_count(allowance, lang)}",
                  "remaining_text": f"{_count(max(allowance - used, 0), lang)} / "
                                    f"{_count(allowance, lang)}"}],
        "big": {"label": texts["left"], "value": _count(max(allowance - used, 0), lang)},
        "stand": f"{_cost.TEXT[lang]['asof']} {ctx.clock(stand)}",
    }
