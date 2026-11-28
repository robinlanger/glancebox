import pytest

from glancebox.frames import _jinja_env


def _render(expr: str) -> str:
    tpl = '{% import "ui.html" as ui %}' + expr
    return _jinja_env([]).from_string(tpl).render()


def test_bar_level_thresholds():
    assert "ui-ok" in _render('{{ ui.bar(74, "x") }}')
    assert "ui-warn" in _render('{{ ui.bar(75, "x") }}')
    assert "ui-bad" in _render('{{ ui.bar(90, "x") }}')


def test_bar_width_is_clamped():
    assert "width:100%" in _render('{{ ui.bar(130, "x") }}')
    assert "width:0%" in _render('{{ ui.bar(-5, "x") }}')


def test_level_returns_class_name_only():
    assert _render("{{ ui.level(10) }}") == "ui-ok"
    assert _render("{{ ui.level(80) }}") == "ui-warn"
    assert _render("{{ ui.level(95) }}") == "ui-bad"


def test_header_alert_class():
    assert "ui-alert" in _render('{{ ui.header("T", "14:05", alert=True) }}')
    out = _render('{{ ui.header("T", "14:05") }}')
    assert "ui-alert" not in out and "14:05" in out


def test_notice_escapes_and_tones():
    out = _render('{{ ui.notice("<b>", sub="<i>", tone="warn") }}')
    assert "&lt;b&gt;" in out and "&lt;i&gt;" in out and "<b>" not in out
    assert "ui-tone-warn" in out


def test_clock_plain_text_is_unchanged():
    assert _render('{{ ui.clock("14:05") }}') == "14:05"


def test_clock_small_suffix():
    assert _render('{{ ui.clock("2:05 PM") }}') == '2:05<span class="ui-ampm">PM</span>'
    assert _render('{{ ui.clock("12:00 AM") }}') == '12:00<span class="ui-ampm">AM</span>'


def test_clock_takes_odd_values():
    assert _render("{{ ui.clock(none) }}") in ("", "None")
    assert _render("{{ ui.clock(1405) }}") == "1405"
    assert _render('{{ ui.clock("<b> PM") }}') == '&lt;b&gt;<span class="ui-ampm">PM</span>'


def test_header_uses_clock():
    out = _render('{{ ui.header("T", "2:05 PM") }}')
    assert '<span class="ui-clock">2:05<span class="ui-ampm">PM</span></span>' in out
    assert '<span class="ui-clock">14:05</span>' in _render('{{ ui.header("T", "14:05") }}')


@pytest.mark.browser
async def test_header_12h_clock_fits():
    from playwright.async_api import async_playwright

    tpl = ('{% extends "base.html" %}{% import "ui.html" as ui %}'
           '{% block body %}{{ ui.header("Wohnzimmer Solaranlage", "12:59 PM") }}{% endblock %}')
    html = _jinja_env([]).from_string(tpl).render()
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 240, "height": 240})
        await page.set_content(html)
        boxes = await page.evaluate(
            "Object.fromEntries(['ui-clock', 'ui-title'].map(c => {"
            " const e = document.querySelector('.' + c); const r = e.getBoundingClientRect();"
            " return [c, {right: r.right, width: r.width,"
            " overflow: e.scrollWidth > e.clientWidth}]; }))")
        await browser.close()
    assert boxes["ui-clock"]["right"] <= 233
    assert not boxes["ui-clock"]["overflow"]
    assert boxes["ui-title"]["width"] >= 120
