# Sicherheitshärtung Firmware: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Die Funde 2, 3 und 6 der Sicherheitsprüfung vom 2026-11-22 in der Firmware beheben.

**Architecture:** Jede Entscheidung, die sich ohne Hardware prüfen lässt, wandert als reine Funktion nach `firmware/lib/core` und bekommt native Unity-Tests; `firmware/src` verdrahtet nur. Der Frame-Abruf wechselt von `HTTPClient` auf einen `WiFiClient` mit Gesamtfrist.

**Tech Stack:** C++17, PlatformIO (`native` für Tests, `ultra` = ESP8266/Arduino), WiFiManager 2.0.17, Unity.

**Spec:** `docs/superpowers/specs/2026-11-22-sicherheitshaertung-design.md`

## Global Constraints

- Branch `security/firmware-hardening`, von `main`. Kein Merge, kein Push, kein Tag, kein Versionssprung.
- Nur `firmware/`, `CHANGELOG.md`, `SECURITY.md`, `docs/en/`, `docs/de/` ändern. Doku immer in beiden Sprachen (`python3 tools/check_docs_parity.py`).
- Nach jeder Task aus `firmware/`: `pio test -e native` grün, `pio run -e ultra` baut ohne neue Warnungen, `python3 ../tools/check_fw_size.py .pio/build/ultra/firmware.bin size-limit.txt` besteht. `size-limit.txt` nicht anheben; reicht der Platz nicht, anhalten und berichten.
- Flash-Layout, `board_build.ldscript` und das Format der gespeicherten Einstellungen bleiben unverändert. Gespeicherte Einstellungen bestehender Geräte müssen weiter laden.
- Nichts flashen, kein Gerät im Netz ansprechen. Hardware-Smoketest und 24-h-Dauertest macht der Maintainer; kein Bericht darf Verhalten auf dem Gerät als geprüft ausgeben.
- Neue Texte in `src/i18n.cpp` immer Englisch und Deutsch. Texte für den Bildschirm nur ASCII.
- Neue Tests in `firmware/test/test_core/test_main.cpp`, mit `RUN_TEST` registriert.
- Nutzersichtbares in `CHANGELOG.md` unter `## [Unreleased]`, Abschnitt `### Security`.
- Commit-Nachrichten im Stil `fix(firmware): ...`, mit Schlusszeile `Co-Authored-By: Claude Fable 5.2 <noreply@anthropic.com>`.

## Review Focus

1. Gespeicherte Server-Adresse mit einem jetzt verbotenen Zeichen: Gerät lädt die Einstellungen weiter und holt Bilder; nur neue Eingaben werden abgelehnt (Test in Task 2).
2. Server antwortet mit klein geschriebenen oder anders geordneten Kopfzeilen (`content-length`, `etag`), mit oder ohne Leerzeichen nach dem Doppelpunkt: Bild wird angezeigt (Test in Task 3).
3. Antwort 304 ohne `Content-Length` und Antwort 200 mit `Transfer-Encoding: chunked`: 304 gilt als Erfolg, chunked als `kErrFrameLength` wie heute (Test in Task 3).
4. Besitzer tippt das richtige Passwort, während die Sperre läuft: klare Antwort 429 mit Wartezeit statt einer Passwortabfrage in Endlosschleife (Test in Task 4).
5. `millis()`-Überlauf während einer Sperre oder Frist: keine Dauersperre (Tests in Task 3 und 4).

---

### Task 1: Einrichtungs-WLAN auf eingerichteten Geräten mit WPA2, weitere Routen gesperrt

**Files:**
- Modify: `firmware/lib/core/settings.h`, `firmware/lib/core/settings.cpp`
- Modify: `firmware/src/portal.cpp`, `firmware/src/i18n.cpp`/`.h` falls ein Text fehlt
- Test: `firmware/test/test_core/test_main.cpp`
- Modify: `SECURITY.md`, `docs/en/recovery.md`, `docs/de/recovery.md`, `docs/en/guide/4-set-up-wifi.md`, `docs/de/guide/4-set-up-wifi.md`

**Interfaces:**
- Produces: `const char* gb::portalApPassword(const Settings& s)`: das Update-Passwort, wenn `settingsComplete(s)` und seine Länge 8 bis 63 ist, sonst `nullptr` (offenes WLAN).

- [ ] **Step 1: Tests schreiben**

```cpp
void test_portal_ap_password_only_when_configured() {
  gb::Settings s{};                       // unconfigured: open AP
  TEST_ASSERT_NULL(gb::portalApPassword(s));
  std::string err;
  TEST_ASSERT_TRUE(gb::applyServerUrl(s, "http://192.168.1.10:8080", &err));
  TEST_ASSERT_TRUE(gb::applyPassword(s, "correct-horse", &err));
  TEST_ASSERT_EQUAL_STRING("correct-horse", gb::portalApPassword(s));
}
```

- [ ] **Step 2: Fehlschlag prüfen** — `pio test -e native`, erwartet: Kompilierfehler `portalApPassword`.

- [ ] **Step 3: `portalApPassword` schreiben.**

- [ ] **Step 4: `portal.cpp` verdrahten.** Im Zweig `complete && wm.getWiFiIsSaved()`: `wm.autoConnect(apName, gb::portalApPassword(s))`. `showPortalScreen` zeigt dann eine Zeile `Wi-Fi password = update password` statt eines offenen Hinweises (fünf Zeilen sind das Maximum von `displayStatus`; die Zeile `noticeScreen` hat Vorrang, wenn sie gesetzt ist). Das Feld `current_password` und seine Prüfung bleiben. Kommentar über `applyPortalValues` anpassen (AP ist nur noch bei der Ersteinrichtung offen).

- [ ] **Step 5: Routen sperren.** `blockUnsafeRoutes` sperrt zusätzlich `/restart`, `/exit`, `/close`, `/info`. Vorher in `.pio/libdeps/ultra/WiFiManager/WiFiManager.cpp` prüfen, dass der Ablauf „WLAN wählen und speichern“ (`/wifi`, `/0wifi`, `/wifisave`, `/param`, `/paramsave`, Captive-Portal-Erkennung) keine davon braucht; braucht er eine, diese offen lassen und im Bericht nennen.

- [ ] **Step 6: Bauen und testen** nach Global Constraints.

- [ ] **Step 7: Doku.** `SECURITY.md`: der Satz zum Einrichtungs-WLAN lautet neu: offen nur, solange kein Update-Passwort gesetzt ist; danach WPA2 mit dem Update-Passwort. `recovery.md` und `4-set-up-wifi.md` (en, de): beim erneuten Einrichten fragt das `GlanceBox-XXXX`-WLAN nach dem Update-Passwort. Changelog.

- [ ] **Step 8: Commit** — `fix(firmware): protect the setup Wi-Fi of a configured device with the update password`

---

### Task 2: Server-Adresse lehnt gefährliche Zeichen ab (nur bei Eingabe)

**Files:**
- Modify: `firmware/lib/core/settings.cpp` (`applyServerUrl`), `firmware/lib/core/settings.h` (Kommentar der Fehlercodes)
- Modify: `firmware/src/i18n.cpp` (`msgForError`), `firmware/src/i18n.h` falls neuer `Msg`
- Test: `firmware/test/test_core/test_main.cpp`

**Interfaces:**
- `gb::applyServerUrl` liefert neu den Fehlercode `"invalid_chars"`, wenn die Eingabe eines von `' " < > \`` , ein Leerzeichen im Inneren, ein Steuerzeichen (< 0x20, 0x7f) oder ein Byte ≥ 0x80 enthält. `normalizeServerUrl` und das Laden gespeicherter Einstellungen bleiben unverändert.

- [ ] **Step 1: Tests schreiben**

```cpp
void test_server_url_rejects_markup_chars() {
  const char* bad[] = {"http://h/'x", "http://h/\"x", "http://h/<x", "http://h/>x",
                       "http://h/`x", "http://h/a b", "http://h/\x01", "http://h/\xc3\xa4"};
  for (const char* url : bad) {
    gb::Settings s{};
    std::string err;
    TEST_ASSERT_FALSE(gb::applyServerUrl(s, url, &err));
    TEST_ASSERT_EQUAL_STRING("invalid_chars", err.c_str());
    TEST_ASSERT_EQUAL_STRING("", s.serverUrl);
  }
}
void test_server_url_still_accepts_normal_urls() {   // surrounding spaces are trimmed as before
  gb::Settings s{};
  std::string err;
  TEST_ASSERT_TRUE(gb::applyServerUrl(s, "  http://192.168.1.10:8090/base/a-b_c.d~e  ", &err));
}
void test_stored_url_with_old_chars_still_loads() {
  // encode a Settings whose serverUrl holds "http://h/a'b" by writing the field directly,
  // decode it again: decoding succeeds and the URL is unchanged
}
```

Den dritten Test mit den vorhandenen `encodeSettings`/Dekodier-Funktionen ausschreiben. Zeigt er, dass das Laden über `applyServerUrl` läuft, das Laden auf `normalizeServerUrl` allein umstellen.

- [ ] **Step 2: Fehlschlag prüfen.**
- [ ] **Step 3: Prüfung in `applyServerUrl` ergänzen**, `msgForError` bildet `invalid_chars` für die Adresse auf einen passenden Text ab (vorhandenen Text wiederverwenden, wenn einer passt; sonst neuen `Msg` in beiden Sprachen).
- [ ] **Step 4: Bauen und testen.**
- [ ] **Step 5: Commit** — `fix(firmware): reject markup and control characters in the server URL` (Changelog).

---

### Task 3: Frame-Abruf mit Gesamtfrist und Kopf-Obergrenze

**Files:**
- Create: `firmware/lib/core/http_head.h`, `firmware/lib/core/http_head.cpp`
- Modify: `firmware/lib/core/frame_poll.h`, `firmware/lib/core/frame_poll.cpp` (neue Fehlercodes und Texte)
- Modify: `firmware/src/frame_client.cpp`, `firmware/src/frame_client.h` (Kommentare)
- Test: `firmware/test/test_core/test_main.cpp`

**Interfaces:**
```cpp
namespace gb {
constexpr size_t kMaxHeadBytes = 1024;
constexpr int kErrHeadTooLarge = -105;   // response head longer than kMaxHeadBytes
constexpr int kErrHeadTimeout = -106;    // head not complete within the deadline
constexpr int kErrHeadMalformed = -107;  // no valid HTTP status line

struct HttpHead {
  int status;              // 100..599
  long contentLength;      // -1 if absent, malformed or chunked
  char etag[kEtagCap];     // "" if absent or too long (storeEtag rules)
  int nextIn;              // parseNextIn of X-Next-In, -1 if absent
  int32_t localSec;        // parseLocalTime of X-Local-Time, -1 if absent
};
// data: the response head up to and including the blank line (CRLF CRLF).
// Header names are case-insensitive; optional spaces around the value are ignored.
bool parseHttpHead(const char* data, size_t len, HttpHead* out);

struct ServerTarget { char host[64]; uint16_t port; char path[128]; };  // path: "" or "/base", no trailing slash
// Splits a normalized server URL (http://host[:port][/path]); false if a part does not fit
// or the URL carries userinfo or a query.
bool parseServerTarget(const char* serverUrl, ServerTarget* out);

// Wraparound-safe: true once nowMs is at or past startMs + budgetMs.
bool deadlinePassed(uint32_t startMs, uint32_t nowMs, uint32_t budgetMs);
}
```
`frameErrorText` kennt die drei neuen Codes: `"reply too large"`, `"server too slow"`, `"bad reply"`.

- [ ] **Step 1: Tests schreiben**

```cpp
void test_http_head_parses_frame_reply() {
  const char* h = "HTTP/1.1 200 OK\r\ncontent-length: 1234\r\nETag: \"abc\"\r\n"
                  "X-Next-In:30\r\nx-local-time:  13:05:09 \r\ncontent-type: image/jpeg\r\n\r\n";
  gb::HttpHead head;
  TEST_ASSERT_TRUE(gb::parseHttpHead(h, strlen(h), &head));
  TEST_ASSERT_EQUAL(200, head.status);
  TEST_ASSERT_EQUAL(1234, head.contentLength);
  TEST_ASSERT_EQUAL_STRING("\"abc\"", head.etag);
  TEST_ASSERT_EQUAL(30, head.nextIn);
  TEST_ASSERT_EQUAL(13 * 3600 + 5 * 60 + 9, head.localSec);
}
void test_http_head_304_without_length() {          // status 304, contentLength -1, parse true
void test_http_head_chunked_has_no_length() {       // "Transfer-Encoding: chunked" -> contentLength -1
void test_http_head_rejects_garbage() {             // "", "HTTP/1.1\r\n\r\n", "FOO 200\r\n\r\n", status 99/600, no blank line
void test_http_head_bad_length_is_minus_one() {     // "Content-Length: 12x", "-5", 20 digits
void test_server_target() {
  // "http://192.168.1.10:8090" -> host, 8090, ""
  // "http://box"               -> "box", 80, ""
  // "http://box/base/x"        -> path "/base/x"
  // "http://u:p@box", "http://box:0", "http://box:70000", 70-char host, 130-char path -> false
}
void test_deadline_wraparound() {
  TEST_ASSERT_FALSE(gb::deadlinePassed(0xFFFFFF00u, 0x00000010u, 8000));
  TEST_ASSERT_TRUE(gb::deadlinePassed(0xFFFFFF00u, 0x00002000u, 8000));
}
void test_frame_error_text_new_codes() { /* the three texts above */ }
```

Die Kommentar-Tests als volle Unity-Tests ausschreiben.

- [ ] **Step 2: Fehlschlag prüfen.**

- [ ] **Step 3: `http_head.cpp` schreiben.** Keine dynamische Speicherung im Parser; `storeEtag`, `parseNextIn`, `parseLocalTime` aus dem Bestand benutzen (Werte vorher in kleine lokale Puffer kopieren und nullterminieren).

- [ ] **Step 4: `fetchFrame` umbauen.** Vorher prüfen, ob `normalizeServerUrl` heute Zugangsdaten (`user:pass@`) oder eine Query in der Adresse zulässt und ob `HTTPClient` sie benutzt; wenn ja, nicht stillschweigend brechen, sondern anhalten und berichten. Ablauf:
  1. `parseServerTarget`; Fehler: `kErrBadUrl`.
  2. `start = millis()`; `client.setTimeout(kTimeoutMs)`; `client.connect(host, port)`; Fehler: `-1` (wie bisher `connection failed`).
  3. Anfrage senden: `GET <path>/api/v1/frame?id=%06x&fw=<version> HTTP/1.1`, `Host`, `Connection: close`, `User-Agent: glancebox/<version>`, bei vorhandenem ETag `If-None-Match`.
  4. Kopf byteweise in einen `static char head[gb::kMaxHeadBytes]` lesen, bis `\r\n\r\n`; zwischen den Lesungen `yield()`. Puffer voll: `kErrHeadTooLarge`. `deadlinePassed(start, millis(), kTimeoutMs)`: `kErrHeadTimeout`. Verbindung endet vorher: `-5`.
  5. `parseHttpHead`; Fehler: `kErrHeadMalformed`. `r.status`, `r.nextIn`, `r.localSec` setzen.
  6. Status 200: `acceptFrameLength(contentLength)` wie heute, dann `displayJpegStream(client, r.len, kTimeoutMs)`; ETag erst nach vollständigem Dekodieren übernehmen.
  7. `client.stop()` auf jedem Pfad.
  `#include <ESP8266HTTPClient.h>` entfällt; `HTTP_CODE_OK` durch `200` ersetzen. Kommentar in `frame_client.h` und `frame_poll.h` (Fehlercodes) anpassen.

- [ ] **Step 5: Bauen und testen.** Flash-Größe vorher und nachher im Bericht nennen.

- [ ] **Step 6: Gegen den echten Server prüfen, ohne Gerät.** Den Server lokal starten (oder einen kleinen Python-Testserver) und die exakt gleiche Anfrage mit `printf ... | nc` senden: Antwortkopf ist kleiner als 1024 Byte und enthält `content-length`, `etag`, `x-next-in`, `x-local-time`. Kopfgröße im Bericht nennen.

- [ ] **Step 7: Commit** — `fix(firmware): bound the frame request with a total deadline and a header size cap` (Changelog).

---

### Task 4: Sperre nach Fehlversuchen und Host-Prüfung

**Files:**
- Create: `firmware/lib/core/auth_throttle.h`, `firmware/lib/core/auth_throttle.cpp`
- Modify: `firmware/lib/core/web_util.h`, `firmware/lib/core/web_util.cpp`
- Modify: `firmware/src/web_ui.cpp` (`webUiAuthorize`, Routen-Registrierung), `firmware/src/safe_mode.cpp` falls dort eigene Routen ohne `webUiAuthorize` liegen
- Test: `firmware/test/test_core/test_main.cpp`

**Interfaces:**
```cpp
namespace gb {
class AuthThrottle {
 public:
  static constexpr uint8_t kMaxFailures = 5;
  static constexpr uint32_t kLockMs = 30000;
  bool locked(uint32_t nowMs);          // clears an expired lock (wraparound-safe)
  void onFailure(uint32_t nowMs);       // the 5th consecutive failure starts a lock
  void onSuccess();                     // resets the counter
  uint32_t retryAfterS(uint32_t nowMs); // whole seconds left, rounded up; 0 if not locked
};
// Host header check against DNS rebinding: true for an IPv4 literal, for ownHostname and for
// ownHostname + ".local" (case-insensitive), each with an optional ":port". False if empty.
bool hostAllowed(const std::string& hostHeader, const std::string& ownHostname);
}
```

- [ ] **Step 1: Tests schreiben**

```cpp
void test_auth_throttle_locks_after_five() {
  gb::AuthThrottle t;
  for (int i = 0; i < 4; ++i) t.onFailure(1000);
  TEST_ASSERT_FALSE(t.locked(1000));
  t.onFailure(1000);
  TEST_ASSERT_TRUE(t.locked(1000));
  TEST_ASSERT_EQUAL(30, t.retryAfterS(1000));
  TEST_ASSERT_TRUE(t.locked(30999));
  TEST_ASSERT_FALSE(t.locked(31000));
  t.onFailure(31000);                    // after a lock one more failure locks again
  TEST_ASSERT_TRUE(t.locked(31000));
}
void test_auth_throttle_success_resets() { /* 4 failures, onSuccess, 4 failures -> not locked */ }
void test_auth_throttle_wraparound() {   /* lock at 0xFFFFFF00: locked at 0x10, free at 0x8000 */ }
void test_host_allowed() {
  TEST_ASSERT_TRUE(gb::hostAllowed("192.168.1.50", "ESP-AB12CD"));
  TEST_ASSERT_TRUE(gb::hostAllowed("192.168.1.50:80", "ESP-AB12CD"));
  TEST_ASSERT_TRUE(gb::hostAllowed("esp-ab12cd", "ESP-AB12CD"));
  TEST_ASSERT_TRUE(gb::hostAllowed("ESP-AB12CD.local", "ESP-AB12CD"));
  TEST_ASSERT_FALSE(gb::hostAllowed("evil.example", "ESP-AB12CD"));
  TEST_ASSERT_FALSE(gb::hostAllowed("192.168.1.50.evil.example", "ESP-AB12CD"));
  TEST_ASSERT_FALSE(gb::hostAllowed("ESP-AB12CD.evil.example", "ESP-AB12CD"));
  TEST_ASSERT_FALSE(gb::hostAllowed("999.1.1.1", "ESP-AB12CD"));
  TEST_ASSERT_FALSE(gb::hostAllowed("", "ESP-AB12CD"));
  TEST_ASSERT_TRUE(gb::hostAllowed("192.168.1.50", ""));    // IPv4 needs no device name
  TEST_ASSERT_FALSE(gb::hostAllowed(".local", ""));
}
```

- [ ] **Step 2: Fehlschlag prüfen.**

- [ ] **Step 3: `AuthThrottle` und `hostAllowed` schreiben.**

- [ ] **Step 4: Verdrahten in `web_ui.cpp`.**
  - Host-Prüfung für jede Route, auch GET und im abgesicherten Modus: eine Hilfsfunktion `hostOk()` (`gb::hostAllowed(server.hostHeader(), WiFi.hostname())`), aufgerufen am Anfang jedes Handlers bzw. über einen gemeinsamen Wrapper bei der Registrierung; Ablehnung mit `403` und dem Text `open this page by the device's IP address`. Statische Dateien (`/app.css`, `/app.js`) sind eingeschlossen.
  - `webUiAuthorize`: Reihenfolge Host, Origin, Sperre, Zugangsdaten. Gesperrt: `429` mit `Retry-After: <s>` und kurzem Text, ohne die Zugangsdaten zu prüfen. Anfrage ohne `Authorization`-Kopfzeile: `requestAuthentication()` wie heute, zählt nicht als Fehlversuch. Mit Kopfzeile und falsch: `onFailure(millis())`. Richtig: `onSuccess()`.
  - Die Datei-Upload-Route prüft die Berechtigung schon am Anfang des Uploads; dort gilt dieselbe Reihenfolge, und ein Upload darf nicht mehrfach als Fehlversuch zählen.
  - `firmware/web/app.js`: zeigt bei 429 den Antworttext an, wenn es heute Fehlertexte aus Antworten anzeigt; sonst unverändert.

- [ ] **Step 5: Bauen und testen.**

- [ ] **Step 6: Doku.** `SECURITY.md`: Sperre und Host-Prüfung in einem Satz. `docs/en/recovery.md`/`docs/de/recovery.md`: Geräteseite über die IP-Adresse öffnen; nach fünf falschen Passwörtern 30 s warten. Changelog.

- [ ] **Step 7: Commit** — `fix(firmware): throttle password attempts and check the Host header`
