// Glance Box device page script. Minified + gzipped at build time (scripts/embed_web.py).
// Minifier limits: no regex literal containing two slashes or slash-star; keep strings ASCII
// (use \u escapes). All texts come from the page (body data-i18n), none are hard-coded here.
"use strict";

// ---- MD5 (RFC 1321) of an ArrayBuffer: /update needs it before the file part ----
function md5(buffer) {
  const bytes = new Uint8Array(buffer);
  const n = bytes.length;
  const words = (((n + 8) >>> 6) + 1) * 16;
  const x = new Uint32Array(words);
  for (let i = 0; i < n; i++) x[i >> 2] |= bytes[i] << ((i % 4) * 8);
  x[n >> 2] |= 0x80 << ((n % 4) * 8);
  x[words - 2] = (n * 8) >>> 0;
  x[words - 1] = Math.floor(n / 0x20000000);
  const S = [7, 12, 17, 22, 5, 9, 14, 20, 4, 11, 16, 23, 6, 10, 15, 21];
  const K = [];
  for (let i = 0; i < 64; i++) K.push(Math.floor(Math.abs(Math.sin(i + 1)) * 4294967296) | 0);
  let a0 = 0x67452301, b0 = 0xefcdab89 | 0, c0 = 0x98badcfe | 0, d0 = 0x10325476;
  for (let o = 0; o < words; o += 16) {
    let a = a0, b = b0, c = c0, d = d0;
    for (let i = 0; i < 64; i++) {
      let f, g;
      if (i < 16) { f = (b & c) | (~b & d); g = i; }
      else if (i < 32) { f = (d & b) | (~d & c); g = (5 * i + 1) % 16; }
      else if (i < 48) { f = b ^ c ^ d; g = (3 * i + 5) % 16; }
      else { f = c ^ (b | ~d); g = (7 * i) % 16; }
      const s = S[(i >> 4) * 4 + (i % 4)];
      const sum = (a + f + K[i] + x[o + g]) | 0;
      a = d; d = c; c = b;
      b = (b + ((sum << s) | (sum >>> (32 - s)))) | 0;
    }
    a0 = (a0 + a) | 0; b0 = (b0 + b) | 0; c0 = (c0 + c) | 0; d0 = (d0 + d) | 0;
  }
  let hex = "";
  for (const v of [a0, b0, c0, d0]) {
    for (let i = 0; i < 4; i++) hex += ((v >>> (i * 8)) & 255).toString(16).padStart(2, "0");
  }
  return hex;
}

// ---- Live preview while dragging: one request at a time, at most one per minGapMs,
// the latest value always wins. flush() drops what is pending and waits for the open one.
// If send(v) resolves to exactly false (refused, e.g. no password yet), the pump drops the
// pending value and ignores push() until flush() has run. A rejected send (network error)
// does not stop it. ----
function createPreviewPump(send, minGapMs) {
  let inFlight = null, queued = null, timer = null, lastSent = -Infinity, stopped = false;
  const pump = () => {
    if (stopped || inFlight || timer || queued === null) return;
    const wait = lastSent + minGapMs - Date.now();
    if (wait > 0) {
      timer = setTimeout(() => {
        timer = null;
        pump();
      }, wait);
      return;
    }
    const v = queued;
    queued = null;
    lastSent = Date.now();
    inFlight = Promise.resolve()
      .then(() => send(v))
      .then((ok) => {
        if (ok === false) {
          stopped = true;
          queued = null;
        }
      })
      .catch(() => {})
      .finally(() => {
        inFlight = null;
        pump();
      });
  };
  return {
    push(v) {
      if (stopped) return;
      queued = v;
      pump();
    },
    async flush() {
      queued = null;
      clearTimeout(timer);
      timer = null;
      while (inFlight) await inFlight;
      stopped = false;
    },
  };
}

if (typeof document !== "undefined") init();

function init() {
  const $ = (id) => document.getElementById(id);
  const T = JSON.parse(document.body.dataset.i18n || "{}");
  const CHECK = "\u2713";

  // POST form fields, expect {"ok":true}. Throws Error(message for the user); errors from an
  // HTTP answer carry its status as .status (network errors have none).
  async function post(url, fields) {
    let r;
    try {
      r = await fetch(url, { method: "POST", body: new URLSearchParams(fields), credentials: "same-origin" });
    } catch (e) {
      throw new Error(T.error);
    }
    const fail = (message) => Object.assign(new Error(message), { status: r.status });
    if (r.status === 401) throw fail(T.auth);
    if (r.status === 429) throw fail((await r.text()).trim() || T.error); // password lock
    let j = {};
    try { j = await r.json(); } catch (e) { /* not JSON */ }
    if (!r.ok || !j.ok) throw fail(j.error || T.error);
    return j;
  }

  // ---- Row feedback: saving ... / check mark / red message ----
  const rowOf = (el) => el.closest(".row");
  function setState(row, state, text) {
    const m = row.querySelector(".msg");
    clearTimeout(row.gbTimer);
    row.dataset.state = state;
    if (m) m.textContent = state === "ok" ? CHECK : text || "";
    if (state === "ok") {
      row.gbTimer = setTimeout(() => {
        delete row.dataset.state;
        if (m) m.textContent = "";
      }, 1500);
    }
  }
  async function save(row, fields) {
    setState(row, "saving");
    try {
      await post("/api/settings", fields);
      setState(row, "ok");
      return true;
    } catch (e) {
      setState(row, "error", e.message);
      return false;
    }
  }

  // ---- Sliders: live preview while dragging, save on release ----
  function paint(input) {
    const min = +input.min, max = +input.max, v = +input.value;
    input.style.setProperty("--p", ((v - min) * 100) / (max - min) + "%");
    const out = rowOf(input).querySelector("output");
    if (out) out.textContent = v === 0 ? T.off : v + " %";
  }
  for (const input of document.querySelectorAll("input[type=range]")) {
    const row = rowOf(input);
    let saved = input.value;
    // The preview never brings up the password dialog (401 without WWW-Authenticate): on 401
    // or 429 the pump stops until release, where the save asks for the password.
    const preview = createPreviewPump(
      (v) => post("/api/brightness-preview", { pct: v }).then(
        () => true,
        (e) => e.status !== 401 && e.status !== 429,
      ),
      100,
    );
    paint(input);
    input.addEventListener("input", () => {
      paint(input);
      preview.push(input.value);
    });
    input.addEventListener("change", async () => {
      await preview.flush(); // the save below re-applies the saved value on the device
      const v = input.value;
      if (await save(row, { [input.name]: v })) {
        saved = v;
      } else {
        input.value = saved;
        paint(input);
      }
    });
  }

  // ---- Night mode switch: off = start equals end (the stored format) ----
  const display = $("display"), sw = $("night_on"), ns = $("night_start"), ne = $("night_end");
  if (sw && ns && ne) {
    let last = sw.checked ? [ns.value, ne.value] : ["22:00", "07:00"];
    sw.addEventListener("change", async () => {
      const on = sw.checked;
      if (!on && ns.value !== ne.value) last = [ns.value, ne.value];
      const start = on ? last[0] : ns.value;
      const end = on ? last[1] : ns.value;
      if (await save(rowOf(sw), { night_start: start, night_end: end })) {
        ns.value = ns.gbSaved = start;
        ne.value = ne.gbSaved = end;
        display.dataset.night = on ? "on" : "off";
      } else {
        sw.checked = !on;
      }
    });
  }

  // ---- Text and time fields: save when leaving the field (or on Enter) ----
  function offerUndo(row, el, prev) {
    const m = row.querySelector(".msg");
    clearTimeout(row.gbTimer);
    const undo = document.createElement("button");
    undo.type = "button";
    undo.className = "lnk undo";
    undo.textContent = T.undo;
    m.textContent = CHECK + " ";
    m.appendChild(undo);
    undo.addEventListener("click", async () => {
      el.value = prev;
      if (await save(row, { [el.name]: prev })) el.gbSaved = prev;
    });
    row.gbTimer = setTimeout(() => {
      if (m.contains(undo)) {
        m.textContent = "";
        delete row.dataset.state;
      }
    }, 8000);
  }
  for (const el of [ns, ne, $("server_url")]) {
    if (!el) continue;
    el.gbSaved = el.value;
    const commit = async () => {
      const v = el.value.trim();
      if (v === el.gbSaved) return;
      const prev = el.gbSaved;
      if (await save(rowOf(el), { [el.name]: v })) {
        el.gbSaved = v;
        if (el.id === "server_url") offerUndo(rowOf(el), el, prev);
      }
    };
    // Time pickers fire "change" per segment while typing; wait until the field is left.
    el.addEventListener(el.type === "time" ? "blur" : "change", commit);
    el.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        el.blur();
        if (el.type !== "time") commit();
      }
    });
  }

  // ---- Password ----
  const pw = $("pw-form");
  if (pw) {
    pw.addEventListener("submit", async (e) => {
      e.preventDefault();
      const input = pw.elements.password, repeat = pw.elements.password_repeat;
      const m = pw.querySelector(".msg");
      // Checked here first, so a typo sends no request (and brings up no password dialog).
      if (input.value !== repeat.value) {
        m.className = "msg err";
        m.textContent = T.pw_mismatch;
        return;
      }
      try {
        await post("/api/settings", { password: input.value, password_repeat: repeat.value });
        m.className = "msg";
        m.textContent = T.pw_changed;
        input.value = "";
        repeat.value = "";
      } catch (err) {
        m.className = "msg err";
        m.textContent = err.message;
      }
    });
  }

  // ---- Firmware update: MD5 in the browser, upload with progress ----
  const up = $("update-form");
  if (up) {
    const file = up.elements.firmware, sum = up.elements.md5;
    const bar = $("up-progress"), m = up.querySelector(".msg"), button = up.querySelector("button");
    let busy = false; // one upload at a time: a second one would overwrite the first's result
    const fail = (text) => {
      busy = false;
      button.disabled = false;
      bar.hidden = true;
      m.className = "msg err";
      m.textContent = text;
    };
    file.addEventListener("change", async () => {
      sum.value = "";
      if (file.files[0]) sum.value = md5(await file.files[0].arrayBuffer());
    });
    up.addEventListener("submit", (e) => {
      e.preventDefault();
      if (busy) return;
      busy = true;
      button.disabled = true;
      const data = new FormData();
      data.append("md5", sum.value.trim()); // must precede the file part
      data.append("firmware", file.files[0]);
      const xhr = new XMLHttpRequest();
      xhr.open("POST", "/update");
      bar.hidden = false;
      bar.value = 0;
      m.className = "msg";
      m.textContent = T.uploading;
      xhr.upload.onprogress = (ev) => {
        if (ev.lengthComputable) bar.value = (ev.loaded * 100) / ev.total;
      };
      xhr.onload = () => {
        if (xhr.status === 200) {
          bar.value = 100;
          m.textContent = T.upload_ok;
          setTimeout(() => location.reload(), 15000);
        } else {
          fail(xhr.status === 401 ? T.auth : xhr.responseText.trim() || T.error);
        }
      };
      xhr.onerror = () => fail(T.error);
      xhr.send(data);
    });
  }
  if (location.hash === "#update" && $("update")) $("update").open = true;

  // ---- Restart and reset ----
  for (const form of document.querySelectorAll("form[action='/restart']")) {
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const row = form;
      try {
        const r = await fetch("/restart", { method: "POST", credentials: "same-origin" });
        if (r.status === 401) throw new Error(T.auth);
        if (r.status === 429) throw new Error((await r.text()).trim() || T.error); // password lock
        if (!r.ok) throw new Error(T.error);
        setState(row, "saving");
        row.querySelector("button").textContent = T.restarting;
        setTimeout(() => location.reload(), 8000);
      } catch (err) {
        alert(err.message);
      }
    });
  }
  const reset = $("reset-form");
  if (reset) {
    reset.addEventListener("submit", (e) => {
      if (!confirm(T.reset_confirm)) e.preventDefault();
    });
  }

  // ---- Status tiles: refresh every 5 s from /status ----
  const dur = (s) => {
    if (s < 60) return s + " s";
    const min = Math.floor(s / 60);
    if (min < 60) return min + " min";
    const h = Math.floor(min / 60);
    if (h < 24) return h + " h " + (min % 60) + " min";
    return Math.floor(h / 24) + " " + T.day + " " + (h % 24) + " h";
  };
  const wifi = (r) => (r >= -60 ? T.wifi0 : r >= -70 ? T.wifi1 : r >= -80 ? T.wifi2 : T.wifi3);
  const tile = (id, text, state) => {
    const el = $(id);
    if (!el) return;
    el.textContent = text;
    if (state) el.dataset.state = state;
  };
  async function refresh() {
    try {
      const s = await (await fetch("/status", { cache: "no-store" })).json();
      const age = s.last_frame_age_s;
      const online = age !== null && age < 120;
      tile("t-conn", online ? T.online : T.offline, online ? "ok" : "bad");
      tile("t-age", age === null ? "-" : T.ago.replace("{}", dur(age)));
      tile("t-wifi", s.rssi === null ? "-" : wifi(s.rssi));
      tile("t-up", dur(s.uptime_s));
    } catch (e) {
      tile("t-conn", T.offline, "bad");
    }
  }
  setInterval(refresh, 5000);
}
