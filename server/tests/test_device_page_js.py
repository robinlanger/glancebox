"""Logic of firmware/web/app.js that needs no browser, run with node."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

_APP = Path(__file__).resolve().parents[2] / "firmware" / "web" / "app.js"
if not _APP.exists() or shutil.which("node") is None:
    pytest.skip("needs firmware/web/app.js and node", allow_module_level=True)

_HARNESS = """
const src = require('fs').readFileSync(process.argv[1], 'utf8');
const { createPreviewPump } = new Function(src + '\\nreturn { createPreviewPump };')();
const tick = () => new Promise((r) => setTimeout(r, 5));
(async () => { %s })().then((v) => console.log(JSON.stringify(v)));
"""


def run_js(body: str):
    out = subprocess.run(["node", "-e", _HARNESS % body, str(_APP)],
                         capture_output=True, text=True, timeout=20, check=True)
    return json.loads(out.stdout)


def test_pump_sends_one_at_a_time_and_latest_wins():
    assert run_js("""
        const sent = [];
        const pump = createPreviewPump(async (v) => { sent.push(v); await tick(); return true; }, 0);
        pump.push(1); pump.push(2); pump.push(3);
        await tick(); await tick(); await tick();
        return sent;
    """) == [1, 3]


def test_pump_stops_after_a_refused_send_until_flush():
    assert run_js("""
        const sent = [];
        const pump = createPreviewPump(async (v) => { sent.push(v); await tick(); return v !== 1; }, 0);
        pump.push(1); pump.push(2); pump.push(3);
        await tick(); await tick(); await tick();
        pump.push(4);
        await tick(); await tick();
        const whilePaused = sent.slice();
        await pump.flush();
        pump.push(5);
        await tick(); await tick();
        return [whilePaused, sent];
    """) == [[1], [1, 5]]
