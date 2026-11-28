import io
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from PIL import Image

from glancebox.config import AppConfig, PageConfig
from glancebox.frames import render_page
from glancebox.pages import PageContext, load_page_types
from glancebox.push import Pushed, PushInbox

PAGES_DIR = Path(__file__).resolve().parents[1]
TZ = ZoneInfo("Europe/Berlin")
NOW = datetime(2026, 11, 15, 14, 5, tzinfo=TZ)  # a Sunday
RECEIVED = datetime(2026, 11, 15, 13, 58, tzinfo=TZ).timestamp()
THURSDAY_9 = datetime(2026, 11, 19, 9, 0, tzinfo=TZ).timestamp()
IN_2H13 = (NOW + timedelta(hours=2, minutes=13, seconds=20)).timestamp()
OPTIONS = {"provider": "claude"}


def ctx(pushed: dict | None, lang: str = "de") -> PageContext:
    """Context whose inbox holds `pushed` (the stored data, i.e. only `rate_limits`)."""
    item = None if pushed is None else Pushed(pushed, RECEIVED)
    return PageContext(now=NOW, lang=lang, timezone="Europe/Berlin",
                       pushed=lambda c: item if c == "claude" else None)


def limits(five=(42.0, IN_2H13), seven=(81.0, THURSDAY_9)) -> dict:
    """Shape per https://code.claude.com/docs/en/statusline (rate_limits.*)."""
    rl = {}
    if five:
        rl["five_hour"] = {"used_percentage": five[0], "resets_at": int(five[1])}
    if seven:
        rl["seven_day"] = {"used_percentage": seven[0], "resets_at": int(seven[1])}
    return {"rate_limits": rl}


def report(session=(42.0, IN_2H13), weekly=(81.0, THURSDAY_9), extra=()) -> dict:
    """usage_report shape of `claude -p "/usage"` (SDKUsageReport, Claude Code 2.1.330)."""
    entries = []
    for kind, window in (("session", session), ("weekly_all", weekly)):
        if window:
            at = datetime.fromtimestamp(window[1], UTC).isoformat()
            entries.append({"kind": kind, "percent": window[0], "resets_at": at})
    return {"usage_report": {"rate_limits": {"limits": [*entries, *extra]}}}


@pytest.fixture
def ai():
    return load_page_types([PAGES_DIR])["ai"]


def test_push_keys_declared(ai):
    assert ai.push_keys == {"claude": ("rate_limits", "usage_report")}


def test_validate_unknown_provider(ai):
    with pytest.raises(ValueError, match="provider"):
        ai.validate({"provider": "nope"})
    with pytest.raises(ValueError, match="provider"):
        ai.validate({})
    with pytest.raises(ValueError, match="lang"):
        ai.validate({"provider": "claude", "lang": "fr"})
    ai.validate({"provider": "claude", "lang": "en", "title": "Claude Max"})


def test_validate_show(ai):
    ai.validate({"provider": "claude", "show": "remaining"})
    ai.validate({"provider": "claude", "show": "used"})
    with pytest.raises(ValueError, match="show"):
        ai.validate({"provider": "claude", "show": "left"})


def test_claude_remaining(ai):
    data = ai.fetch({**OPTIONS, "show": "remaining"}, ctx(limits()))
    assert data["rows"] == [
        {"label": "5 Stunden", "reset": "in 2:13", "percent": 58.0, "text": "58 %", "used": 42.0},
        {"label": "Woche", "reset": "Do 09:00", "percent": 19.0, "text": "19 %", "used": 81.0},
    ]


def test_claude_remaining_after_reset_is_full(ai):
    past = (NOW - timedelta(minutes=1)).timestamp()
    row = ai.fetch({**OPTIONS, "show": "remaining"}, ctx(limits(five=(97.0, past))))["rows"][0]
    assert (row["percent"], row["text"], row["used"]) == (100.0, "100 %", 0.0)


def test_bar_level_uses_used_value():
    from glancebox.frames import _jinja_env

    tpl = _jinja_env([PAGES_DIR / "ai"]).get_template("template.html")
    base = {"title": "Claude", "clock": "14:05", "message": None, "sub": None,
            "alert": False, "stand": None, "big": None, "theme": None}
    low = tpl.render(**base, rows=[{"label": "Woche", "reset": "", "percent": 5.0,
                                    "text": "5 %", "used": 95.0}])
    assert "ui-fill ui-bad" in low and "width:5.0%" in low
    full = tpl.render(**base, rows=[{"label": "Woche", "reset": "", "percent": 100.0,
                                     "text": "100 %", "used": 0.0}])
    assert "ui-fill ui-ok" in full


def test_claude_no_data_yet(ai):
    data = ai.fetch(OPTIONS, ctx(None))
    assert data["title"] == "Claude" and data["clock"] == "14:05"
    assert data["message"] == "Noch keine Daten"
    assert data["sub"] == "Statuszeilen-Skript einrichten"
    assert data["rows"] == [] and data["big"] is None
    en = ai.fetch(OPTIONS, ctx(None, "en"))
    assert (en["message"], en["sub"]) == ("No data yet", "Set up the status-line script")


def test_claude_rows(ai):
    data = ai.fetch(OPTIONS, ctx(limits()))
    assert data["message"] is None and data["big"] is None
    assert data["rows"] == [
        {"label": "5 Stunden", "reset": "in 2:13", "percent": 42.0, "text": "42 %"},
        {"label": "Woche", "reset": "Do 09:00", "percent": 81.0, "text": "81 %"},
    ]
    assert data["stand"] == "Stand 13:58"


def test_claude_stand_from_another_day_shows_weekday(ai):
    yesterday = RECEIVED - 24 * 3600
    for lang, stand in (("de", "Stand Sa 13:58"), ("en", "As of Sat 13:58")):
        item = Pushed(limits(), yesterday)
        context = PageContext(now=NOW, lang=lang, timezone="Europe/Berlin",
                              pushed=lambda c, item=item: item)
        assert ai.fetch({**OPTIONS, "lang": lang}, context)["stand"] == stand


def test_claude_rows_english_and_title(ai):
    data = ai.fetch({**OPTIONS, "lang": "en", "title": "Claude Max"},
                    ctx(limits(five=(7.6, IN_2H13))))
    assert data["title"] == "Claude Max"
    assert [(r["label"], r["reset"], r["text"]) for r in data["rows"]] == [
        ("5 hours", "in 2:13", "8 %"), ("Week", "Thu 09:00", "81 %")]
    assert data["stand"] == "As of 13:58"


def test_claude_twelve_hours(ai):
    data = ai.fetch(OPTIONS, replace(ctx(limits()), time_format="12h"))
    assert data["clock"] == "2:05 PM"
    assert [r["reset"] for r in data["rows"]] == ["in 2:13", "Do 9:00 AM"]   # countdown untouched
    assert data["stand"] == "Stand 1:58 PM"


def test_claude_twelve_hours_english_and_no_data(ai):
    data = ai.fetch(OPTIONS, replace(ctx(limits(), lang="en"), time_format="12h"))
    assert (data["rows"][1]["reset"], data["stand"]) == ("Thu 9:00 AM", "As of 1:58 PM")


def test_claude_stand_from_another_day_twelve_hours(ai):
    item = Pushed(limits(), RECEIVED - 24 * 3600)
    context = PageContext(now=NOW, lang="en", timezone="Europe/Berlin",
                          pushed=lambda c: item, time_format="12h")
    assert ai.fetch(OPTIONS, context)["stand"] == "As of Sat 1:58 PM"


def test_claude_reset_passed_is_zero(ai):
    past = (NOW - timedelta(minutes=1)).timestamp()
    data = ai.fetch(OPTIONS, ctx(limits(five=(97.0, past))))
    assert data["rows"][0] == {"label": "5 Stunden", "reset": "zurückgesetzt",
                               "percent": 0.0, "text": "0 %"}
    en = ai.fetch({**OPTIONS, "lang": "en"}, ctx(limits(five=(97.0, NOW.timestamp()))))
    assert en["rows"][0]["reset"] == "reset" and en["rows"][0]["percent"] == 0.0


def test_claude_missing_seven_day_shows_one_row(ai):
    data = ai.fetch(OPTIONS, ctx(limits(seven=None)))
    assert [r["label"] for r in data["rows"]] == ["5 Stunden"]
    assert data["message"] is None


def test_claude_no_windows_in_push(ai):
    for stored in ({}, {"rate_limits": {}}, {"rate_limits": "x"},
                   {"rate_limits": {"five_hour": {"used_percentage": "a", "resets_at": 1}}}):
        data = ai.fetch(OPTIONS, ctx(stored))
        assert data["rows"] == []
        assert data["message"] == "Keine Limitdaten"
        assert data["sub"] == "Wartet auf die nächste Antwort"
        assert data["stand"] == "Stand 13:58"


def test_claude_report_rows_match_status_line(ai):
    # same numbers in either format give the same page data
    assert ai.fetch(OPTIONS, ctx(report())) == ai.fetch(OPTIONS, ctx(limits()))


def test_claude_report_ignores_scoped_and_unknown_kinds(ai):
    extra = ({"kind": "weekly_scoped", "percent": 16, "resets_at": None},
             {"kind": "something_new", "percent": 99, "resets_at": None}, "junk", None)
    data = ai.fetch(OPTIONS, ctx(report(extra=extra)))
    assert [r["label"] for r in data["rows"]] == ["5 Stunden", "Woche"]


def test_claude_report_only_session(ai):
    data = ai.fetch(OPTIONS, ctx(report(weekly=None)))
    assert [r["label"] for r in data["rows"]] == ["5 Stunden"]


@pytest.mark.parametrize("rate_limits", [None, {}, {"limits": None}, {"limits": []}, "x"])
def test_claude_report_without_limits_is_notice(ai, rate_limits):
    data = ai.fetch(OPTIONS, ctx({"usage_report": {"rate_limits": rate_limits}}))
    assert data["message"] == "Keine Limitdaten" and data["rows"] == []


def test_claude_report_not_a_dict_is_notice(ai):
    assert ai.fetch(OPTIONS, ctx({"usage_report": [1]}))["message"] == "Keine Limitdaten"


@pytest.mark.parametrize("resets_at", [None, "soon", 5, ""])
def test_claude_report_bad_reset_keeps_row(ai, resets_at):
    push = {"usage_report": {"rate_limits": {"limits": [
        {"kind": "session", "percent": 42, "resets_at": resets_at}]}}}
    row = ai.fetch(OPTIONS, ctx(push))["rows"][0]
    assert (row["percent"], row["reset"], row["text"]) == (42.0, "", "42 %")


def test_claude_report_reset_without_offset_is_utc(ai):
    naive = datetime.fromtimestamp(IN_2H13, UTC).replace(tzinfo=None).isoformat()
    push = {"usage_report": {"rate_limits": {"limits": [
        {"kind": "session", "percent": 42, "resets_at": naive}]}}}
    assert ai.fetch(OPTIONS, ctx(push))["rows"][0]["reset"] == "in 2:13"


def test_claude_report_reset_passed_is_zero(ai):
    data = ai.fetch(OPTIONS, ctx(report(session=(90.0, NOW.timestamp() - 60))))
    assert (data["rows"][0]["percent"], data["rows"][0]["reset"]) == (0.0, "zurückgesetzt")


@pytest.mark.parametrize("percent", [True, "5", None])
def test_claude_report_bad_percent_skips_row(ai, percent):
    push = {"usage_report": {"rate_limits": {"limits": [
        {"kind": "session", "percent": percent, "resets_at": None}]}}}
    assert ai.fetch(OPTIONS, ctx(push))["message"] == "Keine Limitdaten"


def test_claude_report_wins_over_rate_limits(ai):
    push = {**limits(five=(10.0, IN_2H13), seven=None), **report(session=(42.0, IN_2H13))}
    assert ai.fetch(OPTIONS, ctx(push))["rows"][0]["percent"] == 42.0


def test_claude_report_first_of_a_kind_wins(ai):
    extra = ({"kind": "session", "percent": 77, "resets_at": None},)
    assert ai.fetch(OPTIONS, ctx(report(extra=extra)))["rows"][0]["percent"] == 42.0


def test_claude_report_unhashable_kind_is_skipped(ai):
    extra = ({"kind": ["session"], "percent": 77, "resets_at": None},)
    data = ai.fetch(OPTIONS, ctx(report(session=None, extra=extra)))
    assert [r["label"] for r in data["rows"]] == ["Woche"]


def test_claude_report_through_the_inbox(ai):
    inbox = PushInbox()
    inbox.put("claude", report(weekly=(95.0, THURSDAY_9)), RECEIVED)
    context = PageContext(now=NOW, lang="de", timezone="Europe/Berlin", pushed=inbox.get)
    data = ai.fetch(OPTIONS, context)
    assert [(r["label"], r["percent"]) for r in data["rows"]] == [
        ("5 Stunden", 42.0), ("Woche", 95.0)]


def _has(img, rgb, tol=40):
    return any(all(abs(a - b) < tol for a, b in zip(img.getpixel((x, y)), rgb, strict=True))
               for x in range(0, 240, 3) for y in range(34, 232, 3))


def _bg(img):
    """Background at the left edge, beside the bars."""
    return img.getpixel((2, 120))


def _near(rgb, want, tol=12):
    return all(abs(a - b) < tol for a, b in zip(rgb, want, strict=True))


CLAUDE_BG, CLAUDE_ORANGE, CLAUDE_RED = (0x26, 0x26, 0x24), (0xD9, 0x77, 0x57), (0xE5, 0x53, 0x4B)
GREEN = (60, 200, 110)


@pytest.mark.browser
@pytest.mark.parametrize("push", [limits, report], ids=["status_line", "usage_report"])
async def test_template_renders_claude(ai, push):
    from glancebox.render import MAX_JPEG_BYTES, Renderer

    cfg = AppConfig(interval=30, timezone="Europe/Berlin", lang="de",
                    pages=(), pages_dirs=(PAGES_DIR,))
    page = PageConfig(index=0, type="ai", options=OPTIONS, duration=30, refresh=30)
    async with Renderer() as r:
        inbox = PushInbox()
        empty = Image.open(io.BytesIO(
            await render_page(page, ai, cfg, r, NOW.timestamp(), inbox))).convert("RGB")
        inbox.put("claude", push((42.0, IN_2H13), (95.0, THURSDAY_9)), RECEIVED)
        jpeg = await render_page(page, ai, cfg, r, NOW.timestamp(), inbox)
        full = Image.open(io.BytesIO(jpeg)).convert("RGB")
    assert empty.size == full.size == (240, 240)
    assert len(jpeg) <= MAX_JPEG_BYTES
    assert empty.convert("L").getextrema()[1] > 150  # the notice is visible
    assert _near(_bg(empty), CLAUDE_BG) and _near(_bg(full), CLAUDE_BG)  # notice too
    assert _has(full, CLAUDE_ORANGE, 20) and _has(full, CLAUDE_RED, 20)  # 42 % orange, 95 % red
    assert not _has(full, GREEN) and not _has(empty, GREEN)


@pytest.mark.browser
async def test_claude_alert_title_is_readable():
    from glancebox.frames import _jinja_env
    from glancebox.render import Renderer

    html = _jinja_env([PAGES_DIR / "ai"]).get_template("template.html").render(
        title="Anthropic API", clock="14:05", message="Keine Daten", sub="Stand 14:05",
        alert=True, theme="claude", stand=None, big=None, rows=[])
    async with Renderer() as r:
        img = Image.open(io.BytesIO(await r.render_html(html))).convert("RGB")
    title = [img.getpixel((x, y)) for x in range(7, 130) for y in range(8, 26)]
    assert max(sum(p) for p in title) > 600  # light text, not orange (sum ~423) on dark red


@pytest.mark.browser
async def test_other_providers_keep_the_plain_look():
    from glancebox.frames import _jinja_env
    from glancebox.render import Renderer

    html = _jinja_env([PAGES_DIR / "ai"]).get_template("template.html").render(
        title="OpenAI API", clock="14:05", message=None, sub=None, alert=False, theme=None,
        stand="Stand 14:05", big={"label": "Diesen Monat", "value": "18,40 $"},
        rows=[{"label": "Budget", "reset": "1.12.", "percent": 36.8, "text": "37 %"}])
    async with Renderer() as r:
        img = Image.open(io.BytesIO(await r.render_html(html))).convert("RGB")
    assert _has(img, GREEN) and _near(_bg(img), (8, 10, 14))
    assert "DejaVu Serif" not in html


def test_theme_flag(ai, fake_http):
    assert ai.fetch(OPTIONS, ctx(None))["theme"] == "claude"  # the notice too
    assert ai.fetch(OPTIONS, ctx(limits()))["theme"] == "claude"
    fake_http(TWO_PAGES["openai-api"])
    assert ai.fetch(COST["openai-api"], cost_ctx())["theme"] is None


def test_anthropic_api_theme_and_alert(ai, fake_http):
    fake_http(TWO_PAGES["anthropic-api"])
    assert ai.fetch(COST["anthropic-api"], cost_ctx())["theme"] == "claude"
    fake_http([], error=http_error(401, "theme-key"))
    data = ai.fetch({**COST["anthropic-api"], "key": "theme-key"}, cost_ctx())
    assert data["alert"] is True and data["theme"] == "claude"


def test_claude_theme_html():
    from glancebox.frames import _jinja_env

    tpl = _jinja_env([PAGES_DIR / "ai"]).get_template("template.html")
    base = {"title": "Claude", "clock": "14:05", "message": None, "sub": None, "alert": False,
            "stand": "Stand 13:58", "big": None,
            "rows": [{"label": "Woche", "reset": "", "percent": 42.0, "text": "42 %"}]}
    themed = tpl.render(**base, theme="claude")
    assert "font-family:'DejaVu Serif'" in themed and "#262624" in themed.upper()
    plain = tpl.render(**base, theme=None)
    assert "DejaVu Serif" not in plain and "#262624" not in plain.upper()


# --- cost providers: anthropic-api, openai-api, xai-api -------------------------------------

UTC_ = ZoneInfo("UTC")
MONTH_START = datetime(2026, 11, 1, tzinfo=UTC_)
ANT_KEY = "sk-ant-admin01-SECRET-anthropic"
OAI_KEY = "sk-admin-SECRET-openai"
XAI_KEY = "xai-mgmt-SECRET-xai"
TEAM = "65c1e471-205f-4566-9c5a-07198bcdf4ce"
COST = {
    "anthropic-api": {"provider": "anthropic-api", "key": ANT_KEY},
    "openai-api": {"provider": "openai-api", "key": OAI_KEY},
    "xai-api": {"provider": "xai-api", "key": XAI_KEY, "team_id": TEAM},
}


def anthropic_page(cents: str, next_page: str | None) -> dict:
    """Shape of GET /v1/organizations/analytics/cost (documented example, no group_by)."""
    return {"data": [{"cost": {"amount": cents, "currency": "USD", "list_amount": cents,
                               "requests": 12},
                      "starting_at": "2026-11-01T00:00:00Z",
                      "ending_at": "2026-11-15T13:00:00Z",
                      "group": {"model": None, "workspace_id": None, "cost_type": None}}],
            "data_refreshed_at": "2026-11-15T12:02:11Z",
            "has_more": next_page is not None, "next_page": next_page}


def openai_page(values: list[list[float]], next_page: str | None) -> dict:
    """Shape of GET /v1/organization/costs (documented example)."""
    day = int(MONTH_START.timestamp())
    return {"object": "page",
            "data": [{"object": "bucket", "start_time": day + i * 86400,
                      "end_time": day + (i + 1) * 86400,
                      "results": [{"object": "organization.costs.result",
                                   "amount": {"value": v, "currency": "usd"},
                                   "line_item": None, "project_id": None} for v in bucket]}
                     for i, bucket in enumerate(values)],
            "has_more": next_page is not None, "next_page": next_page}


def xai_balance(cents: str) -> dict:
    """Shape of GET /v1/billing/teams/{team_id}/prepaid/balance (documented example)."""
    return {"changes": [{"teamId": TEAM, "changeOrigin": "PURCHASE", "topupStatus": "SUCCEEDED",
                         "amount": {"val": "-5000"},
                         "createTime": "2026-11-02T15:28:02.308840Z"}],
            "total": {"val": cents}}


# Two pages each; together $18.40.
TWO_PAGES = {
    "anthropic-api": [anthropic_page("1200.000000", "page_2"),
                      anthropic_page("640.000000", None)],
    "openai-api": [openai_page([[5.0, 3.4]], "page_2"), openai_page([[10.0]], None)],
    "xai-api": [xai_balance("-1840")],
}


class FakeHTTP:
    """Stands in for glancebox.http.get_json: answers from `pages` in order, records calls."""

    def __init__(self, pages: list, error: Exception | None = None):
        self.pages = list(pages)
        self.error = error
        self.calls: list[tuple[str, dict, dict]] = []

    def __call__(self, url, *, params=None, headers=None, timeout=10):
        self.calls.append((url, dict(params or {}), dict(headers or {})))
        if self.error is not None:
            raise self.error
        return self.pages[min(len(self.calls) - 1, len(self.pages) - 1)]


@pytest.fixture
def fake_http(monkeypatch):
    from glancebox import http

    def install(pages, error=None):
        fake = FakeHTTP(pages, error)
        monkeypatch.setattr(http, "get_json", fake)
        return fake
    return install


def cost_ctx(now: datetime = NOW, lang: str = "de") -> PageContext:
    return PageContext(now=now, lang=lang, timezone="Europe/Berlin")


def http_error(status: int, key: str) -> Exception:
    import requests

    resp = requests.Response()
    resp.status_code = status
    # A real HTTPError names the URL only; this one also carries the key to prove it never
    # reaches the log, whatever the exception says.
    return requests.HTTPError(f"{status} Client Error for url: https://x/?k={key}", response=resp)


def test_cost_providers_registered(ai):
    for options in COST.values():
        ai.validate(options)
    assert ai.min_refresh == 0


@pytest.mark.parametrize("provider", ["anthropic-api", "openai-api", "xai-api"])
def test_cost_validate_requires_key(ai, provider):
    options = {k: v for k, v in COST[provider].items() if k != "key"}
    with pytest.raises(ValueError, match="key"):
        ai.validate(options)
    with pytest.raises(ValueError, match="key"):
        ai.validate({**options, "key": ""})


def test_xai_validate_requires_team_id(ai):
    with pytest.raises(ValueError, match="team_id"):
        ai.validate({"provider": "xai-api", "key": XAI_KEY})
    with pytest.raises(ValueError, match="team_id"):
        ai.validate({"provider": "xai-api", "key": XAI_KEY, "team_id": ""})
    with pytest.raises(ValueError, match="budget"):
        ai.validate({**COST["xai-api"], "budget": 50})


@pytest.mark.parametrize("provider", ["anthropic-api", "openai-api"])
def test_cost_validate_budget(ai, provider):
    ai.validate({**COST[provider], "budget": 50})
    ai.validate({**COST[provider], "budget": 12.5})
    for bad in (0, -1, "50", True):
        with pytest.raises(ValueError, match="budget"):
            ai.validate({**COST[provider], "budget": bad})


@pytest.mark.parametrize("provider", ["anthropic-api", "openai-api"])
def test_cost_month_sum_over_two_pages(ai, fake_http, provider):
    fake = fake_http(TWO_PAGES[provider])
    data = ai.fetch(COST[provider], cost_ctx())
    assert len(fake.calls) == 2
    assert fake.calls[1][1]["page"] == "page_2"
    assert data["big"] == {"label": "Diesen Monat", "value": "18,40 $"}
    assert data["rows"] == [] and data["message"] is None and data["alert"] is False
    fake_http(TWO_PAGES[provider])
    en = ai.fetch({**COST[provider], "lang": "en", "key": provider + "-other"}, cost_ctx())
    assert en["big"] == {"label": "This month", "value": "$18.40"}


def test_anthropic_request(ai, fake_http):
    fake = fake_http(TWO_PAGES["anthropic-api"])
    data = ai.fetch(COST["anthropic-api"], cost_ctx())
    url, params, headers = fake.calls[0]
    assert url == "https://api.anthropic.com/v1/organizations/analytics/cost"
    assert params == {"starting_at": "2026-11-01T00:00:00Z"}
    assert headers == {"x-api-key": ANT_KEY, "anthropic-version": "2026-10-21",
                       "anthropic-beta": "analytics-usage-cost-2026-08-24"}
    assert data["title"] == "Anthropic API"
    assert data["stand"] == "Stand 13:02"  # data_refreshed_at 12:02 UTC


def test_cost_stand_twelve_hours(ai, fake_http):
    fake_http(TWO_PAGES["anthropic-api"])
    data = ai.fetch(COST["anthropic-api"], replace(cost_ctx(), time_format="12h"))
    assert data["stand"] == "Stand 1:02 PM"  # data_refreshed_at 12:02 UTC
    fake_http([], error=http_error(401, "other-key"))
    en = ai.fetch({**COST["openai-api"], "lang": "en"},
                  replace(cost_ctx(), time_format="12h"))
    assert (en["message"], en["sub"]) == ("No data", "As of 2:05 PM")


def test_openai_request(ai, fake_http):
    fake = fake_http(TWO_PAGES["openai-api"])
    data = ai.fetch(COST["openai-api"], cost_ctx())
    url, params, headers = fake.calls[0]
    assert url == "https://api.openai.com/v1/organization/costs"
    assert params == {"start_time": int(MONTH_START.timestamp()), "bucket_width": "1d",
                      "limit": 31}
    assert headers == {"Authorization": f"Bearer {OAI_KEY}"}
    assert data["title"] == "OpenAI API"
    assert data["stand"] == "Stand 14:05"


def test_xai_balance(ai, fake_http):
    fake = fake_http(TWO_PAGES["xai-api"])
    data = ai.fetch(COST["xai-api"], cost_ctx())
    url, params, headers = fake.calls[0]
    assert url == f"https://management-api.x.ai/v1/billing/teams/{TEAM}/prepaid/balance"
    assert params == {}
    assert headers == {"Authorization": f"Bearer {XAI_KEY}"}
    assert data["title"] == "xAI API"
    assert data["big"] == {"label": "Guthaben", "value": "18,40 $"}
    assert data["rows"] == [] and data["stand"] == "Stand 14:05"
    fake_http([xai_balance("-123456")])
    en = ai.fetch({**COST["xai-api"], "lang": "en", "key": "other"}, cost_ctx())
    assert en["big"] == {"label": "Balance", "value": "$1,234.56"}
    fake_http([xai_balance("250")])
    owed = ai.fetch({**COST["xai-api"], "key": "third"}, cost_ctx())
    assert owed["big"]["value"] == "-2,50 $"


def test_xai_remaining_has_no_rows(ai, fake_http):
    fake_http(TWO_PAGES["xai-api"])
    data = ai.fetch({**COST["xai-api"], "show": "remaining"}, cost_ctx())
    assert data["rows"] == [] and data["big"] == {"label": "Guthaben", "value": "18,40 $"}


@pytest.mark.parametrize("provider", ["anthropic-api", "openai-api"])
def test_cost_budget_row(ai, fake_http, provider):
    fake_http(TWO_PAGES[provider])
    data = ai.fetch({**COST[provider], "budget": 50}, cost_ctx())
    assert data["rows"] == [{"label": "Budget", "reset": "1.12.", "percent": 36.8,
                             "text": "37 %"}]
    en = ai.fetch({**COST[provider], "budget": 15.3333, "lang": "en"}, cost_ctx())
    assert en["rows"][0]["reset"] == "Dec 1"
    assert en["rows"][0]["text"] == "120 %" and en["rows"][0]["percent"] > 100


def test_budget_row_clamps_bar_keeps_text():
    from glancebox.frames import _jinja_env

    html = _jinja_env([PAGES_DIR / "ai"]).get_template("template.html").render(
        title="OpenAI API", clock="14:05", message=None, sub=None, alert=False,
        stand="Stand 14:05", big={"label": "Diesen Monat", "value": "60,00 $"},
        rows=[{"label": "Budget", "reset": "1.12.", "percent": 120.0, "text": "120 %"}])
    assert "width:100%" in html and "120 %" in html and "ui-bad" in html


@pytest.mark.parametrize("provider", ["anthropic-api", "openai-api", "xai-api"])
def test_cost_http_401_message_without_key(ai, fake_http, caplog, provider):
    key = COST[provider]["key"]
    fake_http([], error=http_error(401, key))
    with caplog.at_level("DEBUG"):
        data = ai.fetch(COST[provider], cost_ctx())
    assert data["message"] == "Keine Daten" and data["sub"] == "Stand 14:05"
    assert data["alert"] is True and data["big"] is None
    assert "401" in caplog.text
    assert key not in caplog.text
    fake_http([], error=http_error(401, key))
    en = ai.fetch({**COST[provider], "lang": "en"}, cost_ctx())
    assert (en["message"], en["sub"]) == ("No data", "As of 14:05")


@pytest.mark.parametrize("provider", ["anthropic-api", "openai-api", "xai-api"])
def test_cost_network_and_shape_errors(ai, fake_http, caplog, provider):
    import requests

    for seconds, error, pages in ((0, requests.ConnectionError("refused"), []),
                                  (61, None, [{"odd": 1}])):  # 61: after the failure cache
        fake = fake_http(pages, error=error)
        data = ai.fetch(COST[provider], cost_ctx(NOW + timedelta(seconds=seconds)))
        assert len(fake.calls) >= 1
        assert data["message"] == "Keine Daten"
    assert COST[provider]["key"] not in caplog.text


@pytest.mark.parametrize("provider", ["anthropic-api", "openai-api"])
def test_cost_pagination_is_capped(ai, fake_http, provider):
    endless = (anthropic_page("1.0", "again") if provider == "anthropic-api"
               else openai_page([[0.01]], "again"))
    fake = fake_http([endless])
    data = ai.fetch(COST[provider], cost_ctx())
    assert len(fake.calls) == 20
    assert data["message"] == "Keine Daten"


@pytest.mark.parametrize("provider", ["anthropic-api", "openai-api", "xai-api"])
def test_cached_for_300s(ai, fake_http, provider):
    single = {"anthropic-api": [anthropic_page("1840.0", None)],
              "openai-api": [openai_page([[18.4]], None)],
              "xai-api": [xai_balance("-1840")]}[provider]
    fake = fake_http(single)
    first = ai.fetch(COST[provider], cost_ctx(NOW))
    second = ai.fetch(COST[provider], cost_ctx(NOW + timedelta(seconds=299)))
    assert len(fake.calls) == 1
    assert second["big"] == first["big"]
    ai.fetch(COST[provider], cost_ctx(NOW + timedelta(seconds=301)))
    assert len(fake.calls) == 2
    # Another key is another cache entry.
    ai.fetch({**COST[provider], "key": "another"}, cost_ctx(NOW + timedelta(seconds=302)))
    assert len(fake.calls) == 3


@pytest.mark.parametrize("provider", ["anthropic-api", "openai-api", "xai-api", "copilot"])
def test_failures_cached_for_60s(ai, fake_http, provider):
    options = COPILOT if provider == "copilot" else COST[provider]
    fake = fake_http([], error=http_error(401, options["key"]))
    for seconds in (0, 30, 59):
        data = ai.fetch(options, cost_ctx(NOW + timedelta(seconds=seconds)))
        assert data["message"] == "Keine Daten" and data["alert"] is True
    assert len(fake.calls) == 1
    # The notice carries the time of the current attempt, never a stale amount.
    assert data["sub"] == "Stand 14:05" and data["big"] is None
    ai.fetch(options, cost_ctx(NOW + timedelta(seconds=61)))
    assert len(fake.calls) == 2


def test_success_after_failure_cache_expired(ai, fake_http):
    import requests

    fake_http([], error=requests.ConnectionError("down"))
    assert ai.fetch(COST["openai-api"], cost_ctx())["message"] == "Keine Daten"
    fake = fake_http([openai_page([[18.4]], None)])
    data = ai.fetch(COST["openai-api"], cost_ctx(NOW + timedelta(seconds=61)))
    assert len(fake.calls) == 1 and data["big"]["value"] == "18,40 $"
    # A success replaces the failure: the amount is now cached for 300 s.
    ai.fetch(COST["openai-api"], cost_ctx(NOW + timedelta(seconds=200)))
    assert len(fake.calls) == 1


def test_xai_cache_keyed_by_team(ai, fake_http):
    fake = fake_http([xai_balance("-1840")])
    ai.fetch(COST["xai-api"], cost_ctx())
    ai.fetch({**COST["xai-api"], "team_id": "other-team"}, cost_ctx())
    assert len(fake.calls) == 2


# --- copilot: premium requests / AI credits against a user-supplied allowance ---------------

GH_KEY = "github_pat_SECRET-copilot"
COPILOT = {"provider": "copilot", "key": GH_KEY, "username": "octocat",
           "monthly_allowance": 300, "unit": "premium-requests"}
GH_HEADERS = {"Authorization": f"Bearer {GH_KEY}", "Accept": "application/vnd.github+json",
              "X-GitHub-Api-Version": "2026-03-10"}


def gh_usage(*quantities: float, unit_type: str = "requests") -> dict:
    """Shape of GET /users/{username}/settings/billing/{premium_request,ai_credit}/usage
    (documented example: one usageItem per model)."""
    return {"timePeriod": {"year": 2026, "month": 11}, "user": "octocat",
            "usageItems": [{"product": "Copilot", "sku": "Copilot Premium Request",
                            "model": f"model-{i}", "unitType": unit_type,
                            "pricePerUnit": 0.04, "grossQuantity": q, "grossAmount": q * 0.04,
                            "discountQuantity": q, "discountAmount": q * 0.04,
                            "netQuantity": 0, "netAmount": 0} for i, q in enumerate(quantities)]}


def test_copilot_registered_and_validate(ai):
    ai.validate(COPILOT)
    ai.validate({**COPILOT, "unit": "ai-credits", "monthly_allowance": 1500})
    ai.validate({k: v for k, v in COPILOT.items() if k != "unit"})  # ai-credits by default
    for name in ("key", "username"):
        with pytest.raises(ValueError, match=name):
            ai.validate({k: v for k, v in COPILOT.items() if k != name})
        with pytest.raises(ValueError, match=name):
            ai.validate({**COPILOT, name: ""})
    for bad in (None, 0, -5, "300", True):
        options = {k: v for k, v in COPILOT.items() if k != "monthly_allowance"}
        if bad is not None:
            options["monthly_allowance"] = bad
        with pytest.raises(ValueError, match="monthly_allowance"):
            ai.validate(options)
    with pytest.raises(ValueError, match="unit"):
        ai.validate({**COPILOT, "unit": "requests"})
    with pytest.raises(ValueError, match="budget"):
        ai.validate({**COPILOT, "budget": 10})


def test_copilot_premium_requests(ai, fake_http):
    fake = fake_http([gh_usage(200, 12)])
    data = ai.fetch(COPILOT, cost_ctx())
    url, params, headers = fake.calls[0]
    assert url == "https://api.github.com/users/octocat/settings/billing/premium_request/usage"
    assert params == {"year": 2026, "month": 11}
    assert headers == GH_HEADERS
    assert data["title"] == "GitHub Copilot"
    assert data["rows"] == [{"label": "Premium-Requests", "reset": "1.12.",
                             "percent": pytest.approx(212 / 300 * 100), "text": "212 / 300"}]
    assert data["big"] == {"label": "Übrig", "value": "88"}
    assert data["stand"] == "Stand 14:05"
    assert data["message"] is None and data["alert"] is False


def test_copilot_stand_twelve_hours(ai, fake_http):
    fake_http([gh_usage(200, 12)])
    data = ai.fetch(COPILOT, replace(cost_ctx(), time_format="12h"))
    assert data["stand"] == "Stand 2:05 PM"


def test_copilot_ai_credits_english(ai, fake_http):
    fake = fake_http([gh_usage(1000, 234.25, unit_type="ai-credits")])
    options = {**COPILOT, "unit": "ai-credits", "monthly_allowance": 1500, "lang": "en"}
    data = ai.fetch(options, cost_ctx())
    assert fake.calls[0][0] == (
        "https://api.github.com/users/octocat/settings/billing/ai_credit/usage")
    assert data["rows"] == [{"label": "AI credits", "reset": "Dec 1",
                             "percent": pytest.approx(1234.25 / 1500 * 100),
                             "text": "1,234 / 1,500"}]
    assert data["big"] == {"label": "Left", "value": "266"}
    fake_http([gh_usage(1000, 234.25, unit_type="ai-credits")])
    de = ai.fetch({**options, "lang": "de", "key": "other"}, cost_ctx())
    assert de["rows"][0]["label"] == "AI-Credits" and de["rows"][0]["text"] == "1.234 / 1.500"


def test_copilot_empty_and_over_allowance(ai, fake_http):
    fake_http([gh_usage()])
    data = ai.fetch(COPILOT, cost_ctx())
    assert data["rows"][0]["text"] == "0 / 300" and data["rows"][0]["percent"] == 0
    assert data["big"]["value"] == "300"
    fake_http([gh_usage(320)])
    over = ai.fetch({**COPILOT, "key": "other"}, cost_ctx())
    assert over["rows"][0]["text"] == "320 / 300" and over["rows"][0]["percent"] > 100
    assert over["big"]["value"] == "0"


def test_copilot_remaining(ai, fake_http):
    fake_http([gh_usage(200, 12)])
    data = ai.fetch({**COPILOT, "show": "remaining"}, cost_ctx())
    assert data["rows"] == [{"label": "Premium-Requests", "reset": "1.12.",
                             "percent": pytest.approx(88 / 300 * 100), "text": "88 / 300",
                             "used": pytest.approx(212 / 300 * 100)}]


def test_copilot_remaining_over_allowance_is_zero(ai, fake_http):
    fake_http([gh_usage(320)])
    row = ai.fetch({**COPILOT, "show": "remaining"}, cost_ctx())["rows"][0]
    assert row["percent"] == 0.0 and row["text"] == "0 / 300" and row["used"] > 100


def test_budget_remaining_over_budget_is_zero(ai, fake_http):
    fake_http(TWO_PAGES["openai-api"])
    row = ai.fetch({**COST["openai-api"], "budget": 15.3333, "show": "remaining"},
                   cost_ctx())["rows"][0]
    assert row["percent"] == 0.0 and row["text"] == "0 %" and row["used"] > 100


def test_copilot_month_is_utc(ai, fake_http):
    # 00:30 on 1 Dec in Berlin is still 30 Nov in UTC, where GitHub's month runs.
    fake = fake_http([gh_usage(5)])
    data = ai.fetch(COPILOT, cost_ctx(datetime(2026, 12, 1, 0, 30, tzinfo=TZ)))
    assert fake.calls[0][1] == {"year": 2026, "month": 11}
    assert data["rows"][0]["reset"] == "1.12."


def test_copilot_username_is_quoted(ai, fake_http):
    fake = fake_http([gh_usage()])
    ai.fetch({**COPILOT, "username": "a/b?c"}, cost_ctx())
    assert fake.calls[0][0] == (
        "https://api.github.com/users/a%2Fb%3Fc/settings/billing/premium_request/usage")


def test_copilot_errors_show_notice_without_key(ai, fake_http, caplog):
    fake_http([], error=http_error(403, GH_KEY))
    with caplog.at_level("DEBUG"):
        data = ai.fetch(COPILOT, cost_ctx())
    assert data["message"] == "Keine Daten" and data["sub"] == "Stand 14:05"
    assert data["alert"] is True and data["big"] is None and data["rows"] == []
    assert "ai copilot: no data: HTTPError (HTTP 403)" in caplog.text
    fake = fake_http([{"odd": 1}])
    assert ai.fetch(COPILOT, cost_ctx(NOW + timedelta(seconds=61)))["message"] == "Keine Daten"
    assert len(fake.calls) == 1
    assert GH_KEY not in caplog.text


def test_copilot_cached_by_key_username_and_unit(ai, fake_http):
    fake = fake_http([gh_usage(10)])
    ai.fetch(COPILOT, cost_ctx(NOW))
    later = ai.fetch(COPILOT, cost_ctx(NOW + timedelta(seconds=299)))
    assert len(fake.calls) == 1 and later["stand"] == "Stand 14:05"
    ai.fetch({**COPILOT, "username": "other"}, cost_ctx(NOW))
    ai.fetch({**COPILOT, "unit": "ai-credits"}, cost_ctx(NOW))
    assert len(fake.calls) == 3
    # The allowance is not part of the request, so changing it reuses the cached usage.
    data = ai.fetch({**COPILOT, "monthly_allowance": 100}, cost_ctx(NOW))
    assert len(fake.calls) == 3 and data["rows"][0]["text"] == "10 / 100"
