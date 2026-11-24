# Energiefluss-Seite mit bewegten Pfeilen: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ein neuer Seitentyp `energy` zeigt 1 bis 4 Zeilen (Netz, PV, Speicher, Gas, Wasser, Wallbox) aus Home Assistant; die Firmware zeichnet auf den Spuren bewegte Pfeile mit etwa 25 Bildern pro Sekunde, gesteuert durch die neue Kopfzeile `X-Anim`.

**Architecture:** Der Server rendert weiter ein Standbild (JPEG) mit leeren Spuren. `pages/energy/page.py` rechnet die Lage der Zeilen einmal aus und gibt sie dem Template und, als Animationsbeschreibung, dem Worker; `Frame` trägt die fertige Kopfzeile, `/api/v1/frame` hängt sie an 200 und 304. Die Firmware bekommt in `firmware/lib/core` ein rein logisches Modul `anim` (Parser, Pfeilposition, Ausschneiden, Zustandsregeln; nativ getestet); `firmware/src` zeichnet nur und ruft den Tick aus `loop()`, der Kopf-Leseschleife und den beiden TJpgDec-Funktionen auf.

**Tech Stack:** Python 3.12, FastAPI, Jinja2, Playwright/Chromium, Pillow, pytest, ruff · C++17, PlatformIO (`native` für Tests, `ultra` = ESP8266/Arduino), TFT_eSPI 2.5.43, TJpgDec, Unity · Home Assistant (Test-VM) mit `input_number` und Template-Sensoren.

**Spec:** `docs/superpowers/specs/2026-11-23-energiefluss-design.md`. Vor jeder Task den passenden Abschnitt lesen; dort stehen Verhalten, Gründe und die Regeltabellen. Ihre Entscheidungen sind endgültig.

## Global Constraints

- Branch `feat/energy-flow`. Committen ja, **kein Push, kein Merge, kein Tag, kein Release.** `VERSION` und `ha-addon/config.yaml` bleiben bei 0.6.3 (siehe Task 11).
- Commits im Stil der Historie (`feat(server): ...`, `feat(pages): ...`, `feat(firmware): ...`, `test: ...`, `docs: ...`), Englisch, jede Nachricht endet mit der Zeile `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Immer einzelne Dateien mit `git add` aufnehmen; die unverfolgte Datei `server/uv.lock` gehört nicht dazu.
- **Server-Tests** aus `server/`: `.venv/bin/pytest -q -m "not browser"` und `.venv/bin/ruff check . ../pages`. Browser-Tests: `.venv/bin/pytest -q -m browser` (Chromium der venv); maßgeblich ist wie in CI das Test-Image: `docker build --target test -t glancebox:test . && docker run --rm --cap-drop ALL --security-opt no-new-privileges glancebox:test pytest -q -m browser` (aus der Repo-Wurzel).
- **Firmware, nativ** (läuft auf dem Mac): `cd firmware && pio test -e native`. Nach jeder Firmware-Task grün.
- **Firmware, `ultra`-Build:** läuft nicht auf dem Mac. Gebaut wird auf dem Heimserver (ssh-Alias `server`) im Wegwerf-Container. Dieser Weg schreibt nur nach `~/gb-build` und in die Volumes `gb-pio` und `gb-pio-build` und ist der vereinbarte Bauweg; aus der Repo-Wurzel:

  ```bash
  rsync -a --delete --exclude '.pio' VERSION tools firmware server:gb-build/
  ssh server 'docker run --rm -v ~/gb-build:/w -v gb-pio:/root/.platformio -v gb-pio-build:/w/firmware/.pio -w /w/firmware python:3.12 sh -c "pip install -q platformio==6.2.0 && pio run -e ultra -e spike -e ultra-crashtest && python3 ../tools/check_fw_size.py .pio/build/ultra/firmware.bin size-limit.txt && cp .pio/build/ultra/firmware.bin /w/glancebox-ultra-dev.bin"'
  scp server:gb-build/glancebox-ultra-dev.bin .superpowers/dev/glancebox-ultra-energy.bin
  ```

  Erwartet: drei Umgebungen bauen ohne neue Warnungen, die Größenprüfung besteht. Kann der Build nicht laufen, im Bericht als **nicht geprüft** nennen, nicht raten.
- `firmware/size-limit.txt` (1 011 696 Byte) nicht anheben; reicht der Platz nicht, anhalten und berichten. Flash-Layout, `platformio.ini` und das Format der gespeicherten Einstellungen bleiben unverändert.
- **Nur nach ausdrücklichem Okay des Nutzers in dem Moment:** Flashen des Displays (OTA über `/update` der Geräteseite mit dem Update-Passwort), jede andere Änderung auf dem Heimserver (außer dem Bauweg oben), jede Änderung an der HA-Test-VM. Solche Schritte tragen unten die Marke **[Okay nötig]**. Ohne Okay: anhalten und fragen.
- Keine persönlichen Daten in Code, Tests, Doku, Commits und Berichten: keine echten LAN-Adressen, Tokens, E-Mail-Adressen. Platzhalter: `http://192.168.x.x:8090`, `http://homeassistant.lan:8123`, `sensor.grid_power`; im Plan heißt es „das Gerät“ und „der Heimserver“. Tokens und das Update-Passwort stehen nie auf einer Kommandozeile, in einem Log oder im Chat (`.env`, `curl --netrc-file`).
- Die Animation braucht keinen Heap: nur feste, statische Strukturen, keine `String`, kein `new`/`malloc`.
- Bestehende Seiten ändern sich nicht sichtbar und werden nicht langsamer; die Tests von `pages/homeassistant` bleiben **unverändert** grün.
- Zwei Sprachen: Seitentexte `de`/`en` mit gleicher Aussage; Doku in `docs/en` und `docs/de` mit gleicher Überschriftenfolge (`python3 tools/check_docs_parity.py`); Nutzersichtbares in `CHANGELOG.md` unter `## [Unreleased]`, auf Englisch.
- Doku, CHANGELOG und Berichte sagen nicht „Echtzeit“/„real-time“ und geben nichts als getestet aus, was nur gebaut wurde. Verhalten auf dem Gerät gilt bis zur Abnahme durch den Nutzer (Task 11) als **nicht geprüft**.
- Werte aus der Spec, wörtlich: Hintergrund `#0b0d12`, Spur `#232a38`, Netzbezug `#ffb020`, Einspeisung `#34d399`, PV `#ffd040`, Speicher `#2ec4b6`, Gas `#ff6b4a`, Wasser `#4da3ff`, Wallbox `#a78bfa`; Pfeilabstand 18 px, Strich 2 px, Spurlinie 3 px; Tick höchstens alle 40 ms; `X-Anim` höchstens 160 Zeichen, höchstens 4 Spuren, Tempo 1 bis 200; Antwortkopf höchstens 1024 Byte; JPEG höchstens 24 576 Byte bei Qualität 85.

### Entscheidungen dieses Plans (von der Spec dem Umsetzer überlassen)

- **Namen:** Server `glancebox/anim.py` (Format) und `glancebox/hass.py` (gemeinsamer HA-Code); Firmware `lib/core/anim.{h,cpp}`. Der Seitentyp übergibt die Beschreibung unter dem reservierten Schlüssel `_anim` im Ergebnis von `fetch`. Haken im Seitentyp: `DEFAULT_REFRESH` (Standard-`refresh`) und `SKIP_UNCHANGED` (gleiche Daten, kein neues Rendern). `SKIP_UNCHANGED` gilt **nur für `energy`**, weil Templates fremder Seiten von mehr als ihren Daten abhängen können (z. B. ein eingebundenes Bild).
- **Maße:** Kopfzeile 28 px hoch auf dem Seitenhintergrund (Titel links, Uhrzeit rechts, je 13 px). Zeilenmitte `41 + (2·i + 1) · 198 // (2·n)`: 1 Zeile 140; 2 Zeilen 90, 189; 3 Zeilen 74, 140, 206; 4 Zeilen 65, 115, 164, 214. Spur-Rechteck `x = 64`, `b = 85`, `h = 15`, `y = Mitte − 7`; die Spurlinie beginnt bei `y + (h − 3) // 2`. Pfeil: Winkel mit Spitze auf der Zeilenmitte, 5 px nach oben und unten (11 px hoch), 5 px tief. Der Wert steht zwischen x = 156 und x = 226.
- **Grenzen des Geräts:** `b` 16 bis 240, `h` 8 bis 32 (die Richtwerte der Spec).
- **Tempo:** 10 bis 80 px/s; `min` und `full` gelten bei Leistungs-Zeilen in W, bei Gas und Wasser in der Einheit des Sensors. Endgültige Zahlen stellt Task 11 mit dem Nutzer am Gerät ein.
- **Ausschneiden:** Teilrechtecke eines JPEG-Blocks werden zeilenweise aus dem Block-Bitmap geschoben (kein Zusatzpuffer); Pfeile am Rand schneidet `TFT_eSPI::setViewport` ab.
- **Messung:** `/status` bekommt `anim_tracks`, `anim_gaps_100`, `anim_gaps_250`, `anim_run_s` und `frame_errors`.
- **Schein-Sensoren:** eine Datei `tools/ha-sim/config/packages/energy.yaml` (Eingabe-Helfer plus Template-Sensoren), die sowohl `tools/ha-sim/` steuerbar macht als auch in die Test-VM kopiert wird.

## Review Focus

1. Sensor meldet Leistung in `kW` statt `W` (`"2.31"`, Einheit `kW`) oder als Text mit vielen Stellen (`"2310.000001"`): Wert wird als „2,3 kW“ gezeigt und das Tempo gegen `full` in W gerechnet, kein Absturz (Test in Task 4: `test_flow_power_in_kilowatts`).
2. Der Ladestand-Sensor (`soc`) fehlt oder ist `unavailable`, die Speicherleistung kommt: die Zeile läuft weiter, die Statuszeile zeigt nur „lädt“; die Seite wird deshalb nicht zur Fehlerseite (Test in Task 4: `test_soc_missing_or_unavailable_keeps_row`).
3. Wert pendelt um null (`"-0.04"`, `"-0.0"`): angezeigt wird „0“ ohne Minuszeichen, die Zeile ist grau und hat keine Spur in `X-Anim` (Test in Task 4: `test_flow_tiny_negative_is_zero`).
4. Der echte Server sendet den Kopfzeilennamen klein (`x-anim`) und der Wert kann Leerzeichen am Rand tragen oder genau 160 bzw. 161 Zeichen lang sein: klein geschrieben und mit Randleerzeichen gültig, 161 Zeichen ungültig (Test in Task 6: `test_http_head_x_anim_name_case_blanks_and_length`).
5. Nach dem Bildschirm „Update failed“ behält das Gerät seinen ETag, der Server antwortet 304 mit gültigem `X-Anim`: es laufen keine Pfeile über den Statusbildschirm (Test in Task 7: `test_anim_304_never_starts_tracks`).

---

### Task 1: Format `X-Anim` auf dem Server

**Files:**
- Create: `server/glancebox/anim.py`
- Test: `server/tests/test_anim.py`

**Interfaces:**
- Produces:

  ```python
  VERSION = 1
  SCREEN = 240
  MAX_TRACKS = 4
  MAX_VALUE_LEN = 160
  MIN_W, MAX_W = 16, 240
  MIN_H, MAX_H = 8, 32
  MIN_SPEED, MAX_SPEED = 1, 200
  LINE_THICKNESS = 3
  ARROW_SPACING = 18
  ARROW_HALF_HEIGHT = 5
  ARROW_STROKE = 2

  @dataclass(frozen=True)
  class Track:
      x: int; y: int; w: int; h: int
      direction: str      # "r" or "l" (screen direction)
      color: str          # "ffb020": 6 hex digits, no "#"
      speed: int          # px/s

  @dataclass(frozen=True)
  class Anim:
      background: str
      track_color: str
      tracks: tuple[Track, ...]

  def line_top(y: int, h: int) -> int        # y + (h - LINE_THICKNESS) // 2
  def encode(anim: Anim) -> str              # header value; ValueError names the broken limit
  ```

- [ ] **Step 1: Tests schreiben** (`server/tests/test_anim.py`)

```python
import dataclasses

import pytest

from glancebox.anim import Anim, Track, encode, line_top

T1 = Track(64, 67, 85, 15, "r", "ffb020", 48)
T2 = Track(64, 133, 85, 15, "l", "34d399", 22)
OK = Anim("0b0d12", "232a38", (T1, T2))


def test_encode_example():
    assert encode(OK) == "1;0b0d12;232a38;64,67,85,15,r,ffb020,48;64,133,85,15,l,34d399,22"


def test_line_top_centres_three_pixels():
    assert line_top(67, 15) == 73 and line_top(67, 14) == 72


def t(**kw):
    return dataclasses.replace(T1, **kw)


@pytest.mark.parametrize(("anim", "match"), [
    (Anim("0b0d12", "232a38", ()), "tracks"),
    (Anim("0b0d12", "232a38", tuple(t(y=10 + 40 * i) for i in range(5))), "tracks"),
    (Anim("0b0d1", "232a38", (T1,)), "color"),
    (Anim("0b0d12", "#232a38", (T1,)), "color"),
    (Anim("0b0d12", "232a38", (t(color="ffb02g"),)), "color"),
    (Anim("0b0d12", "232a38", (t(x=200),)), "screen"),          # 200 + 85 > 240
    (Anim("0b0d12", "232a38", (t(y=230),)), "screen"),
    (Anim("0b0d12", "232a38", (t(x=-1),)), "screen"),
    (Anim("0b0d12", "232a38", (t(w=15),)), "width"),
    (Anim("0b0d12", "232a38", (t(h=7),)), "height"),
    (Anim("0b0d12", "232a38", (t(h=33),)), "height"),
    (Anim("0b0d12", "232a38", (t(direction="x"),)), "direction"),
    (Anim("0b0d12", "232a38", (t(speed=0),)), "speed"),
    (Anim("0b0d12", "232a38", (t(speed=201),)), "speed"),
    (Anim("0b0d12", "232a38", (T1, t(y=75))), "overlap"),        # rows 75..89 meet 67..81
    (Anim("0b0d12", "232a38", (t(x=True),)), "integer"),
])
def test_encode_rejects(anim, match):
    with pytest.raises(ValueError, match=match):
        encode(anim)


def test_longest_valid_value_fits():
    tracks = tuple(Track(100, 10 + 40 * i, 140, 32, "l", "ffffff", 200) for i in range(4))
    assert len(encode(Anim("ffffff", "ffffff", tracks))) <= 160
```

- [ ] **Step 2: Fehlschlag prüfen.** Run (aus `server/`): `.venv/bin/pytest -q tests/test_anim.py` → FAIL (`ModuleNotFoundError: glancebox.anim`).
- [ ] **Step 3: `server/glancebox/anim.py` schreiben** nach dem Interfaces-Block. Zahlen müssen `int` sein (kein `bool`), Farben passen auf `[0-9a-fA-F]{6}` und werden klein ausgegeben; die Längenprüfung gegen `MAX_VALUE_LEN` steht am Ende von `encode`. Kopfkommentar: Grenzen müssen denen in `firmware/lib/core/anim.h` gleichen (Paritätstest folgt in Task 6).
- [ ] **Step 4: Tests bestehen.** Run: `.venv/bin/pytest -q tests/test_anim.py && .venv/bin/ruff check . ../pages` → alle PASS, ruff ohne Meldung.
- [ ] **Step 5: Commit** — `git add server/glancebox/anim.py server/tests/test_anim.py`, Nachricht `feat(server): X-Anim description format with the device limits`.

---

### Task 2: Worker, `Frame` und Kopfzeile

**Files:**
- Modify: `server/glancebox/frames.py` (`Frame`, `FrameStore.put`, `render_page`, `refresh_once`)
- Modify: `server/glancebox/pages.py` (`PageType`, `_load_script_page`, `validate_config`)
- Modify: `server/glancebox/app.py` (`jpeg_response`)
- Test: `server/tests/test_frames.py`, `server/tests/test_pages.py`, `server/tests/test_app.py`

**Interfaces:**
- Consumes: `glancebox.anim.Anim`, `glancebox.anim.encode` (Task 1).
- Produces:
  - `Frame(jpeg, etag, rendered_at, anim: str | None = None, data: dict | None = None)`; `anim` ist der fertige, geprüfte Kopfzeilenwert. Der ETag bleibt der Hash des JPEG allein.
  - `FrameStore.put(index, jpeg, now, anim: str | None = None, data: dict | None = None)`.
  - `frames.ANIM_KEY = "_anim"`; `async def fetch_page_data(page, ptype, cfg, now, inbox=None) -> dict` und `async def render_data(ptype, data, renderer) -> bytes`. `render_page(...)` behält Signatur und Rückgabe (`bytes`) und entfernt `_anim`, bevor es rendert.
  - `PageType(..., default_refresh: int | None = None, skip_unchanged: bool = False)`; aus `page.py` gelesen als `DEFAULT_REFRESH` (Ganzzahl ≥ 1, sonst `ConfigError`) und `SKIP_UNCHANGED` (bool, sonst `ConfigError`).
  - `/api/v1/frame`: Kopfzeile `X-Anim: <frame.anim>` an 200 **und** 304, wenn `frame.anim` gesetzt ist; sonst keine.

- [ ] **Step 1: Tests schreiben.** In `test_frames.py` bekommt `script_type` den Parameter `skip_unchanged=False` (an `PageType` durchgereicht). Neue Tests:

```python
ANIM = Anim("0b0d12", "232a38", (Track(64, 67, 85, 15, "r", "ffb020", 48),))
HEADER = "1;0b0d12;232a38;64,67,85,15,r,ffb020,48"


async def test_anim_from_fetch_reaches_the_frame_not_the_template(tmp_path):
    t = script_type(tmp_path, "a", lambda o, c: {"v": "x", "_anim": ANIM},
                    template="<p>{{ v }}{{ _anim is defined }}</p>")
    r, store = FakeRenderer(), FrameStore(1)
    await refresh_once(make_cfg(page(0, "a", 5)), {"a": t}, r, store, 0)
    assert store.get(0, 0).anim == HEADER
    assert r.html_calls == ["<p>xFalse</p>"]


async def test_invalid_anim_is_dropped_and_logged(tmp_path, caplog):
    bad = Anim("0b0d12", "232a38", (Track(64, 67, 85, 15, "r", "ffb020", 0),))
    t = script_type(tmp_path, "a", lambda o, c: {"v": "x", "_anim": bad})
    store = FrameStore(1)
    with caplog.at_level(logging.WARNING):
        await refresh_once(make_cfg(page(0, "a", 5)), {"a": t}, FakeRenderer(), store, 0)
    assert store.get(0, 0).anim is None and store.last_error(0) is None
    assert "X-Anim" in caplog.text and "speed" in caplog.text


async def test_unchanged_data_keeps_image_and_updates_anim(tmp_path):
    speeds = iter([48, 51, 51])
    values = iter(["x", "x", "y"])

    def fetch(o, c):
        tr = Track(64, 67, 85, 15, "r", "ffb020", next(speeds))
        return {"v": next(values), "_anim": Anim("0b0d12", "232a38", (tr,))}

    t = script_type(tmp_path, "a", fetch, skip_unchanged=True)
    cfg, r, store = make_cfg(page(0, "a", 5)), FakeRenderer(), FrameStore(1)
    await refresh_once(cfg, {"a": t}, r, store, 0)
    first = store.get(0, 0)
    await refresh_once(cfg, {"a": t}, r, store, 5)
    second = store.get(0, 5)
    assert len(r.html_calls) == 1 and second.etag == first.etag
    assert second.anim.endswith(",51") and second.rendered_at == 5   # stays fresh
    await refresh_once(cfg, {"a": t}, r, store, 10)
    assert len(r.html_calls) == 2 and store.get(0, 10).etag != first.etag


async def test_unchanged_data_still_renders_without_the_hook(tmp_path):
    t = script_type(tmp_path, "a", lambda o, c: {"v": "x"})
    cfg, r, store = make_cfg(page(0, "a", 5)), FakeRenderer(), FrameStore(1)
    await refresh_once(cfg, {"a": t}, r, store, 0)
    await refresh_once(cfg, {"a": t}, r, store, 5)
    assert len(r.html_calls) == 2
```

  In `test_pages.py` (Seitenordner in `tmp_path` wie in `test_missing_fetch_reports_dir`):
  - `test_default_refresh_applies_only_without_explicit_refresh`: `page.py` mit `DEFAULT_REFRESH = 5`, `MIN_REFRESH = 2`; ohne `refresh` → 5 (bei `duration` 30), mit `refresh: 60` → 60, mit `refresh: 1` → `ConfigError` mit „at least 2“.
  - `test_default_refresh_and_skip_unchanged_must_be_well_formed`: `DEFAULT_REFRESH = 0`, `= True`, `= "5"` und `SKIP_UNCHANGED = 1` ergeben je `ConfigError` mit dem Namen des Hakens.
  - `test_pages_without_the_hooks_behave_as_before`: `load_page_types([REAL])["clock"]` hat `default_refresh is None` und `skip_unchanged is False`.

  In `test_app.py`:

```python
ANIM = "1;0b0d12;232a38;64,67,85,15,r,ffb020,48"


def anim_store() -> FrameStore:
    store = filled_store()
    store.put(1, b"jpeg1", NOW - 1, anim=ANIM)
    return store


def test_x_anim_on_200_and_304_only_for_its_frame():
    client, _ = make_client(anim_store(), now=NOW)          # NOW % 60 == 40: page 1
    first = client.get("/api/v1/frame")
    assert first.status_code == 200 and first.headers["x-anim"] == ANIM
    again = client.get("/api/v1/frame", headers={"If-None-Match": first.headers["etag"]})
    assert again.status_code == 304 and again.headers["x-anim"] == ANIM
    other, _ = make_client(anim_store(), now=NOW + 30)      # page 0 has no description
    assert "x-anim" not in other.get("/api/v1/frame").headers


def test_no_x_anim_on_the_error_frame():
    client, _ = make_client(FrameStore(2))
    assert "x-anim" not in client.get("/api/v1/frame").headers


def test_anim_does_not_change_the_etag():
    store = FrameStore(2)
    store.put(0, b"jpeg0", NOW)
    plain = store.get(0, NOW).etag
    store.put(0, b"jpeg0", NOW, anim=ANIM)
    assert store.get(0, NOW).etag == plain


def test_response_head_stays_below_the_device_limit():
    store = filled_store()
    store.put(1, b"jpeg1", NOW - 1, anim="1" * 160)         # as long as the limit allows
    r = make_client(store)[0].get("/api/v1/frame")
    head = 17 + sum(len(k) + len(v) + 4 for k, v in r.headers.items()) + 2
    assert head + 60 <= 1024                                # 60: date and server from uvicorn
```

- [ ] **Step 2: Fehlschlag prüfen.** Run: `.venv/bin/pytest -q tests/test_frames.py tests/test_pages.py tests/test_app.py` → die neuen Tests scheitern (`TypeError: unexpected keyword`, `KeyError: 'x-anim'`).
- [ ] **Step 3: `pages.py`.** Haken laden und in `validate_config` anwenden: ohne ausdrückliches `refresh` gilt `default_refresh`, falls gesetzt; danach die bisherige `min_refresh`-Prüfung.
- [ ] **Step 4: `frames.py`.** `render_page` in `fetch_page_data` + `render_data` teilen. `refresh_once` für Skript-Seiten: Daten holen, `_anim` herausnehmen, mit `anim.encode` zum Kopfzeilenwert machen (`ValueError` → `log.warning("%s: X-Anim dropped: %s", label, e)`, Wert `None`, kein Seitenfehler; ein Wert, der kein `Anim` ist, zählt genauso). Hat der Typ `skip_unchanged`, steht ein Bild im Speicher und sind die Daten (ohne `_anim`) gleich den gespeicherten: `store.put(index, altes_jpeg, now, anim=wert, data=daten)` ohne Rendern. Sonst rendern und mit `anim` und `data` ablegen. `url`-Seiten laufen wie bisher.
- [ ] **Step 5: `app.py`.** In `jpeg_response` `X-Anim` in `headers` aufnehmen, bevor zwischen 304 und 200 verzweigt wird.
- [ ] **Step 6: Alles grün.** Run: `.venv/bin/pytest -q -m "not browser" && .venv/bin/ruff check . ../pages` → PASS.
- [ ] **Step 7: Commit** — `feat(server): carry an animation description per frame and send it as X-Anim`.

---

### Task 3: Gemeinsamer Home-Assistant-Code

**Files:**
- Create: `server/glancebox/hass.py`
- Modify: `server/glancebox/render.py` (neue Funktion `text_width`)
- Modify: `pages/homeassistant/page.py` (benutzt die gemeinsamen Funktionen)
- Test: `server/tests/test_hass.py`; `pages/homeassistant/test_homeassistant.py` bleibt **unverändert**

**Interfaces:**
- Produces (`glancebox.hass`):

  ```python
  LANGS = ("de", "en")
  MINUS = "−"
  NA = {"de": "n. v.", "en": "n/a"}
  MISSING = {"de": "fehlt", "en": "missing"}
  def entity_id(value: object) -> str                 # ValueError, message as today
  def validate_connection(options: dict) -> None      # url, token, lang, title; messages as today
  def state_url(base_url: str, entity: str) -> str    # "<base without trailing />/api/states/<entity>"
  def get_state(url: str, token: str, timeout: float) -> dict   # via glancebox.http.get_json; TypeError if not a dict
  def status_of(exc: Exception) -> int | None
  def log_failure(page: str, url: str, exc: Exception) -> None  # "<page>: <redacted url>: ..." without the token
  def number(text: str) -> float | None               # finite float or None
  def format_number(number: float, unit: str | None, decimals: int | None, lang: str) -> tuple[str, str | None]
  ```

- Produces (`glancebox.render`): `text_width(value: str, unit: str | None, sizes: tuple[int, int, int]) -> float` (Breite in px in DejaVu Sans Bold; `sizes` = Wert-px, Einheit-px, Abstand-px), samt dem zwischengespeicherten Font.

- [ ] **Step 1: Ausgangslage festhalten.** Run: `.venv/bin/pytest -q ../pages/homeassistant -m "not browser"` → PASS; Zahl der Tests notieren.
- [ ] **Step 2: Tests schreiben** (`server/tests/test_hass.py`): `format_number(2310, "W", None, "de") == ("2,3", "kW")`, `(-1100, "W", None, "en") == ("−1.1", "kW")`, `(21.0, "°C", None, "de") == ("21", "°C")`; `number("nan") is None`, `number("1e400") is None`, `number("3200.000001") == 3200.000001`; `state_url("http://ha.lan:8123/", "sensor.a")` endet auf `:8123/api/states/sensor.a`; `get_state` reicht `Authorization: Bearer <token>` und den Timeout an ein gepatchtes `glancebox.http.get_json` und wirft `TypeError` bei einer Liste; `validate_connection` lehnt fehlende `url`, `ftp://`, leeren Token, Token mit Leerzeichen, `lang: fr` und `title: 3` ab; `log_failure("energy", url, requests.exceptions.InvalidHeader("Bearer t0ken"))` schreibt weder `t0ken` noch `Bearer` ins Log.
- [ ] **Step 3: Fehlschlag prüfen.** Run: `.venv/bin/pytest -q tests/test_hass.py` → FAIL (Modul fehlt).
- [ ] **Step 4: Code verschieben.** Die Körper aus `pages/homeassistant/page.py` nach `hass.py` und `render.py` verschieben, nicht neu schreiben. `get_state` ruft `http.get_json` über das Modul auf (`from . import http`), damit die Tests es weiter patchen können. In `page.py` bleiben das Zeitbudget (die Tests patchen `mod.time`), `format_state`, `size_class`, `_BOXES` und die Namen, die die Tests benutzen (`Cell`, `Entry`, `entries`, `default_layout`, `format_state`, `size_class`, `text_width`).
- [ ] **Step 5: Unverändert grün.** Run: `.venv/bin/pytest -q -m "not browser" && .venv/bin/pytest -q ../pages/homeassistant -m browser && .venv/bin/ruff check . ../pages` → PASS, gleiche Testzahl wie in Step 1; `git diff --stat pages/homeassistant/test_homeassistant.py` ist leer.
- [ ] **Step 6: Commit** — `refactor(server): share the Home Assistant access and number format between pages`.

---

### Task 4: Seite `energy`: Prüfung, Pfeilregel, Daten

**Files:**
- Create: `pages/energy/page.py`, `pages/energy/test_energy.py`
- Create: `pages/energy/template.html` (in dieser Task nur ein Platzhalter `{% extends "base.html" %}`; Task 5 füllt ihn)
- Modify: `server/glancebox/addon.py` (`ha_defaults`)
- Test: `pages/energy/test_energy.py`, `server/tests/test_addon.py`

**Interfaces:**
- Consumes: `glancebox.hass` (Task 3), `glancebox.anim.Anim`/`Track`/`line_top` (Task 1), `glancebox.render.text_width`.
- Produces (`pages/energy/page.py`):

  ```python
  MIN_REFRESH = 2
  DEFAULT_REFRESH = 5
  SKIP_UNCHANGED = True
  KINDS = ("grid", "pv", "battery", "gas", "water", "wallbox")
  POWER_KINDS = ("grid", "pv", "battery", "wallbox")   # compared in W
  TWO_WAY = ("grid", "battery")                        # others: wrong sign counts as 0
  FULL = {"grid": 5000, "pv": 5000, "battery": 3000, "wallbox": 11000, "gas": 2, "water": 15}
  SPEED_MIN, SPEED_MAX = 10, 80
  BG, TRACK, INACTIVE = "#0b0d12", "#232a38", "#6b7280"
  COLOR = {"import": "#ffb020", "export": "#34d399", "pv": "#ffd040", "battery": "#2ec4b6",
           "gas": "#ff6b4a", "water": "#4da3ff", "wallbox": "#a78bfa"}
  TRACK_X, TRACK_W, TRACK_H = 64, 85, 15
  VALUE_LEFT, VALUE_RIGHT = 156, 226
  DEFAULT_TITLE = {"de": "Energie", "en": "Energy"}

  class RowConfig(NamedTuple):
      kind: str; entity: str; soc: str | None; invert: bool; full: float; min: float
  def rows(options: dict) -> list[RowConfig]
  def validate(options: dict) -> None

  class Box(NamedTuple):
      cy: int; x: int; y: int; w: int; h: int; line_y: int
  def geometry(n: int) -> list[Box]

  class Flow(NamedTuple):
      value: str; unit: str | None; active: bool
      direction: str | None        # "r" (away from the icon), "l" (towards it), None when inactive
      color: str; status: str; speed: int
  def flow(row: RowConfig, state: dict | None, soc: dict | None, lang: str) -> Flow

  def build(options: dict, states: dict[str, dict | None], lang: str, clock: str) -> dict
  def fetch(options: dict, ctx) -> dict
  ```

  `states` bildet Entitäts-ID auf die Antwort von `/api/states/<id>` ab, `None` für 404. `build` liefert die Vorlagendaten `title`, `clock`, `lang`, `state` (`ok`), `message`, `sub`, `bg`, `track`, `rows` (je Zeile `kind`, `cy`, `x`, `y`, `w`, `h`, `line_y`, `value`, `unit`, `size`, `status`, `color`, `active`) und, wenn `animate` nicht `False` ist und mindestens eine Zeile aktiv ist, `_anim` (`Anim` mit je einer `Track` pro aktiver Zeile, in Zeilenreihenfolge, Farben ohne `#`). `fetch` sammelt die Zustände und ruft `build`; bei Fehlern liefert es `state` `token` oder `error` mit `message`/`sub` wie `homeassistant`, mit `rows == []` und ohne `_anim`.

- Texte (exakt): Statuszeile de/en: `Bezug`/`Import`, `Einspeisung`/`Export`, `Erzeugung`/`Producing`, `lädt`/`charging`, `entlädt`/`discharging`, `Verbrauch`/`Usage`; mit Ladestand `lädt · 64 %` / `charging · 64 %`; Speicher bei 0 nur `64 %`; sonst bei 0 leer. Fehlertexte wie `homeassistant` (`Keine Verbindung zu Home Assistant`/`Cannot reach Home Assistant`, `Stand`/`As of`, `Token abgelehnt`/`Token rejected`, `Long-Lived Access Token prüfen`/`Check the long-lived access token`).

- Regeln von `flow` (Spec „Pfeilregel“ und „Wert, Tempo, Vorzeichen“), in dieser Reihenfolge: `state is None` → `MISSING`, inaktiv. `unavailable`/`unknown`/keine endliche Zahl → `NA`, inaktiv. Zahl `v`; bei `POWER_KINDS` mit Einheit `kW` zum Vergleich `v · 1000`. `invert` dreht das Vorzeichen. Typ nicht in `TWO_WAY` und `v < 0` → `v = 0`. `abs(v) < min` → `v = 0`. Anzeige: `hass.format_number(abs(Wert in der Einheit des Sensors), Einheit, None, lang)`. **Aktiv** genau dann, wenn der angezeigte Text eine Ziffer ungleich 0 enthält. Richtung und Farbe: `grid` > 0 → `r`, `import`; `grid` < 0 → `l`, `export`; `pv`, `gas`, `water` → `r`; `battery` > 0 (lädt) → `l`, < 0 (entlädt) → `r`; `wallbox` → `l`. Tempo: `round(SPEED_MIN + (SPEED_MAX − SPEED_MIN) · min(1, abs(v) / full))`, 0 wenn inaktiv. Inaktiv: Farbe `INACTIVE`.

- [ ] **Step 1: Vorzeichen des Speichers klären (Spec, Offener Punkt 7).** In der Home-Assistant-Doku zum Energie-Dashboard nachlesen, welches Vorzeichen ein Leistungssensor des Speichers beim Laden hat. Sagt sie „positiv = entlädt“, gilt das als Standard: dann in den Regeln oben, in den Tests unten und in der Doku (Task 10) `battery` > 0 → entlädt (`r`) setzen. Die Quelle und das Ergebnis kommen in den Bericht und als Kommentar über `TWO_WAY`.

- [ ] **Step 2: Tests schreiben** (`pages/energy/test_energy.py`; Fixtures `energy`/`mod`/`serve`/`ctx`/`ent` nach dem Muster von `pages/homeassistant/test_homeassistant.py`, mit `OPTIONS = {"url": "http://homeassistant.lan:8123", "token": "t0ken", "rows": [{"type": "grid", "entity": "sensor.grid_power"}]}`):

```python
def row(mod, kind="grid", **kw):
    base = {"type": kind, "entity": "sensor.x", **kw}
    return mod.rows({"rows": [base]})[0]


def st(state, unit="W"):
    return {"entity_id": "sensor.x", "state": state,
            "attributes": {"unit_of_measurement": unit}}


@pytest.mark.parametrize(("kind", "state", "kw", "expect"), [
    ("grid", "2310", {}, ("2,3", "kW", True, "r", "#ffb020", "Bezug", 42)),
    ("grid", "-1100", {}, ("1,1", "kW", True, "l", "#34d399", "Einspeisung", 25)),
    ("grid", "1100", {"invert": True}, ("1,1", "kW", True, "l", "#34d399", "Einspeisung", 25)),
    ("grid", "15", {"min": 20}, ("0", "W", False, None, "#6b7280", "", 0)),
    ("grid", "9000", {"full": 3000}, ("9", "kW", True, "r", "#ffb020", "Bezug", 80)),
    ("pv", "3200", {}, ("3,2", "kW", True, "r", "#ffd040", "Erzeugung", 55)),
    ("pv", "-50", {}, ("0", "W", False, None, "#6b7280", "", 0)),
    ("wallbox", "11000", {}, ("11", "kW", True, "l", "#a78bfa", "lädt", 80)),
    ("wallbox", "-300", {}, ("0", "W", False, None, "#6b7280", "", 0)),
])
def test_flow_rule_de(mod, kind, state, kw, expect):
    assert mod.flow(row(mod, kind, **kw), st(state), None, "de") == mod.Flow(*expect)


def test_flow_gas_and_water_use_the_sensor_unit(mod):
    gas = mod.flow(row(mod, "gas"), st("1.0", "m³/h"), None, "en")
    assert gas == mod.Flow("1", "m³/h", True, "r", "#ff6b4a", "Usage", 45)
    water = mod.flow(row(mod, "water"), st("3", "L/min"), None, "de")
    assert (water.value, water.direction, water.status, water.speed) == ("3", "r", "Verbrauch", 24)


def test_flow_battery_with_level(mod):
    soc = st("64.4", "%")
    b = row(mod, "battery", soc="sensor.level")
    assert mod.flow(b, st("1500"), soc, "de")[3:] == ("l", "#2ec4b6", "lädt · 64 %", 45)
    assert mod.flow(b, st("-1500"), soc, "en")[3:] == ("r", "#2ec4b6", "discharging · 64 %", 45)
    idle = mod.flow(b, st("0"), soc, "de")
    assert (idle.active, idle.status, idle.color) == (False, "64 %", "#6b7280")


def test_flow_power_in_kilowatts(mod):                      # Review Focus 1
    f = mod.flow(row(mod, "grid"), st("2.31", "kW"), None, "de")
    assert (f.value, f.unit, f.speed) == ("2,3", "kW", 42)
    assert mod.flow(row(mod, "grid"), st("2310.000001"), None, "de").value == "2,3"


def test_flow_tiny_negative_is_zero(mod):                   # Review Focus 3
    for state in ("-0.04", "-0.0", "0.04"):
        f = mod.flow(row(mod, "grid"), st(state), None, "de")
        assert (f.value, f.active, f.direction, f.speed) == ("0", False, None, 0)


@pytest.mark.parametrize(("lang", "na", "missing"), [("de", "n. v.", "fehlt"),
                                                     ("en", "n/a", "missing")])
def test_flow_unavailable_and_missing(mod, lang, na, missing):
    for state in ("unavailable", "unknown", "nan", "text"):
        f = mod.flow(row(mod), st(state), None, lang)
        assert (f.value, f.unit, f.active) == (na, None, False)
    assert mod.flow(row(mod), None, None, lang).value == missing


def test_geometry(mod):
    assert [b.cy for b in mod.geometry(1)] == [140]
    assert [b.cy for b in mod.geometry(2)] == [90, 189]
    assert [b.cy for b in mod.geometry(4)] == [65, 115, 164, 214]
    assert mod.geometry(3) == [mod.Box(74, 64, 67, 85, 15, 73), mod.Box(140, 64, 133, 85, 15, 139),
                               mod.Box(206, 64, 199, 85, 15, 205)]
```

  Dazu, mit `serve` (HA gemockt):
  - `test_validate_ok` (Minimal, und voll: alle sechs Typen auf zwei Seiten verteilt, `soc`, `invert`, `full: 2.5`, `min: 0`, `animate: False`, zweimal `pv`).
  - `test_validate_rejects` (parametrisiert, `pytest.raises(ValueError, match=…)`): ohne `rows`; `rows: []`; 5 Zeilen („at most 4“); Zeile kein Mapping; `type: heatpump`; ohne `entity`; `entity: "Sensor.A"`; `soc` bei `grid`; `soc: "x"`; `invert: "yes"`; `full: 0`; `full: True`; `min: -1`; unbekannter Schlüssel `inverted` (Meldung nennt `inverted`); `animate: "false"`; dazu `url`/`token`/`lang`/`title` wie bei `homeassistant`.
  - `test_refresh_default_and_floor` (über `validate_config`): ohne `refresh` → 5, `refresh: 1` → `ConfigError`.
  - `test_build_ok_three_rows`: Netz −1100 W, PV 3200 W, Speicher 0 mit Ladestand 64 → `state == "ok"`, drei Zeilen mit den Maßen aus `geometry(3)`, `_anim == Anim("0b0d12", "232a38", (Track(64, 67, 85, 15, "l", "34d399", 25), Track(64, 133, 85, 15, "r", "ffd040", 55)))`, und `glancebox.anim.encode(data["_anim"])` wirft nicht.
  - `test_no_anim_when_nothing_flows_or_animate_false`: alle Werte 0 → kein Schlüssel `_anim`; aktive Zeilen mit `animate: False` → kein Schlüssel `_anim`, übrige Daten gleich.
  - `test_same_states_give_equal_data` (Voraussetzung für `SKIP_UNCHANGED`): zweimal `build` mit 2310 W und 2330 W liefert ohne `_anim` gleiche Daten, aber `_anim` mit Tempo 42 und 43.
  - `test_soc_missing_or_unavailable_keeps_row` (Review Focus 2): `soc` antwortet 404 bzw. `unavailable` → `state == "ok"`, Statuszeile `lädt`, Spur vorhanden.
  - `test_missing_entity_keeps_others`: 404 für eine Zeile → dort `fehlt`, inaktiv; die anderen aktiv.
  - `test_token_rejected` (401, 403) und `test_unreachable` (`ConnectionError`, `Timeout`, 500, Liste statt Objekt): `state` `token` bzw. `error`, `rows == []`, kein `_anim`, Texte de und en.
  - `test_calls_have_short_timeouts` und `test_exhausted_budget_is_error` nach dem Muster von `homeassistant` (4 Zeilen mit `soc` = bis zu 5 Abrufe, je ≤ 5 s, Budget 15 s).
  - `test_token_never_logged` (`ConnectionError`, 401, `InvalidHeader`).
  - `test_value_size_keeps_the_value_out_of_the_track`: für `("2,3", "kW")`, `("11", "kW")`, `("n. v.", None)`, `("1234,5", "m³/h")` gilt `text_width(value, unit, sizes[size]) <= VALUE_RIGHT − VALUE_LEFT − 1` oder `size == "s"`.

  In `server/tests/test_addon.py`: `test_ha_defaults_fill_energy_like_homeassistant`: eine `energy`-Seite ohne `url`/`token` bekommt `http://supervisor/core` und den Supervisor-Token; eine mit eigenen Werten behält sie.

- [ ] **Step 3: Fehlschlag prüfen.** Run: `.venv/bin/pytest -q ../pages/energy tests/test_addon.py -m "not browser"` → FAIL (Seitentyp fehlt, `KeyError: 'url'`).
- [ ] **Step 4: `page.py` schreiben** nach Interfaces und Regeln. Größenklassen des Werts `{"l": (24, 13, 3), "m": (19, 12, 3), "s": (15, 11, 2)}` (Wert-px, Einheit-px, Abstand), gewählt wie `size_class` in `homeassistant`. `fetch` fragt je Zeile `entity` und, falls gesetzt, `soc` ab (ein 404 oder ein `unavailable` des `soc` ist kein Fehler). Unbekannte Schlüssel in einer Zeile sind ein `ValueError`, der den Schlüssel nennt.
- [ ] **Step 5: `addon.py`.** In `page_defaults` gilt der Zweig für `homeassistant` auch für `energy`.
- [ ] **Step 6: Alles grün.** Run: `.venv/bin/pytest -q -m "not browser" && .venv/bin/ruff check . ../pages` → PASS.
- [ ] **Step 7: Commit** — `feat(pages): energy page data, arrow rule and animation description`.

---

### Task 5: Seite `energy`: Template und Bildprüfung

**Files:**
- Modify: `pages/energy/template.html`
- Create: `pages/energy/README.md` (Entwicklerhinweise, Englisch, nach dem Muster von `pages/homeassistant/README.md`)
- Test: `pages/energy/test_energy.py` (Browser-Tests)

**Interfaces:**
- Consumes: die Vorlagendaten aus `build`/`fetch` (Task 4), `glancebox.frames.render_page`, `glancebox.render.Renderer`.
- Produces: das Standbild. Zusage für die Firmware: Im Spur-Rechteck (`x`, `y`, `w`, `h`) liegen nur `bg` und, in den Zeilen `line_y` bis `line_y + 2`, über die ganze Breite `track`.

- [ ] **Step 1: Browser-Tests schreiben** (alle `@pytest.mark.browser`, HA über `serve` gemockt, Rendern über `render_page` mit echtem `Renderer`):

```python
def _near(px, hex_color, tol=10):
    want = tuple(int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
    return all(abs(a - b) <= tol for a, b in zip(px, want, strict=True))


def assert_track_area_flat(img, box, bg, track, margin=2):
    px = img.convert("RGB").load()
    for y in range(box.y - margin, box.y + box.h + margin):
        for x in range(box.x - margin, box.x + box.w + margin):
            in_line = box.line_y <= y < box.line_y + 3 and box.x <= x < box.x + box.w
            assert _near(px[x, y], track if in_line else bg), (x, y, px[x, y])
```

  - `test_track_area_is_flat_ground_and_line`: für 1, 2, 3 und 4 aktive Zeilen (alle sechs Typen kommen vor) gilt `assert_track_area_flat` für jede Zeile; das Bild ist 240×240.
  - `test_inactive_row_keeps_the_same_ground`: Wert 0 und `unavailable` → gleiche Prüfung (leere Spur bleibt gezeichnet), und im Zeilenstreifen gibt es keinen Pixel in einer der `COLOR`-Farben.
  - `test_long_value_never_enters_the_track`: Gas `"1234.5"` mit Einheit `m³/h` und Titel mit 60 Zeichen → `assert_track_area_flat` gilt weiter.
  - `test_fits_at_quality_85`: 4 aktive Zeilen, langer Titel → `len(jpeg) <= 24576` und `Image.open(io.BytesIO(jpeg)).quantization` gleicht dem eines mit `quality=85, progressive=False, optimize=True` gespeicherten 240×240-Bilds.
  - `test_same_data_renders_the_same_bytes` (Spec, Offener Punkt 1): zweimal `render_data` mit gleichen Daten; sind die Bytes ungleich, den Test mit `pytest.xfail("renderer is not byte-stable; SKIP_UNCHANGED carries the 304")` enden lassen und das Ergebnis berichten.
  - `test_error_and_token_states_render`: Hinweis in Orange, kein Pixel in einer `COLOR`-Farbe außer Orange.

- [ ] **Step 2: Fehlschlag prüfen.** Run: `.venv/bin/pytest -q ../pages/energy -m browser` → FAIL (Template ist leer).
- [ ] **Step 3: `template.html` schreiben.** `{% extends "base.html" %}`; `html,body{background:{{ bg }}}`. Kopfzeile 28 px hoch, Titel (13 px, fett, gekürzt mit `…`) links ab x = 8, Uhrzeit (13 px) rechts bis x = 232, ohne Balken. Je Zeile, alles `position:absolute` aus den Zahlen der Daten: Kreis mit Mittelpunkt (34, `cy`) und r = 22 (Rand in `color`, Symbol als eigenes Inline-SVG je Typ, selbst gezeichnet, keine fremden Symbole); Spurlinie `left:{{ x }}px; top:{{ line_y }}px; width:{{ w }}px; height:3px; background:{{ track }}` ohne Rundung, Schatten oder Verlauf; Wertkasten von x = 156 bis 226, rechtsbündig, `overflow:hidden; text-overflow:ellipsis; white-space:nowrap`, Wert fett in Weiß mit Größenklasse `l`/`m`/`s` (24/19/15 px), Einheit grau; darunter die Statuszeile (11 px, in `color`). Inaktive Zeile: Kreis, Symbol und Wert in `color` (= grau). Fehlerzustände: `ui.notice(message, sub, "warn")` unter der Kopfzeile.
- [ ] **Step 4: Tests bestehen.** Run: `.venv/bin/pytest -q ../pages/energy -m browser`. Scheitert die Flächenprüfung an Farbsäumen neben dem Wert, den Wertkasten auf x ≥ 160 legen (Blockraster des JPEG, `VALUE_LEFT` in `page.py` und der Test in Task 4 ziehen mit); **nicht** die Toleranz erhöhen. Danach die ganze Suite im Test-Image (Global Constraints) → PASS.
- [ ] **Step 5: Ansehen.** `python -m glancebox render` braucht ein HA; stattdessen mit `build` und `render_data` ein Bild ins Scratchpad der Sitzung schreiben (3 Zeilen: Einspeisung, PV, Speicher lädt 64 %) und dem Nutzer zeigen. Sein Urteil zum Aufbau (Kopfzeile, Symbole, Abstände) einholen, bevor Task 10 das Vorschaubild erzeugt; das Mockup des Prototyps liegt nicht im Repo.
- [ ] **Step 6: `pages/energy/README.md`** (Englisch): Beispiel-YAML, die Haken `DEFAULT_REFRESH`/`SKIP_UNCHANGED`/`_anim`, „eine Quelle für die Maße“ (`geometry`), die Zusage zum Spur-Rechteck und welcher Test sie hält, die Regeln von `flow`.
- [ ] **Step 7: Commit** — `feat(pages): energy page layout with flat track areas for the device arrows`.

---

### Task 6: Firmware: Parser für `X-Anim`

**Files:**
- Create: `firmware/lib/core/anim.h`, `firmware/lib/core/anim.cpp`
- Modify: `firmware/lib/core/http_head.h`, `firmware/lib/core/http_head.cpp`
- Create: `server/tests/test_anim_parity.py`
- Test: `firmware/test/test_core/test_main.cpp`

**Interfaces:**
- Produces (`anim.h`, Namensraum `gb`):

  ```cpp
  constexpr size_t kAnimMaxTracks = 4;
  constexpr size_t kAnimMaxValueLen = 160;
  constexpr int kAnimScreen = 240;
  constexpr int kAnimMinW = 16;
  constexpr int kAnimMaxW = 240;
  constexpr int kAnimMinH = 8;
  constexpr int kAnimMaxH = 32;
  constexpr int kAnimMinSpeed = 1;
  constexpr int kAnimMaxSpeed = 200;
  constexpr int kAnimLineThickness = 3;
  constexpr int kAnimArrowSpacing = 18;
  constexpr int kAnimArrowHalfHeight = 5;
  constexpr int kAnimArrowStroke = 2;

  struct AnimRect { int16_t x, y, w, h; };
  struct AnimTrack { AnimRect rect; bool left; uint16_t color; uint8_t speed; };  // color: RGB565
  struct AnimSpec {
    uint8_t count;          // 0: no (valid) description
    uint16_t background;    // RGB565
    uint16_t trackColor;    // RGB565
    AnimTrack tracks[kAnimMaxTracks];
  };
  uint16_t animRgb565(uint8_t r, uint8_t g, uint8_t b);
  // Parses "1;rrggbb;rrggbb;x,y,w,h,r|l,rrggbb,speed[;...]". Any broken limit rejects the whole
  // value: false and out->count == 0. No dynamic allocation.
  bool parseAnim(const char* value, size_t len, AnimSpec* out);
  bool animSameGeometry(const AnimSpec& a, const AnimSpec& b);  // count, rects in order, both base colors
  ```

- Produces (`http_head.h`): `HttpHead` bekommt `AnimSpec anim;` (`anim.count == 0`, wenn die Kopfzeile fehlt, ungültig ist oder doppelt vorkommt).

- [ ] **Step 1: Tests schreiben** (in `test_main.cpp`, alle mit `RUN_TEST` registriert):

```cpp
bool anim(const char* v, gb::AnimSpec* a) { return gb::parseAnim(v, strlen(v), a); }

void test_anim_parses_the_example() {
  gb::AnimSpec a;
  TEST_ASSERT_TRUE(anim("1;0b0d12;232a38;64,67,85,15,r,ffb020,48;64,133,85,15,l,34D399,22", &a));
  TEST_ASSERT_EQUAL_UINT8(2, a.count);
  TEST_ASSERT_EQUAL_HEX16(gb::animRgb565(0x0b, 0x0d, 0x12), a.background);
  TEST_ASSERT_EQUAL_HEX16(gb::animRgb565(0x23, 0x2a, 0x38), a.trackColor);
  TEST_ASSERT_EQUAL_INT16(64, a.tracks[0].rect.x);
  TEST_ASSERT_EQUAL_INT16(67, a.tracks[0].rect.y);
  TEST_ASSERT_EQUAL_INT16(85, a.tracks[0].rect.w);
  TEST_ASSERT_EQUAL_INT16(15, a.tracks[0].rect.h);
  TEST_ASSERT_FALSE(a.tracks[0].left);
  TEST_ASSERT_EQUAL_UINT8(48, a.tracks[0].speed);
  TEST_ASSERT_TRUE(a.tracks[1].left);
  TEST_ASSERT_EQUAL_HEX16(gb::animRgb565(0x34, 0xd3, 0x99), a.tracks[1].color);
}

void test_anim_rejects_every_broken_limit() {
  const char* bad[] = {
      "",                                                    // empty
      "2;0b0d12;232a38;64,67,85,15,r,ffb020,48",             // other version
      "1;0b0d12;232a38",                                     // no track
      "1;0b0d12;232a38;64,10,85,15,r,ffb020,48;64,50,85,15,r,ffb020,48;64,90,85,15,r,ffb020,48;"
      "64,130,85,15,r,ffb020,48;64,170,85,15,r,ffb020,48",   // five tracks
      "1;0b0d1;232a38;64,67,85,15,r,ffb020,48",              // 5 hex digits
      "1;0b0d12;232a38;64,67,85,15,r,ffb02g,48",             // not hex
      "1;0b0d12;232a38;200,67,85,15,r,ffb020,48",            // right edge beyond 240
      "1;0b0d12;232a38;64,230,85,15,r,ffb020,48",            // bottom edge beyond 240
      "1;0b0d12;232a38;64,67,15,15,r,ffb020,48",             // too narrow
      "1;0b0d12;232a38;64,67,85,7,r,ffb020,48",              // too low
      "1;0b0d12;232a38;64,67,85,33,r,ffb020,48",             // too high
      "1;0b0d12;232a38;64,67,85,15,x,ffb020,48",             // direction
      "1;0b0d12;232a38;64,67,85,15,r,ffb020,0",              // speed 0
      "1;0b0d12;232a38;64,67,85,15,r,ffb020,201",            // speed too high
      "1;0b0d12;232a38;64,67,85,15,r,ffb020,48;64,75,85,15,r,ffb020,48",  // overlap
      "1;0b0d12;232a38;64,67,85,15,r,ffb020,48;",            // trailing separator
      "1;0b0d12;232a38;64,67,85,15,r,ffb020",                // field missing
      "1;0b0d12;232a38;64,67,85,15,r,ffb020,48,1",           // field too many
      "1;0b0d12;232a38; 64,67,85,15,r,ffb020,48",            // blank inside
      "1;0b0d12;232a38;-4,67,85,15,r,ffb020,48",             // sign
      "1;0b0d12;232a38;64,67,85,15,r,ffb020,4800000000",     // digits overflow
  };
  for (const char* v : bad) {
    gb::AnimSpec a;
    a.count = 3;
    TEST_ASSERT_FALSE_MESSAGE(anim(v, &a), v);
    TEST_ASSERT_EQUAL_UINT8_MESSAGE(0, a.count, v);
  }
}

void test_http_head_carries_x_anim() {
  gb::HttpHead head;
  TEST_ASSERT_TRUE(parseHead("HTTP/1.1 304 Not Modified\r\nETag: \"a\"\r\n"
                             "X-Anim: 1;0b0d12;232a38;64,67,85,15,r,ffb020,48\r\n\r\n", &head));
  TEST_ASSERT_EQUAL_UINT8(1, head.anim.count);
  TEST_ASSERT_TRUE(parseHead("HTTP/1.1 200 OK\r\nContent-Length: 5\r\n\r\n", &head));
  TEST_ASSERT_EQUAL_UINT8(0, head.anim.count);   // absent: reset, nothing left over
  TEST_ASSERT_TRUE(parseHead("HTTP/1.1 200 OK\r\nX-Anim: 9;x\r\nContent-Length: 5\r\n\r\n", &head));
  TEST_ASSERT_EQUAL_UINT8(0, head.anim.count);   // invalid: the frame itself still counts
  TEST_ASSERT_EQUAL(5, head.contentLength);
}

void test_http_head_duplicate_x_anim_is_invalid() {
  gb::HttpHead head;
  TEST_ASSERT_TRUE(parseHead("HTTP/1.1 200 OK\r\n"
                             "X-Anim: 1;0b0d12;232a38;64,67,85,15,r,ffb020,48\r\n"
                             "X-Anim: 1;0b0d12;232a38;64,67,85,15,r,ffb020,48\r\n\r\n", &head));
  TEST_ASSERT_EQUAL_UINT8(0, head.anim.count);
}
```

  `test_http_head_x_anim_name_case_blanks_and_length` (Review Focus 4): Kopf mit `x-anim:` klein und zwei Leerzeichen vor und nach dem Wert → `count == 1`; der längste gültige Wert (vier Spuren `100,10,140,32,l,ffffff,200` mit `y` 10, 50, 90, 130; 127 Zeichen) → `count == 4`; ein Wert mit 161 Zeichen (derselbe, um weitere Spuren verlängert) → `count == 0`, und `parseAnim` liest dabei nie über `len` hinaus (Aufruf mit einem Puffer ohne NUL am Ende). Ein gültiger Wert erreicht die 160 Zeichen nie; die Grenze begrenzt die Arbeit des Parsers. `test_anim_same_geometry`: gleiche Rechtecke mit anderem Tempo, anderer Richtung und Farbe → gleich; anderes `y`, andere Spurzahl, anderer Hintergrund → ungleich.

  `server/tests/test_anim_parity.py` nach dem Muster von `test_frame_limit_parity.py`: liest `firmware/lib/core/anim.h` mit `kAnim(\w+)\s*=\s*(\d+)\s*;` und vergleicht `MaxTracks`, `MaxValueLen`, `Screen`, `MinW`, `MaxW`, `MinH`, `MaxH`, `MinSpeed`, `MaxSpeed`, `LineThickness`, `ArrowSpacing`, `ArrowHalfHeight`, `ArrowStroke` mit den Konstanten in `glancebox.anim`; jede der 13 muss gefunden werden.

- [ ] **Step 2: Fehlschlag prüfen.** Run: `cd firmware && pio test -e native` → Kompilierfehler (`anim.h` fehlt). Run (aus `server/`): `.venv/bin/pytest -q tests/test_anim_parity.py` → FAIL.
- [ ] **Step 3: `anim.h`/`anim.cpp` schreiben.** Zahlen: 1 bis 3 Dezimalziffern, kein Vorzeichen, keine führende Null außer bei `0` selbst. Erst in eine lokale `AnimSpec` parsen und nur bei Erfolg nach `*out` kopieren; bei Misserfolg `out->count = 0`. Länge über `kAnimMaxValueLen` sofort ablehnen.
- [ ] **Step 4: `parseHttpHead` erweitern.** Zu Beginn `out->anim.count = 0`; Zweig `x-anim`: beim ersten Vorkommen `parseAnim(v, vn, &out->anim)`, bei jedem weiteren `out->anim.count = 0` und so merken, dass es dabei bleibt. Ein ungültiges `X-Anim` macht den Kopf nicht ungültig.
- [ ] **Step 5: Tests bestehen.** Run: `cd firmware && pio test -e native` → alle PASS (bisherige plus neue). Run (aus `server/`): `.venv/bin/pytest -q tests/test_anim_parity.py` → PASS.
- [ ] **Step 6: Commit** — `feat(firmware): parse the X-Anim header into a fixed structure`.

---

### Task 7: Firmware: Position, Ausschneiden, Zustand

**Files:**
- Modify: `firmware/lib/core/anim.h`, `firmware/lib/core/anim.cpp`
- Test: `firmware/test/test_core/test_main.cpp`

**Interfaces:**
- Consumes: `AnimRect`, `AnimTrack`, `AnimSpec`, `animSameGeometry` (Task 6).
- Produces:

  ```cpp
  constexpr uint32_t kAnimFrameMs = 40;
  constexpr uint16_t kAnimPhaseMod = kAnimArrowSpacing * 1000;  // phase in 1/1000 px, 0..17999
  constexpr size_t kAnimClipMax = 16;

  // New phase after elapsedMs at speed px/s. Unsigned arithmetic only; elapsedMs above 1000
  // counts as 1000. left = true moves the arrows towards smaller x.
  uint16_t animAdvance(uint16_t phase, uint32_t elapsedMs, uint8_t speed, bool left);

  // block minus the holes: writes the parts still to draw to out, returns their number.
  // Parts do not overlap and together cover exactly block without the holes.
  size_t animClip(const AnimRect& block, const AnimRect* holes, size_t nHoles,
                  AnimRect* out, size_t cap);

  struct AnimStats {
    uint8_t tracks;        // running now
    uint32_t gapsOver100;  // gaps between two drawn frames > 100 ms while tracks ran
    uint32_t gapsOver250;  // ... > 250 ms
    uint32_t runS;         // seconds with running tracks since boot
  };

  class AnimState {
   public:
    // 200, before decoding: keeps running tracks whose rect is also in next (new speed,
    // direction and color at once) when both base colors are unchanged; stops all others.
    void onHead200(const AnimSpec& next);
    void onDecoded(uint32_t nowMs);   // frame complete: all tracks of that spec run
    void onDecodeFailed();            // partial frame: nothing runs
    // 304: only changes running tracks. False when tracks run and spec does not have their
    // geometry (or is empty): everything stopped, the caller must drop its ETag.
    bool onHead304(const AnimSpec& spec);
    void stopAll();                   // status screen
    // True when a frame is due: tracks run, visible, and >= kAnimFrameMs since the last one.
    // Advances the phases and counts the gaps. visible = false keeps the state, draws nothing.
    bool tick(uint32_t nowMs, bool visible);
    uint8_t count() const;
    const AnimTrack& track(uint8_t i) const;
    uint8_t offsetPx(uint8_t i) const;    // 0..17: x offset of the arrow pattern
    uint16_t background() const;
    uint16_t trackColor() const;
    AnimStats stats(uint32_t nowMs) const;
  };
  ```

- [ ] **Step 1: Tests schreiben** (alle registrieren). Positionsrechnung:

```cpp
void test_anim_advance_right_left_and_wrap() {
  TEST_ASSERT_EQUAL_UINT16(5000, gb::animAdvance(0, 100, 50, false));
  TEST_ASSERT_EQUAL_UINT16(13000, gb::animAdvance(0, 100, 50, true));      // leftward from 0
  TEST_ASSERT_EQUAL_UINT16(2000, gb::animAdvance(17000, 100, 30, false));  // wraps at 18000
  TEST_ASSERT_EQUAL_UINT16(0, gb::animAdvance(0, 0, 200, true));
  TEST_ASSERT_EQUAL_UINT16(gb::animAdvance(0, 1000, 200, false),
                           gb::animAdvance(0, 4000000000u, 200, false));   // capped, no overflow
  for (uint32_t ms = 0; ms < 2000; ms += 37) {
    TEST_ASSERT_TRUE(gb::animAdvance(17999, ms, 200, false) < gb::kAnimPhaseMod);
    TEST_ASSERT_TRUE(gb::animAdvance(0, ms, 200, true) < gb::kAnimPhaseMod);
  }
}
```

  Ausschneiden: `test_anim_clip_no_hole` (1 Teil = Block); `test_anim_clip_hole_covers_block` (0 Teile); `test_anim_clip_track_through_a_block` (Block 16×16 bei (64, 64), also Zeilen 64 bis 79; Loch (64, 67, 85, 15) → die Teile decken genau die Zeilen 64 bis 66 über die ganze Blockbreite, 48 Pixel; Block bei (48, 64) → dasselbe Loch lässt den ganzen Block stehen); `test_anim_clip_corner_holes` (vier Löcher an den vier Ecken eines 16×16-Blocks) mit einer Hilfsfunktion, die jede der 256 Zellen prüft: innerhalb eines Lochs von keinem Teil bedeckt, sonst von genau einem; Zahl der Teile ≤ `kAnimClipMax`; `test_anim_clip_hole_outside` (Loch berührt den Block nicht → 1 Teil).

  Zustand, je Zeile der Regeltabelle der Spec ein Test (Hilfen `spec1(speed, left, color)` = eine Spur (64, 67, 85, 15), `spec2()` = zwei Spuren, `specMoved()` = eine Spur mit `y = 133`):
  - `test_anim_new_track_starts_only_after_decode`: `onHead200(spec1)` → `count() == 0`; `onDecoded(1000)` → `count() == 1`.
  - `test_anim_same_rect_keeps_running_with_new_values`: läuft mit Tempo 48 nach rechts; `onHead200(spec1(22, left, andere Farbe))` → `count() == 1`, sofort Tempo 22, links, neue Farbe, `offsetPx` unverändert.
  - `test_anim_missing_track_stops_before_decode`: zwei laufen; `onHead200(spec1)` → `count() == 1` (nur die erste); nach `onDecoded` weiter 1.
  - `test_anim_200_without_description_stops_all`: `onHead200` mit `count == 0` → 0, auch nach `onDecoded`.
  - `test_anim_base_color_change_stops_all_until_decoded`: gleiches Rechteck, anderer Hintergrund → 0 bis `onDecoded`.
  - `test_anim_304_same_geometry_takes_values`: `onHead304(spec1(60, ...))` → `true`, Tempo 60.
  - `test_anim_304_other_geometry_or_missing_stops_and_asks_refetch`: `onHead304(specMoved())` → `false`, `count() == 0`; ebenso mit leerer Beschreibung.
  - `test_anim_304_never_starts_tracks` (Review Focus 5): läuft; `stopAll()`; `onHead304(spec1)` → `true` und `count() == 0`; ebenso direkt nach dem Start ohne laufende Spur.
  - `test_anim_decode_failure_stops_all`: läuft; `onHead200(spec1)`; `onDecodeFailed()` → 0.
  - `test_anim_tick_every_40_ms_and_wraparound`: `onDecoded(0xFFFFFFF0u)`; `tick(0xFFFFFFF0u + 39, true)` → `false`; `tick(0x00000018u, true)` (40 ms später, über den Überlauf) → `true`; bei Tempo 50 danach `offsetPx(0) == 2`.
  - `test_anim_speed_change_does_not_jump`: zehn Ticks im Abstand von 40 ms mit Tempo 50 (20 px, also `offsetPx == 2`), dann `onHead304` mit Tempo 100: `offsetPx` direkt danach unverändert; nach weiteren 40 ms um 4 weiter.
  - `test_anim_invisible_keeps_state_and_draws_nothing`: `tick(now, false)` → `false`, `count()` bleibt; danach `tick(now + 40, true)` → `true`; die dunkle Zeit zählt nicht als Lücke.
  - `test_anim_gap_counters`: Ticks im Abstand 40, 40, 120, 300, 40 ms → `gapsOver100 == 2`, `gapsOver250 == 1`; nach `stopAll()` und neuem Start zählt die Pause dazwischen nicht; `runS` wächst nur, solange Spuren laufen.

- [ ] **Step 2: Fehlschlag prüfen.** Run: `cd firmware && pio test -e native` → Kompilierfehler (`animAdvance`, `AnimState` fehlen).
- [ ] **Step 3: Schreiben.** `animAdvance`: `delta = (min(elapsedMs, 1000) · speed) mod kAnimPhaseMod`, rechts `(phase + delta) mod`, links `(phase + kAnimPhaseMod − delta) mod`; alles `uint32_t`, kein vorzeichenbehafteter Zwischenwert (Warnung aus dem Prototyp in der Spec). `animClip`: Liste beginnt mit dem Block; je Loch jedes Teil in bis zu vier Teile (oben, unten, links, rechts vom Schnitt) zerlegen. `AnimState` hält laufende Spuren, die vorgemerkte Beschreibung aus `onHead200`, Phasen und Zeitstempel in festen Feldern.
- [ ] **Step 4: Tests bestehen.** Run: `cd firmware && pio test -e native` → alle PASS.
- [ ] **Step 5: Commit** — `feat(firmware): arrow position, block clipping and track state rules for the animation`.

---

### Task 8: Firmware: zeichnen und verdrahten

**Files:**
- Modify: `firmware/src/display.h`, `firmware/src/display.cpp`
- Modify: `firmware/src/frame_client.h`, `firmware/src/frame_client.cpp`
- Modify: `firmware/src/main.cpp`
- Modify: `firmware/src/web_ui.h`, `firmware/src/web_ui.cpp` (`StatusProvider`, `statusJson`)

**Interfaces:**
- Consumes: alles aus Task 6 und 7.
- Produces:
  - `display.h`: `JpegStreamResult displayJpegStream(Stream& stream, size_t len, uint32_t deadlineMs, const gb::AnimSpec& anim);` · `bool displayAnimNotModified(const gb::AnimSpec& anim);` (304; `false`: ETag verwerfen) · `void displayAnimTick();` · `gb::AnimStats displayAnimStats();`
  - `FrameResult` bekommt `bool refetch;` (304 passte nicht zu den laufenden Spuren).
  - `StatusProvider` bekommt `gb::AnimStats (*anim)() = nullptr;` und `uint32_t (*frameErrors)() = nullptr;`.
  - `/status`: zusätzliche Felder `"frame_errors"`, `"anim_tracks"`, `"anim_gaps_100"`, `"anim_gaps_250"`, `"anim_run_s"` (Zahlen; ohne Anbieter 0).

Diese Task hat keine nativen Tests (nur Verdrahtung); geprüft wird durch Bauen. Alles Verhalten auf dem Gerät bleibt bis Task 11 **nicht geprüft**.

- [ ] **Step 1: `display.cpp`: Zustand und Zeichnen.** Ein statisches `gb::AnimState`, dazu ein `bool`, ob die Hintergrundbeleuchtung an ist (in `displaySetBacklight` gesetzt: `pct > 0`). `displayAnimTick()`: `if (!anim.tick(millis(), backlightOn)) return;`, dann je Spur in einem `startWrite()`/`endWrite()`: Rechteck mit `background()` füllen, Spurlinie (`rect.y + (rect.h − kAnimLineThickness) / 2`, 3 px, `trackColor()`) füllen, `setViewport(rect.x, rect.y, rect.w, rect.h, false)`, Winkel im Abstand `kAnimArrowSpacing` ab `rect.x + offsetPx(i) − kAnimArrowSpacing` bis über den rechten Rand zeichnen, `resetViewport()`. Ein Winkel nach rechts mit Spitze (`tx`, `cy`), `cy = rect.y + rect.h / 2`: `drawLine(tx − 5, cy − 5, tx, cy)` und `drawLine(tx − 5, cy + 5, tx, cy)`, dasselbe um 1 px nach links versetzt (Strich 2 px); nach links gespiegelt. `display.cpp` darf weiter nur von `lib/core` und TFT_eSPI abhängen (die Umgebung `spike` baut es ohne den Rest von `src`).
- [ ] **Step 2: `display.cpp`: Regeln einhängen.** `displayStatus` ruft als Erstes `anim.stopAll()`. `displayJpegStream` ruft vor `jd_prepare` `anim.onHead200(spec)`, nach vollständigem Dekodieren `anim.onDecoded(millis())`, bei jedem anderen Ergebnis `anim.onDecodeFailed()`. `displayAnimNotModified` gibt `anim.onHead304(spec)` zurück.
- [ ] **Step 3: `display.cpp`: Tick und Ausschneiden beim Dekodieren.** `jpegInput` ruft im Warte-Zweig (`avail <= 0`) `displayAnimTick()` vor `delay(0)`; die Frist `deadlineMs` bleibt unverändert. `jpegOutput` ruft zuerst `displayAnimTick()`; läuft keine Spur oder schneidet kein laufendes Rechteck den Block, bleibt es bei dem einen `pushImage` wie heute. Sonst `gb::animClip` mit den Rechtecken der **laufenden** Spuren und je Teil zeilenweise aus dem Block-Bitmap schieben (`setAddrWindow` + `pushPixels` je Zeile, Byte-Reihenfolge wie bei `pushImage`).
- [ ] **Step 4: `frame_client.cpp`.** `readHead` ruft in jeder Runde der Schleife `displayAnimTick()` (vor `yield()`); die Frist bleibt. Nach `parseHttpHead`: bei 304 `r->refetch = !displayAnimNotModified(head.anim)`; bei 200 `displayJpegStream(client, r->len, kTimeoutMs, head.anim)`. Jeder andere Status und `kErrFrameLength` fassen die Spuren nicht an. `FrameResult` in `fetchFrame` mit `refetch = false` anlegen.
- [ ] **Step 5: `main.cpp`.** `loop()` ruft `displayAnimTick()` einmal je Durchlauf. In `pollFrame`: nach einem 304 mit `r.refetch` `etag[0] = '\0'`; ein Fehlschlag zählt `frameErrors` hoch (neuer Zähler neben `framesOk`). `StatusProvider`: `st.anim = []() { return displayAnimStats(); };` und `st.frameErrors`.
- [ ] **Step 6: `web_ui.cpp`.** `statusJson` um die fünf Felder ergänzen; den Puffer um höchstens 100 Byte vergrößern. `web_ui.h`: Kommentar der neuen Felder.
- [ ] **Step 7: Bauen.** Run: `cd firmware && pio test -e native` → PASS. Dann der Bauweg aus den Global Constraints → drei Umgebungen bauen, Größenprüfung besteht; die Zahl der Bytes und den Abstand zum Limit in den Bericht.
- [ ] **Step 8: Commit** — `feat(firmware): draw moving arrows on the tracks, also while a frame is fetched and decoded`. Im Rumpf: „Built for ultra, spike and ultra-crashtest; not yet run on a device.“

**Nur auf dem Gerät prüfbar (im Bericht wörtlich als nicht geprüft aufführen):** Pfeile laufen und sehen sauber aus; keine Kante um die Spur; Seitenwechsel ohne Reste; Offline-, OTA- und Portal-Bildschirm ohne Pfeile; Nachtmodus 0 % und zurück; Geräteseite und OTA während der Animation; `heap_free` gegenüber 0.6.3; Zeichenzeit mit 4 Spuren.

---

### Task 9: Schein-Sensoren und Probe gegen Home Assistant

**Files:**
- Create: `tools/ha-sim/config/packages/energy.yaml`
- Modify: `tools/ha-sim/README.md`

**Interfaces:**
- Produces: Entitäten `sensor.grid_power`, `sensor.pv_power`, `sensor.battery_power`, `sensor.wallbox_power` (W, `device_class: power`), `sensor.battery_level` (%), `sensor.gas_flow` (m³/h), `sensor.water_flow` (L/min), je gespeist von einem `input_number` (`input_number.sim_grid_power` −10000 bis 10000, Schritt 10; `sim_pv_power` 0 bis 10000; `sim_battery_power` −5000 bis 5000; `sim_wallbox_power` −500 bis 22000; `sim_battery_level` 0 bis 100; `sim_gas_flow` 0 bis 5, Schritt 0.1; `sim_water_flow` 0 bis 30, Schritt 0.5).

- [ ] **Step 1: `energy.yaml` schreiben.** Abschnitte `input_number:` und `template: - sensor:`; je Sensor `name` (z. B. `Grid power` → `sensor.grid_power`), `unique_id: sim_…`, `unit_of_measurement`, `state_class: measurement`, `state: "{{ states('input_number.sim_grid_power') | float(0) }}"`. Kopfkommentar: wozu, und dass Änderungen am Regler sofort wirken.
- [ ] **Step 2: Lokal prüfen.** Run (Repo-Wurzel): `docker run --rm -v "$PWD/tools/ha-sim/config:/config:ro" ghcr.io/home-assistant/home-assistant:stable python -m homeassistant --script check_config -c /config` → keine Zeile `Invalid config`. `git status` zeigt unter `tools/ha-sim/config/` nur die neue Datei.
- [ ] **Step 3: `tools/ha-sim/README.md`** um einen Abschnitt zu den steuerbaren Energiesensoren ergänzen (Liste der Entitäten, wo die Regler in HA stehen). **Commit** — `test: controllable fake energy sensors for the simulated Home Assistant`.
- [ ] **Step 4: [Okay nötig] In die HA-Test-VM bringen.** Erst fragen. Dann `energy.yaml` in den Konfigurationsordner der VM kopieren (als Paket, falls `packages` dort eingebunden ist, sonst die beiden Abschnitte in deren `configuration.yaml` einfügen; vorher eine Sicherung der geänderten Datei anlegen), Konfiguration prüfen lassen und Home Assistant neu laden. Der Nutzer legt in der VM einen langlebigen Token an und trägt `HA_URL` und `HA_TOKEN` in die `.env` der Repo-Wurzel ein (gitignored); der Token erscheint nie in Chat, Log oder Kommandozeile.
- [ ] **Step 5: Server vom Branch gegen das HA laufen lassen** (auf dem Mac, ändert nichts am Heimserver). Eine `config.yaml` im Scratchpad mit den zwei Seiten der Spec („Strom“: Netz, PV, Speicher mit `soc`; „Haus“: Gas, Wasser, Wallbox), `url: ${HA_URL}`, `token: ${HA_TOKEN}`. Run (aus `server/`, Variablen aus `.env` geladen): `.venv/bin/python -m glancebox serve --config <scratchpad>/config.yaml --host 127.0.0.1 --port 8095`. Prüfen:
  - `curl -s -D - -o /dev/null http://127.0.0.1:8095/api/v1/frame` zeigt `x-anim: 1;0b0d12;232a38;…` und `x-next-in` zwischen 2 und 5, solange eine Energieseite dran ist.
  - Regler in HA: Netz auf −1100 → innerhalb von etwa 10 s Richtung `l` und Farbe `34d399` in `x-anim`; Netz auf 0 → Spur verschwindet aus `x-anim`; alle Werte 0 → kein `x-anim`.
  - Wiederholter Abruf mit `If-None-Match` bei unveränderten Reglern → 304 mit `x-anim`; Wert leicht ändern (2310 → 2330) → 304 mit anderem Tempo.
  - `http://127.0.0.1:8095/` zeigt beide Seiten ohne Fehlertext.
  - HA der VM anhalten oder falsche `url`: Hinweis „Keine Verbindung zu Home Assistant“, kein `x-anim`.

  Ergebnis je Punkt in den Bericht. Der Weg über das Add-on (ohne Token) lässt sich vor einem Release-Image nicht in der VM prüfen; er ist nur durch `test_ha_defaults_fill_energy_like_homeassistant` gedeckt und gilt im Bericht als **nicht in einem echten Add-on geprüft**.

---

### Task 10: Doku, Vorschaubild, CHANGELOG

**Files:**
- Create: `docs/en/templates/energy.md`, `docs/de/templates/energy.md`
- Modify: `docs/en/templates/README.md`, `docs/de/templates/README.md`, `mkdocs.yml`
- Modify: `docs/en/configuration.md`, `docs/de/configuration.md`, `docs/en/home-assistant.md`, `docs/de/home-assistant.md`, `docs/en/writing-pages.md`, `docs/de/writing-pages.md`
- Modify: `README.md`, `README.de.md`, `config-example.yaml`, `ha-addon/DOCS.md`
- Modify: `tools/render_previews.py`; Create: `docs/img/templates/energy.png`
- Modify: `CHANGELOG.md`
- Test: `server/tests/test_render_previews.py` (neu)

**Interfaces:**
- Consumes: `build` aus `pages/energy/page.py`, `glancebox.anim` (Konstanten der Pfeilform).
- Produces: `tools/render_previews.py::paint_arrows(img: Image.Image, anim: Anim) -> None` (malt feste Pfeile nach der Beschreibung: Winkel wie in Task 8 Step 1, Spitzen bei `x + 9 + k·18`, auf das Rechteck beschnitten) und den Eintrag `SAMPLES["energy"]`.

- [ ] **Step 1: Test für `paint_arrows`** (`server/tests/test_render_previews.py`, ohne Browser; `tools/` wie in `test_check_fw_size.py` laden): auf ein 240×240-Bild in `#0b0d12` mit einer Spur (64, 67, 85, 15, `r`, `ffb020`) gemalt, gibt es im Rechteck Pixel in `#ffb020`, außerhalb keinen; für `l` liegt bei gleicher Spitze der linkeste gefärbte Pixel der Mittelzeile links von dem der Zeile `cy − 5`.
- [ ] **Step 2: Fehlschlag prüfen**, dann `paint_arrows` und den Eintrag schreiben. Die Daten des Beispiels kommen aus `build` (Englisch, Titel `Power`, Uhr `14:32`; Netz −1100 W, PV 3200 W, Speicher +900 W mit 64 %), nicht aus einer zweiten Tabelle; `render_all` malt die Pfeile für `energy` nach dem Rendern und vor dem Speichern als PNG. Run: `.venv/bin/pytest -q tests/test_render_previews.py` → PASS.
- [ ] **Step 3: Vorschaubild erzeugen.** Run (Repo-Wurzel): `server/.venv/bin/python tools/render_previews.py energy` → `docs/img/templates/energy.png`. Ansehen (Read) und dem Nutzer zeigen. Die anderen PNGs nicht neu erzeugen.
- [ ] **Step 4: `energy.md` in beiden Sprachen.** Überschriften (gleiche Folge): `# energy` · `## What it shows` / `## Was sie zeigt` · `## What you need` / `## Was du brauchst` · `## Example` / `## Beispiel` · `## Options` / `## Optionen` · `## Setup` / `## Einrichtung` · `## When something is wrong` / `## Wenn etwas nicht stimmt`. Inhalt: die Pfeilregel als Tabelle (vom Symbol weg = liefert, zum Symbol hin = nimmt auf, 0 = grau ohne Pfeile), die Zeilentypen mit Vorzeichen und Standard für `full`, beide Beispiel-Seiten der Spec, alle Optionen (`title`, `animate`, `url`, `token`, `lang`, `refresh` mit Standard 5 und Minimum 2; je Zeile `type`, `entity`, `soc`, `invert`, `full`, `min`), im Add-on ohne `url`/`token`. Die vier ehrlichen Hinweise der Spec wörtlich dem Sinn nach: Gas- und Wasserzähler melden oft nur alle paar Minuten; gebraucht wird Durchfluss oder Leistung, nicht der Zählerstand (Ableitungs-Helfer in HA); der Weg vom Sensor zum Display dauert mehrere Sekunden, die Pfeile zeigen Richtung und Größenordnung; Pfeile laufen ab Firmware 0.7.0, mit älterer Firmware erscheint die Seite als Standbild. Fehlersuche: Pfeile falsch herum → `invert`; Pfeile zu schnell oder zu langsam → `full`; Pfeile kriechen nachts → `min`; getrennte Sensoren für Bezug und Einspeisung → Template-Sensor in HA; keine Pfeile → Firmware-Version der Geräteseite prüfen, `animate`. Nur die GeekMagic SmallTV Ultra nennen. Kein „Echtzeit“/„real-time“, kein „getestet“.
- [ ] **Step 5: Übrige Doku.** Katalog (en, de): `### energy` unter „Server & smart home“ mit dem Bild und einem Satz. `mkdocs.yml`: `- energy: templates/energy.md` nach `homeassistant`. `configuration.md` (en, de): `energy` in der Typenliste, neuer Abschnitt `## Page type: energy` / `## Seitentyp: energy` (gleiche Stelle in beiden Dateien) mit kurzem Beispiel, und beim Schlüssel `refresh` der Hinweis, dass ein Seitentyp einen eigenen Standard haben kann (energy: 5). `home-assistant.md` (en, de): der Satz zu `homeassistant` ohne `url`/`token` gilt auch für `energy`. `writing-pages.md` (en, de): ein Punkt zu `DEFAULT_REFRESH`; `_anim` und `SKIP_UNCHANGED` bleiben undokumentiert (internes Format). `README.md`/`README.de.md`: dritte Kachel in der Zeile der `homeassistant`-Kacheln (`energy`: Bild 240×240, ein Satz). `config-example.yaml`: auskommentiertes Beispiel. `ha-addon/DOCS.md`: `energy` neben `homeassistant` nennen.
- [ ] **Step 6: `CHANGELOG.md`** unter `## [Unreleased]`: einleitender Absatz (Server und Firmware gemeinsam aktualisieren; die Seite funktioniert mit älterer Firmware als Standbild), `### Added`: Seite `energy` mit ihren Optionen; Firmware zeichnet Pfeile nach `X-Anim`; `/status` mit den neuen Feldern; `DEFAULT_REFRESH` für eigene Seiten. Kein Wort über Tests auf dem Gerät.
- [ ] **Step 7: Prüfen.** Run: `python3 tools/check_docs_parity.py` → ok. `pip install -r requirements-docs.txt` in einer venv im Scratchpad, dann `NO_MKDOCS_2_WARNING=1 mkdocs build --strict` → baut. `grep -niE "echtzeit|real-?time|getestet|tested" docs/en/templates/energy.md docs/de/templates/energy.md` → keine Treffer; den Abschnitt `## [Unreleased]` in `CHANGELOG.md` auf dieselben Wörter durchlesen. Aus `server/`: `.venv/bin/pytest -q -m "not browser" && .venv/bin/ruff check . ../pages` → PASS.
- [ ] **Step 8: Commit** — `docs: energy page in the catalog, configuration reference, README gallery and changelog`.

---

### Task 11: Abnahme auf dem Gerät und Vorbereitung von 0.7.0

Diese Task hat keinen Code außer dem Einstellen der Tempo-Konstanten. Jeder Schritt mit **[Okay nötig]** beginnt mit der Frage an den Nutzer; die Abnahme erteilt nur er.

- [ ] **Step 1: Ausgangswerte lesen** (nur lesend): `/status` des Geräts (Version, `heap_free`, `frames_ok`, `boot_failed`) notieren.
- [ ] **Step 2: [Okay nötig] Test-Server mit dem Branch.** Vorschlag (lässt die laufende Installation unberührt): den Arbeitsbaum ohne `.git`, `.env` und `config.yaml` in einen eigenen Ordner auf dem Heimserver kopieren, dort mit eigener `config.yaml` (bestehende Seiten des Nutzers plus die zwei Energieseiten gegen das HA der Test-VM, `refresh: 5`), eigener `.env` und eigenem Port als zweite Compose-Instanz starten. Welche Variante gilt (zweite Instanz oder die laufende ersetzen), entscheidet der Nutzer in dem Moment.
- [ ] **Step 3: [Okay nötig] Flashen.** Das in Task 8 gebaute `.superpowers/dev/glancebox-ultra-energy.bin` per OTA einspielen: `curl --netrc-file <Datei mit dem Zugang> -F md5=$(md5 -q <bin>) -F firmware=@<bin> http://<Gerät>/update` (Feld `md5` vor der Datei). Das vorherige Release-Bin (0.6.3) für den Rückweg bereithalten. Danach `/status`: neue Felder vorhanden, `boot_failed` 0, `safe_mode` false. Falls das Gerät auf den Test-Server zeigen soll: die Server-Adresse stellt der Nutzer auf der Geräteseite um (und nach der Abnahme zurück).
- [ ] **Step 4: Abnahmeliste der Spec mit dem Nutzer durchgehen** (Abschnitt „Abnahme auf dem Gerät“, Punkte 1 bis 5), Werte über die Regler in HA setzen: beide Seiten in der Playlist; jede Zeile der Pfeilregel einmal gesehen (Bezug, Einspeisung, PV, Speicher lädt und entlädt, Wallbox, Gas, Wasser, Wert 0); keine Kante, keine Pfeilreste nach Seitenwechsel, auf dem Offline-Bildschirm (Test-Server stoppen) und beim OTA-Bildschirm; Nachtmodus 0 % und zurück; Geräteseite bedienbar und OTA möglich, während eine Energieseite läuft. Eine Seite mit 4 Zeilen ansehen (Offener Punkt 4). Je Punkt das Urteil des Nutzers notieren.
- [ ] **Step 5: Tempo einstellen.** Mit dem Nutzer am Gerät `SPEED_MIN`/`SPEED_MAX` und die Standardwerte in `FULL` bestätigen oder ändern (`pages/energy/page.py`; Tests in `test_energy.py` und die Tabelle in `energy.md` ziehen mit). Bei einer Änderung: Server-Tests grün, Commit `feat(pages): arrow speeds as set on the device`.
- [ ] **Step 6: Messen** (Spec „Stufe 1 und Stufe 2“): bei `refresh: 5` zweimal `/status` im Abstand von mindestens 30 Minuten lesen; `anim_gaps_250` und `anim_gaps_100` je Minute Laufzeit (`anim_run_s`) ausrechnen, dazu `heap_free` gegen den Wert aus Step 1. Mehr als eine Lücke über 250 ms je Minute ist der Anlass für Stufe 2, kein Hindernis für 0.7.0. Zahlen in den Bericht.
- [ ] **Step 7: Dauerlauf.** 24 h mit einer Energieseite in der Playlist: am Ende `uptime_s` ≥ 86400, `boot_failed` 0, `safe_mode` false, `reset_reason` unverändert, `heap_free` stabil, `frame_errors` notiert. Vergleichslauf mit `animate: false` auf beiden Energieseiten, gleiche Firmware, gleicher `refresh`: `frame_errors` je Stunde gegenüberstellen (Dauer des Vergleichslaufs legt der Nutzer fest; die Spec nennt keine).
- [ ] **Step 8: Abnahme festhalten.** Erst wenn der Nutzer die Punkte 1 bis 6 der Spec bestätigt hat, darf ein Text „getestet“ sagen. Das Ergebnis (Datum, Zahlen, offene Punkte) in den Abschlussbericht; Doku und CHANGELOG bleiben, wie sie sind.
- [ ] **Step 9: 0.7.0 vorbereiten, nicht ausführen.** Der Release-Commit nach dem Muster von `80336d2` ändert genau drei Dateien: `VERSION` → `0.7.0`, `ha-addon/config.yaml` → `version: "0.7.0"`, `CHANGELOG.md` (`## [0.7.0]` unter einem leeren `## [Unreleased]`; Kontrolle mit `python3 tools/changelog_section.py 0.7.0`). Er entsteht **erst auf Wunsch des Nutzers** nach der Abnahme, zusammen mit Merge, Tag und Release nach `docs/RELEASING.md`; nichts davon gehört zu diesem Plan. Im Abschlussbericht stehen: die Commits des Branches, was auf dem Gerät geprüft ist und was nicht, die offenen Punkte der Spec (1 bis 7) mit ihrem Stand, und dass der Film oder das GIF vom Gerät noch mit dem Nutzer aufzunehmen ist.
