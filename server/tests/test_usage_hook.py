"""tools/statusline/glancebox-usage.sh: a hook that fetches `/usage` and pushes the report."""

import json
import os
import shutil
import signal
import subprocess
import time
from pathlib import Path

import pytest
from test_statusline import KEY, logging_curl, wait_for, write_env

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


def sleeps(seconds: str) -> list[str]:
    """Running `sleep <seconds>` processes (of any user and run)."""
    ps = subprocess.run(["ps", "-A", "-o", "command="], capture_output=True, text=True,
                        check=True)
    return [c for c in ps.stdout.splitlines() if c.strip() == f"sleep {seconds}"]


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


THROTTLE = "3"  # seconds, instead of 60, through the test knob GLANCEBOX_USAGE_THROTTLE


def marker(xdg: Path, name: str) -> Path:
    return xdg / "glancebox" / name


def settle(xdg: Path) -> None:
    """Waits until no trailing fetch is pending and the lock is free, then a moment for a
    fetch that just started; afterwards neither marker may exist."""
    pending, lock = marker(xdg, "usage.pending"), marker(xdg, "usage.lock")
    wait_until(lambda: not pending.exists() and not lock.exists(), int(THROTTLE) + 3)
    time.sleep(0.5)
    assert not pending.exists() and not lock.exists()


def hook(tmp_path: Path, xdg: Path) -> None:
    """One throttled hook run: it returns in under a second, prints nothing, exits 0."""
    start = time.monotonic()
    r = run(tmp_path, xdg, GLANCEBOX_USAGE_THROTTLE=THROTTLE)
    assert time.monotonic() - start < 1
    assert r.returncode == 0 and r.stdout == "" and r.stderr == ""


def test_throttled_hook_fetches_once_after_the_window(tmp_path, server, fake_claude):
    # The last answer of a burst must reach the display: a throttled hook leaves one fetch
    # waiting for the end of the window instead of dropping it.
    url, received = server
    log = fake_claude(printing(LINE))
    xdg = write_env(tmp_path, url)
    run(tmp_path, xdg, GLANCEBOX_USAGE_THROTTLE=THROTTLE)
    wait_for(received)
    hook(tmp_path, xdg)
    time.sleep(0.5)
    assert len(calls(log)) == 1 and len(received) == 1  # not at once: still in the window
    wait_until(lambda: len(received) >= 2, int(THROTTLE) + 3)
    settle(xdg)
    assert calls(log) == [f"{ARGS}|1"] * 2 and len(received) == 2
    assert received[1]["body"] == LINE.encode()


def test_five_hooks_in_the_window_fetch_twice(tmp_path, server, fake_claude):
    url, received = server
    log = fake_claude(printing(LINE))
    xdg = write_env(tmp_path, url)
    run(tmp_path, xdg, GLANCEBOX_USAGE_THROTTLE=THROTTLE)
    wait_for(received)
    for _ in range(5):
        hook(tmp_path, xdg)
    wait_until(lambda: len(received) >= 2, int(THROTTLE) + 3)
    settle(xdg)
    assert len(calls(log)) == 2 and len(received) == 2


def test_new_stamp_cancels_the_trailing_fetch(tmp_path, server, fake_claude):
    # Newer data (from the status-line script or another fetch) makes the waiting fetch moot.
    url, received = server
    log = fake_claude(printing(LINE))
    xdg = write_env(tmp_path, url)
    run(tmp_path, xdg, GLANCEBOX_USAGE_THROTTLE=THROTTLE)
    wait_for(received)
    seen = int(marker(xdg, "usage.stamp").read_text())
    hook(tmp_path, xdg)
    assert marker(xdg, "usage.pending").is_dir()
    wait_until(lambda: int(time.time()) > seen)
    write_stamp(xdg, f"{int(time.time())}\n")
    settle(xdg)
    assert len(calls(log)) == 1 and len(received) == 1


def test_stale_pending_marker_does_not_block(tmp_path, server, fake_claude):
    # A marker left by a killed run must not stop trailing fetches for good.
    url, received = server
    log = fake_claude(printing(LINE))
    xdg = write_env(tmp_path, url)
    run(tmp_path, xdg, GLANCEBOX_USAGE_THROTTLE=THROTTLE)
    wait_for(received)
    pending = marker(xdg, "usage.pending")
    pending.mkdir()
    old = time.time() - 180
    os.utime(pending, (old, old))
    hook(tmp_path, xdg)
    wait_until(lambda: len(received) >= 2, int(THROTTLE) + 3)
    settle(xdg)
    assert len(calls(log)) == 2 and len(received) == 2


def test_fresh_pending_marker_blocks(tmp_path, server, fake_claude):
    # One fetch is already waiting (its marker is fresh): the hook adds no second one.
    url, received = server
    log = fake_claude(printing(LINE))
    xdg = write_env(tmp_path, url)
    run(tmp_path, xdg, GLANCEBOX_USAGE_THROTTLE=THROTTLE)
    wait_for(received)
    pending = marker(xdg, "usage.pending")
    pending.mkdir()
    hook(tmp_path, xdg)
    time.sleep(int(THROTTLE) + 1)
    assert len(calls(log)) == 1 and len(received) == 1
    pending.rmdir()


def test_two_hooks_at_once_fetch_once(tmp_path, server, fake_claude):
    url, received = server
    log = fake_claude(printing(LINE))
    xdg = write_env(tmp_path, url)
    procs = [subprocess.Popen([str(SCRIPT)], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE,
                              env=env_for(tmp_path, xdg, GLANCEBOX_USAGE_THROTTLE=THROTTLE))
             for _ in range(2)]
    assert [p.communicate(timeout=10) for p in procs] == [(b"", b"")] * 2
    assert [p.returncode for p in procs] == [0, 0]
    wait_for(received)
    time.sleep(1)
    assert len(calls(log)) == 1 and len(received) == 1
    settle(xdg)  # the second may have left a trailing fetch for the end of the window


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


def status_line(tmp_path: Path, xdg: Path) -> None:
    status = json.dumps({"rate_limits": {"five_hour": {"used_percentage": 1}}})
    subprocess.run([str(STATUSLINE)], input=status, capture_output=True, text=True,
                   env=env_for(tmp_path, xdg), timeout=10, check=True)


def test_status_line_stamp_throttles(tmp_path, server, fake_claude):
    # The status line sent just now: the hook does not fetch at once. When the status line
    # sends again during the window, the waiting fetch is dropped as well.
    url, received = server
    log = fake_claude(printing(LINE))
    xdg = write_env(tmp_path, url)
    status_line(tmp_path, xdg)
    wait_for(received)
    seen = int(marker(xdg, "usage.stamp").read_text())
    hook(tmp_path, xdg)
    time.sleep(0.5)
    assert calls(log) == [] and len(received) == 1
    wait_until(lambda: int(time.time()) > seen)
    status_line(tmp_path, xdg)
    wait_until(lambda: len(received) >= 2)
    settle(xdg)
    assert calls(log) == [] and len(received) == 2


def test_status_line_once_then_trailing_fetch(tmp_path, server, fake_claude):
    # One status-line send, then silence: the hook cannot know whether the status line saw
    # the last answer, so it fetches once after the window.
    url, received = server
    log = fake_claude(printing(LINE))
    xdg = write_env(tmp_path, url)
    status_line(tmp_path, xdg)
    wait_for(received)
    hook(tmp_path, xdg)
    time.sleep(0.5)
    assert calls(log) == []
    wait_until(lambda: len(received) >= 2, int(THROTTLE) + 3)
    settle(xdg)
    assert len(calls(log)) == 1 and len(received) == 2


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


def test_key_not_on_command_line(tmp_path, server, fake_claude):
    """Command lines are visible to every local user (ps); the key must not be on curl's."""
    url, received = server
    fake_claude(printing(LINE))
    log = logging_curl(tmp_path / "bin")
    run(tmp_path, write_env(tmp_path, url))
    wait_for(received)
    assert received[0]["auth"] == f"Bearer {KEY}" and received[0]["body"] == LINE.encode()
    assert log.read_text().count("\n") == 1 and KEY not in log.read_text()


def test_key_not_passed_to_claude(tmp_path, server, fake_claude):
    # Not even when the user's shell exports it.
    url, received = server
    env_dump = tmp_path / "claude.env"
    fake_claude(f'env > "{env_dump}"\n' + printing(LINE))
    run(tmp_path, write_env(tmp_path, url), GLANCEBOX_PUSH_KEY=KEY, GLANCEBOX_URL=url)
    wait_for(received)
    assert len(received) == 1
    assert KEY not in env_dump.read_text() and "GLANCEBOX_URL" not in env_dump.read_text()


def test_huge_timeout_falls_back_to_30(tmp_path, server, fake_claude):
    url, received = server
    timers = tmp_path / "timers"
    fake_claude(f"ps -A -o command= > \"{timers}\"\n" + printing(LINE))
    run(tmp_path, write_env(tmp_path, url), GLANCEBOX_USAGE_TIMEOUT="99999999999")
    wait_for(received)
    assert len(received) == 1
    commands = timers.read_text().splitlines()
    assert "sleep 30" in commands and "sleep 99999999999" not in commands


def test_claude_ignoring_term_is_killed(tmp_path, server, fake_claude):
    url, _ = server
    pid_file = tmp_path / "claude.pid"
    # No exec: the shell itself ignores TERM; its short sleeps end on their own.
    fake_claude(f'echo $$ > "{pid_file}"\ntrap "" TERM\nwhile :; do sleep 1; done')
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

    wait_until(gone, 6)
    if not gone():
        os.kill(pid, signal.SIGKILL)  # do not leave it running when the test fails
        pytest.fail("claude ignoring TERM was not killed")


def test_stale_lock_is_removed(tmp_path, server, fake_claude):
    # A run killed while it held the lock must not stop the hook for good.
    url, received = server
    log = fake_claude(printing(LINE))
    xdg = write_env(tmp_path, url)
    lock = xdg / "glancebox" / "usage.lock"
    lock.mkdir()
    old = time.time() - 120
    os.utime(lock, (old, old))
    r = run(tmp_path, xdg)
    assert r.returncode == 0 and r.stdout == "" and r.stderr == ""
    wait_for(received)
    assert len(calls(log)) == 1 and len(received) == 1
    assert not lock.exists()


def test_fresh_lock_blocks(tmp_path, server, fake_claude):
    url, received = server
    log = fake_claude(printing(LINE))
    xdg = write_env(tmp_path, url)
    (xdg / "glancebox" / "usage.lock").mkdir()
    r = run(tmp_path, xdg)
    assert r.returncode == 0 and r.stdout == "" and r.stderr == ""
    time.sleep(1)
    assert calls(log) == [] and received == []


def test_no_timer_left_without_claude(tmp_path, server):
    """A missing claude ends the fetch at once; its timer must not stay behind (it did once:
    stopped before it had set its trap, the watchdog left its sleep running)."""
    if shutil.which("claude", path=SYSTEM_PATH):
        pytest.skip("a real claude is on the system PATH")
    url, received = server
    xdg = write_env(tmp_path, url)
    for _ in range(3):
        (xdg / "glancebox" / "usage.stamp").unlink(missing_ok=True)
        run(tmp_path, xdg, GLANCEBOX_USAGE_TIMEOUT="7")
    wait_until(lambda: not sleeps("7"), 2)
    assert sleeps("7") == [] and received == []
