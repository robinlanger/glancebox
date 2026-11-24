"""tools/statusline/glancebox-statusline.sh: forwards Claude Code's status-line JSON."""

import json
import shutil
import socket
import subprocess
import time
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "tools" / "statusline" / "glancebox-statusline.sh"
KEY = "test-key-0123456789abcdef"
STDIN = json.dumps({"model": {"display_name": "Opus"}, "rate_limits": {
    "five_hour": {"used_percentage": 23.5, "resets_at": 1738425600}}})

pytestmark = pytest.mark.skipif(not (shutil.which("sh") and shutil.which("curl")),
                                reason="needs sh and curl")


def write_env(tmp_path: Path, url: str, key: str = KEY) -> Path:
    cfg = tmp_path / "xdg"
    (cfg / "glancebox").mkdir(parents=True)
    (cfg / "glancebox" / "push.env").write_text(
        f"# Glance Box\nGLANCEBOX_URL={url}\nGLANCEBOX_PUSH_KEY={key}\n")
    return cfg


def run(xdg: Path, *args: str, stdin: str = STDIN) -> subprocess.CompletedProcess:
    env = {"PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin", "HOME": str(xdg.parent),
           "XDG_CONFIG_HOME": str(xdg)}
    return subprocess.run([str(SCRIPT), *args], input=stdin, capture_output=True, text=True,
                          env=env, timeout=10, check=False)


def wait_for(received: list, seconds: float = 3.0) -> None:
    deadline = time.monotonic() + seconds
    while not received and time.monotonic() < deadline:
        time.sleep(0.05)


def test_forwards_stdin_with_key(tmp_path, server):
    url, received = server
    r = run(write_env(tmp_path, url))
    assert r.returncode == 0 and r.stdout == "" and r.stderr == ""
    wait_for(received)
    assert received == [{"path": "/api/v1/push/claude", "auth": f"Bearer {KEY}",
                         "type": "application/json", "body": STDIN.encode()}]


@pytest.mark.parametrize("key", ["abc0123456789xyz=", "abc0123456789xy==", "a=b=c0123456789x"])
def test_key_with_equals_signs_kept(tmp_path, server, key):
    # base64 keys end in "=" or "=="; read with IFS='=' would strip a single trailing "=".
    url, received = server
    run(write_env(tmp_path, url, key))
    wait_for(received)
    assert received[0]["auth"] == f"Bearer {key}"


def test_runs_wrapped_command(tmp_path, server):
    url, received = server
    r = run(write_env(tmp_path, url), "sh", "-c", "cat; echo done")
    assert r.returncode == 0
    assert r.stdout == STDIN + "done\n"
    wait_for(received)
    assert len(received) == 1


def test_wrapped_command_exit_status(tmp_path, server):
    url, _ = server
    assert run(write_env(tmp_path, url), "sh", "-c", "exit 3").returncode == 3


def test_skips_push_without_rate_limits(tmp_path, server):
    """Before the first answer of a session the JSON has no rate_limits; keep the last push."""
    url, received = server
    r = run(write_env(tmp_path, url), stdin='{"model": {"display_name": "Opus"}}')
    assert r.returncode == 0
    time.sleep(1)
    assert received == []


def test_fast_when_server_unreachable(tmp_path):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]  # closed again when the block ends
    xdg = write_env(tmp_path, f"http://127.0.0.1:{port}")
    start = time.monotonic()
    r = run(xdg)
    assert time.monotonic() - start < 1
    assert r.returncode == 0 and r.stdout == "" and r.stderr == ""


def test_silent_without_config(tmp_path):
    xdg = tmp_path / "xdg"
    xdg.mkdir()
    r = run(xdg)
    assert r.returncode == 0 and r.stdout == "" and r.stderr == ""


def test_writes_usage_stamp(tmp_path, server):
    """A send stamps usage.stamp, so the usage hook does not fetch the same values again."""
    url, received = server
    xdg = write_env(tmp_path, url)
    stamp = xdg / "glancebox" / "usage.stamp"
    run(xdg, stdin='{"model": {"display_name": "Opus"}}')
    assert not stamp.exists()
    run(xdg)
    wait_for(received)
    assert abs(int(stamp.read_text()) - time.time()) < 5
