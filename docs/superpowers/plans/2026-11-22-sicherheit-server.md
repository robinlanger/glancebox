# Sicherheitshärtung Server, Add-on, Lieferkette: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Die Funde 1, 4, 5 und 7 der Sicherheitsprüfung vom 2026-11-22 in Server, Add-on und Lieferkette beheben.

**Architecture:** Geheimnisse verlassen die Prozessumgebung: das Add-on reicht sie als eigene Zuordnung an `load_config`, Chromium startet mit einer Positivliste. Seiten-Anfragen laufen durch eine reine Prüffunktion, Fehlertexte durch `redact_urls`. Die Lieferkette wird über Lock-Dateien mit Hashes, Digest- und SHA-Pins und zwei CI-Schritte festgezogen.

**Tech Stack:** Python 3.12, FastAPI, uvicorn, Playwright (Chromium), pytest, Docker, GitHub Actions, `uv`.

**Spec:** `docs/superpowers/specs/2026-11-22-sicherheitshaertung-design.md`

## Global Constraints

- Branch `security/server-hardening`, von `main`. Kein Merge, kein Push, kein Tag, kein Versionssprung (`VERSION` und `ha-addon/config.yaml` `version` bleiben `0.6.1`).
- Keine Datei unter `firmware/` ändern.
- Tests aus `server/`: `.venv/bin/pytest -q -m "not browser"`; Lint: `.venv/bin/ruff check . ../pages`. Beides muss vor jedem Commit grün sein. Browser-Tests (`-m browser`) laufen nur im Docker-Image.
- Zeilenlänge 100, Code und Kommentare auf Englisch, Stil wie im Umfeld.
- Doku gibt es doppelt: jede Änderung unter `docs/en/` auch unter `docs/de/` (`python3 tools/check_docs_parity.py` muss bestehen). `README.md` und `README.de.md` ebenso.
- Nutzersichtbare Änderungen kommen in `CHANGELOG.md` unter `## [Unreleased]` (Abschnitte `### Security`, `### Changed`).
- Nie einen echten Token, eine echte IP oder E-Mail in Code, Tests oder Commits; Platzhalter wie `192.168.x.x`, `example.org`.
- Commit-Nachrichten im Stil `fix(server): ...`, mit Schlusszeile `Co-Authored-By: Claude Fable 5.2 <noreply@anthropic.com>`.
- Digests, Commit-SHAs und Werkzeugversionen zur Bauzeit nachschlagen. Lässt sich einer nicht ermitteln, den Pin weglassen und im Bericht nennen, nie erfinden.

## Review Focus

1. Eine bestehende `url`-Seite auf ein LAN-Ziel (`http://192.168.x.x:3000/d/abc`) oder auf `http://homeassistant:8123/...` muss weiter rendern, samt Unterabrufen an denselben Host (Test in Task 2).
2. Docker-Nutzer mit Schlüsseln in `.env`: `${NAME}` in `config.yaml` muss weiter aufgelöst werden (Test in Task 1).
3. Eigene Seiten im Add-on, die ein Geheimnis per `${NAME}` beziehen, funktionieren weiter; nur direktes `os.environ["NAME"]` in `page.py` nicht mehr. Das steht im Changelog (Task 1).
4. Start in einem Container ohne erlaubte Sandbox darf nicht scheitern: Rückfall mit genau einer Warnzeile (Test in Task 1).
5. Fehlertext ohne Adresse oder mit kaputter Adresse (`http://[`, nur `?a=b`) darf `redact_urls` nicht zum Absturz bringen (Test in Task 3).

---

### Task 1: Geheimnisse aus der Prozessumgebung, Chromium mit Positivliste und Sandbox-Versuch

**Files:**
- Modify: `server/glancebox/config.py` (`load_config`)
- Modify: `server/glancebox/addon.py` (`addon_setup`, `AddonSetup`, `ha_defaults`-Aufruf)
- Modify: `server/glancebox/__main__.py` (`_serve_addon`)
- Modify: `server/glancebox/render.py` (`Renderer`)
- Test: `server/tests/test_config.py`, `server/tests/test_addon.py`, `server/tests/test_render.py`
- Modify: `CHANGELOG.md`, `ha-addon/DOCS.md`, `SECURITY.md`

**Interfaces:**
- Produces: `load_config(path: Path, defaults: Callable[[dict], dict] | None = None, environ: Mapping[str, str] | None = None) -> AppConfig` (`environ=None` heißt `os.environ`).
- Produces: `AddonSetup.environ: dict[str, str]` (Kopie der Umgebung plus Formular-Geheimnisse; nur für `${NAME}`).
- Produces: `render.browser_env(environ: Mapping[str, str]) -> dict[str, str]`.
- Produces: `Renderer.sandboxed: bool | None` (None vor dem Start).

- [ ] **Step 1: Tests schreiben (schlagen fehl)**

```python
# test_config.py
def test_load_config_uses_given_environ(tmp_path, monkeypatch):
    monkeypatch.delenv("MY_KEY", raising=False)
    p = tmp_path / "config.yaml"
    p.write_text("push_key: ${MY_KEY}\npages:\n  - type: clock\n")
    cfg = load_config(p, environ={"MY_KEY": "k" * 16})
    assert cfg.push_key == "k" * 16

# test_addon.py (get/sleep-Fakes wie in test_addon_setup_end_to_end)
def test_addon_setup_keeps_secrets_out_of_process_env(tmp_path):
    environ = {"SUPERVISOR_TOKEN": "tok", "PATH": "/usr/bin"}
    setup = addon.addon_setup(environ, tmp_path / "config.yaml", tmp_path / "fb",
                              get=fake_get_with(options={"anthropic_admin_key": "sk-secret"}),
                              sleep=lambda s: None)
    assert "ANTHROPIC_ADMIN_KEY" not in environ
    assert "SUPERVISOR_TOKEN" not in environ
    assert setup.environ["ANTHROPIC_ADMIN_KEY"] == "sk-secret"

# test_render.py
def test_browser_env_is_allowlist():
    env = browser_env({"PATH": "/usr/bin", "HOME": "/home/pwuser", "TZ": "Europe/Berlin",
                       "LC_ALL": "C.UTF-8", "XDG_CACHE_HOME": "/tmp/c", "FONTCONFIG_PATH": "/f",
                       "SUPERVISOR_TOKEN": "tok", "ANTHROPIC_ADMIN_KEY": "sk", "LD_PRELOAD": "x",
                       "GLANCEBOX_PUSH_KEY": "p"})
    assert set(env) == {"PATH", "HOME", "TZ", "LC_ALL", "XDG_CACHE_HOME", "FONTCONFIG_PATH"}

async def test_sandbox_falls_back_once(caplog):
    # fake playwright: chromium.launch raises when chromium_sandbox=True, else returns a browser
    r = Renderer(); r._pw = _SandboxlessPlaywright()
    await r._launch()
    assert r.sandboxed is False
    assert [k["chromium_sandbox"] for k in r._pw.chromium.calls] == [True, False]
    assert all("SUPERVISOR_TOKEN" not in k["env"] for k in r._pw.chromium.calls)
    assert sum("sandbox" in rec.message.lower() for rec in caplog.records) == 1
    await r._launch()  # relaunch does not retry the sandbox, no second warning
    assert r._pw.chromium.calls[-1]["chromium_sandbox"] is False
```

Dazu den bestehenden Test `test_addon_setup_end_to_end` an `setup.environ` anpassen und einen Test, dass ein `homeassistant`-Seiten-Default weiter den Supervisor-Token bekommt, obwohl er aus `environ` entfernt ist.

- [ ] **Step 2: Fehlschlag prüfen** — `cd server && .venv/bin/pytest -q -m "not browser" tests/test_config.py tests/test_addon.py tests/test_render.py`, erwartet: die neuen Tests rot.

- [ ] **Step 3: `load_config` um `environ` erweitern.** `expand_env(data, "", os.environ if environ is None else environ)`.

- [ ] **Step 4: `addon_setup` umbauen.** Token mit `environ.pop("SUPERVISOR_TOKEN")` lesen; `merged = {**environ, **secrets_env(options, environ)}` bilden, `environ` nicht mehr verändern; `ha_defaults(info, {**merged, "SUPERVISOR_TOKEN": token})` damit Push-Key und HA-Seite ihre Werte behalten; `AddonSetup` bekommt das Feld `environ=merged`. `is_addon()` wird in `_serve` vor `addon_setup` aufgerufen und bleibt unverändert. Docstring des Moduls anpassen (keine Umgebungsvariablen mehr).

- [ ] **Step 5: `_serve_addon`** ruft `load_config(setup.config_path, defaults=setup.defaults, environ=setup.environ)`.

- [ ] **Step 6: `browser_env` und Sandbox-Versuch in `render.py`.** Positivliste: exakt `PATH`, `HOME`, `USER`, `LOGNAME`, `LANG`, `LANGUAGE`, `TZ`, `TMPDIR`; Präfixe `LC_`, `XDG_`, `FONTCONFIG_`. Neue Methode `async def _launch(self) -> None`, von `__aenter__` und `_relaunch` benutzt: beim ersten Mal `chromium.launch(env=browser_env(os.environ), chromium_sandbox=True)`; bei Fehler eine Warnung (`Chromium sandbox not available in this container; running without it`) und Start mit `chromium_sandbox=False`; Ergebnis in `self.sandboxed` merken und bei späteren Starts direkt verwenden. Gelingt der Start mit Sandbox: eine Info-Zeile.

- [ ] **Step 7: Tests grün** — gleicher Befehl wie Step 2, dann ganze Suite und ruff.

- [ ] **Step 8: Im Image prüfen.** `docker build -t glancebox:sec .` und `docker run --rm glancebox:sec pytest -q -m browser` (alle grün). Zusätzlich `docker run --rm -e SUPERVISOR_TOKEN=tok glancebox:sec python -c "..."` mit einem kurzen Skript, das eine Seite mit `Renderer` rendert und währenddessen für jeden Chromium-Kindprozess `/proc/<pid>/environ` liest: `SUPERVISOR_TOKEN` darf in keinem vorkommen. Ergebnis und ob die Sandbox griff im Bericht nennen. Ist Docker lokal nicht nutzbar: im Bericht sagen, nicht als geprüft ausgeben.

- [ ] **Step 9: Doku.** `CHANGELOG.md` Unreleased/Security: Chromium ohne Geheimnisse, Sandbox-Versuch; Unreleased/Changed: Add-on-Geheimnisse sind nur noch über `${NAME}` in `config.yaml` verfügbar, nicht mehr als Umgebungsvariable in eigenen `page.py`. `ha-addon/DOCS.md` Abschnitt Security und `SECURITY.md` um einen Satz zu Chromium ergänzen (kein Schutzversprechen über das Gebaute hinaus; die Grenzen aus der Spec nennen).

- [ ] **Step 10: Commit** — `fix(server): keep secrets out of the process environment and Chromium`

---

### Task 2: Zielsperre für Anfragen aus gerenderten Seiten

**Files:**
- Create: `server/glancebox/netguard.py`
- Modify: `server/glancebox/render.py` (`_render`, `render_url`, `render_html`)
- Test: `server/tests/test_netguard.py`, `server/tests/test_render.py`
- Modify: `CHANGELOG.md`, `docs/en/writing-pages.md`, `docs/de/writing-pages.md`

**Interfaces:**
- Produces: `netguard.blocked(url: str, page_host: str | None) -> bool`. `page_host` ist der Host der konfigurierten `url`-Seite (klein geschrieben, ohne Port) oder `None` für Vorlagen.

Regeln, in dieser Reihenfolge:
1. Schema `data`, `blob`, `about`: erlaubt.
2. Schema nicht `http`/`https`: gesperrt.
3. Host gleich `page_host`: erlaubt (auch wenn intern).
4. Host ist einer von `supervisor`, `hassio`, `homeassistant`, `observer`, `localhost`, oder endet auf `.local.hass.io`: gesperrt.
5. Host ist IP-Literal in `127.0.0.0/8`, `172.30.32.0/23`, `169.254.0.0/16`, `::1`: gesperrt.
6. Sonst erlaubt. Nicht parsebare Adresse: gesperrt.

- [ ] **Step 1: Tests schreiben**

```python
@pytest.mark.parametrize("url,page_host,expected", [
    ("data:image/png;base64,AAAA", None, False),
    ("https://example.org/a.png", None, False),
    ("http://192.168.1.20:3000/d/abc", "192.168.1.20", False),
    ("http://192.168.1.20:3000/api/x", "192.168.1.20", False),
    ("http://192.168.1.99/", "192.168.1.20", False),
    ("http://homeassistant:8123/lovelace", "homeassistant", False),
    ("http://homeassistant:8123/api/", "example.org", True),
    ("http://supervisor/core/api/config", "example.org", True),
    ("http://SUPERVISOR/core", None, True),
    ("http://172.30.32.2:8099/", None, True),
    ("http://172.30.33.5/", None, True),
    ("http://172.30.34.1/", None, False),
    ("http://127.0.0.1:8080/", None, True),
    ("http://[::1]/", None, True),
    ("http://169.254.169.254/latest", None, True),
    ("http://a0d7b954-ssh.local.hass.io/", None, True),
    ("file:///etc/passwd", None, True),
    ("ftp://example.org/x", None, True),
    ("http://[", None, True),
])
def test_blocked(url, page_host, expected):
    assert blocked(url, page_host) is expected
```

In `test_render.py` (Marker `browser`): eine lokale Testseite auf `127.0.0.1`, deren HTML ein Bild von einem zweiten lokalen Server auf `localhost:<anderer Port>` lädt; `render_url` der ersten rendert, und der zweite Server hat keine Anfrage gesehen. Und: `render_html('<img src="http://127.0.0.1:<port>/x.png">')` löst keine Anfrage aus.

- [ ] **Step 2: Fehlschlag prüfen** — `.venv/bin/pytest -q tests/test_netguard.py`, erwartet: ImportError.

- [ ] **Step 3: `netguard.blocked` schreiben** (`urllib.parse.urlsplit`, `ipaddress`).

- [ ] **Step 4: In `Renderer._render` einhängen.** `_render(self, load, budget_s, page_host=None)`; nach `new_context`: `await context.route("**/*", handler)`, der `route.abort("blockedbyclient")` aufruft, wenn `blocked(route.request.url, page_host)`, sonst `route.continue_()`. `render_url` übergibt den Host der konfigurierten Adresse, `render_html` `None`. Zusätzlich `service_workers="block"` im Kontext.

- [ ] **Step 5: Tests grün**, ganze Suite, ruff; Browser-Tests im Image wie in Task 1 Step 8.

- [ ] **Step 6: Doku.** `writing-pages.md` (en, de): ein Absatz, welche Ziele Seiten nicht abrufen können und dass der eigene Host einer `url`-Seite ausgenommen ist. Changelog Unreleased/Security.

- [ ] **Step 7: Commit** — `fix(server): block page requests to Home Assistant internal targets`

---

### Task 3: Adressen in Fehlertexten und Logs bereinigen

**Files:**
- Modify: `server/glancebox/http.py` (neue Funktion)
- Modify: `server/glancebox/frames.py` (`refresh_once`), `server/glancebox/pages.py` (`_validate_url_options`)
- Modify: `pages/homeassistant/page.py` (`_log_failure`), `pages/kuma/page.py:135`, `pages/bahn/page.py:90`
- Test: `server/tests/test_http.py`, `server/tests/test_frames.py`, `pages/homeassistant/test_homeassistant.py`

**Interfaces:**
- Produces: `glancebox.http.redact_urls(text: str) -> str`: jede `http(s)://…`-Adresse im Text behält Schema, Host, Port und Pfad; `user:pass@` wird zu `***@`, Query und Fragment werden zu `?***`.

- [ ] **Step 1: Tests schreiben**

```python
@pytest.mark.parametrize("text,expected", [
    ("Page.goto: net::ERR at http://h:3000/d/x?token=abc&kiosk",
     "Page.goto: net::ERR at http://h:3000/d/x?***"),
    ("401 for url: https://user:pw@example.org/api/states/sensor.a",
     "401 for url: https://***@example.org/api/states/sensor.a"),
    ("see http://a/x#secret and https://b/?k=1.", "see http://a/x?*** and https://b/?***."),
    ("no url here", "no url here"),
    ("broken http://[ and ?a=b", "broken http://[ and ?a=b"),
    ("", ""),
])
def test_redact_urls(text, expected):
    assert redact_urls(text) == expected

# test_frames.py: a page whose render raises RenderError("... http://h/x?token=abc")
#   -> store.last_error(0) contains "http://h/x?***" and not "abc"
#   -> caplog text at WARNING and above does not contain "abc"
```

- [ ] **Step 2: Fehlschlag prüfen.**

- [ ] **Step 3: `redact_urls` schreiben.** Regex über `https?://[^\s"'<>]+`; abschließende Satzzeichen `.,;)` bleiben außerhalb der Adresse.

- [ ] **Step 4: Anwenden.** `refresh_once`: gespeicherter Fehler ist `redact_urls(f"{type(e).__name__}: {e}")`; statt `log.exception` eine `log.warning` mit dem bereinigten Text und der Traceback nur auf `log.debug(..., exc_info=True)`. `_validate_url_options`, `_log_failure`, kuma und bahn: Adresse bzw. Ausnahmetext vor dem Loggen/Werfen durch `redact_urls`.

- [ ] **Step 5: Tests grün**, ganze Suite, ruff.

- [ ] **Step 6: Commit** — `fix(server): strip credentials and query strings from URLs in errors and logs` (Changelog Unreleased/Security im selben Commit).

---

### Task 4: uvicorn, Schutz-Kopfzeilen, Compose

**Files:**
- Modify: `server/glancebox/__main__.py`, `server/glancebox/app.py` (`_add_overview`, `create_ingress_app`), `server/glancebox/templates/index.html`
- Modify: `docker-compose.yml`, `.github/workflows/ci.yml` (Job `server-image`)
- Test: `server/tests/test_app.py`

**Interfaces:**
- Produces: `__main__.uvicorn_config(app, host: str, port: int) -> uvicorn.Config` mit `proxy_headers=False`, `server_header=False`; von `_serve` und `_serve_addon` benutzt (`_serve` startet dann `uvicorn.Server(cfg).run()`).

- [ ] **Step 1: Tests schreiben**

```python
def test_uvicorn_config_ignores_proxy_headers():
    cfg = uvicorn_config(FastAPI(), "0.0.0.0", 8080)
    assert cfg.proxy_headers is False and cfg.server_header is False

def test_overview_security_headers():   # Docker mode
    r = client.get("/")
    csp = r.headers["content-security-policy"]
    assert "default-src 'none'" in csp and "frame-ancestors 'none'" in csp
    assert "'unsafe-inline'" not in csp.split("script-src")[1].split(";")[0]
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["referrer-policy"] == "no-referrer"

def test_ingress_csp_allows_framing_by_home_assistant():
    first, second = ingress_client.get("/"), ingress_client.get("/")
    csp = first.headers["content-security-policy"]
    assert "frame-ancestors" not in csp
    nonce = re.search(r"script-src 'nonce-([^']+)'", csp).group(1)
    assert f'<script nonce="{nonce}">' in first.text
    assert nonce not in second.headers["content-security-policy"]  # fresh per response
```

- [ ] **Step 2: Fehlschlag prüfen.**

- [ ] **Step 3: Umsetzen.** CSP: `default-src 'none'; img-src 'self'; style-src 'unsafe-inline'; script-src 'nonce-<n>'; base-uri 'none'; form-action 'none'`, im Docker-Modus zusätzlich `frame-ancestors 'none'`. Nonce je Antwort mit `secrets.token_urlsafe(16)`, an die Vorlage als `nonce`. `X-Content-Type-Options: nosniff` auch auf `/preview/{index}.jpg`.

- [ ] **Step 4: Compose und CI.** `docker-compose.yml`: `cap_drop: [ALL]` und `security_opt: ["no-new-privileges:true"]`. CI-Job `server-image`: `docker run --rm --cap-drop ALL --security-opt no-new-privileges glancebox:ci ...`, damit CI beweist, dass Chromium so rendert. Lokal mit denselben Schaltern prüfen (Task 1 Step 8). `read_only` nur ergänzen, wenn die Browser-Tests mit `--read-only --tmpfs /tmp` lokal bestehen; sonst weglassen und im Bericht nennen.

- [ ] **Step 5: Tests grün**, ganze Suite, ruff.

- [ ] **Step 6: Commit** — `fix(server): security headers, no proxy headers, drop container capabilities` (Changelog Unreleased/Security).

---

### Task 5: Lieferkette

**Files:**
- Create: `server/requirements.in`, `server/requirements-dev.in`, `server/requirements-dev.lock`, `.github/dependabot.yml`
- Modify: `server/requirements.lock`, `Dockerfile`, `.github/workflows/ci.yml`, `.github/workflows/release.yml`, `.github/workflows/pages.yml`, `docs/RELEASING.md`, `SECURITY.md`, `server/tests/test_addon_package.py` (neuer Test), ggf. Stellen in Doku/README, die `requirements.lock` für die lokale Entwicklung nennen (`grep -rn requirements.lock`)

**Interfaces:** keine für andere Tasks.

- [ ] **Step 1: Test schreiben** (in `test_addon_package.py`, liest Dateien im Repo)

```python
def test_runtime_lock_is_hashed_and_has_no_dev_tools():
    text = (ROOT / "server/requirements.lock").read_text()
    assert "--hash=sha256:" in text
    for dev in ("pytest", "ruff", "httpx"):
        assert not re.search(rf"^{dev}==", text, re.M)

def test_workflows_pin_actions_by_commit():
    for wf in (ROOT / ".github/workflows").glob("*.yml"):
        for line in wf.read_text().splitlines():
            if "uses:" in line:
                assert re.search(r"@[0-9a-f]{40}\b", line), f"{wf.name}: {line.strip()}"

def test_base_image_pinned_by_digest():
    assert re.search(r"^FROM mcr\.microsoft\.com/playwright/python:\S+@sha256:[0-9a-f]{64}",
                     (ROOT / "Dockerfile").read_text(), re.M)
```

- [ ] **Step 2: Fehlschlag prüfen.**

- [ ] **Step 3: Lock-Dateien.** `requirements.in`: die sieben Laufzeit-Pins von heute, unverändert. `requirements-dev.in`: `-c requirements.lock` plus die vier Dev-Pins von heute. Erzeugen mit `uv pip compile --universal --python-version 3.12 --generate-hashes requirements.in -o requirements.lock` (dev analog). Kopfkommentar mit dem Erzeugungsbefehl. Keine Version anheben. Prüfen, dass Hashes für Linux amd64 und arm64 enthalten sind (playwright, pillow, pyyaml).

- [ ] **Step 4: Dockerfile.** Basis-Image mit Digest der Multi-Arch-Liste (`docker buildx imagetools inspect mcr.microsoft.com/playwright/python:v1.65.2-noble`), Tag bleibt lesbar davor. Stufen: bisherige Endstufe heißt `runtime` und installiert `pip install --require-hashes -r server/requirements.lock`; danach `FROM runtime AS test` mit zusätzlich `requirements-dev.lock` (als root installieren, dann zurück zu `USER pwuser`); letzte Stufe `FROM runtime`, damit der Standard-Build ohne Testwerkzeuge ist. Kommentar zu den Dev-Tools im Image anpassen.

- [ ] **Step 5: CI.** Job `server`: beide Lock-Dateien mit `--require-hashes` installieren, Cache-Pfad anpassen. Job `server-image`: `target: test` bauen und darin die Browser-Tests fahren; zusätzlich das Standardziel bauen und `docker run --rm <image> python -c "import pytest"` muss scheitern. Neuer Job `audit`: `pip-audit` (feste Version) gegen `server/requirements.lock`; schlägt bei bekannten Lücken fehl. Meldet er heute schon eine Lücke: nicht anheben, sondern im Bericht nennen.

- [ ] **Step 6: Actions per SHA.** In allen drei Workflows jede `uses:`-Zeile auf den 40-stelligen Commit des heute benutzten Tags, Tag als Kommentar dahinter (`# v4.2.2`). SHA mit `gh api repos/<owner>/<repo>/commits/<tag> --jq .sha` ermitteln.

- [ ] **Step 7: Dependabot.** `.github/dependabot.yml`, wöchentlich, Ökosysteme `pip` (`/server`), `docker` (`/`), `github-actions` (`/`).

- [ ] **Step 8: Release-Workflow.** `permissions` auf Job-Ebene, dazu `id-token: write` und `attestations: write`. `build-push-action` bekommt `id: build`. Nach dem Push (nur wenn kein Probelauf): `actions/attest-build-provenance` für das Image (`subject-name: ghcr.io/robinlanger/glancebox`, `subject-digest: ${{ steps.build.outputs.digest }}`, `push-to-registry: true`) und für `dist/*.bin`. Der Probelauf (`workflow_dispatch`) darf nichts davon ausführen. `docs/RELEASING.md` und `SECURITY.md` um die Prüfzeile `gh attestation verify ... --repo robinlanger/glancebox` ergänzen. YAML mit `python3 -c "import yaml,sys; yaml.safe_load(open(sys.argv[1]))"` und, falls vorhanden, `actionlint` prüfen.

- [ ] **Step 9: Tests grün**, ganze Suite, ruff, Docs-Parität; Image lokal bauen (Standardziel und `--target test`), Browser-Tests im Test-Image grün.

- [ ] **Step 10: Commit** — `build: hashed lock files, digest and SHA pins, audit, attestations` (Changelog Unreleased/Security). Der Release-Workflow lässt sich lokal nicht ausführen: im Bericht ausdrücklich als ungeprüft nennen und einen Probelauf über `workflow_dispatch` nach dem Push empfehlen.
