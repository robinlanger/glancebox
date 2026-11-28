# 12-Stunden-Zeitformat und Add-on-Anleitung – Design

Stand: 2026-11-28 · Issues: #36 „12H Time“, #37 „Home assistant configuration help“ (beide von
TimDowker) · Ziel-Version: Vorschlag 0.9.0, nicht festgelegt · Größe: Projekt in zwei Teilen

Dieses Design entstand ohne Rückfragen an Robin. Jede Stelle, an der eine Rückfrage nötig
gewesen wäre, steht unter [Offene Fragen](#offene-fragen) mit Optionen und Empfehlung; das
Design baut auf der jeweiligen Empfehlung auf. Geprüft wurde es von mir selbst mit dem Blick
eines Umsetzers, nicht von einem zweiten Agenten.

## Absicht

Ein Nutzer außerhalb des deutschsprachigen Raums nutzt Glance Box mit dem Home-Assistant-Add-on.
Er liest Uhrzeiten im 12-Stunden-Format (AM/PM), das es heute nicht gibt, und er fand keinen
Weg vom installierten Add-on zu einer laufenden, selbst zusammengestellten Seitenliste. Beides
soll für alle Nutzer gelöst werden: eine Einstellung für das Zeitformat und eine Anleitung, die
Schritt für Schritt vom Add-on-Store bis zur eigenen `config.yaml` führt.

## Teil A: Zeitformat (#36)

### Ziele

- Eine Einstellung `time_format: 24h | 12h` schaltet alle Uhrzeiten der mitgelieferten Seiten um.
- Ohne die Einstellung bleibt alles wie heute (`24h`), Pixel für Pixel.
- Eine einzige Funktion formatiert Uhrzeiten; keine Seite ruft dafür mehr `strftime("%H:%M")`.
- Eigene Seiten können das Format mit einer Zeile übernehmen (`ctx.clock()`), müssen es nicht.
- Im 12-Stunden-Format läuft nirgends Text über oder wird mit „…“ abgeschnitten.

### Nicht-Ziele

- Datumsformate, weitere Sprachen, Wochenanfang.
- Dauern und Restzeiten: `in 2:13`, `noch 1:23 h`, `12 min`, `vor 4 min` bleiben, wie sie sind.
- Firmware (siehe Befund unten). `url`-Seiten (fremder Inhalt).
- Das Format aus Home Assistant übernehmen (siehe Offene Frage 3).

### Anti-Ziele

- Die Kopfzeile `X-Local-Time` (Server → Display, Nachtmodus) darf sich nie ändern; die Firmware
  liest dort genau `HH:MM:SS` in 24 Stunden.
- Bestehende eigene Seiten dürfen nicht brechen: `ui.header(title, "14:05")` und
  `PageContext(now, lang, timezone)` funktionieren unverändert.

### Befund: alle Stellen mit Uhrzeiten

Gesucht mit `strftime`, `%H`, `:%M`, `:02d`, `hour`, `Uhr`, JS-Zeitfunktionen in `*.py`,
`*.html`, `*.js`, `*.cpp`, `*.h`, `*.sh`.

**Betroffen (Uhrzeit, wird umgestellt):**

| Ort | Was | Heute |
| --- | --- | --- |
| `pages/{bahn,weather,kuma,homeassistant,energy,ai}/page.py`, `pages/printer/page.py` `_base` | Uhr in der Kopfzeile | `ctx.now.strftime("%H:%M")` |
| `server/glancebox/templates/ui.html` `header`, eigene Kopfzeilen in `pages/bahn/template.html` und `pages/energy/template.html` | Darstellung der Kopfzeilen-Uhr | Text |
| `pages/clock/page.py`, `template.html` | große Uhr, 72 px | `%H:%M` |
| `pages/bahn/page.py` `_row` | Abfahrt ab 60 min als Uhrzeit (`right`); Plan-Abfahrt `scheduled` (Text `HH:MM` von DBF) | `%H:%M`, Rohtext |
| `pages/weather/page.py` | Stunden der Vorschau (`"15"`) | `f"{t.hour:02d}"` |
| `pages/printer/providers/_common.py` `clock_text` | „Fertig 16:47“, „seit …“, Ende-Uhrzeit groß, letzter Druck | `%H:%M` |
| `pages/ai/providers/claude.py` | Reset ab 24 h (`Do 09:00`), „Stand 13:58“ | `%H:%M` |
| `pages/ai/providers/_cost.py` (2×), `copilot.py` | „Stand 13:58“ | `%H:%M` |
| Hinweistexte „Stand HH:MM“ in `bahn`, `kuma`, `homeassistant`, `energy`, `printer` (`notice`) | Zeitpunkt des Fehlers | Kopfzeilen-Text |

**Nicht betroffen (mit Begründung):**

- Dauern: `pages/printer/providers/_common.py` `_span`/`ago_text`, `claude.py` „in 2:13“,
  `pages/kuma/page.py` „5 min“, Bahn „12 min“.
- Datum der Uhr-Seite (`14.11.2026` / `2026-11-14`).
- `server/glancebox/app.py:202` `X-Local-Time` (Protokoll, siehe Anti-Ziele).
- `pages/ai/providers/anthropic_api.py:47` (`starting_at` für die API), `departures.py`
  (rechnet mit `HH:MM` von DBF), `pages/weather/page.py` Zeitstempel von Open-Meteo.
- Übersichtsseite `templates/index.html`: zeigt nur Alter („updated 5 s ago“).
- `error.html`: keine Uhrzeit. Log-Zeitstempel. `tools/statusline/*`: keine Uhrzeiten.
- `tools/render_previews.py`: feste Beispieltexte; die Drucker-Beispiele laufen über `build()`
  mit dem Standard `24h` und bleiben gleich.

**Firmware: nicht betroffen, keine Änderung.** Das Display zeichnet keine Uhrzeit selbst, es
zeigt nur die JPEGs des Servers (`firmware/src/display.cpp` enthält keine Zeitformatierung).
Die Firmware formatiert Zeit an genau einer Stelle, `gb::formatHhMm`
(`firmware/lib/core/night.cpp:46`), verwendet in `firmware/src/web_ui.cpp` für (1) die
Diagnosezeile „Uhrzeit“ der Geräteseite und `local_time` in `/status` und (2) den Wert der
Nachtmodus-Felder `<input type=time>`. Der Wert eines solchen Feldes muss laut HTML immer
`HH:MM` in 24 Stunden sein; wie das Feld aussieht, bestimmt der Browser nach seiner eigenen
Sprache, ein US-Browser zeigt dort schon heute AM/PM. Das Einrichtungsportal
(`firmware/src/portal.cpp`) zeigt keine Zeit. Die Firmware kennt `config.yaml` nicht; die
Diagnosezeile bleibt 24-stündig.

### Rahmenbedingungen

- 240 × 240 px, Schrift DejaVu Sans. Gemessene Breiten (Pillow, mitgelieferte Schriftdateien):
  Kopfzeile fett 18 px `12:45` = 57 px, `12:45 PM` = 95 px (Titel verliert 38 von 155 px);
  Uhr-Seite fett 72 px `12:45` = 229 px (kein Platz für mehr); Drucker, rechte Spalte 114 px:
  `Done yesterday 12:14 PM` in 11 px = 142 px, `Done Wed 12:14 PM` = 112 px,
  `Done Nov 25 12:14 PM` = 126 px.
- `PageContext` wird in Tests und eigenen Seiten mit drei Positionsargumenten gebaut; `AppConfig`
  und `PageConfig` ebenfalls positionsweise. Neue Felder kommen ans Ende und haben Standardwerte.
- `pages/printer/page.py` lehnt unbekannte Seitenoptionen ab (`COMMON_KEYS`).
- `strftime("%-I")` gibt es nicht auf jedem System; die Stunde wird aus `.hour` berechnet.
- Der Add-on-Reiter „Konfiguration“ enthält nur Geheimnisse
  (`server/tests/test_addon_package.py::test_addon_schema_matches_secret_fields`).
- `GET /api/config` von Home Assistant liefert Zeitzone, Sprache und Ort, aber kein Zeitformat;
  das ist dort eine Einstellung je Benutzerprofil. Aus dem Gedächtnis, nicht an einem echten
  Home Assistant nachgesehen: beim Umsetzen prüfen.

### Wege

| Weg | Bewertung |
| --- | --- |
| **A: Einstellung in `config.yaml`, eine Formatfunktion, `ctx.clock()`** | **Gewählt.** Gleiches Muster wie `lang` und `timezone`, gilt für Docker und Add-on gleich, Seiten bleiben testbar ohne Browser. |
| B: Jinja-Filter in den Templates | Passt nicht: Die Seiten bauen ihre Texte in Python („Fertig gestern 21:14“), die Templates sehen nur fertige Zeichenketten. |
| C: Fertiges Bild oder HTML nachträglich umschreiben (`14:05` → `2:05 PM`) | Verworfen: träfe auch Dauern wie `in 2:13` und Nutzerdaten. |
| D: Format aus `lang: en` ableiten | Verworfen: Englisch heißt nicht 12 Stunden (UK, Europa), und es würde bestehende Setups ändern. |

### Entwurf

**Einstellung.** Oberste Ebene `time_format: 24h` (Standard) oder `12h`. Dieselbe Angabe ist an
jeder Seite erlaubt und gewinnt dort, wie `lang`. Sie ist ein reservierter Seitenschlüssel wie
`duration` und `refresh` (landet nicht in `options`, also muss keine Seite sie kennen).
Andere Werte, auch die Zahl `12`, lehnt der Server beim Start ab:
`time_format must be '24h' or '12h', got 12`.

**Neue Datei `server/glancebox/timefmt.py`**, die einzige Stelle, die Uhrzeiten formatiert:

- `format_time(when, time_format="24h")` → `"14:05"` oder `"2:05 PM"`. 12 Stunden: Stunde ohne
  führende Null, Leerzeichen, `AM`/`PM` groß, in beiden Sprachen gleich. 00:05 → `12:05 AM`,
  12:00 → `12:00 PM`. `when` ist ein `datetime` oder `time`.
- `format_hour(when, time_format="24h")` → `"15"` oder `"3 PM"`.
- `split_suffix(text)` → `("2:05", "PM")` oder `("14:05", "")`.
- `convert_hhmm(text, time_format="24h")` → macht aus `"21:10"` `"9:10 PM"`; was nicht `H:MM`
  oder `HH:MM` ist, kommt unverändert zurück.

**`PageContext`** bekommt das Feld `time_format: str = "24h"` (letztes Feld) und die Methode
`clock(when=None)`: formatiert `when`, sonst `ctx.now`. `frames.fetch_page_data` setzt das Feld
aus Seite oder Konfiguration.

**Darstellung, je Ort entschieden:**

| Ort | 12-Stunden-Darstellung | Grund |
| --- | --- | --- |
| Kopfzeile (`ui.header`, Bahn) | `2:05` in 18 px, dahinter `PM` in 11 px mit 3 px Abstand | 79 statt 95 px, der Titel behält 133 px |
| Kopfzeile `energy` (13 px, grau) | `2:05 PM` als Text | 61 px, Platz reicht |
| Uhr-Seite | Zeit in 56 px statt 72 px, daneben `PM` in 22 px, grau, auf der Grundlinie | 178 + 6 + 38 = 222 px; die Größe bleibt auch bei `2:05` gleich, damit um 10 und 1 Uhr nichts springt |
| Bahn, Abfahrt ab 60 min | `9:10` als Wert, `PM` im vorhandenen grauen Einheiten-Feld (wie „min“) | kein neues Layout, etwa 24 px breiter als heute |
| Bahn, Plan-Abfahrt (Zeile 2) | `9:10 PM` | Platz reicht |
| Wetter, Stunden | `3 PM`, `12 AM` | 40 px in 60 px breiten Spalten |
| Drucker, Zeilen | heute: `Done 4:47 PM`; anderer Tag innerhalb von 6 Tagen: immer der Wochentag, auch für gestern (`Done Tue 9:14 PM`); weiter weg: nur das Datum (`Done Nov 10`, `Fertig 10.11.`) | „yesterday“ und Datum mit Uhrzeit passen nicht in 114 px |
| Drucker, Ende-Uhrzeit groß | heute: `4:47` in 26 px und `PM` in 12 px; mit Wochentag wie bisher nach Textlänge | 83 + 3 + 21 = 107 px in 116 px |
| ai | `Thu 9:00 AM`, `As of 1:58 PM` | Platz reicht |
| Hinweise „Stand …“ | `Stand 2:05 PM` | Platz reicht |

Die kleine Endung in der Kopfzeile macht ein neues Makro `ui.clock(text)` in `ui.html`: endet
der Text auf ` AM` oder ` PM`, wird die Endung in `<span class="ui-ampm">` gesetzt, sonst
kommt der Text unverändert heraus. `ui.header` nutzt es; die Bahn-Kopfzeile auch.
In der Drucker-Vorlage bekommt die erste kleine Zeile der Ansicht ohne Vorschaubild dieselbe
Verkleinerung ab 16 Zeichen, die die Ansicht mit Bild schon hat.

**Add-on.** Keine neue Option im Formular; `time_format:` steht wie `timezone:` in der
`config.yaml` des Add-ons. Der Kommentar der Starter-Datei (`STARTER_CONFIG`) nennt die Zeile.

**Vorschau und Doku.** Ein neues Vorschaubild `clock-12h.png` (Eintrag in
`tools/render_previews.py`), gezeigt in `docs/{en,de}/templates/clock.md`. Die übrigen Bilder
ändern sich nicht. Doku in beiden Sprachen: `configuration.md` (oberste Ebene und „Optionen
jeder Seite“), `config-example.yaml`, die Vorlagen-Seiten mit Uhrzeiten (clock, bahn, weather,
printer, ai), `writing-pages.md` (`ctx.time_format`, `ctx.clock()`, `ui.clock`),
`home-assistant.md`, `ha-addon/DOCS.md`.

**Tests.** `timefmt` vollständig (Mitternacht, Mittag, einstellige Stunden, Unlesbares);
Konfiguration (Standard, beide Werte, Seite gewinnt, falscher Wert, Zahl); je Seite ein Test in
12 Stunden und der Nachweis, dass 24 Stunden unverändert ist; `X-Local-Time` bleibt gleich;
Browser-Tests gegen Überlauf für Kopfzeile, Uhr-Seite, Bahn und Drucker mit `12:59 PM`.

### Meine Festlegungen (nicht mit Robin besprochen)

- Schreibweise `2:05 PM` (keine führende Null, Großbuchstaben, Leerzeichen), auch bei `lang: de`.
- Werte heißen `24h` und `12h`; Zahlen werden abgelehnt statt geraten.
- Uhr-Seite in 12 Stunden kleiner (56 px) statt die Endung unter die Zeit zu setzen.
- Drucker in 12 Stunden: Wochentag statt „gestern“, Datum ohne Uhrzeit. Nur in diesem Modus.
- Die Diagnose-Uhrzeit der Geräteseite bleibt 24-stündig.
- Ein zusätzliches Vorschaubild, keine 12-Stunden-Variante aller Bilder.

## Teil B: Anleitung für das Add-on (#37)

### Befund: was es schon gibt

- `ha-addon/DOCS.md`: der Reiter „Dokumentation“ des Add-ons. Englisch; Home Assistant
  übersetzt diese Datei nicht (`translations/*.yaml` enthält nur die Namen der Formularfelder).
  Inhalt: flashen, erster Start, Seiten ändern, Geheimnisse, Sicherheit.
- `docs/{en,de}/home-assistant.md` auf der Projektseite: derselbe Stoff als Überblick mit
  Installations-Knopf. Verlinkt aus `README.md`, `README.de.md` und der Navigation.
- Die Übersichtsseite des Add-ons (`templates/index.html`): Kasten „Connect your display“ mit
  Adresse und drei Schritten.

Was fehlt, ist kein Inhalt an sich, sondern die Reihenfolge und das Konkrete: nummerierte
Schritte, an welcher Stelle man die `config.yaml` findet oder anlegt, fertige Beispiele für
die Seiten, die im Add-on anders aussehen (ohne `url`/`token`), und was man bei Fehlern tut.
Am ehesten hängt ein neuer Nutzer an der Datei: Auf Home Assistant OS konnte das Add-on die
Starter-Datei bei der Abnahme von 0.6.0 nicht selbst anlegen (`ensure_config` fällt dann auf
eine flüchtige Kopie zurück), der Nutzer muss `config.yaml` also von Hand erzeugen. Die Doku
nennt das heute nur in einem Nebensatz.

### Ziele

- Wer Home Assistant bedienen kann, kommt ohne weiteres Wissen vom Store zur eigenen Seitenliste.
- Jeder Schritt stimmt mit dem Code überein; jedes YAML-Beispiel wird im Test geladen.
- Typische Fehler stehen mit Ursache und Abhilfe in einer Tabelle.
- Englisch und Deutsch gleich aufgebaut (`tools/check_docs_parity.py`).

### Nicht-Ziele

- Bildschirmfotos von Home Assistant (veralten mit jeder HA-Version, enthalten leicht
  persönliche Daten).
- Eine zweite Beschreibung der Seitentypen: dafür wird auf den Vorlagen-Katalog verlinkt.
- Änderungen am Add-on-Code. Fällt beim Prüfen ein Fehler auf, wird er gemeldet, nicht hier
  mit behoben.

### Anti-Ziele

- Schritte beschreiben, die nicht am Code oder an einem echten Home Assistant geprüft sind,
  ohne das zu kennzeichnen.
- Persönliche Daten: nur Platzhalter wie `192.168.1.x`, `homeassistant.local`, `sensor.pv_power`.

### Wege

| Weg | Bewertung |
| --- | --- |
| **A: `docs/{en,de}/home-assistant.md` zur Schritt-für-Schritt-Anleitung umbauen; `DOCS.md` bleibt kurz und verlinkt darauf** | **Gewählt.** Die Adresse ist schon überall verlinkt, es gibt eine deutsche Fassung, und es entsteht keine dritte Stelle mit demselben Stoff. |
| B: Neue Seite `docs/{en,de}/guide/ha-addon.md` neben der alten | Zwei Seiten zum selben Thema, die auseinanderlaufen. |
| C: Alles in `DOCS.md` | Nur Englisch, nur für installierte Nutzer sichtbar, lange Seite im schmalen HA-Fenster. |

### Entwurf

**`docs/{en,de}/home-assistant.md`**, neu gegliedert (Überschriften in beiden Sprachen gleich
gestuft):

1. *Was du brauchst*: HA OS oder Supervised; geflashtes Display (Link auf die Flash-Anleitung).
2. *Schritt 1: Add-on installieren*: Knopf, sonst Repository-Adresse von Hand; installieren.
3. *Schritt 2: Starten und Oberfläche öffnen*: Starten; „Open web UI“; „In Seitenleiste anzeigen“;
   was die Oberfläche zeigt (Vorschau der Starter-Seiten Uhr und Wetter).
4. *Schritt 3: Display verbinden*: Adresse aus dem Kasten (`http://192.168.1.x:8090`), im
   Einrichtungsportal (Feld „Server URL“) oder später auf der Geräteseite eintragen; nur
   `http://`; die Anzeige „Display connected“ als Erfolgskontrolle.
5. *Schritt 4: Seiten festlegen*: wo `config.yaml` liegt, was tun, wenn der Ordner leer ist
   (Datei mit dem Starter-Inhalt anlegen), Add-on neu starten, in der Oberfläche prüfen.
6. *Beispiele*: je ein fertiger Block für `homeassistant` (ohne `url`/`token`), `energy`,
   `printer` mit `source: hass`, `weather` mit eigenem Ort, `bahn`, `ai` mit `provider: claude`,
   dazu `time_format: 12h` und `lang`/`timezone`; jeweils ein Link auf die Vorlagen-Seite.
7. *Geheimnisse*: wie heute, plus ein Beispiel mit „More secrets“ (`${OCTOPRINT_KEY}`).
8. *Aktualisieren*: Add-on-Update in HA; wann das Display ein Firmware-Update braucht
   (Link auf `updating.md`).
9. *Fehlerbehebung*: Tabelle Symptom → Ursache → Abhilfe, unter anderem:
   Add-on startet nicht (Reiter „Log“ zeigt die Zeile mit dem Fehler der `config.yaml`);
   Änderung wirkt nicht (Neustart fehlt); `config.yaml` nicht zu finden; Display zeigt nichts
   oder die Oberfläche meldet „Waiting for your display“ (Adresse, Port 8090, `http://`, gleiches
   Netz); `http://…:8090/` im Browser zeigt „Not Found“ (richtig so, die Übersicht gibt es nur
   in Home Assistant; zum Prüfen `/healthz`); Adresse wird nicht angezeigt (Port im Reiter
   „Konfiguration“ unter „Netzwerk“ aktivieren); Port 8090 belegt (dort ändern); Seite zeigt
   „Keine Verbindung zu Home Assistant“ oder fehlt (Entität prüfen, Fehler steht unter der
   Vorschau); Wetter am falschen Ort (`location:` setzen).
10. *Sicherheit*: wie heute.

**`ha-addon/DOCS.md`**: gleicher Ablauf in Kurzform (fünf nummerierte Schritte, ein Beispiel),
oben ein Link auf die ausführliche Anleitung
`https://robinlanger.github.io/glancebox/home-assistant/`, unten die drei häufigsten Fehler und
der Abschnitt Sicherheit wie heute.

**`README.md` / `README.de.md`**, `docs/{en,de}/guide/2-start-the-server.md`: je ein Satz mit
Link, dass es für Home Assistant OS eine eigene Schritt-für-Schritt-Anleitung gibt.

**Quelle jeder Aussage.** Aus dem Code belegt: Port 8090 (`ha-addon/config.yaml`), Starter-Seiten
und Rückfall (`addon.py` `STARTER_CONFIG`, `ensure_config`), Werte aus Home Assistant und
„YAML gewinnt“ (`ha_defaults`), Namen der Geheimnisse (`SECRET_FIELDS`), Adresse im Kasten
(`connect_url`), keine Übersicht auf dem LAN-Port (`create_app(ui=False)`), Neustart nötig
(Konfiguration wird einmal beim Start geladen), Fehlerausgabe ins Log (`__main__.main`), nur
`http://` und Platzhalter `:8090` (`firmware/src/portal.cpp`, `firmware/lib/core/settings.cpp`).

**An einem echten Home Assistant zu prüfen** (Abnahme, Ergebnis mit HA-Version festhalten):

1. Wortlaut und Weg der Menüs in der aktuellen HA-Version (heißen Add-ons dort noch
   „Add-ons“ oder „Apps“; wo liegt „Repositories“).
2. Ob die Starter-`config.yaml` nach dem ersten Start im Ordner liegt oder der Rückfall greift.
3. Der Ordnername (`/addon_configs/<id>_glancebox/`) und ob der „File editor“ ihn in seiner
   Standardeinstellung erreicht oder vorher eine Einstellung braucht (vermutet: „Enforce
   Basepath“ ausschalten; ungeprüft).
4. Ob eine von Hand angelegte `config.yaml` vom Add-on gelesen wird.
5. Jedes Beispiel der Anleitung einmal im Add-on gestartet (soweit Entitäten vorhanden sind).
6. Jede Zeile der Fehlertabelle einmal ausgelöst, soweit ohne Aufwand möglich.

Was nicht geprüft werden konnte, wird im Text vorsichtig formuliert und im CHANGELOG als
ungeprüft genannt, wie bei früheren Releases.

**Tests** (`server/tests/test_addon_docs.py`, neu): jeder `yaml`-Block der drei Dateien lädt im
Add-on-Modus (`load_config` mit `ha_defaults`, dann `validate_config`); der Port aus
`ha-addon/config.yaml` steht in allen dreien; jede `${NAME}`-Variable aus `SECRET_FIELDS` wird
genannt; es gibt einen Abschnitt zur Fehlerbehebung; `DOCS.md` verlinkt die Anleitung; keine
IPv4-Adresse außer den Platzhaltern.

### Meine Festlegungen (nicht mit Robin besprochen)

- Die bestehende Seite wird umgebaut, keine neue angelegt.
- Keine Bildschirmfotos.
- Die Schritte heißen „Schritt 1“ bis „Schritt 4“; die Fortschrittsleiste der Fünf-Schritte-
  Anleitung wird nicht übernommen, weil die Seite außerhalb dieser Reihe steht.

## Release (Vorschlag, nicht Teil der Umsetzung)

Beide Teile kommen im CHANGELOG unter `## [Unreleased]`. `VERSION` und `ha-addon/config.yaml`
bleiben auf 0.8.0. Vorschlag für später: 0.9.0, weil eine neue Einstellung dazukommt; nur
Server und Add-on, keine neue Firmware. Antworten auf die beiden Issues erst nach dem Release.

## Offene Fragen

1. **Wie soll die 12-Stunden-Zeit aussehen?** Optionen: (a) `2:05 PM`, an engen Stellen mit
   kleiner Endung; (b) kompakt `2:05p` überall; (c) ohne Endung `2:05`. Empfehlung: (a). Es ist
   die gewohnte Schreibweise, und die kleine Endung löst die Breite, ohne etwas wegzulassen.
2. **Soll das Format je Seite einstellbar sein?** Optionen: (a) ja, wie `lang`; (b) nur global.
   Empfehlung: (a). Kostet eine Zeile, und der Fall ist echt: Fahrpläne liest man in 24 Stunden,
   die Uhr vielleicht nicht.
3. **Add-on: Feld im Formular oder nur `config.yaml`?** Optionen: (a) nur `config.yaml`;
   (b) zusätzlich Auswahlfeld im Reiter „Konfiguration“; (c) aus Home Assistant ableiten.
   Empfehlung: (a). Der Reiter enthält bewusst nur Geheimnisse, alle anderen Einstellungen
   stehen in der Datei. (c) geht nicht sauber: Home Assistant kennt das Zeitformat nur je
   Benutzerprofil, nicht für das System. Ein Raten aus dem Land (`country: US`) wäre möglich,
   aber eine Überraschung.
4. **Uhr-Seite in 12 Stunden: kleiner mit Endung daneben, oder volle Größe mit Endung
   darunter?** Empfehlung: kleiner (56 px) mit `PM` daneben; die Zeile darunter bleibt für den
   Wochentag.
5. **Drucker in 12 Stunden: Wochentag statt „gestern“ und Datum ohne Uhrzeit?** Optionen:
   (a) so; (b) kompakte Endung nur dort (`9:14p`); (c) Abschneiden mit „…“ hinnehmen.
   Empfehlung: (a).
6. **Soll die Geräteseite (Firmware) die Diagnose-Uhrzeit auch umstellen?** Empfehlung: nein.
   Die Firmware kennt die Einstellung nicht, es bräuchte eine neue Kopfzeile und ein
   Firmware-Release für eine Diagnosezeile.
7. **Wo lebt die Anleitung?** Optionen wie unter „Wege“ in Teil B. Empfehlung: bestehende Seite
   umbauen, `DOCS.md` kurz halten.
8. **Vorschaubilder:** nur `clock-12h.png` neu, oder 12-Stunden-Varianten weiterer Seiten?
   Empfehlung: nur das eine.
9. **Wer prüft am echten Home Assistant, und wo?** Die Test-VM (`~/haos`) und der Test-Pi
   liegen auf Robins Heimserver. Empfehlung: Die Umsetzer prüfen dort, wenn Robin den Zugriff
   freigibt; sonst prüft Robin die sechs Punkte selbst vor dem Release.
10. **Version:** 0.9.0 oder 0.8.1? Empfehlung: 0.9.0.

## Dem Umsetzer überlassen

- Genaue Pixelwerte im 12-Stunden-Layout, solange die Browser-Tests gegen Überlauf bestehen
  und 24 Stunden unverändert bleibt.
- Wie `ui.clock` die Endung erkennt (im Template oder über eine Jinja-Funktion aus `timefmt`).
- Wortlaut der Anleitung; die Gliederung und die Fakten oben sind fest.
