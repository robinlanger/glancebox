# Claude Usage Hook Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The `ai` page with `provider: claude` also updates when Claude Code runs without its terminal UI (T3 Code, desktop app, IDE), through a hook script that pushes the output of `claude -p "/usage"`.

**Architecture:** A new hook script (sh and PowerShell) fetches the usage report in the background, throttled to once per 60 s, and posts the one JSON line that contains `usage_report` to the existing push endpoint `/api/v1/push/claude`. The server allows the extra top-level key `usage_report`, and `providers/claude.py` turns either format into the same rows.

**Tech Stack:** Python 3.12 (server, pytest, ruff), POSIX sh + curl + grep, PowerShell 5.1/7, Markdown docs (en + de).

**Spec:** `docs/superpowers/specs/2026-11-24-claude-usage-hook-design.md` (German). Read it first.

## Global Constraints

- Branch `feat/claude-usage-hook`. One commit per task. Commit messages in English, conventional style, ending with the line `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` (use the model that wrote the commit). No push, no tag, no release.
- No personal data in the repo: no real IPs, names, emails or keys. Use placeholders such as `http://192.168.1.10:8080`.
- Code, comments, docs in `docs/en` and the CHANGELOG are English; `docs/de` is German. Follow the tone and line length (100) of the surrounding files.
- The hook script never prints anything, always exits 0, returns at once, and never reads the Claude login token or calls an HTTP API of Anthropic itself.
- The fetch command is exactly: `claude -p "/usage" --output-format stream-json --verbose --no-session-persistence`, run with `GLANCEBOX_USAGE=1` in its environment.
- Throttle: 60 seconds, fixed. Stamp file `usage.stamp` in the same directory as `push.env`, content = Unix epoch seconds as decimal text.
- Run tests from `server/`: `.venv/bin/pytest -q -m "not browser"`; lint: `.venv/bin/ruff check . ../pages`; docs: `python3 tools/check_docs_parity.py` (repo root); shell: `shellcheck tools/statusline/*.sh`.
- Verified on Claude Code 2.1.330 (macOS). `usage_report` is marked experimental by Anthropic; docs must say so.
- VERSION stays 0.7.0. The CHANGELOG entry goes under `## [Unreleased]`.

## Review Focus

1. A push whose `usage_report.rate_limits` is `null` or has an empty `limits` list (API-key login, error): the page must show the notice `No limit data`, never crash. Test in Task 1. The script must not send such a line at all, so good values stay. Test in Task 2.
2. `resets_at` as `null`, as text that is no ISO time, or without a UTC offset: the row appears without a reset text (first two) or is read as UTC (third). Test in Task 1.
3. Two hooks firing in the same second (`Stop` right after `PostToolUse`): only one fetch. Test in Task 2.
4. `claude` hangs or is not installed: the hook still returns at once, sends nothing, and no process is left after the timeout. Test in Task 2.
5. A stamp file with garbage or from the future (clock change): the script fetches instead of staying silent forever. Test in Task 2.

---

### Task 1: Server reads the usage-report format

**Files:**
- Modify: `pages/ai/providers/claude.py`
- Modify: `pages/ai/page.py` (`PUSH_KEYS` and its comment)
- Modify: `pages/ai/README.md` (developer notes on the `claude` provider)
- Test: `pages/ai/test_ai.py`

**Interfaces:**
- Consumes: nothing.
- Produces: the server accepts a push to channel `claude` with the top-level key `usage_report` of this shape (other keys of the pushed object are dropped by the server as today):

```json
{"usage_report": {"rate_limits": {"limits": [
  {"kind": "session", "percent": 5, "resets_at": "2026-11-24T20:20:00.457974+00:00"},
  {"kind": "weekly_all", "percent": 21, "resets_at": "2026-11-28T04:00:00.457999+00:00"},
  {"kind": "weekly_scoped", "percent": 16, "resets_at": "2026-11-28T04:00:00.458263+00:00"}]}}}
```

- [ ] **Step 1: Write the failing tests** in `pages/ai/test_ai.py`, next to the existing `claude` tests. Add a helper `report(session=(42.0, IN_2H13), weekly=(81.0, THURSDAY_9), extra=())` that builds the shape above (`resets_at` as `datetime.fromtimestamp(ts, timezone.utc).isoformat()`, `extra` = further entries of `limits`). Change `test_push_keys_declared` to expect `{"claude": ("rate_limits", "usage_report")}`. New tests:

```python
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
    naive = datetime.fromtimestamp(IN_2H13, timezone.utc).replace(tzinfo=None).isoformat()
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
```

Also extend the existing end-to-end render test (`test_template_renders_claude` area) or add one small test that puts a `report()` push into a `PushInbox` and renders, to prove the path through the real inbox.

- [ ] **Step 2: Run** `.venv/bin/pytest -q ../pages/ai/test_ai.py` from `server/`. Expected: the new tests and `test_push_keys_declared` fail.

- [ ] **Step 3: Implement.** In `page.py`: `PUSH_KEYS = {"claude": ("rate_limits", "usage_report")}` and update the comment (status-line script or usage hook script). In `claude.py`: add a private function

```python
def _windows(data: dict) -> list[tuple[str, float, float | None]]:
    """(window key of WINDOWS, percent used, resets_at as epoch seconds or None), in WINDOWS order."""
```

that reads `usage_report` when that key is present in `data` (kinds `session` → `five_hour`, `weekly_all` → `seven_day`; ISO time via `datetime.fromisoformat`, no offset means UTC) and otherwise `rate_limits` as today. `_fetch` builds its rows from `_windows` only, so reset text, `zurückgesetzt`, `stand` and the notices stay one code path. Extend the module docstring with the second format: source URL `https://code.claude.com/docs/en/agent-sdk/typescript` (`SDKUsageReport`, experimental), verified 2026-11-24 with Claude Code 2.1.330, field meanings as in the spec.

- [ ] **Step 4: Update `pages/ai/README.md`:** the two bullets on `claude` now name both scripts and both keys.

- [ ] **Step 5: Run** `.venv/bin/pytest -q -m "not browser"` and `.venv/bin/ruff check . ../pages` from `server/`. Expected: all pass, no lint findings.

- [ ] **Step 6: Commit** `feat(ai): claude provider reads the usage report format`.

---

### Task 2: Hook scripts

**Files:**
- Create: `tools/statusline/glancebox-usage.sh` (executable)
- Create: `tools/statusline/glancebox-usage.ps1`
- Modify: `tools/statusline/glancebox-statusline.sh`, `tools/statusline/glancebox-statusline.ps1` (write the stamp when they send)
- Test: `server/tests/test_usage_hook.py` (new), `server/tests/test_statusline.py` (one new test)

**Interfaces:**
- Consumes: the push endpoint and body shape from Task 1.
- Produces: hook command for the docs (Task 3):
  - macOS/Linux: `/path/to/glancebox-usage.sh`
  - Windows: `powershell -NoProfile -ExecutionPolicy Bypass -File C:/path/to/glancebox-usage.ps1`
  - Settings read from the same `push.env` as the status-line script. Optional environment variable `GLANCEBOX_USAGE_TIMEOUT` (seconds, default 30) limits the `claude` call.

**Behaviour of `glancebox-usage.sh`** (the `.ps1` mirrors it; use the status-line `.ps1` as the model for reading `push.env`, the hidden background process and passing the key through the environment):

1. If `GLANCEBOX_USAGE` is `1`: exit 0 (loop guard; the script's own `claude` call runs hooks too).
2. Read `GLANCEBOX_URL` and `GLANCEBOX_PUSH_KEY` from `${XDG_CONFIG_HOME:-$HOME/.config}/glancebox/push.env` (Windows: `%APPDATA%\glancebox\push.env`) with the same parsing as the status-line script. Either missing: exit 0.
3. Throttle: read `usage.stamp` beside `push.env`. If its content is a number `t` with `0 <= now - t < 60`: exit 0. Anything else (missing, garbage, future time) means fetch. Write `now` to the stamp **before** starting the fetch.
4. Start the rest in the background, detached from stdin, stdout and stderr, and exit 0 at once. Never read stdin (hooks pass JSON there; a timer passes nothing).
5. Background part: `cd` to the directory of `push.env`, run the fetch command from Global Constraints with stdin from `/dev/null`, killed after `GLANCEBOX_USAGE_TIMEOUT` seconds (no `timeout` binary on macOS: use a watchdog subshell, and leave no sleeping process behind longer than the timeout). From its output take the first line that contains both `"usage_report"` and `"limits":[` followed by something other than `]` (so `null` and `[]` send nothing). If there is such a line, POST it like the status-line script does (`curl -s -m 5`, bearer key, `Content-Type: application/json`, `--data-binary @-`) to `${GLANCEBOX_URL%/}/api/v1/push/claude`.

**Status-line scripts:** in the branch that sends, also write the current epoch seconds to `usage.stamp` (best effort, silent). Nothing else changes.

- [ ] **Step 1: Write the failing tests** in `server/tests/test_usage_hook.py`. Reuse the `server` fixture, `write_env` and `wait_for` pattern from `test_statusline.py` (import them or move them to a small shared helper module in `server/tests/`; keep `test_statusline.py` passing). A fixture `fake_claude(tmp_path, body)` writes an executable `claude` shell script into `tmp_path/"bin"`, which is put first in `PATH`; the fake appends its arguments and `$GLANCEBOX_USAGE` to a log file and then runs `body`. `LINE` is a compact one-line JSON with `"usage_report":{"rate_limits":{"limits":[{"kind":"session","percent":5,"resets_at":"2026-11-24T20:20:00+00:00"}]}}`. Tests:

```python
def test_posts_the_usage_report_line(...):
    # fake prints three lines: a system line, LINE, a result line
    # r.returncode == 0, r.stdout == "" == r.stderr; exactly one POST, body == LINE (no newline),
    # path "/api/v1/push/claude", auth f"Bearer {KEY}", type "application/json"
    # the fake's log shows the exact arguments
    #   -p /usage --output-format stream-json --verbose --no-session-persistence
    # and GLANCEBOX_USAGE=1

def test_returns_at_once(...):          # fake sleeps 2 s first; the script returns in < 1 s
def test_loop_guard(...):               # env GLANCEBOX_USAGE=1: fake never called, no POST
def test_throttled_within_60_s(...):    # run twice: fake called once, one POST
def test_two_hooks_at_once_fetch_once(...):  # start two runs with Popen together: fake called once
def test_fetches_again_after_60_s(...): # stamp = now - 61: fake called
@pytest.mark.parametrize("stamp", ["", "abc", "12 34", str(int(time.time()) + 3600)])
def test_bad_or_future_stamp_fetches(...)
def test_status_line_stamp_throttles(...):   # run glancebox-statusline.sh with rate_limits first,
                                             # then the hook: fake never called
@pytest.mark.parametrize("out", ['{"type":"result"}',
    '{"usage_report":{"rate_limits":null}}', '{"usage_report":{"rate_limits":{"limits":[]}}}'])
def test_sends_nothing_without_limits(...)   # fake called, no POST after 1 s
def test_silent_without_claude(...):    # PATH without a claude: returncode 0, no output, no POST
def test_hanging_claude_is_killed(...): # GLANCEBOX_USAGE_TIMEOUT=1, fake does `exec sleep 30`
                                        # and writes its pid to a file: within 4 s that pid is gone
def test_silent_without_config(...):    # no push.env: returncode 0, no output, fake never called
def test_ignores_stdin(...):            # stdin is a hook JSON text: same result as the first test
```

Add to `test_statusline.py`: `test_writes_usage_stamp` (after a send, `usage.stamp` beside `push.env` holds a number within 5 s of `time.time()`; after a run without `rate_limits` no stamp exists).

- [ ] **Step 2: Run** `.venv/bin/pytest -q tests/test_usage_hook.py tests/test_statusline.py`. Expected: new tests fail (script missing).

- [ ] **Step 3: Write `glancebox-usage.sh`** with a header comment in the style of `glancebox-statusline.sh`: what it is for (Claude Code without the terminal UI: T3 Code, desktop app, IDE), that the `/usage` report is experimental, the `push.env` lines, and this settings example:

```json
"hooks": {
  "Stop": [{"hooks": [{"type": "command", "command": "/path/to/glancebox-usage.sh"}]}],
  "PostToolUse": [{"hooks": [{"type": "command", "command": "/path/to/glancebox-usage.sh"}]}]
}
```

- [ ] **Step 4: Add the stamp line to `glancebox-statusline.sh`.**

- [ ] **Step 5: Run** the two test files again and `shellcheck tools/statusline/*.sh`. Expected: pass, no findings (do not silence findings without a comment saying why).

- [ ] **Step 6: Write `glancebox-usage.ps1`** and the stamp line in `glancebox-statusline.ps1`, same behaviour. Throttle with `[DateTimeOffset]::UtcNow.ToUnixTimeSeconds()`. The hidden child process sets `$env:GLANCEBOX_USAGE = '1'`, runs `claude` with the fetch arguments, stops it after the timeout, picks the line with `Select-String`-like plain matching and posts it with `Invoke-RestMethod` (body as UTF-8 bytes). There is no PowerShell on this machine: the script is **not run here**. Read it twice against the `.sh` behaviour list instead and say in the report that it is untested.

- [ ] **Step 7: Real check on this Mac** (it has a working `claude` login): start a throwaway listener and run the real script against it, without touching the user's real `push.env`:

```bash
# in a temp dir: XDG_CONFIG_HOME=<tmp> with a push.env pointing at http://127.0.0.1:<port>,
# a tiny python http.server handler that writes the POST body to a file
XDG_CONFIG_HOME=<tmp> tools/statusline/glancebox-usage.sh </dev/null; sleep 10
```

Expected: the body file holds one JSON object with `usage_report.rate_limits.limits` containing kinds `session` and `weekly_all`. Feed that body to the provider (`python - <<…` using `_windows`, or a pytest one-off) and confirm two rows. Report the kinds and percents seen, not the whole body.

- [ ] **Step 8: Run** the full suite and ruff as in Task 1 Step 5. **Commit** `feat(tools): usage hook script for Claude Code without the terminal`.

---

### Task 3: Docs and changelog

**Files:**
- Modify: `docs/en/templates/ai.md`, `docs/de/templates/ai.md`
- Modify: `CHANGELOG.md`
- Check and adjust if they mention the status-line script as the only way: `README.md`, `README.de.md`, `ha-addon/DOCS.md`, `docs/*/guide/5-choose-pages.md`, `docs/*/home-assistant.md`

**Interfaces:**
- Consumes: hook commands and the settings JSON from Task 2; behaviour from Tasks 1 and 2.
- Produces: nothing.

- [ ] **Step 1: `docs/en/templates/ai.md`.** Read the whole page first and keep its voice (plain words, second person, short sentences).
  - Table row `claude` and the paragraph under "What you need": the limits come from Claude Code's status line (terminal) or from the hook script (everything else).
  - New subsection `### Claude Code in other apps` directly after `### Keeping your own status line`: who needs it (Claude Code used through T3 Code, the desktop app, an IDE extension or any app that runs Claude Code without its terminal view; those have no status line); what the script does in two sentences (after an answer it asks Claude Code for the `/usage` report in the background and sends it; at most once a minute; costs no tokens); steps: copy `glancebox-usage.sh`, `chmod +x`, same `push.env` as above, the settings JSON from Task 2; a restart note (hooks are read when a session starts, so open a new session or thread); "use both": terminal users keep the status line, the hook then stays quiet while the status line sends; needs a current Claude Code (checked with 2.1.330) and a Claude plan; Anthropic marks this report as experimental, so a Claude Code update can break it and then the page keeps its last values with their `As of` time; one paragraph: the script can also be run by a timer of your system (cron, launchd, Task Scheduler) if you want the display to follow use on claude.ai in the browser or phone, which is not set up or tested by the project.
  - `### Windows`: add the hook command for `glancebox-usage.ps1` and say plainly that this script has not been tested on Windows yet.
  - `## Privacy & security`: the hook sends one JSON line of Claude Code's usage report; the server keeps `usage_report` (limits, session cost counters) and drops the rest; the script does not read your Claude login.
  - `## When something is wrong`: an entry "The display only updates when I use the terminal" pointing to the new subsection, and one for "Nothing arrives from the hook" (run the script by hand in a terminal, then check `As of`; new session needed; `claude` must be on the PATH of the app).
- [ ] **Step 2: `docs/de/templates/ai.md`:** the same content in German, same heading structure.
- [ ] **Step 3: Other files** from the list: one sentence or link where they describe the status line as the way the Claude data arrives. Do not restructure.
- [ ] **Step 4: `CHANGELOG.md`** under `## [Unreleased]`: an intro paragraph in the style of earlier entries saying what was checked (macOS, Claude Code 2.1.330: headless run fires `Stop` and `PostToolUse`, real usage report through the script to a test listener and through the provider) and what was not (the PowerShell script on Windows, Linux, a live session in T3 Code or the desktop app, the display itself); then `### Added` with the hook scripts and the second push format. Server only, no firmware change.
- [ ] **Step 5: Run** `python3 tools/check_docs_parity.py` (repo root) and the full pytest suite (docs may be covered by tests). Expected: pass.
- [ ] **Step 6: Commit** `docs(ai): Claude Code in other apps (usage hook)`.
