# 3D-Drucker-Seite (`printer`): Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ein neuer Seitentyp `printer` zeigt auf dem 240×240-Display, was ein 3D-Drucker gerade macht (Zustand, Fortschritt, Restzeit, Fertig-Uhrzeit, Datei, Düse und Bett, Schicht, Vorschaubild), gelesen direkt von Moonraker, OctoPrint oder PrusaLink oder über Home Assistant mit Vorlagen für fünf Integrationen.

**Architecture:** `pages/printer/page.py` kennt nur das gemeinsame Schema `PrinterStatus`: es prüft die Konfiguration, wendet die Zustandsregeln an (`finished_for`), rechnet die Anzeige-Texte aus und fängt die Fehler der Quellen ab. Je Quelle liefert ein Modul in `pages/printer/providers/` (Muster `pages/ai`) aus `fetch` ein `PrinterStatus`; gemeinsame Helfer (Zeitbudget, Zeitformate, Bild) liegen in `providers/_common.py`. Der Server bekommt nur `http.get_bytes`, `auth=` an `http.get_json` und eine Zeile in `addon.ha_defaults`.

**Tech Stack:** Python 3.12, requests (inkl. `requests.auth.HTTPDigestAuth`), Jinja2, Pillow, Playwright/Chromium, pytest, ruff · Docker nur für die Simulatoren (Tasks 10 und 11). Keine Firmware-Änderung, keine neue Abhängigkeit.

**Spec:** `docs/superpowers/specs/2026-11-25-drucker-seite-design.md`, Mockups in `docs/superpowers/specs/assets/2026-11-25-printer-mockup.html`. Vor jeder Task den passenden Abschnitt lesen; dort stehen die API-Felder, Zuordnungstabellen und Gründe. Ihre Entscheidungen sind endgültig. Ausführung: Opus, `superpowers:subagent-driven-development`, TDD (vom Nutzer festgelegt).

## Global Constraints

- **Nur im Worktree** `/Users/robin/programming/zugtafel/.claude/worktrees/printer-page` arbeiten (Branch `feat/printer-page`). Der Haupt-Checkout `/Users/robin/programming/zugtafel` wird von anderen Sitzungen benutzt: nie dorthin wechseln, nichts dort ändern.
- Committen auf dem Branch ja, ein Commit je Task. **Kein Push, kein Merge, kein Tag, kein Release, keine Versionsänderung** (`VERSION` und `ha-addon/config.yaml` bleiben bei 0.7.1). Nach `main` geht erst etwas, wenn alles fertig und geprüft ist; das gehört nicht zu diesem Plan.
- Commits: `git -c user.email=106265325+robinlanger@users.noreply.github.com commit`, Nachricht Englisch im Stil der Historie (`feat(pages): …`, `feat(server): …`, `test: …`, `docs: …`), jede endet mit der Zeile `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Dateien einzeln mit `git add` aufnehmen; `server/uv.lock` nie.
- **Venv:** Der Worktree hat keine. Die `server/.venv` des Haupt-Checkouts ist eine editierbare Installation, die auf dessen Code zeigt, und darf **nicht** benutzt werden. Task 0 legt `server/.venv` im Worktree an.
- **Tests** aus `server/` des Worktrees: `.venv/bin/pytest -q -m "not browser"` und `.venv/bin/ruff check . ../pages`; Browser-Tests `.venv/bin/pytest -q -m browser`. Nur eine Seite: `.venv/bin/pytest -q -c pyproject.toml ../pages/printer -m "not browser"` (ohne `-c pyproject.toml` findet pytest bei einem einzelnen Pfad außerhalb von `server/` die Einstellungen nicht, async-Tests scheitern dann mit „async def functions are not natively supported“). Maßgeblich wie in CI ist das Test-Image, sofern Docker läuft (aus der Repo-Wurzel): `docker build --target test -t glancebox:test . && docker run --rm --cap-drop ALL --security-opt no-new-privileges glancebox:test pytest -q -m browser`.
- **Privatsphäre:** keine echten IPs, Hostnamen, E-Mail-Adressen oder Tokens in Code, Tests, Fixtures, Doku, Screenshots, Commits und Berichten. Platzhalter: `http://drucker.local:7125`, `http://homeassistant.lan:8123`, `192.168.x.x`, erfundene Dateinamen (`benchy_0.2mm_PLA.gcode`). Die Adresse des echten Druckers steht nur in einer Datei im Scratchpad oder in `.env` (gitignored), nie auf einer Kommandozeile im Bericht.
- **Ehrlichkeit:** Doku, CHANGELOG und Berichte sagen genau, was wie geprüft ist: am echten Gerät, im Simulator oder nur mit Fixtures. Was nicht lief, heißt **nicht geprüft**; nichts wird geraten. Am echten Gerät prüfbar ist nur Moonraker (Drucker des Nutzers), ganz am Ende und mit ihm (Task 12).
- **Kein Halt zwischendurch** (Entscheidung des Nutzers): alles bauen, Gerätetest zuletzt. Schritte, die die Zustimmung des Nutzers in dem Moment brauchen, tragen die Marke **[Okay nötig]**; ohne Okay anhalten und fragen. Das betrifft nur Task 12.
- **Simulatoren** laufen per Docker auf diesem Mac, nie auf dem Heimserver. Heimserver, Display und jede HA-Instanz werden in diesem Plan nicht angefasst. Läuft Docker nicht (`docker info` scheitert), steht im Bericht und in der Doku „nicht geprüft“.
- Zwei Sprachen: Seitentexte `de`/`en` mit gleicher Aussage; Doku in `docs/en` und `docs/de` mit gleicher Überschriftenfolge (`python3 tools/check_docs_parity.py`); Nutzersichtbares in `CHANGELOG.md` unter `## [Unreleased]`, auf Englisch.
- Bestehende Seiten ändern sich nicht; ihre Tests bleiben unverändert grün.
- Werte aus der Spec, wörtlich: `source` aus `moonraker | octoprint | prusalink | hass`; `integration` aus `moonraker | octoprint | prusalink | bambu_lab | creality | custom`; `finished_for` Standard 120 Minuten, 0 = nie „Fertig“; `DEFAULT_REFRESH = 10`, `MIN_REFRESH = 5`, `SKIP_UNCHANGED = True`; Bild höchstens 512 KiB (524 288 Byte), nur `image/png` und `image/jpeg`; Zeitbudget 15 s gesamt, 5 s je Aufruf; Vorschaubild 100×100 px links oben; Moonraker-Datei-Schätzung erst ab 1 % Fortschritt; PrusaLink-Benutzer Standard `maker`; Farben aus `base.html` (`--green`, `--orange`, `--red`, `--muted`).
- Anti-Ziele der Spec gelten für jede Task: ein fehlendes Feld kippt die Seite nie in einen Fehlerzustand (nur der Zustand ist Pflicht); kein API-Key, Passwort oder Token in einem Log.

### Entscheidungen dieses Plans

Jede ist eine **Entscheidung (Plan)**: von der Spec offen gelassen oder dort nur für einen Teil geregelt.

1. **`glancebox/http.py`:** `get_json` und `get_bytes` bekommen `auth=None` (PrusaLink braucht Digest auch für das Bild). `get_json` gibt bei Status 204 `None` zurück (PrusaLink „kein Job“). `get_bytes` folgt keinen Weiterleitungen und liefert `(bytes, mime)`.
2. **Bild:** Was eine Quelle liefert, wird mit Pillow geöffnet, auf höchstens 100×100 verkleinert und als PNG neu kodiert; erst das wird zur Data-URI. Lässt es sich nicht öffnen oder ist es größer als 4096 px je Seite, gibt es kein Bild.
3. **Zugang abgelehnt:** 401/403 gilt bei jeder Quelle als eigener Zustand (orange „Zugang abgelehnt“ / „Access denied“ mit „API-Key prüfen“, „Passwort prüfen“ bzw. bei `hass` die Texte von `energy`), nicht als „Drucker nicht erreichbar“.
4. **Unlesbare Antwort:** Antwortet eine Quelle, aber nicht in der erwarteten Form, zeigt die Seite orange „Antwort nicht lesbar“ / „Unexpected answer“ mit „Stand HH:MM“.
5. **Log:** „nicht erreichbar“ einer direkten Quelle wird nur beim Wechsel des Zustands geloggt (ein ausgeschalteter Drucker soll nicht alle 10 s eine Zeile schreiben).
6. **Gedächtnis pro Seite:** Schlüssel `(source, url, integration, device)`; es hält den Zeitpunkt, an dem `finished` zuerst gesehen wurde, und den letzten fertigen Druck (für „Zuletzt: …“, wenn die Quelle selbst auf bereit wechselt). Nur im Speicher.
7. **`entities:`** nimmt neben `sensor.name` auch `sensor.name#attribut` (so sind die Attribut-Felder der Creality-Vorlage überschreibbar).
8. **HA `unknown`** am Zustands-Sensor gilt wie `unavailable` als offline; `unknown`/`unavailable` an einem anderen Feld heißt „Feld fehlt“.
9. **`device` bei `integration: custom`:** erlaubt, aber ohne Wirkung (die Spec nennt `device` Pflicht „außer bei octoprint“, bei `custom` gibt es nichts, wofür es stünde); Pflicht ist dort nur `entities.state`.
10. **Hinweis „sieht aus wie bambu_lab“** (in der Spec als optional bezeichnet) wird nicht gebaut.
11. **Formate:** Prozent wird abgerundet (99,6 → 99); Restzeit unter einer Minute „noch <1 min“; „heizt“ steht, wenn Soll > 0 und Ist mehr als 5 °C darunter; Uhrzeiten an anderen Tagen: gestern „gestern 21:14“, sonst bis 6 Tage Abstand Wochentag („Mo 07:40“), darüber Datum („23.11. 07:40“ / „Nov 23 07:40“).
12. **`message`** trägt neben der Fehlermeldung auch die kleine Zeile bei `paused` (PrusaLink `ATTENTION`) und `idle` (unbekanntes Rohwort); kein Extra-Feld.
13. **Moonraker:** Metadaten und Bild gelten je `url` für eine Datei; verworfen werden sie, wenn der Dateiname wechselt oder ein Druck neu beginnt. Die History wird nur gelesen, wenn nicht gedruckt wird; „Zuletzt“ nennt nur Jobs mit `status == "completed"`.
14. **HA-Budget:** Ist das Budget vor dem letzten Entitäts-Aufruf verbraucht, gilt das wie bei `energy` als „Keine Verbindung zu Home Assistant“; das Bild entfällt, wenn weniger als 2 s übrig sind.
15. **Testdateien** heißen `test_printer*.py` (pytest verlangt hier eindeutige Dateinamen; `server/tests/test_hass.py` gibt es schon). Herkunft der Fixtures steht in `pages/printer/fixtures/README.md` (JSON kennt keinen Kopfkommentar).
16. **Vorschaubilder:** vier (`printer-printing`, `printer-finished`, `printer-error`, `printer-idle`); die Abschnitte „New in 0.7.0“ der beiden READMEs bleiben unverändert (Sache des Release).

## Review Focus

1. Moonraker-Dateiname mit Leerzeichen, Umlaut, `#` oder Unterordner (`Teile/Halter #2 groß.gcode`): Metadaten und Bild werden mit richtig kodierter Adresse geholt, die Anzeige zeigt `Halter #2 groß` (Task 5: `test_filename_with_space_hash_umlaut_and_folder`).
2. Falscher oder fehlender API-Key (401/403) bei Moonraker, OctoPrint, PrusaLink: „Zugang abgelehnt“, nicht „Drucker nicht erreichbar“, und der Key steht in keiner Logzeile (Task 3: `test_auth_rejected_is_its_own_state`; je Quelle `test_wrong_key_is_auth`).
3. Die Quelle sagt `image/png`, liefert aber kein lesbares Bild (QOI, HTML-Fehlerseite, abgeschnittene Datei) oder ein riesiges: die Seite zeigt denselben Druck ohne Bild (Task 2: `test_broken_or_huge_image_gives_no_thumbnail`).
4. Zahlen am Rand: Fortschritt über 100, negativ oder `nan`; Restzeit negativ; `estimated_time` 0; ETA in der Vergangenheit (HA-Sensor bleibt nach Druckende stehen): nie „noch −5 min“, nie 104 %, das Feld fällt weg oder wird begrenzt (Task 2: `test_numbers_at_the_edges`; Task 6: `test_stale_eta_is_dropped`).
5. Derselbe Dateiname wird neu gesliced und noch einmal gedruckt: Schätzung und Bild stammen vom neuen Upload, nicht aus dem Zwischenspeicher (Task 5: `test_new_print_of_same_filename_reloads_metadata`).

---

### Task 0: Arbeitsumgebung im Worktree

Kein Commit. Geprüft am 2026-11-25 mit einer Wegwerf-Venv: die Befehle laufen, 732 Tests grün (5 übersprungen), Browser-Tests laufen mit dem Chromium aus `~/Library/Caches/ms-playwright` (`chromium-1255`).

- [ ] **Step 1: Venv anlegen.** Run (aus `server/` des Worktrees):

  ```bash
  uv venv --python 3.12 .venv
  VIRTUAL_ENV="$PWD/.venv" uv pip install --require-hashes -r requirements.lock -r requirements-dev.lock
  VIRTUAL_ENV="$PWD/.venv" uv pip install --no-deps -e .
  .venv/bin/python -c "import glancebox; print(glancebox.__file__)"
  ```

  Erwartet: der Pfad liegt unter `.claude/worktrees/printer-page/server/glancebox/`. Zeigt er auf den Haupt-Checkout: anhalten.
- [ ] **Step 2: Ausgangsstand.** Run: `.venv/bin/pytest -q -m "not browser" && .venv/bin/ruff check . ../pages` → PASS, „All checks passed!“. Run: `.venv/bin/pytest -q -m browser` → PASS. Fehlt Chromium („Executable doesn't exist“): `.venv/bin/playwright install chromium`, sonst nichts installieren.
- [ ] **Step 3:** `git status --short` → leer (`.venv` und `*.egg-info` sind ignoriert; `server/uv.lock` darf nicht entstanden sein).

---

### Task 1: `http.get_bytes`, `auth=` und Status 204

**Files:**
- Modify: `server/glancebox/http.py`
- Test: `server/tests/test_http.py`

**Interfaces:**
- Produces:

  ```python
  IMAGE_TYPES = ("image/png", "image/jpeg")

  def get_json(url: str, *, params: dict | None = None, headers: dict | None = None,
               timeout: float = 10, auth=None) -> Any          # None on HTTP 204
  def get_bytes(url: str, *, headers: dict | None = None, timeout: float = 10,
                max_bytes: int, auth=None) -> tuple[bytes, str]   # (body, mime)
  ```

  `get_bytes` wirft `requests.HTTPError` bei Fehlerstatus (auch bei 3xx, Weiterleitungen werden nicht verfolgt) und `ValueError` mit einem der Wörter `type`, `large`, `slow` in der Meldung.

- [ ] **Step 1: Tests schreiben** (in `test_http.py`; `FakeResponse` um `status_code`, `headers`, `iter_content(chunk_size)` und `close()` erweitern, `fake_get` nimmt `**kwargs`):
  - `test_get_json_passes_auth_and_keeps_defaults`: `auth=("u", "p")` kommt bei `requests.get` an; ohne `auth` ist `calls["auth"] is None`.
  - `test_get_json_204_is_none`: Status 204 mit leerem Körper → `None`, `json()` wird nicht aufgerufen.
  - `test_get_bytes_ok`: `Content-Type: image/png; charset=binary`, zwei Stücke → `(b"…", "image/png")`; `requests.get` bekam `stream=True`, `allow_redirects=False`, den User-Agent, `timeout`.
  - `test_get_bytes_rejects_other_types` (parametrisiert `text/html`, `image/qoi`, `image/svg+xml`, fehlender Kopf) → `ValueError, match="type"`, `iter_content` wurde nicht aufgerufen.
  - `test_get_bytes_stops_at_limit`: `Content-Length: 600000` bei `max_bytes=524288` → `ValueError, match="large"` ohne ein Stück zu lesen; ohne `Content-Length` mit zehn Stücken zu 100 000 Byte → `ValueError, match="large"` nach höchstens sechs gelesenen Stücken; in beiden Fällen `close()` aufgerufen.
  - `test_get_bytes_total_time_is_bounded`: `time.monotonic` gemockt, je Stück 3 s, `timeout=5` → `ValueError, match="slow"`.
  - `test_get_bytes_redirect_is_an_error`: Status 302 → `requests.HTTPError`.
- [ ] **Step 2: Fehlschlag prüfen.** Run: `.venv/bin/pytest -q tests/test_http.py` → FAIL (`TypeError: unexpected keyword 'auth'`, `AttributeError: get_bytes`).
- [ ] **Step 3: `http.py` ändern.** `get_bytes` liest mit `iter_content(8192)`, prüft den Typ (Teil vor `;`, klein geschrieben) vor dem ersten Stück und schließt die Antwort in jedem Fall (`with`/`finally`). Ein 3xx wird als `requests.HTTPError(response=resp)` gemeldet.
- [ ] **Step 4: Tests bestehen.** Run: `.venv/bin/pytest -q -m "not browser" && .venv/bin/ruff check . ../pages` → PASS (die Fakes anderer Seiten rufen `get_json` ohne `auth` und bleiben gültig).
- [ ] **Step 5: Commit** — `git add server/glancebox/http.py server/tests/test_http.py`, Nachricht `feat(server): get_bytes with size limit and image type check, auth and 204 for get_json`.

---

### Task 2: Gemeinsames Schema und Helfer (`providers/_common.py`)

**Files:**
- Create: `pages/printer/providers/__init__.py` (eine Zeile Docstring wie `pages/ai/providers/__init__.py`), `pages/printer/providers/_common.py`
- Create: `pages/printer/conftest.py`, `pages/printer/page.py` (vorerst nur Docstring und `def fetch(options, ctx): raise NotImplementedError`, damit `load_page_types` den Ordner lädt; Task 3 füllt sie)
- Test: `pages/printer/test_printer_common.py`

**Interfaces:**
- Produces (`_common.py`):

  ```python
  STATES = ("printing", "paused", "finished", "error", "idle", "offline")
  LANGS = ("de", "en")
  MAX_IMAGE_BYTES = 512 * 1024
  THUMB_PX = 100
  BUDGET_S, CALL_TIMEOUT_S = 15.0, 5.0

  @dataclass(frozen=True)
  class Thumbnail:
      data: bytes
      mime: str

  @dataclass(frozen=True)
  class PrinterStatus:
      state: str                                         # one of STATES
      progress: float | None = None                      # 0..100
      remaining_s: int | None = None
      eta: datetime | None = None                        # aware
      filename: str | None = None                        # already cleaned
      nozzle: tuple[float, float | None] | None = None   # (actual, target)
      bed: tuple[float, float | None] | None = None
      layer: tuple[int, int | None] | None = None
      message: str | None = None
      duration_s: int | None = None
      ended_at: datetime | None = None
      state_since: datetime | None = None
      thumbnail: Thumbnail | None = None
      last_job: tuple[str, datetime | None] | None = None

  class SourceError(Exception):
      """kind: "offline" | "auth" | "unreachable" | "config" | "data"."""
      def __init__(self, kind: str, detail: str | None = None, *, url: str | None = None,
                   cause: Exception | None = None) -> None

  class Budget:
      def __init__(self, total: float = BUDGET_S, per_call: float = CALL_TIMEOUT_S,
                   clock: Callable[[], float] = time.monotonic) -> None
      def left(self) -> float
      def timeout(self) -> float          # min(per_call, left()); SourceError("unreachable") at <= 0

  def clean_filename(path: str | None) -> str | None
  def number(value: object) -> float | None                 # finite float or None; never raises
  def clamp_progress(value: object) -> float | None         # None for nan/garbage, else 0..100
  def temp(actual: object, target: object) -> tuple[float, float | None] | None
  def remaining_text(seconds: int, lang: str) -> str
  def duration_text(seconds: int, lang: str) -> str
  def clock_text(when: datetime, now: datetime, lang: str) -> str
  def ago_text(when: datetime, now: datetime, lang: str) -> str
  def data_uri(thumb: Thumbnail | None) -> str | None
  def cached_thumbnail(key: tuple, load: Callable[[], Thumbnail | None]) -> Thumbnail | None
  def source_error(exc: Exception, url: str, *, direct: bool) -> SourceError
  ```

  `source_error` ordnet zu: Status 401/403 → `auth`; `requests.ConnectionError`/`Timeout` → `offline` (direkt) bzw. `unreachable` (HA); alles andere (anderer Status, `ValueError`, `TypeError`, `KeyError`) → `data` (direkt) bzw. `unreachable` (HA).
- Produces (`conftest.py`, Fixtures für alle Testdateien der Seite): `printer` (`load_page_types([PAGES_DIR])["printer"]`), `mod` (`sys.modules["glancebox_pages.printer"]`), `common` (`…printer.providers._common`), `load(name) -> dict` (liest `pages/printer/fixtures/<name>.json`), `NOW = datetime(2026, 11, 25, 14, 32, tzinfo=ZoneInfo("Europe/Berlin"))` (ein Mittwoch), `ctx(lang="de")`, und `route(monkeypatch)`: installiert Fakes für `glancebox.http.get_json` und `glancebox.http.get_bytes`, die Antworten aus einem Dict `{pfad_mit_query_oder_ganze_url: Antwort}` liefern (Exception → werfen, `int` → `requests.HTTPError` mit diesem Status, wie `serve` in `pages/energy/test_energy.py`), alle Aufrufe mit `url`, `params`, `headers`, `timeout`, `auth` mitschreiben und unbekannte Adressen mit `AssertionError` ablehnen.

- [ ] **Step 1: Tests schreiben** (`test_printer_common.py`):

```python
@pytest.mark.parametrize(("path", "name"), [
    ("benchy_0.2mm_PLA.gcode", "benchy_0.2mm_PLA"),
    ("Teile/Halter #2 groß.GCODE", "Halter #2 groß"),
    ("/usb/BOX.BGCODE", "BOX"), ("plate_1.gcode.3mf", "plate_1"), ("deckel.3mf", "deckel"),
    ("ohne_endung", "ohne_endung"), ("", None), (None, None),
])
def test_clean_filename(common, path, name):
    assert common.clean_filename(path) == name


@pytest.mark.parametrize(("seconds", "de", "en"), [
    (0, "noch <1 min", "<1 min left"), (59, "noch <1 min", "<1 min left"),
    (1380, "noch 23 min", "23 min left"), (3599, "noch 59 min", "59 min left"),
    (4980, "noch 1:23 h", "1:23 h left"), (86399, "noch 23:59 h", "23:59 h left"),
    (97200, "noch 1 d 3 h", "1 d 3 h left"),
])
def test_remaining_text(common, seconds, de, en):
    assert (common.remaining_text(seconds, "de"), common.remaining_text(seconds, "en")) == (de, en)


def test_duration_text(common):
    assert common.duration_text(11520, "de") == "Dauer 3:12 h"
    assert common.duration_text(2700, "en") == "Took 45 min"


@pytest.mark.parametrize(("when", "de", "en"), [
    (datetime(2026, 11, 25, 15, 55), "15:55", "15:55"),
    (datetime(2026, 11, 24, 21, 14), "gestern 21:14", "yesterday 21:14"),
    (datetime(2026, 11, 30, 7, 40), "Mo 07:40", "Mon 07:40"),
    (datetime(2026, 11, 26, 0, 5), "Do 00:05", "Thu 00:05"),
    (datetime(2026, 11, 10, 7, 40), "10.11. 07:40", "Nov 10 07:40"),
])
def test_clock_text(common, when, de, en):
    when = when.replace(tzinfo=NOW.tzinfo)
    assert (common.clock_text(when, NOW, "de"), common.clock_text(when, NOW, "en")) == (de, en)


def test_ago_text(common):
    at = lambda **kw: NOW - timedelta(**kw)  # noqa: E731
    assert common.ago_text(at(seconds=20), NOW, "de") == "gerade eben"
    assert common.ago_text(at(minutes=4), NOW, "de") == "vor 4 min"
    assert common.ago_text(at(minutes=4), NOW, "en") == "4 min ago"
    assert common.ago_text(at(hours=3, minutes=10), NOW, "de") == "vor 3 h"
    assert common.ago_text(at(days=2), NOW, "en") == "2 d ago"
    assert common.ago_text(NOW + timedelta(minutes=5), NOW, "en") == "just now"   # clock skew


def test_numbers_at_the_edges(common):                       # Review Focus 4
    assert [common.clamp_progress(v) for v in (47.4, 104, -3, "12.5")] == [47.4, 100.0, 0.0, 12.5]
    assert [common.clamp_progress(v) for v in (float("nan"), "unknown", None, True)] == [None] * 4
    assert common.temp(214.2, 215) == (214.2, 215.0)
    assert common.temp("60", None) == (60.0, None) and common.temp(23.0, 0) == (23.0, None)
    assert common.temp(None, 215) is None and common.temp("unavailable", 0) is None
    assert common.remaining_text(-300, "de") == "noch <1 min"
```

  Dazu:
  - `test_clock_text_converts_to_the_zone_of_now`: eine UTC-Zeit `14:55+00:00` → `15:55`.
  - `test_data_uri_normalises_the_image`: ein 300×200-PNG und ein 300×300-JPEG (im Test mit Pillow erzeugt) → Text beginnt mit `data:image/png;base64,`; dekodiert ist das Bild höchstens 100×100, Seitenverhältnis erhalten, Modus `RGB` oder `RGBA`; zweimal aufgerufen gleicher Text (Voraussetzung für `SKIP_UNCHANGED`).
  - `test_broken_or_huge_image_gives_no_thumbnail` (Review Focus 3): `Thumbnail(b"qoif....", "image/png")`, `Thumbnail(b"<html>404</html>", "image/png")`, ein nach 100 Byte abgeschnittenes PNG, ein PNG mit 5000×10 px → jeweils `None`; `data_uri(None) is None`.
  - `test_cached_thumbnail`: gleicher Schlüssel ruft `load` einmal; `load`, das `None` liefert oder wirft, wird beim nächsten Mal wieder gerufen und gibt `None`; nach fünf verschiedenen Schlüsseln hält der Cache höchstens vier Einträge.
  - `test_budget`: Uhr über `clock=` gesteuert; `timeout()` ist 5, nach 12 s 3, nach 15 s `SourceError` mit `kind == "unreachable"`.
  - `test_source_error_mapping`: Tabelle aus dem Interfaces-Block, je für `direct=True` und `False`; `str(err)` und `repr(err)` enthalten weder einen Key noch eine Query (`redact_urls` auf `url`).
- [ ] **Step 2: Fehlschlag prüfen.** Run: `.venv/bin/pytest -q -c pyproject.toml ../pages/printer` → FAIL (`ModuleNotFoundError`/`AttributeError`).
- [ ] **Step 3: `_common.py` schreiben** nach Interfaces und Tests. `clean_filename` nimmt den letzten Pfadteil (`/` und `\`) und streift `.gcode`, `.bgcode`, `.3mf` ohne Rücksicht auf Groß-/Kleinschreibung ab, wiederholt. Wochentage `Mo Di Mi Do Fr Sa So` / `Mon … Sun`, Monate englisch `Jan … Dec`. `data_uri` öffnet mit `PIL.Image.open`, prüft `size` vor `load()`, verkleinert mit `Image.thumbnail((100, 100))` und speichert als PNG mit `optimize=True`; jede Ausnahme von Pillow ergibt `None`. `temp` macht aus Ziel 0 oder weniger `None`.
- [ ] **Step 4: Tests bestehen.** Run: `.venv/bin/pytest -q -m "not browser" && .venv/bin/ruff check . ../pages` → PASS.
- [ ] **Step 5: Commit** — `git add pages/printer/providers/__init__.py pages/printer/providers/_common.py pages/printer/conftest.py pages/printer/page.py pages/printer/test_printer_common.py`, Nachricht `feat(pages): printer status schema, time formats and thumbnail handling`.

---

### Task 3: `page.py`: Validierung, Zustandsregeln, Anzeige-Daten

**Files:**
- Modify: `pages/printer/page.py`
- Create: `pages/printer/template.html` (vorerst nur `{% extends "base.html" %}`; Task 4 füllt sie)
- Test: `pages/printer/test_printer.py`

**Interfaces:**
- Consumes: alles aus `_common.py` (Task 2).
- Produces (`page.py`):

  ```python
  MIN_REFRESH = 5
  DEFAULT_REFRESH = 10
  SKIP_UNCHANGED = True
  DEFAULT_FINISHED_FOR = 120
  COMMON_KEYS = ("source", "url", "title", "lang", "thumbnail", "finished_for")
  PROVIDERS: dict[str, ModuleType] = {}     # filled by Tasks 5 to 8, in the order of the spec
  DEFAULT_TITLE = {"de": "Drucker", "en": "Printer"}
  TEXT: dict[str, dict[str, str]]           # de/en, see the spec's text list

  def validate(options: dict) -> None
  def memory_key(options: dict) -> tuple
  def settle(status: PrinterStatus, key: tuple, finished_for: int, now: datetime) -> PrinterStatus
  def build(status: PrinterStatus, options: dict, lang: str, now: datetime) -> dict
  def notice(options: dict, lang: str, now: datetime, err: SourceError) -> dict
  def fetch(options: dict, ctx) -> dict
  ```

  Vertrag eines Provider-Moduls (Tasks 5 bis 8): `NAME: str`, `KEYS: tuple[str, ...]` (Optionen dieser Quelle neben `COMMON_KEYS`), `validate(options) -> None`, `fetch(options, ctx) -> PrinterStatus`. `options["lang"]` ist beim Aufruf schon aufgelöst (wie bei `ai`). Ein Provider wirft für alles, was kein Druckerzustand ist, `SourceError`; `fetch` der Seite fängt zusätzlich `requests.RequestException`, `ValueError`, `TypeError`, `KeyError`, `AttributeError` und macht daraus `SourceError("data")`.

  Vorlagendaten aus `build` und `notice` (nur `str`, `int`, `bool`, `None`, Listen und Dicts daraus, damit `SKIP_UNCHANGED` greift):

  ```python
  {"title": str, "clock": "14:32", "lang": "de", "alert": bool,
   "view": "job" | "idle" | "notice",
   "tone": "green" | "orange" | "red" | "muted",
   "label": "Druckt",               # state word; "" in the idle and notice views
   "big": "47" | "15:58" | "Bereit" | None, "big_unit": "%" | None,
   "main": "noch 1:23 h" | "Dauer 3:12 h" | None, "main_muted": bool,
   "lines": ["fertig 15:55", "Schicht 112/240"],          # at most 2
   "message": str | None,           # error text (job view) or the small note (paused, idle)
   "bar": int | None,               # 0..100
   "filename": str | None, "thumb": "data:image/png;base64,…" | None,
   "temps": [{"kind": "nozzle" | "bed", "actual": "214°", "target": "215" | None,
              "label": "Düse" | "Düse heizt", "on": bool}],
   "notice": {"message": str, "sub": str | None, "tone": "muted" | "warn"} | None}
  ```

- [ ] **Step 1: Tests schreiben** (`test_printer.py`; ein Schein-Provider wird mit `monkeypatch.setitem(mod.PROVIDERS, "fake", SimpleNamespace(NAME="Fake", KEYS=("api_key",), validate=…, fetch=…))` eingehängt, `S = common.PrinterStatus`):

```python
PRINTING = dict(state="printing", progress=47.6, remaining_s=4980, filename="benchy_0.2mm_PLA",
                nozzle=(214.2, 215.0), bed=(60.0, 60.0), layer=(112, 240))


def test_build_printing(mod, common):
    d = mod.build(common.PrinterStatus(**PRINTING), {}, "de", NOW)
    assert (d["view"], d["tone"], d["label"], d["alert"]) == ("job", "green", "Druckt", False)
    assert (d["big"], d["big_unit"], d["bar"]) == ("47", "%", 47)
    assert (d["main"], d["main_muted"]) == ("noch 1:23 h", False)
    assert d["lines"] == ["fertig 15:55", "Schicht 112/240"]
    assert d["temps"] == [
        {"kind": "nozzle", "actual": "214°", "target": "215", "label": "Düse", "on": True},
        {"kind": "bed", "actual": "60°", "target": "60", "label": "Bett", "on": True}]
    assert (d["title"], d["clock"], d["filename"], d["thumb"]) == (
        "Drucker", "14:32", "benchy_0.2mm_PLA", None)


def test_build_en(mod, common):
    d = mod.build(common.PrinterStatus(**PRINTING), {"title": "Voron"}, "en", NOW)
    assert (d["title"], d["label"], d["main"]) == ("Voron", "Printing", "1:23 h left")
    assert d["lines"] == ["done 15:55", "Layer 112/240"]
    assert [t["label"] for t in d["temps"]] == ["Nozzle", "Bed"]


def test_only_the_state_is_required(mod, common):            # anti-goal of the spec
    for state in common.STATES:
        d = mod.build(common.PrinterStatus(state), {}, "de", NOW)
        assert d["temps"] == [] and d["thumb"] is None and d["filename"] is None
    d = mod.build(common.PrinterStatus("printing"), {}, "de", NOW)
    assert (d["big"], d["bar"], d["main"], d["lines"]) == (None, None, None, [])
```

  Dazu (alle über `build`, wo nichts anderes steht):
  - `test_eta_and_remaining_complete_each_other`: nur `remaining_s=4980` → Zeile `fertig 15:55`; nur `eta=NOW+83 min` → `noch 1:23 h`; ETA am Montag 07:40 → `fertig Mo 07:40`; `layer=(112, None)` → `Schicht 112`.
  - `test_build_paused`: `tone == "orange"`, `label == "Pausiert"`, `main_muted is True`, mit `state_since=NOW−27 min` erste Zeile `seit 14:05`, ohne sie keine solche Zeile; `message="Eingriff nötig"` steht in `message`.
  - `test_build_finished`: `ended_at=NOW−4 min`, `duration_s=11520` → `label "Fertig"`, `big == "14:28"`, `big_unit is None`, `main == "Dauer 3:12 h"`, `lines == ["vor 4 min"]`, `bar == 100`, `tone == "green"`; ohne `duration_s` ist `main is None`.
  - `test_build_error`: `progress=47`, `message="Heater extruder not heating at expected rate"` → `alert is True`, `tone == "red"`, `label == "Fehler"`, `message` gesetzt, `lines == []`, `main is None`; ohne Meldung `message is None`.
  - `test_build_idle`: `last_job=("benchy_0.2mm_PLA", NOW−1 Tag um 21:14)`, `nozzle=(142.0, 215.0)`, `bed=(23.0, None)` → `view == "idle"`, `big == "Bereit"`, `lines == ["Zuletzt: benchy_0.2mm_PLA", "fertig gestern 21:14"]`, Temperaturen `{"actual": "142°", "target": "215", "label": "Düse heizt", "on": True}` und `{"actual": "23°", "target": None, "label": "Bett", "on": False}`; ohne `last_job` `lines == []`; `message="busy_unknown"` bleibt als `message` erhalten.
  - `test_build_offline`: `view == "notice"`, `alert is False`, `notice == {"message": "Drucker nicht erreichbar", "sub": None, "tone": "muted"}`; mit `message="Klipper startet"` ist das der `sub`.
  - `test_thumbnail_option`: Status mit einem 300×300-PNG → `thumb` beginnt mit `data:image/png;base64,`; mit `{"thumbnail": False}` ist `thumb is None`; im `idle`- und `offline`-Zustand immer `None`.
  - `test_notice_kinds` (parametrisiert, de und en): `auth` mit `source: fake` → orange, „Zugang abgelehnt“ / „Access denied“, `sub` „API-Key prüfen“ / „Check the API key“ (bei `source: prusalink` ohne `api_key` „Passwort prüfen“, bei `hass` „Token abgelehnt“ + „Long-Lived Access Token prüfen“ wie `energy`); `unreachable` → „Keine Verbindung zu Home Assistant“ + „Stand 14:32“; `config` mit `detail="Entität fehlt: sensor.voron_current_print_state"` → das ist die Meldung; `data` → „Antwort nicht lesbar“ + „Stand 14:32“; `offline` → wie `test_build_offline`. In allen `tone == "warn"` außer `offline`, `alert is False`.
  - `test_finished_becomes_idle_after_finished_for`: `settle` mit `ended_at=NOW−119 min`, `finished_for=120` → bleibt `finished`; bei `NOW−121 min` → `state == "idle"`, `last_job == ("benchy_0.2mm_PLA", ended_at)`, `progress`, `remaining_s`, `thumbnail` leer; ohne `ended_at` zählt `state_since`.
  - `test_finished_first_seen_is_remembered`: ohne `ended_at`/`state_since`: erster Aufruf um 14:32 → `finished` mit `ended_at == NOW`; Aufruf um 16:31 → `finished`; um 16:33 → `idle`; ein anderer Schlüssel hat seine eigene Frist; nach einem `printing` dazwischen beginnt die Frist beim nächsten `finished` neu.
  - `test_finished_for_zero_never_shows_finished` und `test_finished_for_large_value` (10080 → nach 6 Tagen noch `finished`).
  - `test_last_finished_job_survives_the_printer_going_idle`: `settle` sieht `finished` (Datei A), danach liefert die Quelle `idle` ohne `last_job` → Ergebnis trägt `last_job == ("A", Ende)`; liefert die Quelle selbst ein `last_job`, gewinnt das.
  - `test_validate_ok` und `test_validate_rejects` (parametrisiert, `pytest.raises(ValueError, match=…)`): ohne `source`; `source: bambu`; ohne `url`; `url: "drucker.local"` (kein Schema); `lang: "fr"`; `title: 5`; `thumbnail: "no"`; `finished_for: -1`, `True`, `1.5`, `"120"`; unbekannter Schlüssel `finish_for` (Meldung nennt ihn); Schlüssel einer anderen Quelle (`token` bei `source: fake`; Meldung nennt Schlüssel und Quelle).
  - `test_refresh_default_and_floor` (über `validate_config`, Muster `pages/energy/test_energy.py::test_refresh_default_and_floor`): ohne `refresh` → 10; `refresh: 4` → `ConfigError`.
  - `test_fetch_uses_lang_and_provider`: `fetch` reicht `options` mit aufgelöstem `lang` an den Provider, wendet `settle` an und gibt `build` zurück; `ctx.lang == "en"` ohne `lang`-Option → englische Texte.
  - `test_auth_rejected_is_its_own_state` (Review Focus 2): Provider wirft `SourceError("auth")` → `view == "notice"`, Meldung „Zugang abgelehnt“, nicht „Drucker nicht erreichbar“.
  - `test_unexpected_exception_is_a_data_notice`: Provider wirft `KeyError("result")` bzw. `TypeError` → „Antwort nicht lesbar“; nichts steigt aus `fetch` auf.
  - `test_offline_is_logged_once_and_without_secrets`: dreimal `SourceError("offline", url="http://drucker.local:7125/x?apikey=S3CRET", cause=ConnectionError(…))`, `caplog` auf DEBUG → genau eine Zeile ab WARNING, `S3CRET` in keiner; nach einem erfolgreichen Abruf und erneutem Ausfall wieder eine.
  - `test_same_status_gives_equal_data`: zweimal `build` mit gleichem Status → gleiche Daten; `progress` 47.1 und 47.9 → gleiche Daten.
- [ ] **Step 2: Fehlschlag prüfen.** Run: `.venv/bin/pytest -q -c pyproject.toml ../pages/printer -m "not browser"` → die neuen Tests scheitern.
- [ ] **Step 3: `page.py` schreiben.** `validate`: `source` in `PROVIDERS`, dann gemeinsame Schlüssel (`url` mit `urlparse` wie in `glancebox.hass.validate_connection`; `finished_for` ganzzahlig ≥ 0, kein `bool`), dann Abgleich `set(options) − COMMON_KEYS − KEYS` des Providers, dann dessen `validate`. `settle` hält `_memory: dict[tuple, …]` auf Modulebene (Entscheidung 6). `build` füllt zuerst ETA und Restzeit gegenseitig aus `now` und lässt eine ETA vor `now` fallen. `fetch` loggt über `glancebox.hass.log_failure("printer", url, cause)` (Entscheidung 5). Die Reihenfolge in `lines`: `printing` Fertig-Uhrzeit, Schicht; `paused` „seit“, Schicht; `finished` „vor …“.
- [ ] **Step 4: Tests bestehen.** Run: `.venv/bin/pytest -q -m "not browser" && .venv/bin/ruff check . ../pages` → PASS.
- [ ] **Step 5: Commit** — `git add pages/printer/page.py pages/printer/template.html pages/printer/test_printer.py`, Nachricht `feat(pages): printer page validation, state rules and display data`.

---

### Task 4: Template und Bildprüfung

**Files:**
- Modify: `pages/printer/template.html`
- Create: `pages/printer/README.md` (Entwicklernotiz, Englisch, Muster `pages/energy/README.md`; die Abschnitte je Quelle kommen in den Tasks 5 bis 8 dazu)
- Test: `pages/printer/test_printer.py` (Browser-Tests)

**Interfaces:**
- Consumes: Vorlagendaten aus `build`/`notice` (Task 3), `glancebox.frames.render_data(ptype, data, renderer)`, `glancebox.frames._jinja_env`, `glancebox.render.Renderer`, Makros `ui.header(title, clock, alert)` und `ui.notice(message, sub, tone)` aus `server/glancebox/templates/ui.html`.
- Produces: `MOCKUPS: dict[str, PrinterStatus]` in `test_printer.py` mit den sieben Fällen der Mockup-Datei (`printing`, `plain` = Druckt ohne Bild, `paused`, `finished`, `error`, `idle`, `offline`), Werte wie dort (47 %, 1:23 h, Schicht 112/240, `benchy_0.2mm_PLA_MK4`, 214°/215, 60°/60, Fehlertext „Heater extruder not heating at expected rate“); das Bild ist ein im Test mit Pillow erzeugtes 300×300-PNG in einer festen Farbe (`#d9822b`). Task 9 nutzt dieselbe Form für die Vorschaubilder.

- [ ] **Step 1: Browser-Tests schreiben** (alle `@pytest.mark.browser`; rendern mit `render_data(printer, mod.build(status, options, lang, NOW), renderer)`; Farbhelfer nach dem Muster `_near`/`_any_color` aus `pages/energy/test_energy.py`):
  - `test_every_mockup_state_renders` (parametrisiert über `MOCKUPS` × `de`/`en`): Bild 240×240, `len(jpeg) <= 24576`; im Kopfbereich (y < 34) ist bei `error` die Farbe `rgb(150,25,25)` zu finden, sonst `rgb(0,55,110)`.
  - `test_state_colours`: `printing` → Grün (`rgb(60,200,110)`) im Balkenbereich y 150–158, Balken endet bei x ≈ 8 + 224 · 0,47 (Pixel bei x = 100 grün, bei x = 130 nicht); `paused` → dort Orange, kein Grün im Bild; `error` → Rot; `finished` → Balken bei x = 225 grün.
  - `test_thumbnail_is_drawn_and_missing_one_leaves_no_box`: mit Bild liegt im Rechteck (8, 42)–(108, 142) die Bildfarbe; im Fall `plain` gibt es dort keinen Pixel in dieser Farbe und die Prozentzahl beginnt links (heller Pixel bei x < 60, y 60–110).
  - `test_texts_fit_without_ellipsis` (Muster `test_status_line_fits_without_ellipsis` in `pages/energy/test_energy.py`: HTML mit `_jinja_env`, Playwright direkt, `scrollWidth > clientWidth` je Element): für alle `MOCKUPS` in `de` und `en`, dazu die Grenzfälle `100 %`, `noch 23:59 h`, `fertig Mo 07:40`, `Schicht 1234/1234`, Temperaturen `285°/285` und `110°/110`, Label „Düse heizt“ / „Nozzle heating“, „Dauer 23:59 h“: kein Element außer dem Dateinamen und dem Titel läuft über; kein Element ragt über x = 240 oder y = 240 hinaus (`getBoundingClientRect`); Elemente der rechten Spalte beginnen bei x ≥ 116, wenn ein Bild da ist.
  - `test_long_filename_and_title_are_cut_not_wrapped`: Dateiname mit 80 Zeichen, Titel mit 60 → das Dateinamen-Element ist eine Zeile hoch (Höhe ≤ 16 px) und läuft über (`scrollWidth > clientWidth`); der Balken und die Temperaturzeile liegen an derselben Stelle wie ohne langen Namen.
  - `test_error_message_takes_at_most_three_lines`: Meldung mit 300 Zeichen → das Meldungs-Element ist höchstens 45 px hoch und endet über dem Balken (y < 150).
  - `test_heater_off_is_grey_and_shows_only_the_actual_value`: `finished` mit `nozzle=(48.0, None)` → im Temperaturbereich (y > 190) kein Orange; `idle` mit `nozzle=(142.0, 215.0)` → Orange vorhanden.
  - `test_offline_and_notice_states`: `offline` → kein Orange und kein Rot im Bild, Kopf blau; `notice` für `auth` → Orange vorhanden.
  - `test_same_data_renders_the_same_bytes`: wie in `energy` (bei ungleichen Bytes `pytest.xfail("renderer is not byte-stable; SKIP_UNCHANGED carries the 304")`).
- [ ] **Step 2: Fehlschlag prüfen.** Run: `.venv/bin/pytest -q -c pyproject.toml ../pages/printer -m browser` → FAIL (Template ist leer).
- [ ] **Step 3: `template.html` schreiben.** `{% extends "base.html" %}`, `{% import "ui.html" as ui %}`, Kopf `{{ ui.header(title, clock, alert) }}`. Maße aus der Mockup-Datei übernehmen (dort stehen sie als Inline-Styles): Bild `left:8px; top:42px; 100×100`, Rundung 6 px, `<img src="{{ thumb }}">` mit `object-fit:contain`; mit Bild rechte Spalte ab x = 116/118 (Label 13 px fett bei y 42, Prozent 34 px bei y 58, Hauptzeile 16 px fett bei y 98, kleine Zeilen 12 px bei y 118 und 133); ohne Bild Prozent 52 px links und Restzeit/Fertig-Uhrzeit rechtsbündig bis x = 232; Balken `left:8px; top:150px; 224×8`, Rundung 4 px, Füllung in der Farbe von `tone`; Dateiname 12 px bei y 164, eine Zeile, `text-overflow:ellipsis`; Trennlinie bei y 184; zwei Temperaturfelder ab y 192 (links x = 8, rechts x = 124, je 112 breit: Symbol 22 px, Wert 22 px fett, Soll 13 px grau als „/215“, Label 10 px). Symbole Düse und Bett als eigenes Inline-SVG wie in der Mockup-Datei (selbst gezeichnet). `idle`: „Bereit“ 30 px fett bei y 48, kleine Zeilen bei y 90 und 106, Notiz darunter, Temperaturen wie oben. `notice`: `{{ ui.notice(notice.message, notice.sub, notice.tone) }}`. Fehlt `big`, entfällt die Zahl; fehlt `bar`, entfällt der Balken; fehlen die Temperaturen, entfallen Trennlinie und Felder. Farben nur über die Variablen aus `base.html`. Kein `<script>`, kein nachgeladener Inhalt.
- [ ] **Step 4: Tests bestehen.** Run: `.venv/bin/pytest -q -c pyproject.toml ../pages/printer -m browser` → PASS. Passt ein Text nicht, Schrift oder Kasten im Template ändern, nicht den Test lockern. Danach `.venv/bin/pytest -q -m "not browser" && .venv/bin/ruff check . ../pages` → PASS.
- [ ] **Step 5: Ansehen.** Für die sieben `MOCKUPS` (Deutsch) je ein Bild ins Scratchpad der Sitzung rendern, mit Read ansehen und neben die Mockup-Datei halten: Anordnung, Größenverhältnisse und Farben stimmen überein. Abweichungen im Bericht nennen.
- [ ] **Step 6: `pages/printer/README.md`** (Englisch): Beispiel-YAML mit allen Optionen aus dem Abschnitt „Konfiguration (vollständig)“ der Spec, die Haken `DEFAULT_REFRESH`/`MIN_REFRESH`/`SKIP_UNCHANGED`, der Provider-Vertrag, das Schema `PrinterStatus`, die Zustandsregeln (`settle`, Gedächtnis nur im Speicher), die Fehlerarten von `SourceError` und ihre Anzeige, der Weg des Bildes (Quelle → Pillow → Data-URI, der Renderer lädt nichts nach).
- [ ] **Step 7: Commit** — `git add pages/printer/template.html pages/printer/README.md pages/printer/test_printer.py`, Nachricht `feat(pages): printer page layout for all states`.

---

### Task 5: Quelle `moonraker`

**Files:**
- Create: `pages/printer/providers/moonraker.py`
- Create: `pages/printer/fixtures/README.md`, `pages/printer/fixtures/moonraker_query_printing.json`, `moonraker_metadata.json`, `moonraker_history.json`
- Modify: `pages/printer/page.py` (`PROVIDERS["moonraker"]`), `pages/printer/README.md`
- Test: `pages/printer/test_printer_moonraker.py`, `pages/printer/test_printer_common.py` (Fixture-Wächter)

**Interfaces:**
- Consumes: `glancebox.http.get_json(…, auth=None)`, `get_bytes` (Task 1); `_common` (Task 2); Provider-Vertrag (Task 3).
- Produces: `NAME = "Moonraker"`, `KEYS = ("api_key",)`, `validate`, `fetch`, dazu rein rechnend und einzeln getestet:

  ```python
  QUERY = "webhooks&print_stats&virtual_sdcard&display_status&extruder&heater_bed&gcode_move"
  def progress(status: dict, meta: dict | None) -> float | None            # 0..100
  def remaining(status: dict, meta: dict | None, percent: float | None) -> int | None
  def layer(status: dict, meta: dict | None) -> tuple[int, int | None] | None
  def pick_thumbnail(meta: dict | None) -> str | None                      # relative_path
  def file_url(base: str, filename: str, relative_path: str) -> str
  ```

- [ ] **Step 1: Fixtures anlegen.** Antworten in der Form der Moonraker-Doku (`{"result": {"status": {…}, "eventtime": …}}`, `{"result": {…}}`, `{"result": {"count": 1, "jobs": [{…}]}}`), Felder laut Spec-Abschnitt „`source: moonraker`“. Zahlen der Druck-Fixture: `print_stats.state "printing"`, `filename "benchy_0.2mm_PLA.gcode"`, `print_duration 4800.0`, `total_duration 4925.0`, `info {"current_layer": null, "total_layer": null}`; `virtual_sdcard.file_position 95000`, `progress 0.45`; `display_status.progress 0.46`; `extruder {"temperature": 214.2, "target": 215.0}`; `heater_bed {"temperature": 60.0, "target": 60.0}`; `gcode_move.gcode_position [120.0, 95.0, 22.4, 1830.5]`; `webhooks {"state": "ready", "state_message": "Printer is ready"}`. Metadaten: `gcode_start_byte 1000`, `gcode_end_byte 201000`, `estimated_time 10000`, `layer_height 0.2`, `first_layer_height 0.2`, `object_height 48.0`, kein `layer_count`, `thumbnails` mit 32×32, 300×300 und 400×300 (`relative_path ".thumbs/benchy_0.2mm_PLA-300x300.png"`). History: ein Job `status "completed"`, `filename "benchy_0.2mm_PLA.gcode"`, `end_time 1795551240.0` (2026-11-24 21:14 Europe/Berlin), `total_duration 11520.0`. `fixtures/README.md`: Tabelle Datei · abgeleitet aus (Moonraker master b559b9a8 `docs/external_api/…`, Klipper 7558e8c2 `docs/Status_Reference.md`) · „not captured from a device“.
- [ ] **Step 2: Tests schreiben** (`test_printer_moonraker.py`, Adressen über `route`, Basis `http://drucker.local:7125`):

```python
def test_progress_is_file_relative(mk, load):
    st = load("moonraker_query_printing")["result"]["status"]
    meta = load("moonraker_metadata")["result"]
    assert mk.progress(st, meta) == pytest.approx(47.0)          # (95000-1000)/(201000-1000)
    assert mk.progress(st, None) == pytest.approx(46.0)          # display_status
    del st["display_status"]
    assert mk.progress(st, None) == pytest.approx(45.0)          # virtual_sdcard


def test_remaining_is_the_mean_of_both_estimates(mk, load):
    st = load("moonraker_query_printing")["result"]["status"]
    meta = load("moonraker_metadata")["result"]
    assert mk.remaining(st, meta, 47.0) == 5306      # mean of 5200 (slicer) and 5412.77 (file)
    assert mk.remaining(st, None, 47.0) == 5413      # file estimate only
    assert mk.remaining(st, meta, 0.5) == 5200       # below 1 %: slicer only
    assert mk.remaining(st, None, 0.5) is None
    assert mk.remaining(st, {"estimated_time": 0}, None) is None


def test_layer_fallback_like_mainsail(mk, load):
    st = load("moonraker_query_printing")["result"]["status"]
    meta = load("moonraker_metadata")["result"]
    assert mk.layer(st, meta) == (112, 240)
    st["print_stats"]["info"] = {"current_layer": 7, "total_layer": 90}
    assert mk.layer(st, meta) == (7, 90)
    assert mk.layer(load("moonraker_query_printing")["result"]["status"], None) is None


def test_pick_thumbnail(mk):
    t = lambda w, p: {"width": w, "height": w, "size": 1, "relative_path": p}  # noqa: E731
    assert mk.pick_thumbnail({"thumbnails": [t(32, "a"), t(300, "b"), t(400, "c")]}) == "b"
    assert mk.pick_thumbnail({"thumbnails": [t(400, "c"), t(640, "d")]}) == "c"
    assert mk.pick_thumbnail({"thumbnails": [t(48, "x.jpg"), t(32, "a.png")]}) == "a.png"
    assert mk.pick_thumbnail({"thumbnails": []}) is None and mk.pick_thumbnail(None) is None
```

  Dazu:
  - `test_fetch_printing`: Query, Metadaten und Bild über `route` → `PrinterStatus` mit `state "printing"`, `progress ≈ 47`, `remaining_s == 5306`, `filename == "benchy_0.2mm_PLA"`, `nozzle == (214.2, 215.0)`, `bed == (60.0, 60.0)`, `layer == (112, 240)`, `thumbnail.mime == "image/png"`; aufgerufen wurden genau `/printer/objects/query?<QUERY>`, `/server/files/metadata` (mit `params={"filename": "benchy_0.2mm_PLA.gcode"}`) und `/server/files/gcodes/.thumbs/benchy_0.2mm_PLA-300x300.png` (mit `max_bytes == 524288`); die History nicht.
  - `test_metadata_and_thumbnail_once_per_file`: zweiter `fetch` ruft nur die Query.
  - `test_new_print_of_same_filename_reloads_metadata` (Review Focus 5): `printing` → `complete` → `printing` mit gleichem Namen, die Metadaten liefern jetzt `estimated_time 20000` → drittes Ergebnis rechnet mit 20000.
  - `test_filename_with_space_hash_umlaut_and_folder` (Review Focus 1): `filename "Teile/Halter #2 groß.gcode"`, `relative_path ".thumbs/Halter #2 groß-300x300.png"` → Metadaten mit `params={"filename": "Teile/Halter #2 groß.gcode"}`; Bildadresse `…/server/files/gcodes/Teile/.thumbs/Halter%20%232%20gro%C3%9F-300x300.png`; `status.filename == "Halter #2 groß"`. Dazu `file_url` direkt für eine Datei im Wurzelordner (kein doppelter `/`).
  - `test_print_states` (parametrisiert): `standby` → idle; `paused` → paused; `complete` → finished; `cancelled` → idle; `error` mit `message "Heater extruder not heating at expected rate"` → error mit dieser Meldung.
  - `test_klippy_not_ready`: `webhooks.state "shutdown"`/`"error"` → `error` mit `state_message`; `"startup"` → `offline` mit `message` „Klipper startet“ / „Klipper is starting“.
  - `test_finished_reads_history`: `complete` → `/server/history/list` mit `params={"limit": 1, "order": "desc"}`; `ended_at` = `end_time` als Zeit in der Zone von `ctx.now`, `duration_s == 4925` (aus `print_stats.total_duration`); History-Job mit anderem Dateinamen → `ended_at is None`.
  - `test_idle_shows_last_completed_job`: `standby` + History `completed` → `last_job == ("benchy_0.2mm_PLA", Ende)`; History `cancelled` → `None`.
  - `test_history_component_off`: History antwortet 404 → Zustand bleibt, `ended_at`/`last_job` leer, kein Fehler.
  - `test_missing_objects_do_not_break`: Query ohne `heater_bed`, `display_status`, `gcode_move` bzw. mit `{}` dafür → `bed is None`, sonst wie zuvor; Metadaten 404 oder Bild 404/`ValueError` → Druck ohne Bild und mit Fallback-Fortschritt 45/46.
  - `test_thumbnail_false_skips_the_download`: `{"thumbnail": False}` → kein Aufruf von `get_bytes`.
  - `test_api_key_header`: mit `api_key` trägt jeder Aufruf `X-Api-Key`; ohne keinen solchen Kopf.
  - `test_wrong_key_is_auth` (Review Focus 2): Query 401 → `SourceError` mit `kind == "auth"`; `ConnectionError`/`Timeout` → `kind == "offline"`; Status 500 oder eine Liste statt eines Objekts → `kind == "data"`.
  - `test_calls_share_the_time_budget`: `time.monotonic` wie in `_timed` (`pages/energy/test_energy.py`) → jeder Timeout ≤ 5; ist nach der Query das Budget verbraucht, kommt der Status ohne Metadaten und Bild zurück.
  - `test_validate`: `api_key: 5` und `api_key: ""` → `ValueError`; über die Seite: `token` bei `source: moonraker` wird abgelehnt.
  - `test_key_never_logged`: 401, `ConnectionError`, `requests.exceptions.InvalidHeader("X-Api-Key: S3CRET")` über `printer.fetch` → `S3CRET` in keiner Logzeile.
  - In `test_printer_common.py`: `test_every_fixture_is_listed_and_anonymous`: jede `fixtures/*.json` steht in `fixtures/README.md`; keine enthält eine IPv4-Adresse (`\b\d{1,3}(\.\d{1,3}){3}\b`), ein `@` gefolgt von einer Domain oder einen anderen Host als `drucker.local` / `homeassistant.lan`.
- [ ] **Step 3: Fehlschlag prüfen.** Run: `.venv/bin/pytest -q -c pyproject.toml ../pages/printer -m "not browser"` → FAIL.
- [ ] **Step 4: `moonraker.py` schreiben.** Kopfkommentar nach dem Muster von `pages/ai/providers/copilot.py`: Endpunkte, gelesene Felder, Quellen mit Stand aus dem Spec-Anhang, und der Satz „Derived from documentation and source code; not yet checked against a device.“ (Task 12 ändert ihn). Formeln:

  ```python
  # progress: (file_position - gcode_start_byte) / (gcode_end_byte - gcode_start_byte), clamped 0..1,
  #   when both bytes are known and end > start; else display_status.progress; else
  #   virtual_sdcard.progress.
  # remaining: slicer = estimated_time - print_duration (when estimated_time > 0);
  #   file = print_duration / (percent / 100) - print_duration (when percent >= 1);
  #   mean of those present, never below 0, rounded.
  # layer total: info.total_layer, else metadata layer_count, else
  #   ceil((object_height - first_layer_height) / layer_height + 1).
  # layer current: info.current_layer, else (only when print_duration > 0)
  #   ceil((gcode_position.z - first_layer_height) / layer_height + 1), clamped 0..total.
  #   Round the quotient to 4 decimals before ceil (22.2 / 0.2 is 110.99999999999999).
  ```

  Bildadresse: `<url>/server/files/gcodes/<dirname(filename)>/<relative_path>`, jeder Pfadteil mit `urllib.parse.quote(teil, safe="")`. Bild über `_common.cached_thumbnail(("moonraker", url, filename), …)`; Metadaten und der letzte `print_stats.state` je `url` in einem Dict auf Modulebene (Entscheidung 13). `page.py`: `PROVIDERS["moonraker"] = moonraker`.
- [ ] **Step 5: Tests bestehen.** Run: `.venv/bin/pytest -q -m "not browser" && .venv/bin/ruff check . ../pages` → PASS.
- [ ] **Step 6: `pages/printer/README.md`:** Abschnitt „moonraker“ (Aufrufe, Formeln, Zustandstabelle, was zwischengespeichert wird). **Commit** — alle Dateien dieser Task einzeln hinzufügen, Nachricht `feat(pages): printer source moonraker`.

---

### Task 6: Quelle `hass` mit Vorlagen

**Files:**
- Create: `pages/printer/providers/hass.py`
- Create: `pages/printer/fixtures/hass_moonraker.json`, `hass_octoprint.json`, `hass_prusalink.json`, `hass_bambu_lab.json`, `hass_creality.json` (je ein Dict `entity_id → Antwort von /api/states/<id>` für einen laufenden Druck); `fixtures/README.md` ergänzen
- Modify: `pages/printer/page.py` (`PROVIDERS["hass"]`), `server/glancebox/addon.py` (`ha_defaults.page_defaults`), `pages/printer/README.md`
- Test: `pages/printer/test_printer_hass.py`, `server/tests/test_addon.py`

**Interfaces:**
- Consumes: `glancebox.hass.validate_connection(options)`, `entity_id(value)`, `state_url(base_url, entity)`, `get_state(url, token, timeout)`, `status_of(exc)`, `log_failure(page, url, exc)`; `glancebox.http.get_bytes`; `_common.Budget`, `source_error`, `number`, `clamp_progress`, `temp`, `clean_filename`, `cached_thumbnail`.
- Produces:

  ```python
  NAME = "Home Assistant"
  KEYS = ("token", "integration", "device", "entities", "states")
  FIELDS = ("state", "progress", "remaining", "eta", "filename", "nozzle", "nozzle_target",
            "bed", "bed_target", "layer", "layer_total", "thumbnail")

  @dataclass(frozen=True)
  class Preset:
      entities: dict[str, str]             # field -> "sensor.{d}_progress" or "sensor.{d}_x#attr"
      states: dict[str, tuple[str, ...]]   # schema state -> raw words
      default_device: str | None = None    # "octoprint" for the octoprint preset
      klippy: str | None = None            # moonraker only: "sensor.{d}_printer_state"
      finished_at_100: bool = False        # octoprint: operational + progress >= 100

  PRESETS: dict[str, Preset]               # moonraker, octoprint, prusalink, bambu_lab, creality

  class Ref(NamedTuple):
      entity: str
      attribute: str | None

  def refs(options: dict) -> dict[str, Ref]           # preset with device, then entities: on top
  def words(options: dict) -> dict[str, str]          # raw word (lower case) -> schema state
  def seconds(value: float, unit: str | None) -> int | None      # s, min, h, d; None otherwise
  def status_from(states: dict[str, dict | None], options: dict, now: datetime) -> PrinterStatus
  def image_url(base_url: str, entity: str) -> str | None
  def validate(options: dict) -> None
  def fetch(options: dict, ctx) -> PrinterStatus
  ```

- [ ] **Step 1: Fixtures anlegen.** Entitäts-IDs genau nach der Vorlagen-Tabelle der Spec mit `device` `voron` (moonraker), Standard `octoprint`, `mk4` (prusalink), `x1c` (bambu_lab), `k1` (creality). Jede Antwort hat `entity_id`, `state`, `attributes` (mit `unit_of_measurement`, wo die Integration eine setzt), `last_changed`. In allen fünf: Fortschritt `"47.0"`, Datei `benchy_0.2mm_PLA.gcode`, Düse 214.2/215, Bett 60/60, Schicht 112/240, wo die Vorlage eine kennt. Einheiten der Restzeit: moonraker und bambu_lab `h` (`"1.38"`), creality `s` (`"4980"`); ETA als ISO-8601 mit Zeitzone (`"2026-11-25T14:55:00+00:00"`); Creality: Attribut `file` am Zustands-Sensor, Attribut `target` an den Temperatursensoren. `fixtures/README.md`: je Datei die Quelle mit Version aus dem Spec-Anhang (moonraker-home-assistant v1.14.0, HA core dev `components/octoprint` 5f380806 und `components/prusalink` 8dbdb49d, ha-bambulab v2.4.1, ha_creality_ws v0.9.10) und „not captured from a Home Assistant instance“.
- [ ] **Step 2: Tests schreiben** (`test_printer_hass.py`; `OPT = {"source": "hass", "url": "http://homeassistant.lan:8123", "token": "t0ken"}`):

```python
@pytest.mark.parametrize(("integration", "device", "expect"), [
    ("moonraker", "voron", dict(remaining_s=4968, layer=(112, 240), nozzle=(214.2, 215.0))),
    ("octoprint", None, dict(remaining_s=None, layer=None, nozzle=(214.2, 215.0))),
    ("prusalink", "mk4", dict(remaining_s=None, layer=None, nozzle=(214.2, 215.0))),
    ("bambu_lab", "x1c", dict(remaining_s=4968, layer=(112, 240), nozzle=(214.2, 215.0))),
    ("creality", "k1", dict(remaining_s=4980, layer=(112, 240), nozzle=(214.2, 215.0))),
])
def test_presets_read_a_running_print(ha, load, integration, device, expect):
    options = {**OPT, "integration": integration, **({"device": device} if device else {})}
    status = ha.status_from(load(f"hass_{integration}"), options, NOW)
    assert (status.state, status.progress, status.filename) == ("printing", 47.0, "benchy_0.2mm_PLA")
    assert status.bed == (60.0, 60.0)
    for name, value in expect.items():
        assert getattr(status, name) == value


def test_seconds(ha):
    assert [ha.seconds(1.38, "h"), ha.seconds(83, "min"), ha.seconds(4980, "s"),
            ha.seconds(1.5, "d")] == [4968, 4980, 4980, 129600]
    assert ha.seconds(83, None) is None and ha.seconds(83, "%") is None
    assert ha.seconds(-5, "min") is None
```

  Dazu:
  - `test_preset_entity_ids` (parametrisiert, eine Zeile je Integration): `refs(options)` gleicht Feld für Feld der Vorlagen-Tabelle der Spec (alle zwölf Felder, fehlende als nicht vorhanden; Creality `filename == Ref("sensor.k1_print_status", "file")`, `nozzle_target == Ref("sensor.k1_nozzle_temperature", "target")`; OctoPrint mit `device: octoprint_2` → `sensor.octoprint_2_current_state`).
  - `test_state_words` (parametrisiert über jede Zelle der Zustandswörter-Tabelle der Spec): Rohwort → Schema-Zustand, auch mit Großbuchstaben und Leerzeichen am Rand (`" Printing "`).
  - `test_octoprint_finished_is_operational_at_100`: `operational` + `job_percentage "100"` → finished; `operational` + `"47"` → idle; `operational` ohne Fortschritts-Sensor → idle.
  - `test_moonraker_klippy_overrides`: `sensor.voron_printer_state` `shutdown`/`error` → error; `startup` → offline; `ready` → der Druckzustand gilt; Sensor fehlt (404) → der Druckzustand gilt.
  - `test_unavailable_and_unknown_state_is_offline` (Entscheidung 8), je Integration.
  - `test_unknown_word_is_idle_with_the_raw_word`: `"calibrating_extrusion"` → `state "idle"`, `message == "calibrating_extrusion"`; `caplog` hat genau eine Warnung mit dem Wort, auch nach drei Aufrufen.
  - `test_states_option_adds_and_overrides`: `states: {"printing": ["calibrating_extrusion"], "idle": ["finish"]}` bei `bambu_lab` → das neue Wort druckt, `finish` ist jetzt idle, `running` druckt weiter.
  - `test_custom_integration`: `integration: custom`, `entities: {"state": "sensor.mein_status", "progress": "sensor.mein_fortschritt"}`: Schema-Wörter (`printing`, `paused`, …) gelten ohne `states:`; mit `states: {"printing": ["running", "busy"], "finished": ["done"]}` gelten diese zusätzlich.
  - `test_entities_override_one_field`: bei `moonraker` `entities: {"nozzle_target": "sensor.voron_ziel#temperature"}` → dieser Ref, alle anderen aus der Vorlage.
  - `test_optional_fields_missing_or_unavailable`: jedes Feld außer `state` einzeln als 404 (`None`) und als `unavailable`/`unknown` → dieses Feld ist `None`, der Zustand bleibt `printing` (PrusaLink-Temperatursensoren deaktiviert = 404 → `nozzle is None`).
  - `test_stale_eta_is_dropped` (Review Focus 4): ETA vor `now` → `eta is None`, `remaining_s is None`; ETA `"unknown"` oder kein ISO-Text → `None`; ETA ohne Zeitzone → als Zeit in der Zone von `now`.
  - `test_remaining_without_unit_is_not_used`; `test_progress_garbage`: `"104"` → 100.0, `"-1"` → 0.0, `"nan"` → `None`.
  - `test_state_since_is_last_changed`: `last_changed "2026-11-25T13:05:00+00:00"` → `state_since` 14:05 Ortszeit; kaputter Text → `None`.
  - `test_fetch_calls_each_entity_once_then_the_image` (über `route`): bei `moonraker` 12 Aufrufe von `/api/states/…` (elf Felder und der Klippy-Sensor; bei `creality` jede Entität nur einmal, obwohl mehrere Felder sie teilen), Kopf `Authorization: Bearer t0ken`, danach genau ein `get_bytes` auf `http://homeassistant.lan:8123/api/camera_proxy/camera.voron_thumbnail`; `bambu_lab` → `/api/image_proxy/image.x1c_cover_image`; `octoprint` → kein Bildabruf; Bildfehler (500, `ValueError`) → Status ohne Bild.
  - `test_no_image_when_idle_or_disabled`: Zustand idle/offline oder `thumbnail: False` → kein `get_bytes`.
  - `test_missing_state_entity_is_a_config_error`: 404 am Zustands-Sensor → `SourceError` mit `kind == "config"`, `detail == "Entität fehlt: sensor.voron_current_print_state"` (en: `"Entity missing: …"`).
  - `test_token_rejected_and_unreachable`: 401/403 → `kind == "auth"`; `ConnectionError`, `Timeout`, 500, Liste statt Objekt → `kind == "unreachable"`.
  - `test_budget_like_energy`: je Aufruf ≤ 5 s; Uhr mit 2 s je Aufruf → nach dem achten Aufruf `SourceError("unreachable")`; Uhr mit 1,1 s je Aufruf → alle 12 gelesen, das Bild entfällt (weniger als 2 s übrig), der Status kommt.
  - `test_validate_ok` und `test_validate_rejects` (parametrisiert): ohne `token`; ohne `integration`; `integration: elegoo`; ohne `device` bei `moonraker`, `prusalink`, `bambu_lab`, `creality`; `device: "Voron 2"`; `entities` kein Mapping; unbekanntes Feld `entities: {"temp": …}` (Meldung nennt die erlaubten Namen); `entities: {"state": "Sensor.X"}`; `custom` ohne `entities.state`; `states` kein Mapping, unbekannter Schema-Zustand `states: {"done": […]}`, Wert keine Liste von Texten. Gültig: `octoprint` ohne `device`; `custom` mit und ohne `device` (Entscheidung 9); `entities` mit `#attribut`.
  - `test_token_never_logged`: wie `pages/energy/test_energy.py::test_token_never_logged`.
  - In `server/tests/test_addon.py`: `test_ha_defaults_fill_printer_with_source_hass`: `{"type": "printer", "source": "hass", "integration": "moonraker", "device": "voron"}` bekommt `http://supervisor/core` und den Supervisor-Token; eine mit eigenem `url`/`token` behält sie; `{"type": "printer", "source": "moonraker", "url": "http://drucker.local:7125"}` bleibt unverändert und bekommt **kein** `token`.
- [ ] **Step 3: Fehlschlag prüfen.** Run: `.venv/bin/pytest -q -c pyproject.toml ../pages/printer tests/test_addon.py -m "not browser"` → FAIL.
- [ ] **Step 4: `hass.py` schreiben.** `PRESETS` wörtlich aus den beiden Tabellen der Spec (Abschnitt „`source: hass` (Vorlagen)“); `{d}` wird durch `device` ersetzt, bei `octoprint` ersetzt `device` das Präfix `octoprint`. `words`: Schema-Wörter als sie selbst, darüber die Tabelle der Vorlage, darüber `states:`. `fetch`: Reihenfolge Zustand, Klippy, dann die übrigen Felder in der Reihenfolge von `FIELDS`, Bild zuletzt; 404 am Zustand → `config`, 404 sonst → Feld fehlt; Bild über `cached_thumbnail(("hass", url, entity, filename), …)`, ohne Dateinamen ungepuffert. `image_url`: Domäne `camera` → `/api/camera_proxy/<id>`, `image` → `/api/image_proxy/<id>`, sonst `None`. Kopfkommentar: Quellen mit Version, und „Derived from the integrations' source code; not checked against a Home Assistant instance.“
- [ ] **Step 5: `addon.py`.** In `ha_defaults.page_defaults` gilt der Zweig für `homeassistant`/`energy` auch für `kind == "printer" and page.get("source") == "hass"`. `page.py`: `PROVIDERS["hass"] = hass`.
- [ ] **Step 6: Tests bestehen.** Run: `.venv/bin/pytest -q -m "not browser" && .venv/bin/ruff check . ../pages` → PASS.
- [ ] **Step 7: README-Abschnitt „hass“** (Vorlagen, Zuordnung, `#attribut`, Einheiten). **Commit** — Nachricht `feat(pages): printer source hass with presets for five integrations`.

---

### Task 7: Quelle `octoprint`

**Files:**
- Create: `pages/printer/providers/octoprint.py`, `pages/printer/fixtures/octoprint_job_printing.json`, `octoprint_printer_printing.json`, `octoprint_file_v1.json`, `octoprint_file_v2.json`; `fixtures/README.md` ergänzen
- Modify: `pages/printer/page.py` (`PROVIDERS["octoprint"]`), `pages/printer/providers/_common.py` (`same_host_url`), `pages/printer/README.md`
- Test: `pages/printer/test_printer_octoprint.py`, `pages/printer/test_printer_common.py`

**Interfaces:**
- Consumes: wie Task 5.
- Produces: `NAME = "OctoPrint"`, `KEYS = ("api_key",)`, `validate` (`api_key` Pflicht), `fetch`, `state_of(flags: dict, completion: float | None, has_file: bool) -> str`, und in `_common.py` `same_host_url(base: str, ref: str) -> str | None`.

- [ ] **Step 1: Fixtures** nach OctoPrint 2.0.2 `docs/api/job.rst`, `printer.rst`, `datamodel.rst` (alte Antwortform, ohne `X-OctoPrint-Api-Version`): `/api/job` mit `job.file {"name": "benchy_0.2mm_PLA.gcode", "path": "Teile/benchy_0.2mm_PLA.gcode", "origin": "local"}`, `progress {"completion": 47.0, "printTime": 4800, "printTimeLeft": 4980}`, `state "Printing"`; `/api/printer` mit `temperature.tool0 {"actual": 214.2, "target": 215.0}`, `temperature.bed {"actual": 60.0, "target": 60.0}`, `state.flags` (alle sieben Flags der Spec plus `cancelling`, `finishing`). Datei-Antworten: `octoprint_file_v1.json` mit `"thumbnail": "plugin/prusaslicerthumbnails/thumbnail/benchy_0.2mm_PLA.png?20261125140500"` (Plugin 1.2.4), `octoprint_file_v2.json` mit `refs.thumbnail`.
- [ ] **Step 2: Tests schreiben:**
  - `test_state_of` (parametrisiert): `error` oder `closedOrError` → error; `paused`/`pausing` → paused; `cancelling` → idle; `printing`/`finishing` → printing; `operational` + `completion >= 100` + Datei → finished; `operational` + 100 ohne Datei → idle; `operational`/`ready` → idle; kein Flag gesetzt → offline. Vorrang in dieser Reihenfolge (`error` und `printing` zugleich → error).
  - `test_fetch_printing`: beide Aufrufe mit `X-Api-Key`, `/api/printer` mit `params={"exclude": "sd"}`; Ergebnis `printing`, `progress 47.0`, `remaining_s 4980`, `filename "benchy_0.2mm_PLA"`, Temperaturen, `layer is None`; kein Kopf `X-OctoPrint-Api-Version`.
  - `test_printer_409_is_offline`: `/api/printer` → 409 → `PrinterStatus("offline")` (kein `SourceError`); `/api/job` wird dann nicht mehr gebraucht.
  - `test_finished_has_duration`: `operational`, `completion 100.0`, `printTime 11520` → `finished`, `duration_s == 11520`, `ended_at is None` (die Seite merkt sich das erste Sehen, Task 3).
  - `test_error_message`: `state.flags.error` mit `job["error"] == "Too many consecutive timeouts"` → `message` trägt den Text; ohne ihn `None`.
  - `test_thumbnail_v1_and_v2`: Datei-Aufruf `/api/files/local/Teile/benchy_0.2mm_PLA.gcode` (Pfadteile kodiert); v1 → Bild von `<url>/plugin/prusaslicerthumbnails/thumbnail/benchy_0.2mm_PLA.png?20261125140500`; v2 → Bild vom Pfad aus `refs.thumbnail`; beide mit `X-Api-Key` und `max_bytes == 524288`.
  - `test_no_thumbnail`: Datei-Antwort ohne beide Felder, `origin: "sdcard"`, Datei-Aufruf 404, `thumbnail: False` → kein Bild, Zustand bleibt; bei `sdcard` und `thumbnail: False` kein Datei-Aufruf.
  - `test_thumbnail_reference_must_stay_on_the_printer`: `refs.thumbnail == "http://example.org/x.png"` oder `"//example.org/x.png"` → kein `get_bytes`; eine absolute Adresse mit demselben Schema, Host und Port wie `url` ist erlaubt.
  - `test_thumbnail_once_per_file`: zweiter `fetch` ohne Datei- und Bildaufruf.
  - `test_null_fields`: `progress.completion`, `printTimeLeft`, `job.file.name` und `temperature.bed` sind `null` bzw. fehlen → Felder `None`, kein Fehler.
  - `test_wrong_key_is_auth` (403 und 401), `ConnectionError` → `offline`, 500 → `data`; `test_validate` (ohne `api_key` → `ValueError`); `test_key_never_logged`.
- [ ] **Step 3: Fehlschlag prüfen**, dann **`octoprint.py` schreiben**. Bildverweise löst `_common.same_host_url` auf (relativer Pfad → an `base` gehängt; absolute Adresse nur bei gleichem Schema, Host und Port; `//host/…` und alles andere → `None`); ihr Test `test_same_host_url` steht in `test_printer_common.py`. Kopfkommentar mit Quellen und „Derived from the documentation; not yet run against OctoPrint.“ (Task 11 ändert ihn). `page.py`: `PROVIDERS["octoprint"] = octoprint`.
- [ ] **Step 4: Tests bestehen.** Run: `.venv/bin/pytest -q -m "not browser" && .venv/bin/ruff check . ../pages` → PASS.
- [ ] **Step 5: README-Abschnitt „octoprint“.** **Commit** — Nachricht `feat(pages): printer source octoprint`.

---

### Task 8: Quelle `prusalink`

**Files:**
- Create: `pages/printer/providers/prusalink.py`, `pages/printer/fixtures/prusalink_status_printing.json`, `prusalink_job_printing.json`; `fixtures/README.md` ergänzen
- Modify: `pages/printer/page.py` (`PROVIDERS["prusalink"]`), `pages/printer/README.md`
- Test: `pages/printer/test_printer_prusalink.py`

**Interfaces:**
- Consumes: wie Task 5, dazu `auth=` an `get_json`/`get_bytes` (Task 1) und `_common.same_host_url` (Task 7).
- Produces: `NAME = "PrusaLink"`, `KEYS = ("api_key", "user", "password")`, `DEFAULT_USER = "maker"`, `STATE_MAP: dict[str, str]`, `validate`, `fetch`.

- [ ] **Step 1: Fixtures** nach Prusa-Link-Web `spec/openapi.yaml` und Prusa-Firmware-Buddy v8.0.2: `/api/v1/status` mit `printer {"state": "PRINTING", "temp_nozzle": 214.2, "target_nozzle": 215.0, "temp_bed": 60.0, "target_bed": 60.0}` und `job {"id": 12, "progress": 47.0, "time_remaining": 4980, "time_printing": 4800}`; `/api/v1/job` mit `file {"name": "BENCHY~1.BGC", "display_name": "benchy_0.2mm_PLA.bgcode", "path": "/usb", "refs": {"thumbnail": "/thumb/l/usb/BENCHY~1.BGC", "download": "/usb/BENCHY~1.BGC"}}`.
- [ ] **Step 2: Tests schreiben:**
  - `test_state_map` (parametrisiert): `PRINTING` → printing; `PAUSED` → paused; `FINISHED` → finished; `STOPPED`, `IDLE`, `READY`, `BUSY` → idle; `ERROR` → error; `ATTENTION` → paused mit `message` „Eingriff nötig“ / „Attention needed“; ein unbekanntes Wort (`"SERVICE"`) → idle mit `message == "SERVICE"` und einer Warnung im Log (einmal).
  - `test_fetch_printing`: `printing`, `progress 47.0`, `remaining_s 4980`, `filename == "benchy_0.2mm_PLA"` (aus `display_name`; fehlt er, aus `name`), Temperaturen, `layer is None`, Bild von `<url>/thumb/l/usb/BENCHY~1.BGC`.
  - `test_job_204_means_no_job`: `/api/v1/job` → `None` (204) bei `IDLE` → idle ohne Datei; bei `IDLE`/`READY` und bei `thumbnail: False` ohne laufenden Druck wird `/api/v1/job` trotzdem höchstens einmal je `fetch` gerufen.
  - `test_finished_has_duration`: `FINISHED`, `time_printing 11520` → `duration_s == 11520`.
  - `test_digest_auth_by_default`: mit `password: "geheim"` trägt jeder Aufruf (auch `get_bytes`) ein `requests.auth.HTTPDigestAuth` mit `username == "maker"`, mit `user: "robin"` diesen Namen; kein `X-Api-Key`.
  - `test_api_key_instead_of_password`: mit `api_key` Kopf `X-Api-Key`, `auth is None`.
  - `test_thumbnail_rules`: `refs.thumbnail` fehlt → kein Bild; Verweis auf fremden Host → kein Abruf; `get_bytes` wirft `ValueError` (QOI: Typ nicht `image/png`/`image/jpeg`) → kein Bild, Zustand bleibt; die Adresse wird nie aus dem Dateinamen gebaut (ohne `refs` kein `get_bytes`).
  - `test_missing_fields`: `status` ohne `job`, ohne `temp_bed`, `progress` `null` → Felder `None`.
  - `test_wrong_password_is_auth` (401/403), `ConnectionError` → `offline`, 500 → `data`.
  - `test_validate`: weder `password` noch `api_key` → `ValueError`; beide zugleich → `ValueError`; `user` ohne `password` → `ValueError`; `user: 5` → `ValueError`.
  - `test_password_never_logged`: `geheim` und der Key in keiner Logzeile (401, `ConnectionError`).
- [ ] **Step 3: Fehlschlag prüfen**, dann **`prusalink.py` schreiben**. Ein neues `HTTPDigestAuth` je `fetch` (es hält den Zustand des Handshakes). Kopfkommentar mit Quellen und „Derived from the OpenAPI description and firmware source; never run against a printer.“ `page.py`: `PROVIDERS["prusalink"] = prusalink`; die Reihenfolge in `PROVIDERS` ist jetzt `moonraker`, `octoprint`, `prusalink`, `hass` (so nennt sie die Fehlermeldung von `validate`).
- [ ] **Step 4: Tests bestehen.** Run: `.venv/bin/pytest -q -m "not browser" && .venv/bin/pytest -q -m browser && .venv/bin/ruff check . ../pages` → PASS.
- [ ] **Step 5: README-Abschnitt „prusalink“.** **Commit** — Nachricht `feat(pages): printer source prusalink`.

---

### Task 9: Vorschaubilder, Doku, CHANGELOG

**Files:**
- Modify: `tools/render_previews.py`; Create: `docs/img/templates/printer-printing.png`, `printer-finished.png`, `printer-error.png`, `printer-idle.png`
- Create: `docs/en/templates/printer.md`, `docs/de/templates/printer.md`
- Modify: `docs/en/templates/README.md`, `docs/de/templates/README.md`, `mkdocs.yml`, `docs/en/configuration.md`, `docs/de/configuration.md`, `docs/en/home-assistant.md`, `docs/de/home-assistant.md`, `docs/en/index.md`, `docs/de/index.md`
- Modify: `docs/en/writing-pages.md`, `docs/de/writing-pages.md`, `README.md`, `README.de.md`, `config-example.yaml`, `ha-addon/DOCS.md`, `CHANGELOG.md`
- Test: `server/tests/test_render_previews.py`

**Interfaces:**
- Consumes: `build` und `PrinterStatus` der Seite (Tasks 2 und 3).
- Produces: `tools/render_previews.py::sample_thumbnail() -> bytes` (ein selbst gezeichnetes 300×300-PNG: der Würfel aus der Mockup-Datei, Symbol `thumbimg`, mit `ImageDraw.polygon` aus dessen Koordinaten × 3) und die vier Einträge `SAMPLES["printer-…"]`.

- [ ] **Step 1: Test schreiben** (`test_render_previews.py`): `test_sample_thumbnail_is_a_small_own_drawing`: PNG, 300×300, enthält die Farben `#d9822b` und `#f2a24a`, `len(...) < 20000`; `test_printer_samples_build`: für jeden der vier Einträge liefert die Hilfsfunktion `_printer_data(options, sample)` Daten mit `view` `job`/`job`/`job`/`idle` und englischen Texten (`Printing`, `Finished`, `Error`, `Ready`).
- [ ] **Step 2: Fehlschlag prüfen**, dann **`render_previews.py` erweitern**: in `SAMPLES` steht für `printer` als drittes Element ein Dict mit den Feldern eines `PrinterStatus` (wie die `MOCKUPS` aus Task 4, Englisch, Uhr 14:32); `_printer_data` baut daraus über `sys.modules["glancebox_pages.printer"]` den Status und ruft `build` mit einer festen Zeit (Muster `_energy_data`); `render_all` bekommt den Zweig `elif ptype == "printer"`. Run: `.venv/bin/pytest -q tests/test_render_previews.py` → PASS.
- [ ] **Step 3: Bilder erzeugen.** Run (Repo-Wurzel des Worktrees): `server/.venv/bin/python tools/render_previews.py printer-printing printer-finished printer-error printer-idle`. Jedes mit Read ansehen. Die anderen PNGs nicht neu erzeugen (`git status` zeigt nur die vier neuen).
- [ ] **Step 4: `printer.md` in beiden Sprachen.** Überschriften in gleicher Folge: `# printer` · `## What it shows` / `## Was sie zeigt` · `## What you need` / `## Was du brauchst` · `## Example` / `## Beispiel` · `## Options` / `## Optionen` · `## Setup` / `## Einrichtung` (darunter `### Moonraker (Klipper)`, `### OctoPrint`, `### PrusaLink`, `### Home Assistant`) · `## Tested with` / `## Getestet mit` · `## When something is wrong` / `## Wenn etwas nicht stimmt`. Inhalt:
  - Was sie zeigt: die Zustände mit den vier Bildern; „Fertig“ nur `finished_for` Minuten, danach „Bereit“; die Frist beginnt nach einem Neustart des Servers neu, wenn die Quelle das Ende nicht kennt.
  - Beispiele: je Quelle ein kurzes YAML mit den Platzhaltern (`http://drucker.local:7125`, `${MOONRAKER_KEY}`, `${OCTOPRINT_KEY}`, `${PRUSALINK_PASSWORD}`, `${HA_URL}`/`${HA_TOKEN}`), im Add-on `source: hass` ohne `url`/`token`; Secrets in `.env` bzw. im Add-on unter `extra_secrets`.
  - Optionen: alle aus „Konfiguration (vollständig)“ der Spec; Tabelle der HA-Vorlagen (Integration, woher sie kommt: HACS oder Core, was sie liefert: Restzeit, Schicht, Bild) und der Feldnamen von `entities:`; `states:` mit dem Beispiel der Spec; `integration: custom` für andere Marken.
  - Einrichtung: Moonraker `trusted_clients` oder API-Key; OctoPrint Anwendungsschlüssel; PrusaLink Passwort im Drucker-Menü, Benutzer `maker`; HA: welche Integration, wie man das Präfix für `device:` in der Entitätsliste findet, bei PrusaLink die Temperatursensoren aktivieren, zweite OctoPrint-Instanz `device: octoprint_2`. Hinweis: Namen auf `.local` löst ein Docker-Container oft nicht auf, dann die Adresse `http://192.168.x.x:7125` eintragen.
  - Grenzen (aus den Nicht-Zielen): nur Werkzeug 0, kein Webcam-Bild, nur lesend, Bambu Lab und Creality nur über Home Assistant; OctoPrint und PrusaLink ohne Schicht; Bild bei OctoPrint 1.x nur mit dem Plugin „PrusaSlicer Thumbnails“.
  - **Getestet mit:** Tabelle Quelle · wie geprüft · Stand. Zu diesem Zeitpunkt jede Zeile wahrheitsgemäß: Moonraker direkt „nur mit nachgebauten Antworten (Fixtures), Gerätetest steht aus“; Moonraker-Simulator und OctoPrint-Simulator „noch nicht gelaufen“; PrusaLink, HA-Vorlagen moonraker, octoprint, prusalink, bambu_lab, creality „nur Fixtures aus Doku und Quellcode“, mit den Versionen aus dem Spec-Anhang und der Bitte um Rückmeldung aus der Community. Die Tasks 10 bis 12 ersetzen ihre Zeilen.
  - Wenn etwas nicht stimmt: „Drucker nicht erreichbar“ (aus, falsche Adresse, `.local`), „Zugang abgelehnt“, „Entität fehlt: …“, unbekannter Zustand als kleine Zeile → `states:`, kein Bild (Slicer schreibt keins, Plugin fehlt, Format), keine Restzeit (Einheit fehlt, Sensor deaktiviert).
- [ ] **Step 5: Übrige Doku.** Katalog (en, de): neuer Abschnitt `## 3D printing` / `## 3D-Druck` vor `## AI & development` mit `### printer`, Bild `printer-printing.png`, einem Satz, Link. `mkdocs.yml`: `- printer: templates/printer.md` nach `energy`. `configuration.md` (en, de): `printer` in der Typenliste, beim Schlüssel `refresh` das Beispiel um `printer`: Standard 10, mindestens 5 ergänzen, neuer Abschnitt `## Page type: printer` / `## Seitentyp: printer` nach dem zu `energy` mit kurzem Beispiel und Verweis. `home-assistant.md` (en, de) und `ha-addon/DOCS.md`: `printer` mit `source: hass` braucht weder `url` noch `token`; Schlüssel direkter Quellen über `extra_secrets`. `index.md` (en, de): eine Galerie-Karte mit `printer-printing.png` (gleiche Front-Matter-Schlüssel in beiden Dateien). `README.md`/`README.de.md`: in der Galerie-Tabelle eine neue Zeile mit zwei Kacheln (`printer`: Druckt, `printer`: Fertig), „Ready-made templates“ in den Highlights um den 3D-Drucker ergänzen; den Satz „Tested on a real SmallTV Ultra …“ nicht ändern. `config-example.yaml`: auskommentiertes Beispiel für `source: moonraker` und eine Zeile Verweis auf die anderen Quellen.
- [ ] **Step 6: `CHANGELOG.md`** unter `## [Unreleased]`: einleitender Absatz (Server-only, keine Firmware-Änderung), ein Absatz „Checked / Not checked“ mit demselben Stand wie die Tabelle, `### Added`: Seite `printer` mit Quellen und Optionen; `http.get_bytes` für eigene Seiten. Dazu in `docs/en/writing-pages.md` und `docs/de/writing-pages.md` beim Punkt zu `http.get_json` je einen Satz zu `http.get_bytes` (Größenlimit, nur PNG/JPEG).
- [ ] **Step 7: Prüfen.** Run: `python3 tools/check_docs_parity.py` → ok. `uv venv` im Scratchpad, `uv pip install -r requirements-docs.txt`, dann `NO_MKDOCS_2_WARNING=1 mkdocs build --strict` → baut (das erzeugte `site/` ist ignoriert). `grep -rnE "\b[0-9]{1,3}(\.[0-9]{1,3}){3}\b" docs/en/templates/printer.md docs/de/templates/printer.md pages/printer` → keine Treffer. Aus `server/`: `.venv/bin/pytest -q -m "not browser" && .venv/bin/pytest -q -m browser && .venv/bin/ruff check . ../pages` → PASS. Läuft Docker: das Test-Image aus den Global Constraints; sonst „Test-Image nicht geprüft“ in den Bericht.
- [ ] **Step 8: Commit** — alle Dateien einzeln hinzufügen, Nachricht `docs: printer page in the catalog, configuration reference, README gallery and changelog`.

---

### Task 10: Simulator-Lauf Moonraker (Docker, nur auf diesem Mac)

Kein neuer Code, außer ein Fehler zeigt sich. Jede Abweichung: zuerst ein Test mit einer Fixture in der beobachteten Form (anonymisiert), dann die Korrektur, eigener Commit `fix(pages): …`. `$S` ist das Scratchpad der Sitzung; nichts davon kommt ins Repo.

- [ ] **Step 1: Docker prüfen.** Run: `docker info --format '{{.ServerVersion}}'`. Scheitert das (am 2026-11-25 lief der Docker-Daemon nicht), den Nutzer bitten, Docker Desktop zu starten. Bleibt Docker aus: Tasks 10 und 11 enden hier, in der Doku-Tabelle steht „nicht geprüft (Docker nicht verfügbar)“.
- [ ] **Step 2: Virtuellen Drucker starten.**

  ```bash
  git clone --depth 1 https://github.com/mainsail-crew/virtual-klipper-printer "$S/vkp"
  git -C "$S/vkp" rev-parse --short HEAD          # in den Bericht
  printf 'services:\n  printer:\n    ports: !override\n      - "127.0.0.1:7125:7125"\n' > "$S/vkp/local.yml"
  docker compose -f "$S/vkp/docker-compose.yml" -f "$S/vkp/local.yml" up -d
  curl -s http://127.0.0.1:7125/server/info
  curl -s 'http://127.0.0.1:7125/printer/objects/query?webhooks&print_stats'
  ```

  Erwartet: `"klippy_state": "ready"` (kann eine Minute dauern) und `"state": "standby"`. Die Compose-Datei des Projekts nutzt das Image `ghcr.io/mainsail-crew/virtual-klipper-printer:latest`; den Digest (`docker image inspect … --format '{{index .RepoDigests 0}}'`) in den Bericht. Kennt die Compose-Version `!override` nicht, ohne `local.yml` starten (Port 7125 ist dann im LAN offen, solange der Container läuft) und das berichten. Antwortet Moonraker mit 401: in `$S/vkp/printer_data/config/moonraker.conf` unter `[authorization]` `trusted_clients` um das Docker-Netz ergänzen, Container neu starten, im Bericht nennen.
- [ ] **Step 3: Testdatei bauen und drucken.** Mit einem kurzen Python-Skript im Scratchpad eine G-Code-Datei `glancebox_probe.gcode` schreiben: Kopf `; generated by PrusaSlicer 2.8.0`, zwei Vorschaubilder im PrusaSlicer-Format (`; thumbnail begin 32x32 <len>` bzw. `300x300`, Base64-Zeilen zu höchstens 78 Zeichen, `; thumbnail end`; die Bilder aus `tools/render_previews.py::sample_thumbnail`), `G28`, dann 20 Schichten aus `;LAYER_CHANGE`, `;Z:<z>`, `G1 Z<z> F600` und vier `G1 X… Y… F1200`-Fahrten ohne Extrusion, dazwischen `G4 P3000`, Fuß `; estimated printing time (normal mode) = 2m 0s`, `; layer_height = 0.2`, `; first_layer_height = 0.2`. Hochladen und starten:

  ```bash
  curl -s -F "file=@$S/glancebox_probe.gcode" http://127.0.0.1:7125/server/files/upload
  curl -s 'http://127.0.0.1:7125/server/files/metadata?filename=glancebox_probe.gcode'
  curl -s -X POST 'http://127.0.0.1:7125/printer/print/start?filename=glancebox_probe.gcode'
  ```

  Erwartet: die Metadaten nennen `thumbnails` mit zwei Einträgen und `estimated_time`. Bricht der virtuelle Drucker den Druck ab, die Meldung notieren (sie ist zugleich die Probe für den Fehlerzustand) und die Datei anpassen.
- [ ] **Step 4: Seite gegen den Simulator.** `$S/sim.yaml` mit einer Seite `type: printer`, `source: moonraker`, `url: http://127.0.0.1:7125`, `finished_for: 2`. Run (aus `server/`): `.venv/bin/python -m glancebox render 0 -o "$S/moonraker-<zustand>.jpg" --config "$S/sim.yaml"`, je einmal und jedes Bild mit Read ansehen:
  - während des Drucks: „Druckt“, Prozent steigt zwischen zwei Aufrufen, Restzeit und Fertig-Uhrzeit plausibel, Schicht, Dateiname `glancebox_probe`, Vorschaubild, Temperaturen;
  - nach `curl -s -X POST http://127.0.0.1:7125/printer/print/pause`: „Pausiert“; nach `…/print/resume` wieder „Druckt“;
  - nach dem Ende: „Fertig“ mit Ende-Uhrzeit und Dauer. Der Übergang zu „Bereit“ mit „Zuletzt: glancebox_probe“ braucht einen laufenden Server (das Gedächtnis lebt im Prozess): `.venv/bin/python -m glancebox serve --config "$S/sim.yaml" --host 127.0.0.1 --port 8095`, nach gut 2 Minuten `curl -s -o "$S/moonraker-idle.jpg" http://127.0.0.1:8095/api/v1/frame`;
  - zweiter Druck mit `…/print/cancel` → „Bereit“, kein Fehler;
  - `curl -s -X POST http://127.0.0.1:7125/printer/emergency_stop` → roter Kopf mit der Meldung von Klippy; danach `curl -s -X POST http://127.0.0.1:7125/printer/firmware_restart`;
  - `docker compose … stop` → „Drucker nicht erreichbar“ in Grau, im Server-Log genau eine Zeile dazu.
  Zu jedem Punkt die rohe Antwort von `/printer/objects/query?<QUERY>` im Scratchpad ablegen und mit den Fixtures vergleichen (Feldnamen, `null`-Werte, fehlende Objekte).
- [ ] **Step 5: Aufräumen.** `docker compose -f "$S/vkp/docker-compose.yml" -f "$S/vkp/local.yml" down`; `docker ps` zeigt keinen Container `printer`.
- [ ] **Step 6: Festhalten.** In `docs/en/templates/printer.md` und `docs/de/templates/printer.md` die Zeile „Moonraker, Simulator“ mit Datum, Commit des Simulator-Repos und dem, was geprüft wurde (und was nicht: echte Heizkurven, History-Komponente falls aus, API-Key); denselben Stand in den Absatz „Checked / Not checked“ des CHANGELOG. `python3 tools/check_docs_parity.py` → ok. **Commit** — `docs(printer): Moonraker simulator run in the test table` (plus zuvor etwaige `fix(pages): …`-Commits).

---

### Task 11: Simulator-Lauf OctoPrint (Docker, nur auf diesem Mac)

Regeln wie in Task 10.

- [ ] **Step 1: OctoPrint mit Virtual Printer starten.**

  ```bash
  docker volume create gb-octoprint-sim
  docker run -d --name gb-octoprint-sim -p 127.0.0.1:5005:80 -v gb-octoprint-sim:/octoprint octoprint/octoprint:1.11.8
  ```

  Die Einrichtung (Benutzer, Anwendungsschlüssel) läuft über den Assistenten unter `http://127.0.0.1:5005`: einen Wegwerf-Benutzer anlegen, unter **Settings → Application Keys** einen Schlüssel erzeugen und als `OCTOPRINT_KEY` in `$S/sim.env` schreiben (nicht in den Bericht). Den Virtual Printer einschalten: **Settings → Virtual Printer → Enable**, dann verbinden:

  ```bash
  set -a; . "$S/sim.env"; set +a
  curl -s -H "X-Api-Key: $OCTOPRINT_KEY" -H 'Content-Type: application/json' -d '{"command":"connect","port":"VIRTUAL"}' http://127.0.0.1:5005/api/connection
  curl -s -H "X-Api-Key: $OCTOPRINT_KEY" 'http://127.0.0.1:5005/api/printer?exclude=sd'
  ```

  Erwartet: `state.flags.operational: true`. Lässt sich der Assistent in dieser Sitzung nicht bedienen (kein Browser-Werkzeug), den Nutzer um diese drei Klicks bitten; geht auch das nicht: „nicht geprüft“.
- [ ] **Step 2: Drucken.** `curl -s -H "X-Api-Key: $OCTOPRINT_KEY" -F "file=@$S/glancebox_probe.gcode" -F select=true -F print=true http://127.0.0.1:5005/api/files/local` (die Datei aus Task 10; fehlt sie, dort Step 3 nachholen). `$S/octo.yaml`: `source: octoprint`, `url: http://127.0.0.1:5005`, `api_key: ${OCTOPRINT_KEY}`, `finished_for: 2`.
- [ ] **Step 3: Seite prüfen** mit `python -m glancebox render` wie in Task 10 Step 4 (Umgebung aus `sim.env`): „Druckt“ mit Prozent, Restzeit, Temperaturen, ohne Schicht und (ohne Plugin) ohne Bild; `{"command":"pause","action":"pause"}` an `/api/job` → „Pausiert“; `"action":"resume"`; nach dem Ende „Fertig“ (OctoPrint bleibt `operational` bei 100 %) und im laufenden Server nach 2 Minuten „Bereit“; `{"command":"cancel"}` bei einem zweiten Druck → „Bereit“; `{"command":"disconnect"}` an `/api/connection` → 409 von `/api/printer` → „Drucker nicht erreichbar“; falscher Key → „Zugang abgelehnt“. Rohe Antworten von `/api/job` und `/api/printer` mit den Fixtures vergleichen.
- [ ] **Step 4: Bild mit Plugin (1.x).** Im Container `docker exec gb-octoprint-sim pip install "https://github.com/jneilliii/OctoPrint-PrusaSlicerThumbnails/archive/1.2.4.zip"`, `docker restart gb-octoprint-sim`, Datei neu hochladen, `GET /api/files/local/glancebox_probe.gcode` zeigt `thumbnail`; die Seite zeigt das Bild. Scheitert die Installation: „Bildweg mit Plugin nicht geprüft“.
- [ ] **Step 5: OctoPrint 2.0 (nur wenn es ohne Umstände startet).** In einer Venv im Scratchpad `uv pip install octoprint==2.0.2` und `octoprint serve --port 5006 --basedir "$S/octo2"`; gelingt das, Schritte 1 bis 3 in Kurzform und der Bildweg über `refs.thumbnail`. Gelingt es nicht innerhalb eines Versuchs: „OctoPrint 2.0 nicht geprüft, nur Fixtures“.
- [ ] **Step 6: Aufräumen.** `docker rm -f gb-octoprint-sim && docker volume rm gb-octoprint-sim`; `$S/sim.env` löschen.
- [ ] **Step 7: Festhalten** wie Task 10 Step 6 (Zeilen „OctoPrint 1.11.8, Simulator“, „OctoPrint 2.0“, Plugin-Bildweg), Kopfkommentar von `octoprint.py` an den Stand anpassen. **Commit** — `docs(printer): OctoPrint simulator run in the test table`.

---

### Task 12: Gerätetest mit dem Nutzer und Abschluss

Diese Task beginnt erst, wenn die Tasks 0 bis 11 fertig sind. Jeder Schritt mit **[Okay nötig]** beginnt mit der Frage an den Nutzer.

- [ ] **Step 1: Stand zusammenfassen** (für den Nutzer): Commits des Branches, was grün ist, Ergebnis der Simulator-Läufe, die Bilder aus Task 4 Step 5.
- [ ] **Step 2: [Okay nötig] Angaben erfragen.** Druckermodell; Adresse von Moonraker (kommt nur in `$S/device.yaml` oder `.env`, nie in Repo, Commit oder Bericht); Frontend (Mainsail oder Fluidd); ob Moonraker einen API-Key verlangt (dann in `.env` als `MOONRAKER_KEY`); ob und wo die HA-Integration für Moonraker (HACS) eingerichtet ist oder werden soll. Ohne Antwort: anhalten.
- [ ] **Step 3: [Okay nötig] Lesend gegen den echten Drucker.** Vom Mac aus, nur GET: `python -m glancebox render 0 -o "$S/device-<zustand>.jpg" --config "$S/device.yaml"` im Leerlauf, dann mit dem Nutzer während eines echten Drucks (Start, Mitte, Pause wenn er mag, Ende, „Fertig“ → „Bereit“ mit kleinem `finished_for`, Drucker aus). Je Zustand: Bild ansehen und neben das Frontend halten (Prozent, Restzeit und Schicht gegen Mainsail/Fluidd; Abweichung der Restzeit in Minuten notieren). Der Server läuft dafür lokal auf dem Mac; Heimserver und Display bleiben unberührt, außer der Nutzer wünscht es ausdrücklich.
- [ ] **Step 4: Abweichungen nacharbeiten.** Je Abweichung ein Test mit anonymisierter echter Antwort, dann die Korrektur (`fix(pages): …`). Eine echte Antwort von `/printer/objects/query`, `/server/files/metadata` und `/server/history/list` als `pages/printer/fixtures/moonraker_device_*.json` ablegen: Dateinamen ersetzt, keine Hostnamen, keine Seriennummern; `test_every_fixture_is_listed_and_anonymous` bleibt grün; in `fixtures/README.md` „captured from a device on <Datum>, anonymised“.
- [ ] **Step 5: [Okay nötig] Optional: über Home Assistant.** Nur wenn der Nutzer die Moonraker-Integration eingerichtet hat und einen Token bereitstellt (`.env`): dieselbe Probe mit `source: hass`, `integration: moonraker`; die echten Entitäts-IDs und Einheiten gegen die Vorlage halten, Abweichungen wie in Step 4. Sonst: „HA-Vorlage moonraker: nur Fixtures“ bleibt stehen.
- [ ] **Step 6: Doku auf den wahren Stand.** Zeile „Moonraker direkt“ in beiden `printer.md`: Modell (nur wenn der Nutzer es genannt haben will), Frontend, Datum, was gesehen wurde und was nicht; Kopfkommentar von `moonraker.py`; Absatz „Checked / Not checked“ im CHANGELOG. `python3 tools/check_docs_parity.py`, alle Tests und ruff → PASS. **Commit** — `docs(printer): device test results`.
- [ ] **Step 7: Abschlussbericht, nichts ausführen.** Commits des Branches; Tabelle „geprüft am Gerät / im Simulator / nur Fixtures / nicht geprüft“; offene Punkte. Versionsnummer (Vorschlag der Spec: 0.8.0), Merge nach `main`, Tag und Release entstehen erst auf Wunsch des Nutzers nach `docs/RELEASING.md` und gehören nicht zu diesem Plan.
