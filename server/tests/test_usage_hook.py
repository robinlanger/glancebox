"""tools/statusline/glancebox-usage.sh: a hook that fetches `/usage` and pushes the report."""

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest
from test_statusline import KEY, wait_for, write_env

TOOLS = Path(__file__).resolve().parents[2] / "tools" / "statusline"
SCRIPT = TOOLS / "glancebox-usage.sh"
STATUSLINE = TOOLS / "glancebox-statusline.sh"
SYSTEM_PATH = "/usr/bin:/bin"
LINE = json.dumps({"usage_report": {"rate_limits": {"limits": [
    {"kind": "session", "percent": 5, "resets_at": "2026-11-24T20:20:00+00:00"}]}}},
    separators=(",", ":"))
ARGS = "-p /usage --output-format stream-json --verbose --no-session-persistence"

pytestmark = pytest.mark.skipif(not (shutil.which("sh") and shutil.which("curl")),
                                reason="needs sh and curl")


@pytest.fixture
def fake_claude(tmp_path):
    """make(body) writes an executable `claude` into tmp_path/bin that logs its arguments and
    $GLANCEBOX_USAGE (one line per call) and then runs body; returns the log path."""
    log = tmp_path / "claude.log"

    def make(body: str) -> Path:
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir(exist_ok=True)
        fake = bin_dir / "claude"
        fake.write_text(f'#!/bin/sh\nprintf \'%s|%s\\n\' "$*" "$GLANCEBOX_USAGE" >> "{log}"\n'
                        f"{body}\n")
        fake.chmod(0o755)
        return log

    return make


def printing(*lines: str) -> str:
    return "\n".join(f"printf '%s\\n' '{line}'" for line in lines)


def env_for(tmp_path: Path, xdg: Path, **extra: str) -> dict:
    return {"PATH": f"{tmp_path / 'bin'}:{SYSTEM_PATH}", "HOME": str(tmp_path),
            "XDG_CONFIG_HOME": str(xdg), **extra}


def run(tmp_path: Path, xdg: Path, stdin: str = "", **extra: str) -> subprocess.CompletedProcess:
    return subprocess.run([str(SCRIPT)], input=stdin, capture_output=True, text=True,
                          env=env_for(tmp_path, xdg, **extra), timeout=10, check=False)


def calls(log: Path) -> list[str]:
    return log.read_text().splitlines() if log.exists() else []


def wait_until(condition, seconds: float = 3.0) -> None:
    deadline = time.monotonic() + seconds
    while not condition() and time.monotonic() < deadline:
        time.sleep(0.05)


def assert_posted_line(r: subprocess.CompletedProcess, received: list, log: Path) -> None:
    assert r.returncode == 0 and r.stdout == "" and r.stderr == ""
    wait_for(received)
    time.sleep(0.2)  # a second POST would show up now
    assert received == [{"path": "/api/v1/push/claude", "auth": f"Bearer {KEY}",
                         "type": "application/json", "body": LINE.encode()}]
    assert calls(log) == [f"{ARGS}|1"]


def test_posts_the_usage_report_line(tmp_path, server, fake_claude):
    url, received = server
    log = fake_claude(printing('{"type":"system","subtype":"init"}', LINE,
                               '{"type":"result","result":""}'))
    assert_posted_line(run(tmp_path, write_env(tmp_path, url)), received, log)


def test_ignores_stdin(tmp_path, server, fake_claude):
    url, received = server
    log = fake_claude(printing(LINE))
    hook = json.dumps({"session_id": "abc", "hook_event_name": "Stop"})
    assert_posted_line(run(tmp_path, write_env(tmp_path, url), stdin=hook), received, log)


def test_returns_at_once(tmp_path, server, fake_claude):
    url, received = server
    fake_claude("sleep 2\n" + printing(LINE))
    start = time.monotonic()
    r = run(tmp_path, write_env(tmp_path, url))
    assert time.monotonic() - start < 1
    assert r.returncode == 0 and r.stdout == "" and r.stderr == ""
    wait_for(received, 5)
    assert len(received) == 1


def test_loop_guard(tmp_path, server, fake_claude):
    url, received = server
    log = fake_claude(printing(LINE))
    r = run(tmp_path, write_env(tmp_path, url), GLANCEBOX_USAGE="1")
    assert r.returncode == 0 and r.stdout == "" and r.stderr == ""
    time.sleep(1)
    assert calls(log) == [] and received == []


def test_throttled_within_60_s(tmp_path, server, fake_claude):
    url, received = server
    log = fake_claude(printing(LINE))
    xdg = write_env(tmp_path, url)
    run(tmp_path, xdg)
    wait_for(received)
    r = run(tmp_path, xdg)
    assert r.returncode == 0 and r.stdout == "" and r.stderr == ""
    time.sleep(1)
    assert len(calls(log)) == 1 and len(received) == 1


def test_two_hooks_at_once_fetch_once(tmp_path, server, fake_claude):
    url, received = server
    log = fake_claude(printing(LINE))
    xdg = write_env(tmp_path, url)
    procs = [subprocess.Popen([str(SCRIPT)], stdin=subprocess.DEVNULL,
                              env=env_for(tmp_path, xdg)) for _ in range(2)]
    assert [p.wait(timeout=10) for p in procs] == [0, 0]
    wait_for(received)
    time.sleep(1)
    assert len(calls(log)) == 1 and len(received) == 1


def write_stamp(xdg: Path, text: str) -> None:
    (xdg / "glancebox" / "usage.stamp").write_text(text)


def test_fetches_again_after_60_s(tmp_path, server, fake_claude):
    url, received = server
    log = fake_claude(printing(LINE))
    xdg = write_env(tmp_path, url)
    write_stamp(xdg, f"{int(time.time()) - 61}\n")
    run(tmp_path, xdg)
    wait_for(received)
    assert len(calls(log)) == 1 and len(received) == 1
    stamp = int((xdg / "glancebox" / "usage.stamp").read_text())
    assert abs(stamp - time.time()) < 5


@pytest.mark.parametrize("stamp", ["", "abc", "12 34", str(int(time.time()) + 3600)])
def test_bad_or_future_stamp_fetches(tmp_path, server, fake_claude, stamp):
    url, received = server
    log = fake_claude(printing(LINE))
    xdg = write_env(tmp_path, url)
    write_stamp(xdg, stamp)
    r = run(tmp_path, xdg)
    assert r.returncode == 0 and r.stdout == "" and r.stderr == ""
    wait_for(received)
    assert len(calls(log)) == 1 and len(received) == 1


def test_status_line_stamp_throttles(tmp_path, server, fake_claude):
    url, received = server
    log = fake_claude(printing(LINE))
    xdg = write_env(tmp_path, url)
    status = json.dumps({"rate_limits": {"five_hour": {"used_percentage": 1}}})
    subprocess.run([str(STATUSLINE)], input=status, capture_output=True, text=True,
                   env=env_for(tmp_path, xdg), timeout=10, check=True)
    wait_for(received)
    r = run(tmp_path, xdg)
    assert r.returncode == 0 and r.stdout == "" and r.stderr == ""
    time.sleep(1)
    assert calls(log) == [] and len(received) == 1


@pytest.mark.parametrize("out", ['{"type":"result"}', '{"usage_report":{"rate_limits":null}}',
                                 '{"usage_report":{"rate_limits":{"limits":[]}}}'])
def test_sends_nothing_without_limits(tmp_path, server, fake_claude, out):
    url, received = server
    log = fake_claude(printing(out))
    r = run(tmp_path, write_env(tmp_path, url))
    assert r.returncode == 0 and r.stdout == "" and r.stderr == ""
    wait_until(lambda: calls(log))
    time.sleep(1)
    assert len(calls(log)) == 1 and received == []


def test_silent_without_claude(tmp_path, server):
    if shutil.which("claude", path=SYSTEM_PATH):
        pytest.skip("a real claude is on the system PATH")
    url, received = server
    r = run(tmp_path, write_env(tmp_path, url))
    assert r.returncode == 0 and r.stdout == "" and r.stderr == ""
    time.sleep(1)
    assert received == []


def test_hanging_claude_is_killed(tmp_path, server, fake_claude):
    url, received = server
    pid_file = tmp_path / "claude.pid"
    fake_claude(f'echo $$ > "{pid_file}"\nexec sleep 30')
    r = run(tmp_path, write_env(tmp_path, url), GLANCEBOX_USAGE_TIMEOUT="1")
    assert r.returncode == 0 and r.stdout == "" and r.stderr == ""
    wait_until(pid_file.exists)
    pid = int(pid_file.read_text())

    def gone() -> bool:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        return False

    wait_until(gone, 4)
    assert gone()
    assert received == []


def test_silent_without_config(tmp_path, fake_claude):
    log = fake_claude(printing(LINE))
    xdg = tmp_path / "xdg"
    xdg.mkdir()
    r = run(tmp_path, xdg)
    assert r.returncode == 0 and r.stdout == "" and r.stderr == ""
    time.sleep(0.5)
    assert calls(log) == []
