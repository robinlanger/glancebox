# Geräteseite und Einrichtung (Issues 20 bis 22): Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Der Helligkeitsregler klebt nicht mehr nach der Passwortabfrage (#20), ein neues Update-Passwort wird überall zweimal eingegeben (#21), und das Einrichtungsportal prüft das Formular, bevor es mit dem WLAN verbindet (#22).

**Architecture:** Jede Regel, die ohne Hardware prüfbar ist, liegt als reine Funktion in `firmware/lib/core` mit nativen Unity-Tests; `firmware/src` verdrahtet nur. Das Portal bekommt eine von `WiFiManager` abgeleitete Klasse und einen eigenen `/wifisave`-Handler, der vor dem der Bibliothek registriert wird. Die Vorschau-Route der Geräteseite antwortet ohne Passwortaufforderung, das Skript hält die Vorschau nach einer Abweisung bis zum Loslassen an.

**Tech Stack:** C++17, PlatformIO (`native` für Tests, `ultra` = ESP8266/Arduino), WiFiManager 2.0.17, Unity; JavaScript ohne Build-Schritt (`firmware/web/app.js`), pytest + `node` für einen Skript-Test.

**Spec:** `docs/superpowers/specs/2026-11-22-geraeteseite-einrichtung-design.md`. Vor jeder Task den Abschnitt des jeweiligen Issues lesen; dort stehen Verhalten, Texte und Gründe.

## Global Constraints

- Branch `fix/device-page-and-setup`. Kein Merge, kein Push, kein Tag, kein Versionssprung.
- Nur `firmware/`, `server/tests/test_device_page_js.py`, `CHANGELOG.md`, `docs/en/`, `docs/de/` ändern. Doku immer in beiden Sprachen; `python3 tools/check_docs_parity.py` besteht.
- Nach jeder Task aus `firmware/`: `pio test -e native` grün (läuft lokal).
- Nach jeder Task: `pio run -e ultra` baut ohne neue Warnungen und `python3 ../tools/check_fw_size.py .pio/build/ultra/firmware.bin size-limit.txt` besteht. Der `ultra`-Build läuft **nicht** auf dem Mac, sondern auf dem Build-Rechner des Maintainers (Wegwerf-Container `python:3.12` mit `platformio==6.2.0`, eigene Volumes für `~/.platformio` und `firmware/.pio`); den genauen Aufruf gibt die steuernde Sitzung vor. Dorthin gehören nur `VERSION`, `tools/` und `firmware/`. Kann der Build nicht laufen, im Bericht als nicht geprüft nennen, nicht raten.
- `firmware/size-limit.txt` nicht anheben; reicht der Platz nicht, anhalten und berichten.
- Flash-Layout, `platformio.ini` und das Format der gespeicherten Einstellungen bleiben unverändert.
- Nichts flashen, kein Gerät im Netz ansprechen. Verhalten im Browser oder auf dem Gerät prüft der Maintainer. Jeder Bericht führt die Punkte unter „Nur im Browser/auf dem Gerät prüfbar“ seiner Task wörtlich als **nicht geprüft** auf.
- Neue Texte in `src/i18n.cpp` Englisch und Deutsch, neue `Msg`-Werte am Ende vor `Count`, beide Tabellen (`kEn`, `kDe`) ergänzen. Texte, die auf dem Bildschirm erscheinen können: nur ASCII, höchstens 47 Zeichen.
- `app.js`: Grenzen des Minifizierers beachten (Kopf der Datei): kein Regex-Literal mit zwei Schrägstrichen, Strings nur ASCII, alle Texte kommen aus `data-i18n`.
- Neue native Tests in `firmware/test/test_core/test_main.cpp`, mit `RUN_TEST` registriert.
- Keine echten LAN-Adressen oder E-Mail-Adressen in Code, Tests, Doku, Commits; Platzhalter wie `192.168.x.x`, in Tests Adressen aus `192.168.1.x`/`10.0.0.x` wie in den vorhandenen Tests.
- Nutzersichtbares in `CHANGELOG.md` unter `## [Unreleased]` (Abschnitte `### Fixed`, `### Changed`, `### Security` nach Bedarf anlegen), auf Englisch wie der Rest der Datei.
- Commit-Nachrichten im Stil `fix(firmware): ...` / `feat(firmware): ...`, die Issue-Zeile im Rumpf, Schlusszeile `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. Browser hat ein veraltetes Passwort gespeichert und jemand zieht am Regler: höchstens ein gezählter Fehlversuch pro Zug, keine 30-s-Sperre durch das Ziehen (Test in Task 1: Pumpe hält nach Abweisung an).
2. Eingerichtetes Gerät mit einer gespeicherten Server-URL, die heute verbotene Zeichen enthält, bekommt im Portal nur ein neues WLAN: Formular geht ohne `current_password` durch (Test in Task 2).
3. Captive-Portal-Browser ignoriert `required`/`minlength`: die Firmware lehnt leere URL und kurzes Passwort trotzdem ab, mit der klaren Meldung (Tests in Task 2).
4. Jemand füllt nur das Wiederholungsfeld und lässt das erste Passwortfeld leer: Fehler „stimmen nicht überein“ statt stillem „unverändert“ (Tests in Task 4, Patch und Portal).
5. Passwort mit Leerzeichen am Ende in nur einem der beiden Felder: gilt als ungleich, nichts wird gekürzt (Test in Task 4).

---

### Task 1: Regler-Vorschau ohne Passwortdialog (#20)

**Files:**
- Create: `server/tests/test_device_page_js.py`
- Modify: `firmware/web/app.js` (`createPreviewPump`, `post`, Regler-Schleife)
- Modify: `firmware/src/web_ui.h`, `firmware/src/web_ui.cpp` (`refuse`, `webUiAuthorize`, `handlePreview`)
- Modify: `docs/en/setup.md`, `docs/de/setup.md`, `CHANGELOG.md`

**Interfaces:**
- Produces: `bool webUiAuthorize(bool challenge = true)`; `createPreviewPump(send, minGapMs)` mit der neuen Regel „`send` löst mit `false` auf = anhalten bis `flush()`“; Fehler aus `post()` tragen `status`.

- [ ] **Step 1: Test schreiben** (`server/tests/test_device_page_js.py`)

```python
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
```

- [ ] **Step 2: Fehlschlag prüfen**

Run (aus `server/`): `pytest -q tests/test_device_page_js.py`
Expected: der erste Test besteht, der zweite scheitert mit `[[1, 3, 4], [1, 3, 4, 5]]`.

- [ ] **Step 3: `createPreviewPump` in `firmware/web/app.js` erweitern**

Löst `send(v)` mit genau `false` auf: wartenden Wert verwerfen, weitere `push()` ignorieren, bis `flush()` gelaufen ist. Ein abgelehntes Promise (Netzfehler) hält **nicht** an. Kommentar über der Funktion ergänzen.

- [ ] **Step 4: Test besteht**

Run: `pytest -q tests/test_device_page_js.py` → 2 passed.

- [ ] **Step 5: `post()` und Regler in `app.js`**

`post()`: jeder aus einer HTTP-Antwort entstehende Fehler bekommt `status = r.status` (Meldungen unverändert). Regler: `send` ist `post("/api/brightness-preview", { pct: v })`, aufgelöst zu `false` bei `status` 401 oder 429, sonst zu `true` (auch bei anderen Fehlern).

- [ ] **Step 6: Firmware: Vorschau antwortet ohne Aufforderung**

`bool webUiAuthorize(bool challenge = true)` in `web_ui.h`/`.cpp`; der Kommentar in `web_ui.h` nennt den Parameter. Bei `challenge == false` und `Access::NeedAuth`/`WrongPassword`: `server.send(401, "text/plain", "password required\n")`, kein `WWW-Authenticate`. Host, Origin, Sperre unverändert. Nur `handlePreview` ruft `webUiAuthorize(false)`.

- [ ] **Step 7: Prüfen**

Run (aus `firmware/`): `pio test -e native` → alle bestehen (keine neuen nativen Tests in dieser Task).
Run (Build-Rechner): `pio run -e ultra`, dann Größenprüfung → `OK`.

- [ ] **Step 8: Doku und CHANGELOG**

`docs/en/setup.md` und `docs/de/setup.md`, Abschnitt zur Geräteseite: ein Satz, dass sich das Display vor der ersten Passworteingabe erst beim Loslassen ändert. `CHANGELOG.md`, `### Fixed`: Regler folgte nach der Passwortabfrage weiter dem Zeiger. Run: `python3 tools/check_docs_parity.py`.

- [ ] **Step 9: Commit**

```bash
git add server/tests/test_device_page_js.py firmware/web/app.js firmware/src/web_ui.h firmware/src/web_ui.cpp docs/en/setup.md docs/de/setup.md CHANGELOG.md
git commit -m "fix(firmware): keep the brightness slider from sticking after the password prompt" -m "The live preview no longer triggers the browser's password dialog while the pointer is down; the dialog comes with the save on release." -m "Fixes #20" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

**Nur im Browser/auf dem Gerät prüfbar (als nicht geprüft berichten):** Regler lässt nach der Passworteingabe los; 401 ohne `WWW-Authenticate` zeigt in Chrome, Firefox, Safari keinen Dialog; nach der Anmeldung läuft die Vorschau beim Ziehen wieder live; `curl -i -X POST -d pct=50 http://<display-ip>/api/brightness-preview` liefert 401 ohne `WWW-Authenticate`.

---

### Task 2: Formularprüfung des Portals als reine Funktion, klare Meldung für leere URL (#22, Teil 1)

**Files:**
- Modify: `firmware/lib/core/settings.h`, `firmware/lib/core/settings.cpp`
- Modify: `firmware/src/i18n.h`, `firmware/src/i18n.cpp`
- Test: `firmware/test/test_core/test_main.cpp`
- Modify: `CHANGELOG.md`

**Interfaces:**
- Produces (in `namespace gb`, `settings.h`):

```cpp
// Values of the setup-portal form, as submitted.
struct PortalForm {
  std::string serverUrl, password, brightness, currentPassword;
};
// Validates the form against s and writes s with the form applied to *next. Order:
// "server_url" (applyServerUrl codes), "update_password" (applyPassword codes; required while s
// has no valid password, empty = keep otherwise), "brightness" ("bad_brightness"; empty =
// keep, else digits only, 5..100), "current_password" ("wrong_password"; only checked when
// *next differs from s and s has a valid password). On failure *field/*error are set and
// *next is unspecified.
bool applyPortalForm(const Settings& s, const PortalForm& f, Settings* next, std::string* field,
                     std::string* error);
```

- Produces: `normalizeServerUrl` meldet für leere Eingabe oder nur Leerraum `"required"` (statt `"empty_host"`); `http://` und `http://:8080` bleiben `"empty_host"`.
- Produces: `Msg::ErrUrlRequired` („Server URL is required“ / „Die Server-URL fehlt“); `msgForError` kennt zusätzlich `"required"` → `ErrUrlRequired`, `"wrong_password"` → `ErrWrongPassword`, `"bad_brightness"` → `ErrBrightness`.

- [ ] **Step 1: Tests schreiben**

In `test_apply_server_url_errors_leave_value` (Zeile mit `applyServerUrl(s, "", &err)`) die Erwartung `"empty_host"` auf `"required"` ändern. Neu:

```cpp
void test_server_url_empty_is_required() {
  std::string err;
  TEST_ASSERT_FALSE(normalizeServerUrl("", &err).has_value());
  TEST_ASSERT_EQUAL_STRING("required", err.c_str());
  TEST_ASSERT_FALSE(normalizeServerUrl("  \t ", &err).has_value());
  TEST_ASSERT_EQUAL_STRING("required", err.c_str());
  TEST_ASSERT_FALSE(normalizeServerUrl("http://", &err).has_value());
  TEST_ASSERT_EQUAL_STRING("empty_host", err.c_str());
}

static bool portalFails(const Settings& s, const PortalForm& f, const char* field, const char* code) {
  Settings next;
  std::string gotField, gotCode;
  if (applyPortalForm(s, f, &next, &gotField, &gotCode)) return false;
  return gotField == field && gotCode == code;
}

void test_portal_form_first_setup() {
  const Settings s{};
  Settings next;
  std::string field, err;
  TEST_ASSERT_TRUE(applyPortalForm(s, {"192.168.1.10:8090", "correct-horse", "60", ""}, &next, &field, &err));
  TEST_ASSERT_EQUAL_STRING("http://192.168.1.10:8090", next.serverUrl);
  TEST_ASSERT_EQUAL_STRING("correct-horse", next.updatePassword);
  TEST_ASSERT_EQUAL_UINT8(60, next.brightness);
  TEST_ASSERT_TRUE(applyPortalForm(s, {"a.lan", "correct-horse", "", ""}, &next, &field, &err));
  TEST_ASSERT_EQUAL_UINT8(kDefaultBrightness, next.brightness);  // empty = keep

  TEST_ASSERT_TRUE(portalFails(s, {"", "correct-horse", "60", ""}, "server_url", "required"));
  TEST_ASSERT_TRUE(portalFails(s, {"https://a.lan", "correct-horse", "", ""}, "server_url", "https_unsupported"));
  TEST_ASSERT_TRUE(portalFails(s, {"a.lan", "", "", ""}, "update_password", "too_short"));
  TEST_ASSERT_TRUE(portalFails(s, {"a.lan", "short", "", ""}, "update_password", "too_short"));
  TEST_ASSERT_TRUE(portalFails(s, {"a.lan", "correct-horse", "4", ""}, "brightness", "bad_brightness"));
  TEST_ASSERT_TRUE(portalFails(s, {"a.lan", "correct-horse", "101", ""}, "brightness", "bad_brightness"));
  TEST_ASSERT_TRUE(portalFails(s, {"a.lan", "correct-horse", "+50", ""}, "brightness", "bad_brightness"));
}

void test_portal_form_configured_device() {
  const Settings s = patchBase();  // http://10.0.0.2:8090, "oldpassword", brightness 80
  Settings next;
  std::string field, err;
  // Wi-Fi-only change: stored values resubmitted, no current password needed.
  TEST_ASSERT_TRUE(applyPortalForm(s, {"http://10.0.0.2:8090", "", "80", ""}, &next, &field, &err));
  TEST_ASSERT_EQUAL_STRING("oldpassword", next.updatePassword);
  // Any change needs the current password.
  TEST_ASSERT_TRUE(portalFails(s, {"http://10.0.0.3:8090", "", "", ""}, "current_password", "wrong_password"));
  TEST_ASSERT_TRUE(portalFails(s, {"http://10.0.0.2:8090", "", "70", "nope-nope"}, "current_password", "wrong_password"));
  TEST_ASSERT_TRUE(applyPortalForm(s, {"http://10.0.0.3:8090", "newpassword1", "70", "oldpassword"}, &next, &field, &err));
  TEST_ASSERT_EQUAL_STRING("http://10.0.0.3:8090", next.serverUrl);
  TEST_ASSERT_EQUAL_STRING("newpassword1", next.updatePassword);
  TEST_ASSERT_EQUAL_UINT8(70, next.brightness);
  // Errors in a value come before the current-password check.
  TEST_ASSERT_TRUE(portalFails(s, {"", "", "", "oldpassword"}, "server_url", "required"));
}

void test_portal_form_keeps_stored_url_with_old_characters() {
  Settings s = patchBase();
  std::strcpy(s.serverUrl, "http://old'host");  // stored before the character check existed
  Settings next;
  std::string field, err;
  TEST_ASSERT_TRUE(applyPortalForm(s, {"http://old'host", "", "", ""}, &next, &field, &err));
  TEST_ASSERT_TRUE(portalFails(s, {"http://new'host", "", "", "oldpassword"}, "server_url", "invalid_chars"));
}
```

Alle vier mit `RUN_TEST` registrieren. (`patchBase()` steht weiter unten in der Datei; die neuen Tests dahinter einfügen.)

- [ ] **Step 2: Fehlschlag prüfen**

Run (aus `firmware/`): `pio test -e native`
Expected: Kompilierfehler `PortalForm`/`applyPortalForm` nicht deklariert.

- [ ] **Step 3: `normalizeServerUrl`, `PortalForm`, `applyPortalForm` in `lib/core/settings.{h,cpp}`**

`applyPortalForm` nutzt `applyServerUrl`, `applyPassword`, das vorhandene `parseDayBrightness` und den Vergleich `encodeSettings(*next) != encodeSettings(s)` aus `portal.cpp`. Die Kommentare in `settings.h` zu `normalizeServerUrl`/`applyServerUrl` um `"required"` ergänzen.

- [ ] **Step 4: Text und Zuordnung in `src/i18n.{h,cpp}`**

`Msg::ErrUrlRequired` mit den Texten oben; `msgForError` um die drei Codes erweitern; Kommentar in `i18n.h` anpassen.

- [ ] **Step 5: Prüfen**

Run: `pio test -e native` → alle bestehen (102 bisherige in `test_core` plus 4 neue; `test_tjpgd` unverändert 4).
Run (Build-Rechner): `pio run -e ultra`, Größenprüfung → `OK`.

- [ ] **Step 6: CHANGELOG**

`### Changed`: ein leeres Feld Server-URL meldet jetzt „Server URL is required“ (Portal und Geräteseite).

- [ ] **Step 7: Commit**

```bash
git add firmware/lib/core/settings.h firmware/lib/core/settings.cpp firmware/src/i18n.h firmware/src/i18n.cpp firmware/test/test_core/test_main.cpp CHANGELOG.md
git commit -m "feat(firmware): validate the setup form in one tested function, clearer message for an empty server URL" -m "Refs #22" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

**Nur auf dem Gerät prüfbar (als nicht geprüft berichten):** die neue Meldung auf der Geräteseite, wenn dort die Adresse geleert wird.

---

### Task 3: Portal prüft vor dem Verbinden (#22, Teil 2)

**Files:**
- Modify: `firmware/src/portal.cpp`
- Modify: `docs/en/setup.md`, `docs/de/setup.md`, `docs/en/guide/4-set-up-wifi.md`, `docs/de/guide/4-set-up-wifi.md`, `CHANGELOG.md`

**Interfaces:**
- Consumes: `gb::PortalForm`, `gb::applyPortalForm(...)`, `msgForError(code, isPassword)` aus Task 2.
- Produces: `portalRun(gb::Settings&)` unverändert in Signatur und Abbruchbedingungen.

Diese Task hat keinen nativen Test: Sie verdrahtet nur. Geprüft wird durch Build und Review gegen den Abschnitt „#22 … Ablauf im Portal“ der Spec.

- [ ] **Step 1: Abgeleitete Klasse für die zwei geschützten Funktionen**

```cpp
// WiFiManager 2.0.17 keeps the page and save handlers protected; the pre-check below calls them.
class Portal : public WiFiManager {
 public:
  using WiFiManager::handleWifi;      // renders the Wi-Fi form (true = with network list)
  using WiFiManager::handleWifiSave;  // the library's /wifisave: answers, then connects
};
```

`portalRun` und `blockUnsafeRoutes` arbeiten mit `Portal` statt `WiFiManager`.

- [ ] **Step 2: Routen**

`blockUnsafeRoutes` sperrt zusätzlich `/param` und `/paramsave`; Kommentar darüber anpassen (`/wifisave` wird jetzt vom eigenen Handler bedient).

- [ ] **Step 3: Felder**

`pUrl`: Beschriftung `Server URL`, Attribute `placeholder='http://192.168.x.x:8090' required`. `pPw`: zusätzlich `minlength='8' autocomplete='new-password'`, bei `!complete` außerdem `required`. Übrige Felder unverändert. `setSaveParamsCallback` und `paramsSaved` entfallen.

- [ ] **Step 4: Hinweis**

`noticeHtml` auf 320 Zeichen. `setNotice` schreibt
`<p id='gbn' style='color:#b00'>EN<br>DE</p><script>document.getElementById('gbn').scrollIntoView()</script>`.

- [ ] **Step 5: Eigener `/wifisave`-Handler**

Im `setWebServerCallback`, nach `blockUnsafeRoutes`, `wm.server->on("/wifisave", HTTP_ANY, ...)`:

1. `gb::PortalForm` aus `wm.server->arg("server_url")`, `"update_password"`, `"brightness"`, `"current_password"` (letzteres nur, wenn `complete`, sonst leer).
2. `gb::applyPortalForm(s, form, &next, &field, &error)`.
3. Ungültig: `setNotice(msgForError(error, field == "update_password"))`; ist die eingegebene URL für sich gültig (`gb::applyServerUrl` auf eine Kopie von `s`), `pUrl.setValue(<normalisierte URL>, sizeof(s.serverUrl) - 1)`; `showPortalScreen()`; `wm.handleWifi(true)`; fertig. `handleWifiSave` wird **nicht** aufgerufen.
4. Gültig: `clearNotice()`; Formular in einer Variablen von `portalRun` merken (`std::optional<gb::PortalForm>`, pro Schleifendurchlauf neu); `showPortalScreen()`; `wm.handleWifiSave()`; danach `pPw` und `pCurrent` mit `setValue("", sizeof(s.updatePassword) - 1)` leeren.

- [ ] **Step 6: Anwenden nach der Rückkehr**

`applyPortalValues` nimmt das gemerkte `gb::PortalForm`, ruft `gb::applyPortalForm`, setzt bei Fehler den Hinweis wie in Step 5, speichert sonst mit `settingsSave` (Fehler: `Msg::ErrSaveFailed`), übernimmt `s = next`, `displaySetBrightness`, `clearNotice`. In `portalRun` ersetzt „Formular gemerkt“ das bisherige `paramsSaved` an beiden Stellen; die Bedingungen selbst bleiben.

- [ ] **Step 7: Prüfen**

Run (aus `firmware/`): `pio test -e native` → alle bestehen.
Run (Build-Rechner): `pio run -e ultra` ohne neue Warnungen, Größenprüfung → `OK`. Im Bericht die Größe vor und nach der Task nennen.
Gegenlesen: Kein Pfad ruft `handleWifiSave()` mit ungültigem Formular; `portalRun` verlässt die Schleife weiterhin nur bei `connected && gb::settingsComplete(s)` oder im bestehenden Zweig „eingerichtet, Netz weg, nichts abgeschickt“.

- [ ] **Step 8: Doku und CHANGELOG**

`setup.md` (en/de): Tabelle der Portalfelder und Schritt 4 (Fehler erscheint sofort auf der Formularseite, vor dem Verbinden; WLAN-Name und Passwörter danach neu eingeben; Beispieladresse zum Platzhalter passend erklären, Port 8080 bleibt der Docker-Standard). `guide/4-set-up-wifi.md` (en/de): Schritt „Server URL“ entsprechend. `CHANGELOG.md`: `### Changed` (Prüfung vor dem Verbinden, Platzhalter), `### Security` (Portal gibt eingegebene Passwörter nicht mehr im Seitenquelltext zurück; `/param` und `/paramsave` gesperrt). Run: `python3 tools/check_docs_parity.py`.

- [ ] **Step 9: Commit**

```bash
git add firmware/src/portal.cpp docs/en/setup.md docs/de/setup.md docs/en/guide/4-set-up-wifi.md docs/de/guide/4-set-up-wifi.md CHANGELOG.md
git commit -m "feat(firmware): check server URL and password in the setup portal before connecting to Wi-Fi" -m "An invalid form comes back at once with the error; WiFiManager only connects after the form passed." -m "Fixes #22" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

**Nur auf dem Gerät prüfbar (als nicht geprüft berichten):** eigener Handler verdeckt den der Bibliothek; Fehlerseite in den Captive-Portal-Browsern von iOS und Android; Rollen zum Hinweis; Wirkung von `required`/`minlength`/Platzhalter; Hinweis auf dem Bildschirm; gültiges Formular mit falschem WLAN-Passwort (Portal bleibt offen, kein Passwort im Seitenquelltext, erneutes Absenden klappt); erste Einrichtung und erneute Einrichtung eines eingerichteten Geräts von Anfang bis Ende; 403 auf `/param` und `/paramsave`; Geräteseite startet erst nach vollständiger Einrichtung.

---

### Task 4: Neues Passwort zweimal eingeben (#21)

**Files:**
- Modify: `firmware/lib/core/settings.h`, `firmware/lib/core/settings.cpp`
- Modify: `firmware/src/i18n.h`, `firmware/src/i18n.cpp`
- Modify: `firmware/src/web_ui.cpp` (`handleRoot`, `appendNoscriptForm`, `handleSettings`, `handleApiSettings`, `i18nJson`)
- Modify: `firmware/web/app.js` (Abschnitt „Password“), bei Bedarf `firmware/web/app.css`
- Modify: `firmware/src/portal.cpp`
- Test: `firmware/test/test_core/test_main.cpp`
- Modify: `docs/en/setup.md`, `docs/de/setup.md`, `docs/en/guide/4-set-up-wifi.md`, `docs/de/guide/4-set-up-wifi.md`, `CHANGELOG.md`

**Interfaces:**
- Consumes: `gb::PortalForm`, `gb::applyPortalForm` (Task 2); Handler und Parameter in `portal.cpp` (Task 3).
- Produces (in `namespace gb`):

```cpp
// A new update password with its repetition: "mismatch" when they differ (byte-exact, checked
// first), otherwise the applyPassword rules and codes.
bool applyNewPassword(Settings& s, const std::string& pw, const std::string& repeat,
                      std::string* error);
```

- Produces: `SettingsPatch` bekommt `std::optional<std::string> passwordRepeat`. `applySettingsPatch`: ist `password` vorhanden, gilt `applyNewPassword(next, *password, passwordRepeat.value_or(""))`; `"mismatch"` meldet Feld `"password_repeat"`, alle anderen Codes weiter Feld `"password"`.
- Produces: `PortalForm` bekommt `passwordRepeat` **direkt nach** `password` (Reihenfolge `serverUrl, password, passwordRepeat, brightness, currentPassword`). `applyPortalForm`: das Passwort wird geprüft, wenn `password` oder `passwordRepeat` nicht leer ist oder `s` kein gültiges Passwort hat; `"mismatch"` meldet Feld `"update_password_repeat"`.
- Produces: `Msg::PwNew` („New password“ / „Neues Passwort“), `Msg::PwRepeat` („Repeat new password“ / „Neues Passwort wiederholen“), `Msg::ErrPwMismatch` („The two passwords do not match“ / „Die beiden Passwörter stimmen nicht überein“); `msgForError("mismatch", …)` → `ErrPwMismatch`.
- Feldnamen: Geräteseite `password_repeat`, Portal `update_password_repeat`.

- [ ] **Step 1: Tests schreiben**

Die Aufrufe von `applyPortalForm` aus Task 2 bekommen das neue Feld an dritter Stelle (gleich dem Passwort, bzw. `""`, wo das Passwort leer ist). `test_settings_patch_password`: zu `p.password = "short"` auch `p.passwordRepeat = "short"`, zu `"longenough1"` auch `p.passwordRepeat = "longenough1"`. Neu:

```cpp
void test_apply_new_password_needs_equal_repeat() {
  Settings s = patchBase();
  std::string err;
  TEST_ASSERT_FALSE(applyNewPassword(s, "newpassword1", "newpassword2", &err));
  TEST_ASSERT_EQUAL_STRING("mismatch", err.c_str());
  TEST_ASSERT_FALSE(applyNewPassword(s, "newpassword1", "newpassword1 ", &err));  // nothing is trimmed
  TEST_ASSERT_EQUAL_STRING("mismatch", err.c_str());
  TEST_ASSERT_FALSE(applyNewPassword(s, "short", "longenough1", &err));  // mismatch comes first
  TEST_ASSERT_EQUAL_STRING("mismatch", err.c_str());
  TEST_ASSERT_FALSE(applyNewPassword(s, "short", "short", &err));
  TEST_ASSERT_EQUAL_STRING("too_short", err.c_str());
  TEST_ASSERT_EQUAL_STRING("oldpassword", s.updatePassword);
  TEST_ASSERT_TRUE(applyNewPassword(s, "newpassword1", "newpassword1", &err));
  TEST_ASSERT_EQUAL_STRING("newpassword1", s.updatePassword);
}

void test_settings_patch_password_needs_repeat() {
  Settings s = patchBase();
  std::string field, err;
  SettingsPatch p;
  p.password = "longenough1";  // repeat missing
  TEST_ASSERT_FALSE(applySettingsPatch(s, p, &field, &err));
  TEST_ASSERT_EQUAL_STRING("password_repeat", field.c_str());
  TEST_ASSERT_EQUAL_STRING("mismatch", err.c_str());
  p.passwordRepeat = "longenough2";
  TEST_ASSERT_FALSE(applySettingsPatch(s, p, &field, &err));
  TEST_ASSERT_EQUAL_STRING("mismatch", err.c_str());
  TEST_ASSERT_EQUAL_STRING("oldpassword", s.updatePassword);
  SettingsPatch q;
  q.passwordRepeat = "longenough1";  // repeat alone: no password field, nothing to apply
  TEST_ASSERT_TRUE(applySettingsPatch(s, q, &field, &err));
  TEST_ASSERT_EQUAL_STRING("oldpassword", s.updatePassword);
}

void test_portal_form_password_repeat() {
  const Settings fresh{};
  TEST_ASSERT_TRUE(portalFails(fresh, {"a.lan", "correct-horse", "correct-hores", "", ""},
                               "update_password_repeat", "mismatch"));
  TEST_ASSERT_TRUE(portalFails(fresh, {"a.lan", "correct-horse", "", "", ""},
                               "update_password_repeat", "mismatch"));
  const Settings s = patchBase();
  // Only the repeat field filled: an error, not a silent "keep".
  TEST_ASSERT_TRUE(portalFails(s, {"http://10.0.0.2:8090", "", "newpassword1", "", "oldpassword"},
                               "update_password_repeat", "mismatch"));
  Settings next;
  std::string field, err;
  TEST_ASSERT_TRUE(applyPortalForm(s, {"http://10.0.0.2:8090", "", "", "", ""}, &next, &field, &err));
  TEST_ASSERT_EQUAL_STRING("oldpassword", next.updatePassword);  // both empty = keep
  TEST_ASSERT_TRUE(applyPortalForm(s, {"http://10.0.0.2:8090", "newpassword1", "newpassword1", "", "oldpassword"},
                                   &next, &field, &err));
  TEST_ASSERT_EQUAL_STRING("newpassword1", next.updatePassword);
}
```

Alle drei mit `RUN_TEST` registrieren.

Hinweis zu `test_settings_patch_password_needs_repeat`, Teil `q`: Die Geräteseite schickt `password_repeat` nie ohne `password`; der Fall „nur Wiederholung gefüllt“ wird dort vom Skript bzw. in `handleSettings` abgefangen (Step 5 und 6).

- [ ] **Step 2: Fehlschlag prüfen**

Run (aus `firmware/`): `pio test -e native`
Expected: Kompilierfehler `applyNewPassword`/`passwordRepeat` nicht deklariert.

- [ ] **Step 3: Kern in `lib/core/settings.{h,cpp}`**

`applyNewPassword`, `SettingsPatch::passwordRepeat`, `PortalForm::passwordRepeat` und die beiden Regeln aus dem Interfaces-Block. Kommentare in `settings.h` (Feldnamen, Codes) ergänzen.

- [ ] **Step 4: Tests bestehen**

Run: `pio test -e native` → alle bestehen.

- [ ] **Step 5: Texte und Geräteseite (`i18n`, `web_ui.cpp`)**

- Drei `Msg`-Werte und `msgForError("mismatch")` wie im Interfaces-Block; `i18nJson` bekommt den Schlüssel `pw_mismatch`.
- `#pw-form`: zwei beschriftete Felder (`PwNew` → `name=password`, `PwRepeat` → `name=password_repeat`), beide `type=password minlength=8 maxlength=32 required autocomplete=new-password`, im Stil des Update-Formulars (`<label>Text<input …></label>` in `.stack`).
- `appendNoscriptForm`: nach dem Feld `password` ein Feld `password_repeat` mit `PwRepeat`, gleiche Attribute wie das Feld `password` dort.
- `handleSettings`: ist `password` oder `password_repeat` nicht leer, `gb::applyNewPassword`; Fehler wie bisher über `sendMessage(400, …, msgForError(err, true))`.
- `handleApiSettings`: `patchArg(p.passwordRepeat, F("password_repeat"))`.

- [ ] **Step 6: Skript (`app.js`, Abschnitt „Password“)**

Vor dem Senden vergleichen: bei Ungleichheit `T.pw_mismatch` als Fehler im `.msg` des Formulars zeigen und **nichts** senden. Sonst `post("/api/settings", { password, password_repeat })`; nach Erfolg beide Felder leeren. Die vorhandenen Tests aus Task 1 laufen weiter: `pytest -q tests/test_device_page_js.py` (aus `server/`) → 2 passed.

- [ ] **Step 7: Portal (`portal.cpp`)**

Parameter `update_password_repeat`, Beschriftung `Repeat update password`, direkt nach `pPw`, gleiche Länge und Attribute wie `pPw`. Der Handler aus Task 3 liest das Feld ins `PortalForm`, leert es nach `handleWifiSave()` mit, und `isPassword` für `msgForError` gilt für beide Passwortfelder (`update_password`, `update_password_repeat`).

- [ ] **Step 8: Prüfen**

Run: `pio test -e native` → alle bestehen.
Run (Build-Rechner): `pio run -e ultra` ohne neue Warnungen, Größenprüfung → `OK`.

- [ ] **Step 9: Doku und CHANGELOG**

`setup.md` (en/de): Portal-Tabelle (zweites Passwortfeld), Geräteseite („Passwort ändern“ fragt zweimal). `guide/4-set-up-wifi.md` (en/de): Schritt „Update password“ nennt die Wiederholung. `CHANGELOG.md`, `### Changed`: neues Update-Passwort wird zweimal abgefragt (Portal, Geräteseite mit und ohne JavaScript). Run: `python3 tools/check_docs_parity.py`.

- [ ] **Step 10: Commit**

```bash
git add firmware/lib/core/settings.h firmware/lib/core/settings.cpp firmware/src/i18n.h firmware/src/i18n.cpp firmware/src/web_ui.cpp firmware/src/portal.cpp firmware/web/app.js firmware/web/app.css firmware/test/test_core/test_main.cpp docs/en/setup.md docs/de/setup.md docs/en/guide/4-set-up-wifi.md docs/de/guide/4-set-up-wifi.md CHANGELOG.md
git commit -m "feat(firmware): ask for a new update password twice" -m "Setup portal and device page (with and without JavaScript) only store a new password when both entries match." -m "Fixes #21" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

**Nur im Browser/auf dem Gerät prüfbar (als nicht geprüft berichten):** Aussehen des Formulars mit zwei Feldern (hell und dunkel, Handybreite); Meldung bei ungleichen Eingaben ohne Passwortdialog; Passwortwechsel mit gleichen Eingaben und die erneute Abfrage des Browsers danach; das Formular ohne JavaScript; die beiden Passwortfelder im Portal bei erster und erneuter Einrichtung.

---

## Abschluss

Nach Task 4, vor der Übergabe an den Maintainer:

- `pio test -e native`, `pytest -q tests/test_device_page_js.py tests/test_webasset.py` (aus `server/`), `python3 tools/check_docs_parity.py`, letzter `ultra`-Build mit Größenprüfung: Ergebnisse mit Zahlen berichten.
- Eine gemeinsame Liste aller „nur im Browser/auf dem Gerät prüfbar“-Punkte der vier Tasks als Prüfliste für den Maintainer.
- `git log --oneline main..HEAD` zeigt die Commits mit `Fixes #20`, `Fixes #22`, `Fixes #21` im Rumpf.
