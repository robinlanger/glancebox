# 12-Hour Time Format and Add-on Guide Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A `time_format: 24h | 12h` setting switches every time of day on the built-in pages (issue #36), and the Home Assistant add-on gets a step-by-step setup guide with examples and troubleshooting (issue #37).

**Architecture:** Part A: one new module `server/glancebox/timefmt.py` formats all times of day; the setting lives in `config.yaml` (top level, overridable per page as a reserved page key) and reaches pages as `ctx.time_format` / `ctx.clock()`. Pages stop calling `strftime("%H:%M")`. Tight layouts show a small AM/PM suffix. Part B: `docs/{en,de}/home-assistant.md` is rebuilt into the guide, `ha-addon/DOCS.md` stays short and links to it; a new test loads every YAML example of these files in add-on mode. No firmware change in either part.

**Tech Stack:** Python 3.12 (FastAPI server, Jinja2, pytest, ruff, Playwright/Chromium for `browser` tests), Markdown docs (MkDocs, en + de).

**Spec:** `docs/superpowers/specs/2026-11-28-zeitformat-addon-anleitung-design.md` (German). Read it first; its tables "Befund" and "Darstellung, je Ort entschieden" are binding. Its section "Offene Fragen" lists decisions Robin has not confirmed: if Robin changed one, follow Robin.

## Global Constraints

- Branch `feat/issues-36-37`, in the worktree you were started in. One commit per task. No push, no tag, no release, no comment on the GitHub issues.
- Commit with exactly this form (the email is the project's noreply address):
  `git -c user.email=106265325+robinlanger@users.noreply.github.com commit -m "<message>"`, message in English, conventional style, ending with the trailer line `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- No personal data in the repo: no real IPs, names, emails, tokens, entity ids of a real home. Placeholders only: `192.168.1.x`, `http://192.168.1.50:8080`, `homeassistant.local`, `sensor.pv_power`.
- Code, comments, `docs/en`, `ha-addon/DOCS.md` and the CHANGELOG are English; `docs/de` is German. Line length 100 in Python. Follow the tone of the surrounding files (short sentences, no marketing).
- Default behaviour must not change: without `time_format` every page's data and picture is identical to today. Every existing test keeps passing unchanged, except the two `clock` tests named in Task 5.
- 12-hour text is exactly `H:MM AM` / `H:MM PM`: no leading zero, one space, capitals, the same for `lang: de` and `en`. Midnight is `12:00 AM`, noon `12:00 PM`.
- Durations and countdowns are never touched: `in 2:13`, `noch 1:23 h`, `12 min`, `vor 4 min`.
- The response header `X-Local-Time` (`server/glancebox/app.py`) stays `HH:MM:SS` in 24 hours. Nothing under `firmware/` changes.
- New dataclass fields go last and have defaults: `PageContext(now, lang, timezone)`, `AppConfig(30, "Europe/Berlin", "de", pages, ())` and `PageConfig(0, "clock", {}, 30, 60)` must keep working positionally.
- Environment: the worktree has no virtualenv. Create it once before Task 1 (not committed, `server/.venv/` is ignored):
  `python3.12 -m venv server/.venv && server/.venv/bin/pip install --require-hashes -r server/requirements.lock -r server/requirements-dev.lock && server/.venv/bin/pip install --no-deps -e server && server/.venv/bin/playwright install chromium`
- Run from `server/`: tests `.venv/bin/python -m pytest -q -m "not browser"`, browser tests `.venv/bin/python -m pytest -q -m browser`, lint `.venv/bin/ruff check . ../pages`. From the repo root: `python3 tools/check_docs_parity.py`.
- `VERSION` and `ha-addon/config.yaml` `version` stay `0.8.0`. CHANGELOG entries go under a new `## [Unreleased]` section above `## [0.8.0]`.
- Anything not checked on a real Home Assistant is worded carefully in the docs and listed as unchecked in the CHANGELOG. Never write "tested" for something only read from code.

## Review Focus

1. A custom page that still calls `ui.header(title, "14:05")`, or passes a non-string or `None` as clock: the header renders as today, no exception. Test in Task 3.
2. `time_format: 12` (a YAML number), `time_format: 12H`, `time_format:` left empty, and a per-page `time_format: am`: the server refuses to start with a message naming the key and the two allowed values; an empty top-level value means the default. Test in Task 2.
3. Times at the edges: 00:00, 00:59, 12:00, 12:59, 23:59, and a DBF `scheduled` text that is not `HH:MM` (empty, `"24:10"`, `"--:--"`): no exception, the odd text is shown unchanged. Tests in Task 1 and Task 6.
4. A printer page that validates its options strictly (`unknown key`) with a per-page `time_format: 12h`: the config loads, because the key never reaches the page's options. Test in Task 2.
5. A YAML example in the guide that the add-on would reject (wrong indentation, a key the page does not know, a `${NAME}` the form does not offer): the docs test fails. Test in Task 10.

---

## File Structure

| File | Responsibility |
| --- | --- |
| `server/glancebox/timefmt.py` (new) | The only place that formats a time of day. |
| `server/glancebox/config.py` | Parses and validates `time_format` (top level and per page). |
| `server/glancebox/pages.py`, `frames.py` | `PageContext.time_format`, `PageContext.clock()`; the per-page value wins. |
| `server/glancebox/templates/ui.html`, `base.html` | `ui.clock` macro, `.ui-ampm` style. |
| `pages/*/page.py`, `pages/*/template.html`, providers | Use `ctx.clock()` / `timefmt`; 12-hour layout where width is tight. |
| `server/glancebox/addon.py` | Starter playlist comment names `time_format`. |
| `tools/render_previews.py`, `docs/img/templates/clock-12h.png` | One new preview. |
| `docs/{en,de}/…`, `config-example.yaml`, `pages/*/README.md` | Option reference. |
| `docs/{en,de}/home-assistant.md`, `ha-addon/DOCS.md` | The guide (Part B). |
| `server/tests/test_addon_docs.py` (new) | Keeps the guide in line with the code. |

---

# Part A: time format (issue #36)

### Task 1: `timefmt` module

**Files:**
- Create: `server/glancebox/timefmt.py`
- Test: `server/tests/test_timefmt.py` (new)

**Interfaces:**
- Consumes: nothing.
- Produces (all later tasks use these names):

```python
TIME_FORMATS: tuple[str, str] = ("24h", "12h")
def format_time(when: datetime | time, time_format: str = "24h") -> str   # "14:05" | "2:05 PM"
def format_hour(when: datetime | time, time_format: str = "24h") -> str   # "15" | "3 PM"
def split_suffix(text: str) -> tuple[str, str]        # ("2:05", "PM") | ("14:05", "")
def convert_hhmm(text: str, time_format: str = "24h") -> str  # "21:10" -> "9:10 PM"
```

- [ ] **Step 1: Write the failing tests** in `server/tests/test_timefmt.py`:

```python
from datetime import datetime, time

import pytest

from glancebox.timefmt import TIME_FORMATS, convert_hhmm, format_hour, format_time, split_suffix


def test_formats():
    assert TIME_FORMATS == ("24h", "12h")


@pytest.mark.parametrize(("hm", "h24", "h12"), [
    ((0, 0), "00:00", "12:00 AM"), ((0, 59), "00:59", "12:59 AM"), ((1, 5), "01:05", "1:05 AM"),
    ((9, 5), "09:05", "9:05 AM"), ((11, 59), "11:59", "11:59 AM"), ((12, 0), "12:00", "12:00 PM"),
    ((12, 59), "12:59", "12:59 PM"), ((13, 0), "13:00", "1:00 PM"), ((23, 59), "23:59", "11:59 PM"),
])
def test_format_time(hm, h24, h12):
    for when in (time(*hm), datetime(2026, 11, 28, *hm)):
        assert format_time(when) == h24
        assert format_time(when, "24h") == h24
        assert format_time(when, "12h") == h12


@pytest.mark.parametrize(("hour", "h24", "h12"), [
    (0, "00", "12 AM"), (3, "03", "3 AM"), (12, "12", "12 PM"), (15, "15", "3 PM"),
    (23, "23", "11 PM")])
def test_format_hour(hour, h24, h12):
    assert (format_hour(time(hour, 30)), format_hour(time(hour, 30), "12h")) == (h24, h12)


@pytest.mark.parametrize(("text", "parts"), [
    ("2:05 PM", ("2:05", "PM")), ("12:00 AM", ("12:00", "AM")), ("14:05", ("14:05", "")),
    ("Tue 9:14 PM", ("Tue 9:14", "PM")), ("", ("", "")), ("PM", ("PM", "")),
    ("2:05 pm", ("2:05 pm", "")), ("Stand 14:05", ("Stand 14:05", ""))])
def test_split_suffix(text, parts):
    assert split_suffix(text) == parts


@pytest.mark.parametrize(("text", "h12"), [
    ("21:10", "9:10 PM"), ("00:05", "12:05 AM"), ("7:40", "7:40 AM"), ("12:00", "12:00 PM"),
    ("", ""), ("24:10", "24:10"), ("12:60", "12:60"), ("--:--", "--:--"), ("21.10", "21.10"),
    ("21:10:00", "21:10:00")])
def test_convert_hhmm(text, h12):
    assert convert_hhmm(text) == text
    assert convert_hhmm(text, "24h") == text
    assert convert_hhmm(text, "12h") == h12


def test_unknown_format_is_an_error():
    with pytest.raises(ValueError, match="time_format"):
        format_time(time(1, 2), "am")
```

- [ ] **Step 2: Run** `.venv/bin/python -m pytest -q tests/test_timefmt.py` from `server/`. Expected: import error (module missing).
- [ ] **Step 3: Implement** the four functions with the signatures above. Compute the hour from `.hour` (`hour % 12 or 12`); do not use `strftime("%I")` or `"%-I"`. `convert_hhmm` accepts only `H:MM` / `HH:MM` with hour 0 to 23 and minute 0 to 59 and returns anything else unchanged; in `24h` it returns its input unchanged. `format_time` and `format_hour` raise `ValueError("time_format must be '24h' or '12h', got …")` for another format. Module docstring: this is the only place that formats a time of day; durations are not its business.
- [ ] **Step 4: Run** the test file again, then `.venv/bin/ruff check .`. Expected: all pass, no findings.
- [ ] **Step 5: Commit** `feat(server): central time-of-day formatting (24h/12h)`.

---

### Task 2: `time_format` in the configuration and the page context

**Files:**
- Modify: `server/glancebox/config.py` (`_TOP_LEVEL_KEYS`, `_RESERVED_PAGE_KEYS`, `PageConfig`, `AppConfig`, `_parse_page`, `load_config`)
- Modify: `server/glancebox/pages.py` (`PageContext`)
- Modify: `server/glancebox/frames.py` (`fetch_page_data`)
- Test: `server/tests/test_config.py`, `server/tests/test_frames.py`, `server/tests/test_pages.py`, `server/tests/test_app.py`

**Interfaces:**
- Consumes: `glancebox.timefmt.TIME_FORMATS`, `format_time` (Task 1).
- Produces:
  - `AppConfig.time_format: str = "24h"` (last field), `PageConfig.time_format: str | None = None` (last field; `None` = use the top-level value).
  - `PageContext.time_format: str = "24h"` (last field, after `pushed`).
  - `PageContext.clock(self, when: datetime | time | None = None) -> str`: `format_time(when or self.now, self.time_format)`.

- [ ] **Step 1: Write the failing tests.**

`server/tests/test_config.py` (uses the file's `write` helper):

```python
def test_time_format_default_and_values(tmp_path):
    base = "pages:\n  - type: clock\n"
    assert load_config(write(tmp_path, base)).time_format == "24h"
    assert load_config(write(tmp_path, "time_format: 12h\n" + base)).time_format == "12h"
    assert load_config(write(tmp_path, "time_format: 24h\n" + base)).time_format == "24h"
    assert load_config(write(tmp_path, "time_format:\n" + base)).time_format == "24h"  # empty


@pytest.mark.parametrize("value", ["12", "12H", "am", "'12'", "true", "[12h]"])
def test_time_format_rejects_other_values(tmp_path, value):
    with pytest.raises(ConfigError, match="time_format must be '24h' or '12h'"):
        load_config(write(tmp_path, f"time_format: {value}\npages:\n  - type: clock\n"))


def test_time_format_per_page(tmp_path):
    cfg = load_config(write(tmp_path, "time_format: 12h\npages:\n  - type: clock\n"
                                      "  - {type: bahn, station: X, time_format: 24h}\n"))
    assert [p.time_format for p in cfg.pages] == [None, "24h"]
    assert "time_format" not in cfg.pages[1].options       # reserved, like duration/refresh


def test_time_format_per_page_rejects_other_values(tmp_path):
    with pytest.raises(ConfigError, match=r"pages\[0\]: time_format must be '24h' or '12h'"):
        load_config(write(tmp_path, "pages:\n  - {type: clock, time_format: am}\n"))
```

`server/tests/test_pages.py` (review focus 4; use the file's existing way of building a config from the repo's `pages/` directory, or `load_config` + `load_page_types(cfg.pages_dirs)` + `validate_config`):

```python
def test_strict_page_accepts_per_page_time_format(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text("pages:\n  - {type: printer, source: moonraker, "
                 "url: 'http://drucker.local:7125', time_format: 12h}\n")
    cfg = load_config(p)
    cfg = validate_config(cfg, load_page_types(cfg.pages_dirs))
    assert cfg.pages[0].time_format == "12h"
```

`server/tests/test_frames.py`, next to `test_context_uses_page_lang_and_tz` (same `script_type` / `page` / `make_cfg` helpers; `page()` builds a `PageConfig`, so set the field with `dataclasses.replace`):

```python
async def test_context_time_format_page_wins(tmp_path):
    seen = []

    def fetch(o, c):
        seen.append((c.time_format, c.clock(), c.clock(datetime(2026, 1, 1, 21, 10))))
        return {"v": 1}

    t = script_type(tmp_path, "a", fetch)
    cfg = dataclasses.replace(
        make_cfg(page(0, "a"), dataclasses.replace(page(1, "a"), time_format="24h")),
        time_format="12h")
    await refresh_once(cfg, {"a": t}, FakeRenderer(), FrameStore(2), 0)
    # now = epoch 0 = 01:00 in Europe/Berlin
    assert seen == [("12h", "1:00 AM", "9:10 PM"), ("24h", "01:00", "21:10")]


def test_context_defaults_to_24h():
    ctx = PageContext(datetime(2026, 11, 28, 14, 5), "de", "Europe/Berlin")
    assert (ctx.time_format, ctx.clock()) == ("24h", "14:05")
```

`server/tests/test_app.py`, next to `test_frame_has_local_time_header` (anti-goal of the spec): build the client as that test does but with a config whose `time_format` is `"12h"` (`dataclasses.replace` on the config the helper uses, or a parameter added to `make_client`) and assert `headers["x-local-time"] == "14:46:40"`. Name: `test_local_time_header_ignores_time_format`.

- [ ] **Step 2: Run** `.venv/bin/python -m pytest -q tests/test_config.py tests/test_frames.py tests/test_pages.py tests/test_app.py` from `server/`. Expected: the new tests fail (unknown top-level key, missing attribute); `test_local_time_header_ignores_time_format` may already pass once the field exists, that is fine.
- [ ] **Step 3: Implement.** `config.py`: one private helper `_time_format(value: Any, where: str) -> str` raising `ConfigError(f"{where}time_format must be '24h' or '12h', got {value!r}")` (top level: `where=""`; page: `where="pages[0]: "`), a YAML string only (reject `bool`/`int`/list). Top level: missing or `None` → `"24h"`. Page: key present → validated string, absent → `None`. `frames.fetch_page_data`: `time_format=page.time_format or cfg.time_format`.
- [ ] **Step 4: Run** `.venv/bin/python -m pytest -q -m "not browser"` and `.venv/bin/ruff check . ../pages`. Expected: all pass.
- [ ] **Step 5: Commit** `feat(server): time_format option, top level and per page`.

---

### Task 3: header clock with a small AM/PM suffix

**Files:**
- Modify: `server/glancebox/templates/ui.html` (new macro `clock`, `header` uses it)
- Modify: `server/glancebox/templates/base.html` (style `.ui-ampm`)
- Test: `server/tests/test_ui.py`

**Interfaces:**
- Consumes: nothing from Python (a pure template change), or `timefmt.split_suffix` if you register it as a Jinja global in `frames._jinja_env` (your choice; `tools/render_previews.py` and the tests build their environment through `_jinja_env`, so a global registered there reaches all of them).
- Produces: `{{ ui.clock(text) }}` → the text unchanged, or for a text ending in ` AM` / ` PM`: `2:05<span class="ui-ampm">PM</span>`. `ui.header(title, clock, alert=False)` keeps its signature.

- [ ] **Step 1: Write the failing tests** in `server/tests/test_ui.py`:

```python
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
```

- [ ] **Step 2: Run** `.venv/bin/python -m pytest -q tests/test_ui.py`. Expected: the four new tests fail.
- [ ] **Step 3: Implement.** Add to `base.html`: `.ui-ampm{font-size:11px;margin-left:3px;}` (inherits weight and colour of the clock). The escaped time part must stay escaped (autoescape is on; never mark user text `safe`).
- [ ] **Step 4: Add a browser test** in `server/tests/test_ui.py` (`@pytest.mark.browser`, pattern of `test_render_html_umlauts` in `server/tests/test_render.py`): render a page that extends `base.html` and calls `ui.header("Wohnzimmer Solaranlage", "12:59 PM")`, with Playwright as in `pages/printer/test_printer.py` (the helper near line 560 that returns boxes with `overflow`), and assert: `.ui-clock` right edge ≤ 233, `.ui-clock` not overflowing, `.ui-title` width ≥ 120. Run it with `-m browser`; expected: pass.
- [ ] **Step 5: Run** the whole suite and ruff as in Task 2. Expected: all pass (existing pages still pass 24-hour text, so their pictures are unchanged).
- [ ] **Step 6: Commit** `feat(ui): header clock shows AM/PM as a small suffix`.

---

### Task 4: header clocks and "as of" texts on weather, kuma, homeassistant, energy

**Files:**
- Modify: `pages/weather/page.py` (clock, `hours[].hour`), `pages/kuma/page.py`, `pages/homeassistant/page.py`, `pages/energy/page.py` (clock in `fetch`; `build(options, states, lang, clock)` keeps taking the finished clock text)
- Test: `pages/weather/test_weather.py`, `pages/kuma/test_kuma.py`, `pages/homeassistant/test_homeassistant.py`, `pages/energy/test_energy.py`
- Modify: `pages/weather/README.md`, `pages/kuma/README.md`, `pages/homeassistant/README.md`, `pages/energy/README.md` only where they describe the `clock` or `hour` value.

**Interfaces:**
- Consumes: `ctx.clock()`, `ctx.time_format` (Task 2), `timefmt.format_hour` (Task 1).
- Produces: template data unchanged in shape; `clock` and the "Stand …" / "As of …" subtitle carry the formatted time; weather `hours[i]["hour"]` is `"15"` or `"3 PM"`.

In every test file build the 12-hour context from the file's own helper: `dataclasses.replace(ctx(), time_format="12h")`.

- [ ] **Step 1: Write the failing tests.**

`pages/weather/test_weather.py` (`NOW` is 14:05):

```python
def test_twelve_hour_clock_and_hours(weather, calls):
    data = weather.fetch({"latitude": 50.1, "longitude": 8.7}, replace(ctx(), time_format="12h"))
    assert data["clock"] == "2:05 PM"
    assert [h["hour"] for h in data["hours"]] == ["3 PM", "4 PM", "5 PM", "6 PM"]


def test_twelve_hour_hours_cross_midnight(weather, calls):
    late = datetime(2026, 11, 14, 22, 30, tzinfo=TZ)
    data = weather.fetch({"latitude": 50.1, "longitude": 8.7},
                         replace(ctx(now=late), time_format="12h"))
    assert [h["hour"] for h in data["hours"]] == ["11 PM", "12 AM", "1 AM", "2 AM"]
```

`kuma`, `homeassistant`, `energy`: for each file add (a) one test that a successful fetch in 12 hours has `data["clock"]` in the form `H:MM AM|PM` for the file's `NOW`, and (b) one test that the error path (the file already has a test for "cannot reach …") gives `sub == f"{'Stand'} {<12-hour clock>}"` for `lang="de"` and `f"As of {…}"` for `lang="en"`. Name them `test_twelve_hour_clock` and `test_twelve_hour_error_subtitle`. Write the expected text out as a literal computed by hand from that file's `NOW`, not with `format_time`.

- [ ] **Step 2: Run** the four test files. Expected: the new tests fail with 24-hour text.
- [ ] **Step 3: Implement:** replace every `ctx.now.strftime("%H:%M")` in these four pages by `ctx.clock()`, and `f"{t.hour:02d}"` in weather by `format_hour(t, ctx.time_format)`. After this step `grep -n 'strftime("%H:%M")' pages/weather pages/kuma pages/homeassistant pages/energy -r` prints nothing.
- [ ] **Step 4: Browser check for weather** (`@pytest.mark.browser`, next to `test_template_renders`): render with hours `["10 PM", "11 PM", "12 AM", "1 AM"]` using the overflow helper pattern of `pages/printer/test_printer.py` and assert no `.t` element overflows and each stays inside its 60 px column. The `energy` header shows the plain text `2:05 PM` (13 px, no suffix markup): add one assertion to an existing energy browser test, or a new one, that `.hd .c` does not overflow with clock `12:59 PM` and title `Energiefluss Zuhause`.
- [ ] **Step 5: Run** the whole suite (both marker sets) and ruff. Expected: all pass.
- [ ] **Step 6: Commit** `feat(pages): weather, kuma, homeassistant and energy follow time_format`.

---

### Task 5: clock page

**Files:**
- Modify: `pages/clock/page.py`, `pages/clock/template.html`, `pages/clock/README.md`
- Test: `pages/clock/test_clock.py`

**Interfaces:**
- Consumes: `ctx.clock()`, `timefmt.split_suffix`.
- Produces: `fetch` returns `{"time", "ampm", "weekday", "date"}`; `ampm` is `""` in 24 hours, `"AM"` / `"PM"` in 12 hours; `time` is then without the suffix (`"9:05"`).

- [ ] **Step 1: Update and add tests.** The two existing equality tests get the new key: `{"time": "09:05", "ampm": "", "weekday": "Samstag", "date": "14.11.2026"}` (and the English one). New:

```python
def test_fetch_twelve_hours(clock):
    ctx = PageContext(NOW, "en", "Europe/Berlin", time_format="12h")
    assert clock.fetch({}, ctx) == {"time": "9:05", "ampm": "AM", "weekday": "Saturday",
                                    "date": "2026-11-14"}
    noon = PageContext(NOW.replace(hour=12, minute=59), "de", "Europe/Berlin", time_format="12h")
    assert (clock.fetch({}, noon)["time"], clock.fetch({}, noon)["ampm"]) == ("12:59", "PM")
```

Browser test `test_template_twelve_hours_fits`: render the template with `time="12:59"`, `ampm="PM"` and assert the box of the time plus suffix lies within x 4 … 236, nothing overflows, and the suffix text is `PM`. Second browser assertion: with `ampm=""` and `time="12:59"` the `.time` element's computed font size is `72px` (24 hours unchanged).

- [ ] **Step 2: Run** `pages/clock/test_clock.py`. Expected: fail.
- [ ] **Step 3: Implement.** `page.py`: `time, ampm = split_suffix(ctx.clock())`; keep the file's teaching comments (it is the template for people's own pages) and add one line explaining `ctx.clock()`. `template.html`: with `ampm`, the time is 56 px and a `<span class="ampm">` follows on the same baseline, 22 px, bold, `var(--muted)`, 6 px to the right; without `ampm` the markup and styles are exactly today's. The font size does not depend on the hour (no jump between `9:59` and `10:00`).
- [ ] **Step 4: Run** the whole suite (both marker sets) and ruff. Expected: all pass.
- [ ] **Step 5: Commit** `feat(clock): 12-hour display with AM/PM`.

---

### Task 6: bahn page

**Files:**
- Modify: `pages/bahn/page.py` (`_row`, `fetch`), `pages/bahn/template.html` (header clock through `ui.clock`), `pages/bahn/README.md`
- Test: `pages/bahn/test_bahn.py`

**Interfaces:**
- Consumes: `ctx.clock()`, `ctx.time_format`, `timefmt.format_time`, `split_suffix`, `convert_hhmm`, `ui.clock` (Task 3).
- Produces: `_row(dep, now, time_format: str = "24h") -> dict`; in 12 hours a departure 60 or more minutes away has `right="9:10"`, `unit="PM"`, and `scheduled="9:10 PM"`. `pages/bahn/departures.py` is not changed (`Departure.scheduled` stays `HH:MM`, `realtime()` parses it).

- [ ] **Step 1: Write the failing tests** (`NOW` is 19:49; `Departure` and `module` as in `test_right_soon_and_hours`):

```python
def test_twelve_hour_rows(bahn):
    _, module, _ = bahn
    soon = Departure("S1", "X", "19:50", 0, None, False, False)
    later = Departure("S1", "X", "21:10", 5, None, False, False)
    r1, r2 = (module._row(d, NOW, "12h") for d in (soon, later))
    assert (r1["right"], r1["unit"], r1["scheduled"]) == ("1", "min", "7:50 PM")
    assert (r2["right"], r2["unit"], r2["scheduled"]) == ("9:15", "PM", "9:10 PM")
    assert module._row(later, NOW)["scheduled"] == "21:10"          # default unchanged
    assert module._row(later, NOW, "24h")["right"] == "21:15"


def test_twelve_hour_keeps_odd_scheduled_text(bahn):
    _, module, _ = bahn
    # DBF always sends HH:MM; a cancelled row never calls realtime(), so odd text gets this far
    odd = Departure("S1", "X", "--:--", None, None, False, True)
    assert module._row(odd, NOW, "12h")["scheduled"] == "--:--"


def test_twelve_hour_header_and_error_subtitle(bahn, monkeypatch):
    ptype, module, _ = bahn
    ctx12 = replace(_ctx(), time_format="12h")
    assert ptype.fetch({"station": "X"}, ctx12)["clock"] == "7:49 PM"
    def boom(*a, **k): raise RuntimeError("down")
    monkeypatch.setattr(module.departures, "fetch", boom)
    assert ptype.fetch({"station": "X"}, ctx12)["sub"] == "Stand 7:49 PM"
```

Browser test `test_template_twelve_hours_fits` next to `test_template_renders_sample`: six rows (`limit: 6`) with destination `Frankfurt (Main) Flughafen Fernbf`, `right="12:59"`, `unit="PM"`, `scheduled="12:59 PM"`, delay 12, platform `Gl. 102`, clock `12:59 PM`; assert no `.right` and no `.l2` child is cut off or leaves x 0 … 240, and the header clock contains `.ui-ampm`.

- [ ] **Step 2: Run** `pages/bahn/test_bahn.py`. Expected: fail.
- [ ] **Step 3: Implement.** `_row`: time and suffix from `split_suffix(format_time(dep.realtime(now), time_format))`; the suffix goes into the existing `unit` field (the grey span that shows "min"). `scheduled` through `convert_hhmm`. `fetch` passes `ctx.time_format` and uses `ctx.clock()` for the header and the "Stand" text. Template: `{% import "ui.html" as ui %}` and `{{ ui.clock(clock) }}` inside the existing `.clock` span; nothing else changes.
- [ ] **Step 4: Run** the whole suite (both marker sets) and ruff. Expected: all pass.
- [ ] **Step 5: Commit** `feat(bahn): departure times follow time_format`.

---

### Task 7: ai page

**Files:**
- Modify: `pages/ai/page.py` (header clock), `pages/ai/providers/claude.py` (`_reset_text`, `stand`), `pages/ai/providers/_cost.py` (both "as of" texts), `pages/ai/providers/copilot.py` (`stand`), `pages/ai/README.md`
- Test: `pages/ai/test_ai.py`

**Interfaces:**
- Consumes: `ctx.clock(when)` (Task 2).
- Produces: no shape change. `_reset_text(resets_at, now, lang)` gains what it needs to format (pass `ctx` or the format; your choice, it is private).

- [ ] **Step 1: Write the failing tests** (`NOW` Sunday 14:05, push received 13:58, weekly reset Thursday 09:00, session reset in 2:13):

```python
def test_claude_twelve_hours(ai):
    data = ai.fetch(OPTIONS, replace(ctx(limits()), time_format="12h"))
    assert data["clock"] == "2:05 PM"
    assert [r["reset"] for r in data["rows"]] == ["in 2:13", "Do 9:00 AM"]   # countdown untouched
    assert data["stand"] == "Stand 1:58 PM"


def test_claude_twelve_hours_english_and_no_data(ai):
    data = ai.fetch(OPTIONS, replace(ctx(limits(), lang="en"), time_format="12h"))
    assert (data["rows"][1]["reset"], data["stand"]) == ("Thu 9:00 AM", "As of 1:58 PM")
```

Add one 12-hour test each for a cost provider and for `copilot`, next to the existing test that asserts their `stand` (or `sub`) text in 24 hours, with the same fixtures and the expected text written out by hand. Names: `test_cost_stand_twelve_hours`, `test_copilot_stand_twelve_hours`.

- [ ] **Step 2: Run** `pages/ai/test_ai.py`. Expected: fail.
- [ ] **Step 3: Implement.** After this step `grep -rn '%H:%M' pages/ai` shows only `anthropic_api.py` (`%Y-%m-%dT%H:%M:%SZ`, an API parameter that must stay).
- [ ] **Step 4: Run** the whole suite and ruff. Expected: all pass.
- [ ] **Step 5: Commit** `feat(ai): reset and as-of times follow time_format`.

---

### Task 8: printer page

**Files:**
- Modify: `pages/printer/providers/_common.py` (`clock_text`), `pages/printer/page.py` (`_base`, `build`, `_offline`, `notice`, `fetch`), `pages/printer/template.html`, `pages/printer/README.md`
- Test: `pages/printer/test_printer_common.py`, `pages/printer/test_printer.py`

**Interfaces:**
- Consumes: `timefmt.format_time`, `split_suffix`; `ctx.time_format`.
- Produces:
  - `clock_text(when, now, lang, time_format="24h") -> str`
  - `build(status, options, lang, now, time_format="24h") -> dict`, `notice(options, lang, now, err, time_format="24h") -> dict` (`tools/render_previews.py` calls `build` with four arguments and must keep working).
  - Template data gains `big_suffix: str | None` (always present, `None` unless the big text is a 12-hour time of today).

- [ ] **Step 1: Write the failing tests.**

`test_printer_common.py` (`NOW` is Wednesday 2026-11-25 14:32):

```python
@pytest.mark.parametrize(("when", "de", "en"), [
    (datetime(2026, 11, 25, 15, 55), "3:55 PM", "3:55 PM"),
    (datetime(2026, 11, 25, 0, 5), "12:05 AM", "12:05 AM"),
    (datetime(2026, 11, 24, 21, 14), "Di 9:14 PM", "Tue 9:14 PM"),     # weekday, not "yesterday"
    (datetime(2026, 11, 30, 7, 40), "Mo 7:40 AM", "Mon 7:40 AM"),
    (datetime(2026, 11, 10, 7, 40), "10.11.", "Nov 10"),               # date only
])
def test_clock_text_twelve_hours(common, when, de, en):
    when = when.replace(tzinfo=NOW.tzinfo)
    assert (common.clock_text(when, NOW, "de", "12h"),
            common.clock_text(when, NOW, "en", "12h")) == (de, en)
```

The existing `test_clock_text` stays as it is and must keep passing (24 hours unchanged, including "gestern 21:14" and "10.11. 07:40").

`test_printer.py`, using the file's helpers for building a status and calling `build`:

```python
def test_build_twelve_hours_printing(mod):       # eta today 16:47
    d = mod.build(<printing status with eta 16:47>, OPTIONS, "en", NOW, "12h")
    assert d["clock"] == "2:32 PM"
    assert "Done 4:47 PM" in d["lines"] and d["big_suffix"] is None    # big is the percentage

def test_build_twelve_hours_finished_today(mod):  # ended 14:28
    d = mod.build(<finished status ended_at 14:28>, OPTIONS, "en", NOW, "12h")
    assert (d["big"], d["big_suffix"], d["big_unit"]) == ("2:28", "PM", None)

def test_build_twelve_hours_finished_yesterday(mod):
    d = mod.build(<finished status ended_at yesterday 21:14>, {**OPTIONS, "finished_for": 1440},
                  "en", NOW, "12h")
    assert (d["big"], d["big_suffix"]) == ("Tue 9:14 PM", None)

def test_build_default_has_no_suffix(mod):
    d = mod.build(<finished status ended_at 14:28>, OPTIONS, "en", NOW)
    assert (d["big"], d["big_suffix"]) == ("14:28", None)

def test_notice_twelve_hours(mod):                # next to the "As of 14:32" test
    … sub == "As of 2:32 PM" / "Stand 2:32 PM", clock == "2:32 PM"
```

Replace each `<…>` by a status built the way the neighbouring tests build theirs. One end-to-end test through `fetch` with `replace(ctx("en"), time_format="12h")` proves the value reaches `build` (assert `data["clock"] == "2:32 PM"`).

Browser tests, with the file's helper that returns boxes with `overflow` (near line 560), for both variants (with and without thumbnail), `lang` `de` and `en`:
`test_twelve_hour_texts_fit`: (1) finished with `big="12:59"`, `big_suffix="PM"`; (2) printing with lines `["Done Wed 12:59 PM", "Layer 1234/1234"]` / `["Fertig Mi 12:59 PM", "Schicht 1234/1234"]`; (3) paused with line `since Wed 12:59 PM` / `seit Mi 12:59 PM`; (4) finished with `big="Wed 12:59 PM"`. Assert that no element with class `big`, `mid` or `sm` overflows and that the suffix element exists in (1).

- [ ] **Step 2: Run** the two test files. Expected: fail.
- [ ] **Step 3: Implement.**
  - `clock_text` in 12 hours: today → the time; another day within 6 days (both directions) → weekday abbreviation and time, also for yesterday; further away → the date alone (`10.11.` / `Nov 10`). In 24 hours the function returns exactly what it returns today.
  - `build`: the big finish time is split with `split_suffix`; `big_suffix` is set only when the remaining text contains no space (a time of today), otherwise the whole text stays in `big`.
  - Template: with `big_suffix`, the big text is 26 px in both variants, followed by the suffix in 12 px with 3 px gap, same colour; the existing size rules by text length stay for everything else. In the variant without thumbnail the first small line (`smalls[0]`) gets the class `s` from 16 characters on, as the variant with thumbnail already does. Update the comment block at the top of the template that describes the layout.
- [ ] **Step 4: Run** the whole suite (both marker sets) and ruff. Expected: all pass, including every existing mockup test.
- [ ] **Step 5: Commit** `feat(printer): finish and pause times follow time_format`.

---

### Task 9: add-on starter note, preview, reference docs

**Files:**
- Modify: `server/glancebox/addon.py` (`STARTER_CONFIG` comment only)
- Modify: `tools/render_previews.py` (one new sample), create `docs/img/templates/clock-12h.png` by running it
- Modify: `config-example.yaml`
- Modify (en and de, same headings): `docs/{en,de}/configuration.md`, `docs/{en,de}/templates/clock.md`, `bahn.md`, `weather.md`, `printer.md`, `ai.md`, `docs/{en,de}/writing-pages.md`
- Modify: `CHANGELOG.md` (`## [Unreleased]`)
- Test: `server/tests/test_addon.py`, `server/tests/test_render_previews.py`, `server/tests/test_config.py`

**Interfaces:**
- Consumes: everything from Tasks 1 to 8.
- Produces: the preview sample name `clock-12h`.

- [ ] **Step 1: Write the failing tests.**

```python
# server/tests/test_addon.py
def test_starter_config_names_time_format():
    assert "time_format:" in STARTER_CONFIG
    # only inside comments: the starter itself stays on the default
    assert all(line.lstrip().startswith("#") for line in STARTER_CONFIG.splitlines()
               if "time_format" in line)

# server/tests/test_render_previews.py
def test_twelve_hour_clock_sample_exists():
    ptype, options, data = _load().SAMPLES["clock-12h"]
    assert ptype == "clock" and (data["time"], data["ampm"]) == ("2:32", "PM")

def test_every_clock_sample_has_the_ampm_key():
    assert all("ampm" in d for p, _, d in _load().SAMPLES.values() if p == "clock")

# server/tests/test_config.py
def test_example_config_documents_time_format():
    text = (Path(__file__).resolve().parents[2] / "config-example.yaml").read_text()
    assert re.search(r"^time_format: 24h\b", text, re.MULTILINE)
```

If `test_config.py` (or another test) already loads `config-example.yaml` through `load_config`, it covers the new line's validity; otherwise add that load to the new test with the environment variables the file refers to.

- [ ] **Step 2: Run** the three test files. Expected: the new tests fail.
- [ ] **Step 3: Implement.** `STARTER_CONFIG`: extend the existing comment sentence so it reads that `timezone:`, `lang:` and `time_format: 12h` (AM/PM) can be set in the file. `test_starter_config_validates` must keep passing. `SAMPLES`: add `"ampm": ""` to the existing `clock` sample and the new `"clock-12h": ("clock", {"lang": "en"}, {"time": "2:32", "ampm": "PM", "weekday": "Thursday", "date": "2026-11-12"})`. `config-example.yaml`: `time_format: 24h           # 24h or 12h (AM/PM)` under `lang:`.
- [ ] **Step 4: Render the preview:** `server/.venv/bin/python tools/render_previews.py clock clock-12h` from the repo root. Expected: two lines with file sizes; `git status` shows `clock-12h.png` as new and `clock.png` as unchanged (if `clock.png` changed, the 24-hour layout changed: go back to Task 5). Do not re-render the other previews.
- [ ] **Step 5: Write the docs** (en first, then de with the same headings and tables):
  - `configuration.md`: row `time_format` in "Top-level options" (`24h` default; `12h` shows times as `2:05 PM`; durations such as "in 2:13" are not affected) and in "Options every page has" (default: the top-level value; overrides it for this page). Mention the start-up error for other values.
  - `templates/clock.md`: option row, the new picture below the first one with the caption "With `time_format: 12h`", and the note that the digits are smaller there.
  - `templates/bahn.md`, `weather.md`, `printer.md`, `ai.md`: one sentence each in the options or notes saying what `time_format: 12h` changes on that page; `printer.md` also says that in 12 hours a time on another day shows the weekday instead of "yesterday" and a date without a time.
  - `writing-pages.md`: rows `ctx.time_format` and `ctx.clock(when=None)` in the context table; the examples that build the header clock use `ctx.clock()`; `ui.clock(text)` in the list of `ui` macros; one sentence that existing pages with `strftime("%H:%M")` keep working and simply stay in 24 hours.
  - `CHANGELOG.md`, under `## [Unreleased]` → `### Added`: the option, where it applies, what it does not touch (durations, the device page's "Local time" row, `url` pages), and "No firmware change". State what was checked: unit tests and browser render tests; not checked on the real display.
- [ ] **Step 6: Run** the whole suite, ruff, `python3 tools/check_docs_parity.py` (expected `OK: … document pairs match`) and, if `requirements-docs.txt` is installed, `NO_MKDOCS_2_WARNING=1 mkdocs build --strict`.
- [ ] **Step 7: Commit** `docs: time_format option, 12-hour clock preview`.

---

# Part B: add-on guide (issue #37)

### Task 10: the guide

**Files:**
- Create: `server/tests/test_addon_docs.py`
- Modify: `docs/en/home-assistant.md`, `docs/de/home-assistant.md` (rebuilt), `ha-addon/DOCS.md`
- Modify: `README.md`, `README.de.md`, `docs/en/guide/2-start-the-server.md`, `docs/de/guide/2-start-the-server.md` (one sentence with a link each)
- Modify: `CHANGELOG.md` (`## [Unreleased]`)

**Interfaces:**
- Consumes: `glancebox.addon.SECRET_FIELDS`, `HaInfo`, `ha_defaults`, `STARTER_CONFIG`; `glancebox.config.load_config`; `glancebox.pages.load_page_types`, `validate_config`; the `time_format` option (Task 2) for one example.
- Produces: the three documents. Section order of `docs/{en,de}/home-assistant.md` is fixed by the spec ("Teil B → Entwurf", items 1 to 10).

- [ ] **Step 1: Write the failing tests** in `server/tests/test_addon_docs.py`:

```python
"""The add-on guide stays in line with the code: examples load, facts match."""
ROOT = Path(__file__).resolve().parents[2]
GUIDES = [ROOT / "ha-addon/DOCS.md", ROOT / "docs/en/home-assistant.md",
          ROOT / "docs/de/home-assistant.md"]
GUIDE_URL = "https://robinlanger.github.io/glancebox/home-assistant/"
EXTRA = {"OCTOPRINT_KEY": "k" * 24}       # the "More secrets" example of the guide
ENV = {"SUPERVISOR_TOKEN": "s", **{var: "x" * 24 for var in SECRET_FIELDS.values()}, **EXTRA}


def yaml_blocks(path: Path) -> list[str]: ...   # bodies of ```yaml fences, dedented


@pytest.mark.parametrize("path", GUIDES, ids=lambda p: p.name + "@" + p.parent.name)
def test_yaml_examples_load_in_addon_mode(path, tmp_path):
    blocks = yaml_blocks(path)
    assert blocks, "no examples"
    hook = ha_defaults(HaInfo("Europe/Berlin", "en", 50.0, 8.0), ENV)
    for i, block in enumerate(blocks):
        # a block is a whole config.yaml (has `pages:`) or a list of pages (starts with `- type:`)
        text = block if re.search(r"^pages:", block, re.MULTILINE) else \
            "pages:\n" + textwrap.indent(block, "  ")
        f = tmp_path / f"{i}.yaml"
        f.write_text(text)
        cfg = load_config(f, defaults=hook, environ=ENV)
        validate_config(cfg, load_page_types(cfg.pages_dirs))     # raises with the block's error


@pytest.mark.parametrize("path", GUIDES, ids=...)
def test_guide_facts(path):
    text = path.read_text()
    port = yaml.safe_load((ROOT / "ha-addon/config.yaml").read_text())["ports"]["8080/tcp"]
    assert f":{port}" in text
    for var in SECRET_FIELDS.values():
        if var != SECRET_FIELDS["push_key"]:              # the push key is used automatically
            assert f"${{{var}}}" in text, var
    assert re.search(r"^## (Troubleshooting|Fehlerbehebung)$", text, re.MULTILINE)
    assert "time_format" in text
    assert "/healthz" in text
    # placeholders only (192.168.1.x, 192.168.x.x have no four numbers; the setup portal's own
    # address is fixed in the firmware)
    for ip in re.findall(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", text):
        assert ip.startswith("192.168.1.") or ip == "192.168.4.1", ip


def test_examples_cover_the_addon_specific_pages():
    for path in GUIDES[1:]:
        blocks = "\n".join(yaml_blocks(path))
        for needle in ("type: homeassistant", "type: energy", "source: hass", "type: weather",
                       "type: bahn", "provider: claude", "time_format: 12h", "${OCTOPRINT_KEY}"):
            assert needle in blocks, f"{path.name}: {needle}"
        # the point of the add-on: no url/token for pages that read from this Home Assistant
        ha_pages = [p for b in yaml_blocks(path) for p in pages_of(b)
                    if p.get("type") in ("homeassistant", "energy")]
        assert ha_pages and all("url" not in p and "token" not in p for p in ha_pages)


def test_docs_md_links_the_guide_and_stays_short():
    text = GUIDES[0].read_text()
    assert GUIDE_URL in text
    assert len(text.splitlines()) <= 120


def test_guide_has_numbered_steps():
    for path, word in ((GUIDES[1], "Step"), (GUIDES[2], "Schritt")):
        heads = re.findall(rf"^## {word} (\d):", path.read_text(), re.MULTILINE)
        assert heads == ["1", "2", "3", "4"], path
```

Write the two small helpers (`yaml_blocks`, `pages_of`) in the test file.

- [ ] **Step 2: Run** `.venv/bin/python -m pytest -q tests/test_addon_docs.py`. Expected: fail (no troubleshooting section, no numbered steps, missing examples).
- [ ] **Step 3: Write `docs/en/home-assistant.md`** in the section order of the spec. Rules:
  - Every instruction is one numbered action with its visible result ("The page shows a preview of the clock and the weather").
  - Take facts only from the code named in the spec under "Quelle jeder Aussage"; read those functions before writing. Facts to state exactly: the add-on listens on host port 8090; the display accepts only `http://`; the address goes into the portal field "Server URL" or the device page; the overview exists only inside Home Assistant (port 8090 answers `/healthz`, `/` gives "Not Found"); the add-on must be restarted after every change of `config.yaml` or of a secret; values set in `config.yaml` win over Home Assistant's; a config error stops the add-on and the reason is one line in the add-on's Log tab.
  - Home Assistant menu paths and the location of `config.yaml` (`/addon_configs/<id>_glancebox/config.yaml`) are written as today until Task 11 confirms or corrects them. Describe both outcomes of the first start: the file is there, or the folder is empty and the web UI shows the starter content to paste into a new `config.yaml`.
  - Examples: complete, copy-ready blocks that pass the test; one `config.yaml` that combines clock, weather and a `homeassistant` page as "a typical first playlist"; link each page type to its page in `templates/`. No second description of page options.
  - Troubleshooting as a table "What you see | Likely cause | What to do" with the rows listed in the spec. For an error text, quote the server's real message (search the code for it; for example `unknown page type`, `environment variable … is not set`, `refresh must be at least`).
  - Keep the install button and the Security section.
- [ ] **Step 4: Write `docs/de/home-assistant.md`:** same headings at the same levels, same tables and examples (comments in the YAML translated), German wording in the tone of the other `docs/de` pages ("du").
- [ ] **Step 5: Rewrite `ha-addon/DOCS.md`** (English, at most 120 lines): link to the full guide at the top, five numbered steps (flash once, start, open web UI, enter the address, edit `config.yaml` and restart), the typical first playlist, the secrets list as today plus `time_format` in one sentence, the three most common problems (add-on does not start → Log tab; change has no effect → restart; display stays empty → address with `http://` and port 8090, check `http://192.168.1.x:8090/healthz`) with a link to the full table, Security as today.
- [ ] **Step 6: Pointers.** `README.md` / `README.de.md`: the existing sentence "Home Assistant OS? …" says that the linked page is a step-by-step guide. `guide/2-start-the-server.md` (en, de): a `!!! tip` at the top pointing Home Assistant OS users to the guide. `CHANGELOG.md` → `## [Unreleased]` → `### Changed`: the guide, and the sentence which parts were checked on a real Home Assistant (filled in by Task 11; until then "not yet checked on a real Home Assistant").
- [ ] **Step 7: Run** the whole suite, ruff, `python3 tools/check_docs_parity.py` and `mkdocs build --strict` (if installed; a broken `#anchor` fails it). Expected: all pass.
- [ ] **Step 8: Commit** `docs: step-by-step guide for the Home Assistant add-on`.

---

### Task 11: check the guide on a real Home Assistant

This task needs a Home Assistant OS instance (the project's test VM or test Pi). They are on Robin's home server: do not connect to anything unless Robin gave access for this task. Without access, skip Steps 1 to 3, do Step 4 with "not checked", and report that the task is open.

**Files:**
- Modify: `docs/en/home-assistant.md`, `docs/de/home-assistant.md`, `ha-addon/DOCS.md` (corrections only), `CHANGELOG.md`

- [ ] **Step 1: Build and install the branch's add-on** on the test instance the way earlier releases did (see `docs/RELEASING.md` and `tools/ha-sim/README.md`). Note the Home Assistant OS and Core versions.
- [ ] **Step 2: Walk through the guide as written**, as a new user would, and record for each of the six points of the spec ("An einem echten Home Assistant zu prüfen") what happened:
  1. menu names and paths (Add-ons or Apps; where "Repositories" is);
  2. whether `config.yaml` exists after the first start;
  3. the folder name and whether the File editor reaches `/addon_configs/…` with its default settings;
  4. whether a hand-made `config.yaml` is read after a restart;
  5. each example of the guide started once (entities from `tools/ha-sim` where the instance has none);
  6. each troubleshooting row triggered once where that is cheap (typo in `config.yaml`, no restart, wrong port in the display address, browser on port 8090), plus `time_format: 12h` on the clock page in the add-on's web UI.
- [ ] **Step 3: Correct the three documents** where the walk-through differed. A code defect found on the way is reported to Robin, not fixed here.
- [ ] **Step 4: Update the CHANGELOG sentence:** checked on (date, Home Assistant OS version, VM or Pi), and the list of points that could not be checked. Run the suite, `check_docs_parity.py`, and commit `docs: add-on guide checked on Home Assistant OS <version>` (or, without access, `docs: note that the add-on guide is unchecked on a real Home Assistant`).

---

### Task 12: final verification and hand-over

**Files:** none new; fixes only if a check fails.

- [ ] **Step 1: Leftovers.** From the repo root:
  `grep -rnE 'strftime\(.%H:%M.\)|:%H:%M\}' pages server/glancebox --include='*.py'`
  Expected: only `server/glancebox/app.py` (`X-Local-Time`, `%H:%M:%S`) and `pages/ai/providers/anthropic_api.py` (API parameter). Anything else is a missed place: fix it in the page's style with a test.
- [ ] **Step 2: Full checks.** From `server/`: `.venv/bin/python -m pytest -q` (all markers; expected: all pass, the `homeassistant_live` tests skip without `HA_URL`), `.venv/bin/ruff check . ../pages`. From the root: `python3 tools/check_docs_parity.py`, `NO_MKDOCS_2_WARNING=1 mkdocs build --strict`, `git status --short docs/img` (expected: only `clock-12h.png` was added on this branch; `git diff main --stat -- docs/img firmware` shows no other picture and nothing under `firmware/`).
- [ ] **Step 3: Default unchanged.** `server/.venv/bin/python tools/render_previews.py` into the working tree, then `git status --short docs/img/templates`. Expected: no file modified (the 24-hour pictures are byte-identical). If a picture differs, find the cause before going on; then `git checkout -- docs/img/templates` only if the difference is proven to be encoder noise unrelated to this branch, and say so in the report.
- [ ] **Step 4: One real run.** Write a scratch config outside the repo with `time_format: 12h`, `lang: en`, a `clock` page, a `weather` page with `location: Berlin` and a `bahn` page with `time_format: 24h`; render each page with `server/.venv/bin/python -m glancebox render <n> -o <scratch>/<n>.png --config <scratch>/config.yaml` and look at the three pictures: clock and weather in AM/PM, bahn in 24 hours.
- [ ] **Step 5: Report, no release.** Summarise for Robin: what was done per issue, what was checked where (unit, browser, real run, real Home Assistant or not), the open questions of the spec that are still open, and this proposal: release as **0.9.0** (server and add-on only, no new firmware; bump `VERSION` and `ha-addon/config.yaml`, turn `## [Unreleased]` into `## [0.9.0]` as `docs/RELEASING.md` describes), then answer issues #36 and #37 with the option name and the guide link. Do not bump, tag, push or comment.
