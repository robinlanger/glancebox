"""AI usage page (ai): limits or costs of one AI provider, selected with `provider:`.

Each provider module in providers/ has NAME (default header title), validate(options) and
fetch(options, ctx) -> dict with the keys of EMPTY below that it sets. `options["lang"]` is
already resolved (page option, else the top-level lang) when the provider's fetch runs.
"""

from __future__ import annotations

from types import ModuleType

from .providers import anthropic_api, claude, copilot, openai_api, xai_api

LANGS = ("de", "en")
SHOWS = ("used", "remaining")  # show: what the bars count (issue #6)

# Only the claude provider reads pushed data (from the Claude Code status-line script or the
# usage hook script).
PUSH_KEYS = {"claude": ("rate_limits", "usage_report")}

PROVIDERS: dict[str, ModuleType] = {
    "claude": claude,
    "anthropic-api": anthropic_api,
    "openai-api": openai_api,
    "xai-api": xai_api,
    "copilot": copilot,
}

# Template data shared by all providers. rows: [{"label", "reset", "percent": float, "text"}],
# percent = share used; a row may add "remaining_text" for show: remaining (copilot's counts);
# big: None or {"label", "value"}; stand: "Stand 13:58" or None; message replaces the body;
# alert: True turns the header red (a provider could not get its data);
# theme: None or "claude" (the claude.ai dark look, set by the claude and anthropic-api providers).
EMPTY = {"rows": [], "big": None, "stand": None, "message": None, "sub": None, "alert": False,
         "theme": None}


def validate(options: dict) -> None:
    provider = options.get("provider")
    if provider not in PROVIDERS:
        raise ValueError(f"provider must be one of: {', '.join(PROVIDERS)}")
    if options.get("lang", "de") not in LANGS:
        raise ValueError("lang must be 'de' or 'en'")
    if options.get("show", "used") not in SHOWS:
        raise ValueError("show must be 'used' or 'remaining'")
    title = options.get("title")
    if title is not None and not isinstance(title, str):
        raise ValueError("title must be text")
    PROVIDERS[provider].validate(options)


def fetch(options: dict, ctx) -> dict:
    lang = options.get("lang", ctx.lang if ctx.lang in LANGS else "de")
    provider = PROVIDERS[options["provider"]]
    data = {**EMPTY, **provider.fetch({**options, "lang": lang}, ctx)}
    remaining = options.get("show") == "remaining"
    data["rows"] = [_remaining(row) if remaining else
                    {k: v for k, v in row.items() if k != "remaining_text"}
                    for row in data["rows"]]
    data["title"] = options.get("title") or provider.NAME
    data["clock"] = ctx.clock()
    return data


def _remaining(row: dict) -> dict:
    """Row turned to the share left; "used" keeps the share used for the bar color."""
    used = row["percent"]
    left = max(0.0, 100.0 - used)
    text = row.get("remaining_text") or f"{round(left)} %"
    rest = {k: v for k, v in row.items() if k != "remaining_text"}
    return {**rest, "percent": left, "text": text, "used": used}
