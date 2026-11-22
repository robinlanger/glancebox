# Geräteseite und Einrichtung (Issues 20 bis 22): Design

Stand 2026-11-22, Basis: Branch `fix/device-page-and-setup` auf `main` bei 0b674a5 (0.6.2).

Der Maintainer hat auf die Fragerunde verzichtet. Alle Festlegungen, die sonst seine wären, sind
unten als **Entscheidung (Fable)** markiert, jeweils mit Grund und mit dem Preis, falls sie falsch
ist. Jede lässt sich einzeln zurücknehmen.

## Anlass und Ziel

Drei kleine Meldungen betreffen die Stellen, an denen der Besitzer das Gerät mit der Hand bedient:

- **#20:** Der Helligkeitsregler der Geräteseite klebt nach der Passwortabfrage am Mauszeiger.
- **#21:** Ein neues Update-Passwort wird nur einmal und verdeckt getippt. Seit 0.6.2 schützt
  dasselbe Passwort auch das Einrichtungs-WLAN eines eingerichteten Geräts und das Zurücksetzen
  auf der Geräteseite. Ein Tippfehler heißt deshalb: seriell neu flashen.
- **#22:** Das Einrichtungsportal verbindet erst mit dem WLAN und meldet Erfolg, prüft danach
  Server-URL und Passwort und öffnet sich bei einem Fehler erneut. Ein leeres Feld heißt
  „Server URL: host is missing“.

Ziel: Alle drei verhalten sich so, wie ein Besitzer es ohne Anleitung erwartet. Die Arbeit endet
auf diesem Branch; die Commits schließen die Issues beim Merge.

## Ziele

- Der Regler hört auf zu folgen, sobald die Maus losgelassen ist, auch wenn dabei das Passwort
  abgefragt wird.
- Ein neues Update-Passwort wird an jeder Stelle zweimal eingegeben und nur gespeichert, wenn
  beide Eingaben gleich sind.
- Das Portal prüft Server-URL, Passwort, Helligkeit und das aktuelle Passwort, **bevor**
  WiFiManager eine WLAN-Verbindung versucht, und zeigt den Fehler sofort auf der Formularseite.
- Ein leeres Server-URL-Feld heißt „Server URL is required“; das Feld zeigt den Platzhalter
  `http://192.168.x.x:8090`.

## Nicht-Ziele

- Kein Knopf „Passwort anzeigen“, keine Stärkeanzeige.
- Kein neues Aussehen des Portals, keine deutschen Feldbeschriftungen im Portal (sie sind heute
  englisch; nur der Fehlerhinweis ist zweisprachig).
- Keine Prüfung, ob im Portal überhaupt ein WLAN gewählt wurde (siehe „Beobachtungen“).
- Kein Versionssprung, kein Tag, kein Push, kein Flashen des echten Displays.
- Kein neues JavaScript-Test-Gerüst über einen einzelnen Test hinaus.

## Anti-Ziele

- Ein Gerät, dessen Geräteseite startet, bevor Server-URL und Update-Passwort gesetzt sind. Die
  Seite darf weiterhin erst nach vollständiger Einrichtung starten, damit niemand sonst im LAN das
  erste Passwort setzt. `portalRun` bleibt die einzige Stelle, die das entscheidet.
- Ein bestehendes Gerät, das nach dem Update seine Einstellungen nicht mehr lädt oder dessen
  gespeicherte URL (auch eine mit heute verbotenen Zeichen) im Portal nicht mehr durchgeht.
- Ein Passwort, das irgendwo im Seitenquelltext des Portals wieder auftaucht.
- Die Passwortsperre (5 Fehlversuche, 30 s) löst durch bloßes Ziehen am Regler aus.
- Doku oder Bericht, die Verhalten im Browser oder auf dem Gerät als geprüft ausgeben, obwohl es
  nur gebaut wurde.

## Randbedingungen

- Reine Logik in `firmware/lib/core` mit nativen Unity-Tests
  (`firmware/test/test_core/test_main.cpp`; heute 106 native Tests, davon 102 in `test_core`); `firmware/src`
  verdrahtet nur.
- `firmware/size-limit.txt` (1 011 696 Byte) wird nicht angehoben. `firmware.bin` liegt bei etwa
  439 kB; die Änderungen kosten grob 1 bis 2 kB. Kein Platzrisiko.
- Format der gespeicherten Einstellungen und Flash-Layout bleiben unverändert.
- Texte in `i18n.cpp` Englisch und Deutsch; Texte für den Bildschirm nur ASCII (der Bildschirm
  zeigt den englischen Text, höchstens 47 Zeichen).
- Doku in `docs/en` und `docs/de` gleich (`python3 tools/check_docs_parity.py`); Nutzersichtbares
  in `CHANGELOG.md` unter `## [Unreleased]`.
- Keine echten LAN-Adressen oder E-Mail-Adressen in Commits und Doku.
- Aus der Sicherheitsarbeit vom 2026-11-22 bleibt alles gültig: WPA2 am Einrichtungs-WLAN
  eingerichteter Geräte, `current_password` für Änderungen im Portal, Zeichenprüfung der URL nur
  bei neuer Eingabe, Passwortsperre, Host- und Origin-Prüfung, gesperrte WiFiManager-Routen.
- Der `ultra`-Build läuft nicht auf dem Mac, sondern auf dem Build-Rechner des Maintainers.
  Verhalten im Browser und auf dem Gerät kann nur der Maintainer prüfen.

## Was der Code heute tut

**Regler (`firmware/web/app.js`).** Jeder Regler schickt bei `input` (also während des Ziehens)
über `createPreviewPump` ein `POST /api/brightness-preview` und speichert bei `change` (Loslassen)
über `POST /api/settings`. Beide Routen laufen durch `webUiAuthorize()`; ohne oder mit falschem
Passwort antwortet `refuse()` mit `server.requestAuthentication()`, also 401 mit
`WWW-Authenticate: Basic`. Auf diese Antwort zeigt der Browser seinen eigenen Passwortdialog, auch
bei `fetch`. Die erste Anfrage, die ein Passwort braucht, ist damit die Vorschau **während die
Maustaste gedrückt ist**. Der Dialog ist modal; das Loslassen geht an den Dialog, die Seite sieht
es nie, und der Regler bleibt im Ziehzustand bis zum nächsten Klick. Die vermutete Ursache aus dem
Issue stimmt also mit dem Code überein. Bestätigt ist sie durch Lesen, nicht im Browser.

**Passwort.** Geräteseite mit Skript: Formular `#pw-form` mit einem Feld `password`, geschickt an
`/api/settings`. Ohne Skript: `<noscript>`-Formular an `/settings` mit einem Feld `password`
(leer = unverändert). Portal: Parameter `update_password`, bei der ersten Einrichtung Pflicht,
später leer = unverändert.

**Portal (`firmware/src/portal.cpp`, WiFiManager 2.0.17).** Die Parameter stehen im WLAN-Formular
(`/wifi`, `_paramsInWifi`), das an `/wifisave` schickt. `WiFiManager::handleWifiSave()` liest SSID
und Passwort, ruft `doParamSave()` (kopiert die Feldwerte in die Parameter, ruft den
Save-Params-Callback), schickt die Seite „Saving Credentials“ und setzt `connect = true`; die
Portalschleife verbindet dann. Erst nach der Rückkehr von `startConfigPortal`/`autoConnect` prüft
`applyPortalValues`.

Was die Bibliothek an Haken bietet (in der Quelle nachgelesen):

- `setPreSaveConfigCallback` und `setPreSaveParamsCallback` laufen vor dem Speichern, sind aber
  `void`: Sie können weder ablehnen noch die Antwortseite ändern.
- `setWebServerCallback` läuft in `setupHTTPServer()` **vor** den `server->on(...)` der
  Bibliothek. `ESP8266WebServer` nimmt die erste passende Route; ein dort registriertes
  `/wifisave` verdeckt also das der Bibliothek. Genau so arbeitet `blockUnsafeRoutes` schon.
- `handleWifi(bool scan)` (rendert die Formularseite) und `handleWifiSave()` sind `protected`,
  nicht `private`. Eine abgeleitete Klasse darf beide aufrufen.
- Der Hinweis-Parameter hält nur einen Zeiger auf `noticeHtml`; die Seite liest ihn bei jedem
  Rendern neu.
- Das Eingabefeld eines Parameters ist `<input id name maxlength value='{v}' {c}>`: `{c}` nimmt
  beliebige Attribute (`placeholder`, `required`, `minlength`), `{v}` wird **nicht** maskiert.
- Scheitert die WLAN-Verbindung, bleibt das blockierende Portal offen. Die von `doParamSave()`
  kopierten Werte, auch die Passwörter, stehen danach in `value='...'` der Formularseite.

Damit gibt es den gesuchten Weg: eigener `/wifisave`-Handler, der bei ungültigem Formular die
Formularseite mit Hinweis ausgibt, ohne dass WiFiManager verbindet, und bei gültigem Formular die
Originalfunktion aufruft.

**Tests für `app.js`** gibt es nicht. `server/tests/test_webasset.py` prüft nur das Minifizieren.
`createPreviewPump` steht absichtlich außerhalb von `init()` und lässt sich ohne Browser laden.

---

## #20 Regler klebt nach der Passwortabfrage

### Wege

- **A (gewählt): Die Vorschau fragt nie nach dem Passwort.** `/api/brightness-preview` antwortet
  ohne gültige Anmeldung mit 401 **ohne** `WWW-Authenticate`. Der Browser zeigt dann keinen
  Dialog. Die Abfrage kommt erst beim Speichern, also nach dem Loslassen. Kennt der Browser das
  Passwort schon, schickt er es von sich aus mit (gleicher Pfad `/api/`), und die Vorschau läuft
  wie bisher.
- **B: Nur im Skript lösen.** Vorschau erst senden, nachdem in dieser Seitenansicht eine
  angemeldete Anfrage geklappt hat. Keine Firmware-Änderung, aber nach jedem Neuladen der Seite
  hat der erste Zug keine Vorschau, obwohl der Browser das Passwort kennt. Und wird das Passwort
  in einem anderen Tab geändert, kommt der Dialog wieder mitten im Ziehen.
- **C: Den hängenden Zug reparieren.** Nach der ersten Vorschau-Antwort den Regler neu erzeugen
  oder den Fokus nehmen. Hängt an Browser-Eigenheiten und behandelt das Symptom.

**Entscheidung (Fable):** Weg A. **Grund:** Er beseitigt die Ursache (Dialog bei gedrückter
Maustaste) für jeden Browser und jeden Auslöser, auch Touch und veraltetes Passwort, und lässt die
Vorschau im Normalfall unangetastet. **Kosten, falls falsch:** Schickt ein Browser das Passwort
nicht von sich aus an `/api/brightness-preview`, hat er nie Live-Vorschau; die Helligkeit ändert
sich dann erst beim Loslassen. Rückweg: eine Zeile in `handlePreview`.

### Verhalten

Firmware (`web_ui.cpp`):

- `webUiAuthorize` bekommt einen Parameter `bool challenge = true`. Mit `false` wird bei fehlendem
  oder falschem Passwort `401 text/plain` mit dem Text `password required` gesendet, ohne
  `WWW-Authenticate`. Host, Origin und Sperre (403, 403, 429) bleiben wie bisher.
- Nur `handlePreview` ruft mit `false`. Alle anderen Routen unverändert.
- Ein falsches Passwort an der Vorschau zählt weiter für die Sperre (`decideAccess` unverändert).

Skript (`app.js`):

- `post()` hängt an jeden geworfenen Fehler den HTTP-Status als `status` (bei Netzfehlern fehlt
  er).
- `createPreviewPump(send, minGapMs)`: Löst `send` mit genau `false` auf, verwirft die Pumpe den
  wartenden Wert und ignoriert weitere `push()` bis zum nächsten `flush()`. Alles andere wie
  bisher (eine Anfrage zur Zeit, Mindestabstand, der letzte Wert gewinnt).
- Der Regler übergibt ein `send`, das bei Status 401 oder 429 `false` liefert. `flush()` läuft
  wie bisher bei `change`, also beim Loslassen; danach ist die Pumpe wieder frei.

Ergebnis je Fall:

| Fall | Beim Ziehen | Beim Loslassen |
| --- | --- | --- |
| Browser kennt das Passwort | Vorschau wie bisher | speichert |
| Browser kennt kein Passwort | eine Vorschau-Anfrage, 401 ohne Dialog, danach still | Dialog, dann speichern |
| Browser hat ein altes Passwort | eine Anfrage, zählt als ein Fehlversuch, danach still | Dialog (zweiter Fehlversuch), dann speichern |
| Sperre aktiv | eine Anfrage, 429, danach still | rote Meldung mit Wartezeit wie bisher |

**Entscheidung (Fable):** Ohne gespeicherte Anmeldung gibt es beim ersten Zug keine Vorschau; das
Display ändert sich erst nach Loslassen und Passwort. **Grund:** Jede Vorschau vor der Anmeldung
bräuchte entweder den Dialog im Ziehen (der Fehler) oder eine Abfrage beim Öffnen der Seite, die
bewusst ohne Passwort lesbar ist. **Kosten, falls falsch:** ein Zug ohne Vorschau pro
Browsersitzung; die Doku sagt es in einem Satz.

**Entscheidung (Fable):** Die Pumpe hält nach einer abgewiesenen Vorschau bis zum Loslassen an.
**Grund:** Sonst schickt ein Zug mit altem Passwort zehn falsche Anmeldungen pro Sekunde und löst
die 30-s-Sperre aus, die dann auch das Speichern trifft. **Kosten, falls falsch:** keine; nach dem
Loslassen ist alles wie vorher.

**Entscheidung (Fable):** Die Pumpe bekommt einen Test, der `app.js` mit `node` lädt
(`server/tests/test_device_page_js.py`, übersprungen, wenn `node` oder die Datei fehlt).
**Grund:** Das Anhalten ist Logik, die sich ohne Browser prüfen lässt, und `server/tests` prüft
schon heute Firmware-Dateien (`test_webasset.py`); in CI läuft pytest auf dem Runner, der `node`
hat. **Kosten, falls falsch:** eine Testdatei, die in einer Umgebung ohne `node` still übersprungen
wird.

### Nur im Browser prüfbar

Dass der Regler loslässt; dass 401 ohne `WWW-Authenticate` in Chrome, Firefox und Safari keinen
Dialog zeigt; dass nach der Anmeldung die Vorschau wieder live läuft.

---

## #21 Neues Passwort zweimal eingeben

### Wege

- **A (gewählt): zweites Feld an jeder Stelle, Prüfung in der Firmware.** Wie im Issue verlangt.
  Funktioniert ohne Skript und im Portal.
- **B: Knopf „Passwort anzeigen“ statt Wiederholung.** Weniger Tippen, braucht aber Skript, fehlt
  also im `<noscript>`-Formular, und hilft nicht gegen einen Tippfehler, den man nicht bemerkt.
- **C: beides.** Mehr Oberfläche für denselben Nutzen.

**Entscheidung (Fable):** Weg A, ohne Anzeige-Knopf. **Grund:** Das Issue nennt genau diese
Lösung, und sie ist die einzige, die an allen drei Stellen gleich funktioniert. **Kosten, falls
falsch:** Der Knopf lässt sich später ergänzen, ohne etwas zurückzubauen.

### Wo und wie

Eine Regel in `lib/core`, an allen Stellen benutzt:
`applyNewPassword(s, pw, repeat, &error)` meldet `"mismatch"`, wenn `pw != repeat`
(byte-genau, kein Kürzen von Leerzeichen), sonst gelten die Regeln von `applyPassword`.
Die Gleichheit wird **zuerst** geprüft.

| Stelle | Felder | Regel |
| --- | --- | --- |
| Geräteseite mit Skript (`#pw-form`) | `password`, `password_repeat`, je mit Beschriftung | Das Skript vergleicht vor dem Senden und zeigt bei Ungleichheit die Meldung, ohne Anfrage (also auch ohne Passwortdialog). Sonst `POST /api/settings` mit beiden Feldern. Nach Erfolg beide Felder leeren. |
| `/api/settings` | `password`, `password_repeat` | Ist `password` vorhanden, muss `password_repeat` gleich sein; fehlt es, gilt das als ungleich. Fehlerfeld `password_repeat`, Code `mismatch`. |
| Geräteseite ohne Skript (`/settings`) | `password`, `password_repeat` | Beide leer = unverändert. Ist eines nicht leer, müssen beide gleich sein. |
| Portal, erste Einrichtung | `update_password`, `update_password_repeat` | Beide Pflicht und gleich. |
| Portal, eingerichtetes Gerät | dieselben | Beide leer = unverändert. Ist eines nicht leer, müssen beide gleich sein (und `current_password` stimmen, wie bisher). |

**Entscheidung (Fable):** Auch `/api/settings` verlangt die Wiederholung, ein fehlendes Feld gilt
als ungleich. **Grund:** Eine Regel für jeden Weg; es bleibt kein Weg, auf dem eine einzelne
verdeckte Eingabe das Passwort setzt. Die Schnittstelle ist nicht dokumentiert, ihr einziger
Nutzer ist `app.js`. **Kosten, falls falsch:** Ein eigenes Skript, das das Passwort über
`/api/settings` setzt, bekommt 400, bis es `password_repeat` mitschickt.

**Entscheidung (Fable):** Wer nur das Wiederholungsfeld füllt, bekommt „stimmen nicht überein“
statt eines stillen „unverändert“. **Grund:** Sonst glaubt jemand, das Passwort geändert zu haben.
**Kosten, falls falsch:** keine erkennbaren.

**Entscheidung (Fable):** Feldnamen `password_repeat` und `update_password_repeat`.
**Grund:** Sie hängen an den bestehenden Namen. **Kosten, falls falsch:** reine Umbenennung.

### Texte

| `Msg` | Englisch | Deutsch | Wo |
| --- | --- | --- | --- |
| `PwNew` | New password | Neues Passwort | Beschriftung im Formular mit Skript |
| `PwRepeat` | Repeat new password | Neues Passwort wiederholen | Beschriftung, mit und ohne Skript |
| `ErrPwMismatch` | The two passwords do not match | Die beiden Passwörter stimmen nicht überein | Fehler überall; im Skript als `T.pw_mismatch` |

Im `<noscript>`-Formular bleibt die erste Beschriftung `NewPassword` („New update password (empty
= keep)“), darunter kommt `PwRepeat`. Portal: neue Beschriftung „Repeat update password“
(englisch wie die anderen Portalfelder).

Bestehende Geräte: Nichts Gespeichertes ändert sich. Das Passwort bleibt, bis es jemand ändert.

### Nur im Browser prüfbar

Aussehen des Formulars mit zwei Feldern, Meldung bei Ungleichheit, das Formular ohne Skript.

---

## #22 Portal prüft vor dem Verbinden

### Wege

- **A (gewählt): eigener `/wifisave`-Handler in einer von `WiFiManager` abgeleiteten Klasse.**
  Der Handler prüft das Formular. Ungültig: Hinweis setzen, Formularseite ausgeben
  (`handleWifi(true)`), fertig; `connect` wird nie gesetzt. Gültig: `handleWifiSave()` der
  Bibliothek aufrufen, alles Weitere wie heute.
- **B: nur Browser-Prüfung** (`required`, `minlength` an den Feldern). Null Code, nichts geht
  verloren, deckt aber `https://`, verbotene Zeichen, ungleiche Passwörter und das falsche
  aktuelle Passwort nicht ab, und Captive-Portal-Browser halten sich nicht verlässlich daran.
- **C: Pre-Save-Callback.** Kann nicht ablehnen (siehe oben). Scheidet aus.
- **D: WiFiManager ersetzen oder patchen.** Unverhältnismäßig.

**Entscheidung (Fable):** Weg A als Prüfung, dazu die Attribute aus B als erste Linie.
**Grund:** A ist der einzige Weg, der wirklich vor dem Verbinden ablehnt und den Fehler auf der
Formularseite zeigt; B fängt die häufigsten Fehler (leere URL, kurzes Passwort) schon ab, bevor
irgendetwas gesendet wird und ohne dass Eingaben verloren gehen. **Kosten, falls falsch:** Die
Lösung hängt an zwei `protected`-Funktionen und an der Registrierungsreihenfolge von WiFiManager
2.0.17 (in `platformio.ini` fest). Ein Bibliothekswechsel muss beides neu prüfen.

### Prüfung (reine Logik)

`gb::applyPortalForm(s, form, &next, &field, &error)` in `lib/core/settings` ersetzt die Prüfung
in `applyPortalValues`. Reihenfolge und Regeln (inhaltlich wie heute, bis auf die markierten
Punkte):

1. `server_url`: `applyServerUrl`. Eine unverändert zurückgeschickte gespeicherte URL bleibt
   erlaubt. Leer oder nur Leerzeichen: neuer Code `required`.
2. `update_password` (+ Wiederholung, siehe #21): Pflicht, solange kein gültiges Passwort
   gespeichert ist; sonst leer = unverändert.
3. `brightness`: leer = unverändert; sonst nur Ziffern, 5 bis 100, Code `bad_brightness`.
4. `current_password`: Nur wenn sich die Einstellungen ändern würden **und** ein gültiges
   Passwort gespeichert ist, muss es stimmen; Code `wrong_password`. Reine WLAN-Änderungen
   brauchen es weiterhin nicht (das WPA2 des Einrichtungs-WLANs ist dort der Schutz).

**Entscheidung (Fable):** Der Code `required` entsteht in `normalizeServerUrl` und gilt damit auch
auf der Geräteseite, wenn dort jemand die Adresse leert. `http://` ohne Host bleibt
`empty_host`. **Grund:** dieselbe Eingabe, dieselbe Meldung, an jeder Stelle. **Kosten, falls
falsch:** ein Text auf der Geräteseite ändert sich mit.

**Entscheidung (Fable):** Helligkeit im Portal nur noch als reine Ziffernfolge (heute `strtol`,
das auch `+50` annimmt). **Grund:** dieselbe Funktion wie auf der Geräteseite. **Kosten, falls
falsch:** keine erkennbaren; das Feld ist `type=number`.

Die sofortige Antwort auf ein falsches `current_password` ist kein neues Rateorakel: Wer das
Formular eines eingerichteten Geräts erreicht, hat sich schon mit dem Update-Passwort am
WPA2-WLAN angemeldet.

### Ablauf im Portal

- `blockUnsafeRoutes` sperrt zusätzlich `/param` und `/paramsave` (403).
- Der eigene Handler für `/wifisave` (jede Methode) liest `server_url`, `update_password`,
  `update_password_repeat`, `brightness`, `current_password` aus der Anfrage und ruft
  `applyPortalForm`.
- **Ungültig:** Hinweis setzen (Englisch und Deutsch), Bildschirm neu zeichnen (zeigt den
  englischen Hinweis wie heute), Formularseite mit Netzliste ausgeben. Das Feld Server-URL zeigt
  die eingegebene Adresse wieder, wenn sie für sich gültig ist (in normalisierter Form), sonst den
  gespeicherten Wert. WLAN-Name, WLAN-Passwort und alle Passwortfelder sind leer. WiFiManager
  verbindet nicht.
- **Gültig:** Hinweis löschen, Formular merken, `handleWifiSave()` aufrufen (Seite „Saving
  Credentials“, danach Verbindungsversuch wie heute), anschließend die Werte der drei
  Passwort-Parameter leeren.
- **Nach der Rückkehr** von `startConfigPortal`/`autoConnect`: Ist ein Formular gemerkt, wird es
  noch einmal durch `applyPortalForm` geschickt, gespeichert und die Helligkeit gesetzt, genau an
  der Stelle, an der heute `applyPortalValues` läuft. Die Schleifenbedingungen bleiben; „Formular
  gemerkt“ ersetzt `paramsSaved`.
- Scheitert die WLAN-Verbindung (falsches WLAN-Passwort), bleibt das Portal wie heute offen. Die
  Server-URL steht noch im Feld, die Passwörter nicht; ein neues Absenden ersetzt das gemerkte
  Formular.

**Entscheidung (Fable):** Gespeichert wird weiterhin erst nach der Rückkehr des Portals, nicht
schon vor dem Verbinden. **Grund:** Würde vor dem Verbinden gespeichert, wäre ein Gerät mit
falschem WLAN-Passwort „eingerichtet“, und sein Einrichtungs-WLAN würde beim nächsten Durchlauf
auf WPA2 wechseln, während der Besitzer noch am offenen WLAN hängt. **Kosten, falls falsch:**
keine Verhaltensänderung gegenüber heute.

**Entscheidung (Fable):** Nach einem abgelehnten Formular müssen WLAN-Name (ein Tipp in der
Netzliste), WLAN-Passwort und Update-Passwort neu eingegeben werden; nur die Server-URL bleibt
stehen. **Grund:** Passwörter schickt das Gerät grundsätzlich nicht zurück. Den WLAN-Namen
vorzubelegen bräuchte ein eingebettetes Skript mit sicher kodiertem Namen für einen gesparten
Tipp. **Kosten, falls falsch:** ein Tipp mehr; lässt sich nachrüsten.

**Entscheidung (Fable):** Passwortfelder werden nach einem angenommenen Formular geleert und
stehen nie im Seitenquelltext. **Grund:** Heute stehen sie nach einem gescheiterten
Verbindungsversuch in `value='...'`, unmaskiert und bei der ersten Einrichtung über ein offenes
WLAN abrufbar. Der neue Handler sitzt genau an dieser Stelle. **Kosten, falls falsch:** Nach
einem falschen WLAN-Passwort tippt man das Update-Passwort noch einmal.

**Entscheidung (Fable):** `/param` und `/paramsave` werden gesperrt. **Grund:** Sie nehmen
dieselben Felder an, aber ohne die neue Prüfung, und sind im Menü nicht verlinkt (das Menü hat nur
„wifi“). **Kosten, falls falsch:** keine; die Seiten waren nie Teil der Anleitung.

**Entscheidung (Fable):** Der Hinweis rollt sich per kleinem Skript ins Bild
(`scrollIntoView`); der Puffer `noticeHtml` wächst von 200 auf 320 Zeichen. **Grund:** Der Hinweis
steht in der Seite unter der Netzliste und den WLAN-Feldern; auf einem Handy mit vielen Netzen
wäre er sonst unter dem sichtbaren Bereich, und „sofort sichtbar“ ist der Kern des Issues.
**Kosten, falls falsch:** eine Zeile Skript; ohne Skript steht der Hinweis an derselben Stelle wie
heute.

### Felder und Texte

| Parameter | Beschriftung | Attribute |
| --- | --- | --- |
| `current_password` (nur eingerichtet) | unverändert | `type='password'` |
| `server_url` | `Server URL` | `placeholder='http://192.168.x.x:8090' required` |
| `update_password` | unverändert (`… (min. 8 characters)` bzw. `… (empty = keep)`) | `type='password' minlength='8' autocomplete='new-password'`, bei der ersten Einrichtung zusätzlich `required` |
| `update_password_repeat` | `Repeat update password` | wie `update_password` |
| `brightness` | unverändert | unverändert |

| `Msg` | Englisch | Deutsch |
| --- | --- | --- |
| `ErrUrlRequired` | Server URL is required | Die Server-URL fehlt |

**Entscheidung (Fable):** Platzhalter `http://192.168.x.x:8090` wie im Issue; der Hinweis
`(http://host:8080)` verschwindet aus der Beschriftung. **Grund:** Wunsch des Maintainers; 8090
ist der Port des Home-Assistant-Add-ons. **Kosten, falls falsch:** Der Docker-Server nutzt
standardmäßig 8080; wer den Platzhalter abtippt, landet auf dem falschen Port. Ein String.

**Entscheidung (Fable):** Die Portal-Skizze `docs/img/site/setup-portal.svg` bleibt, wie sie ist.
**Grund:** Sie ist eine Skizze, kein Bildschirmfoto; der Text daneben nennt das zweite Feld.
**Kosten, falls falsch:** Die Skizze zeigt ein Feld weniger als das Portal.

Bestehende Geräte: Ein eingerichtetes Gerät, das nur ein neues WLAN bekommt, schickt die
gespeicherte URL unverändert zurück und kommt ohne `current_password` durch, wie heute. Das gilt
auch für eine gespeicherte URL mit heute verbotenen Zeichen.

### Nur auf dem Gerät prüfbar

Dass der eigene Handler den der Bibliothek tatsächlich verdeckt; die Fehlerseite in den
Captive-Portal-Browsern von iOS und Android; das Rollen zum Hinweis; die Browser-Prüfung der
Attribute; der Hinweis auf dem Bildschirm; der Weg „gültiges Formular, falsches WLAN-Passwort“;
403 auf `/param`.

---

## Beobachtungen außerhalb des Auftrags

- Ein Formular ohne WLAN-Namen wird von WiFiManager als „gespeichert“ bestätigt und tut bei der
  ersten Einrichtung nichts. Derselbe Fehlertyp wie #22, aber nicht gemeldet; bleibt offen.
- Das bisherige Zurückgeben der Passwörter im Seitenquelltext (siehe oben) wird hier mit behoben
  und gehört in den CHANGELOG.

## Dem Umsetzer überlassen

- Aufteilung innerhalb von `portal.cpp` (Name der abgeleiteten Klasse, Hilfsfunktionen).
- Genaues Markup und CSS der beiden Passwortfelder, solange die bestehenden Klassen (`.stack`,
  `label`) genutzt werden.
- Wortlaut von Doku und CHANGELOG, in beiden Sprachen gleich.
- Ob `msgForPatchError` in `web_ui.cpp` nach der Erweiterung von `msgForError` noch gebraucht
  wird.
