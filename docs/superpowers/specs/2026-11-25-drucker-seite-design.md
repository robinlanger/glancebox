# 3D-Drucker-Seite (`printer`): Design

Stand 2026-11-25, Basis: lokales `main` bei 15652f1 (0.7.1). Umsetzung im Worktree
`feat/printer-page`. Ziel-Version: offen (Vorschlag 0.8.0, Server-only, keine Firmware-Änderung).

Was der Nutzer festgelegt hat, steht als **Entscheidung (Nutzer)**. Was ich beim Entwurf
festgelegt habe, steht als **Entscheidung (Claude)** mit Grund; jede ist einzeln korrigierbar.
Alle Angaben zu fremden APIs stammen aus Quellcode und Doku, gelesen am 2026-11-25 (Quellen im
Anhang). **Nichts davon ist bisher an einem Gerät oder einer HA-Instanz geprüft.**

## Absicht

Auf dem 240×240-Display soll man im Vorbeigehen sehen, was der 3D-Drucker macht: druckt er, wie
weit ist er, wann ist er fertig, ist etwas schiefgegangen, sind Düse und Bett heiß. Das soll
herstellerübergreifend gehen (Klipper/Moonraker, OctoPrint, Prusa, Bambu Lab, Creality), für
Leute mit Home Assistant und für Leute mit der reinen Docker-Variante ohne HA.

Der Nutzer besitzt einen Drucker mit Klipper/Moonraker. Moonraker ist damit der erste Weg, der
an echter Hardware geprüft wird, direkt und (wenn der Nutzer die HACS-Integration einrichtet)
über HA. Alle anderen Marken gelten als „nur mit Fixtures oder Simulator getestet“, bis jemand
aus der Community sie bestätigt. **Entscheidung (Nutzer).**

## Ziele

1. Neuer Seitentyp `printer` mit `source:` aus `moonraker`, `octoprint`, `prusalink`, `hass`.
   **Entscheidung (Nutzer): Ansatz A, alles in einem Zug bauen, testen, was testbar ist.**
2. `source: hass` mit Vorlagen (`integration:`) für `moonraker` (HACS), `octoprint` (Core),
   `prusalink` (Core), `bambu_lab` (HACS ha-bambulab), `creality` (HACS ha_creality_ws).
3. Anzeige: Zustand, Fortschritt in % mit Balken, Restzeit und Fertig-Uhrzeit, Dateiname,
   Düse und Bett Ist/Soll, Schicht (wenn bekannt), Slicer-Vorschaubild (wenn verfügbar),
   Fehlermeldung, sinnvolle Ansicht ohne Druck.
4. „Fertig“ wird nur eine einstellbare Zeit gezeigt (`finished_for`, Standard 120 Minuten),
   danach „Bereit“. **Entscheidung (Nutzer)**, Grund: Klipper bleibt auf `complete`, Bambu auf
   `finish`, bis der nächste Druck startet; die Seite soll nicht tagelang „Fertig“ zeigen.
5. Texte Deutsch und Englisch; Doku DE/EN parallel; Vorschaubilder im Katalog.
6. Ehrliche Testmatrix in der Doku: was an echter Hardware, was im Simulator, was nur mit
   Fixtures geprüft ist.

## Nicht-Ziele

- Bambu Lab und Creality **direkt** (ohne HA). Bambu braucht MQTT über TLS plus Entwickler-
  modus am Drucker, Creality einen nachgebauten Websocket. Beide nur über HA.
- Elegoo, Anycubic, Snapmaker, Duet als eigene Vorlagen. Wer sie nutzt, kann `source: hass`
  mit `integration: custom` und eigener Entitätsliste nehmen (siehe unten).
- Mehrere Werkzeuge/Düsen (IDEX, Toolchanger, XL). Gezeigt wird Werkzeug 0 / `extruder`.
- Webcam-Bild. Nur das Slicer-Vorschaubild der Datei.
- Drucker steuern (Pause, Abbruch). Die Seite liest nur.
- Ein Einstellungsmenü in einer Oberfläche. Glance Box hat keins; „einstellbar“ heißt hier
  eine Option in `config.yaml`.
- Websockets/MQTT. Alles wird per HTTP abgefragt (Moonraker empfiehlt Polling für einfache
  Clients ausdrücklich).

## Anti-Ziele (wäre ein Fehlschlag, auch wenn es technisch läuft)

- Die Doku behauptet, eine Marke funktioniere, ohne dass das geprüft wurde.
- Persönliche Daten (Drucker-IP, Hostname, E-Mail) landen in Code, Doku, Fixtures, Screenshots
  oder Commits. Fixtures nutzen `drucker.local`, `homeassistant.lan` und erfundene Dateinamen.
- Ein fehlendes Feld (kein Bild, keine Schicht, kein Soll) lässt die Seite in den Fehlerzustand
  kippen. Fehlende Felder werden weggelassen, nur der Zustand ist Pflicht.
- Ein API-Key oder Token taucht in einem Log auf.

## Ansätze (erwogen)

| | Beschreibung | Für | Gegen |
|---|---|---|---|
| **A (gewählt)** | Direkt: Moonraker, OctoPrint, PrusaLink; über HA: Vorlagen für 5 Integrationen | Jede Marke abgedeckt, Docker ohne HA bekommt die drei einfachen APIs; Moonraker doppelt prüfbar | Größter Umfang |
| B | Nur HA | Wenig Code | Docker-Nutzer ohne HA leer; Moonraker-HA zeigt Bild nur beim Drucken, keine Slicer-Schätzung |
| C | Nur direkt | Unabhängig von HA | Bambu und Creality fallen weg |

**Entscheidung (Nutzer): A, alles in einem Zug.** Reihenfolge innerhalb der Umsetzung
(**Entscheidung (Claude)**): gemeinsames Schema und Layout → Moonraker direkt → HA-Vorlagen →
OctoPrint → PrusaLink, damit das am echten Gerät Prüfbare zuerst steht. **Entscheidung (Nutzer):
kein Halt zwischendurch.** Alles wird in einem Zug gebaut, der Test am echten Drucker kommt am
Ende; Abweichungen des Geräts werden danach nachgearbeitet. Commits entstehen auf dem Branch
`feat/printer-page`; nach `main` geht erst etwas, wenn alles drin und geprüft ist.

## Aufbau im Repo

Nach dem Muster von `pages/ai`:

```
pages/printer/
  page.py            # validate/fetch, Zustandsregeln, finished_for, Layout-Daten, Texte DE/EN
  template.html
  README.md          # Entwicklernotizen (wie pages/energy/README.md)
  test_printer.py    # Seite + Layout (Browser-Tests wie bei energy)
  providers/
    __init__.py
    _common.py       # Status-Dataclass, Zeitformate, Bild-Cache, gemeinsame Helfer
    moonraker.py
    octoprint.py
    prusalink.py
    hass.py          # HA-Vorlagen (PRESETS) + Lesen der Entitäten
  test_providers_*.py (oder ein Testfile je Provider)
  fixtures/          # JSON-Antworten, aus Quellcode/Doku abgeleitet, als solche markiert
```

Server-Änderungen:
- `glancebox/http.py`: neue Funktion `get_bytes(url, *, headers, timeout, max_bytes)` für das
  Vorschaubild, mit Größenlimit (Abbruch beim Streamen, nicht erst nach dem Laden) und Prüfung
  des Content-Type auf `image/png` oder `image/jpeg`. **Entscheidung (Claude):** 512 KiB Limit.
- `glancebox/addon.py`: `ha_defaults` füllt `url`/`token` auch bei `type: printer` mit
  `source: hass`, genau wie bei `homeassistant`/`energy`. Secrets für direkte Quellen laufen
  über das vorhandene `extra_secrets` (keine neuen Formularfelder).
- Digest-Auth für PrusaLink: `requests.auth.HTTPDigestAuth` (in `requests` enthalten, keine
  neue Abhängigkeit). `http.get_json` braucht dafür einen `auth=`-Parameter.

## Gemeinsames Datenschema

Jeder Provider liefert aus `fetch` ein `PrinterStatus` (Dataclass in `_common.py`):

| Feld | Typ | Bedeutung |
|---|---|---|
| `state` | `printing \| paused \| finished \| error \| idle \| offline` | Pflicht |
| `progress` | float 0–100 \| None | |
| `remaining_s` | int \| None | Restzeit in Sekunden |
| `eta` | datetime (aware) \| None | Fertig-Uhrzeit; wenn nur eins von beiden da ist, wird das andere aus `ctx.now` berechnet |
| `filename` | str \| None | Anzeige ohne Pfad und ohne `.gcode`/`.bgcode`/`.3mf` |
| `nozzle`, `bed` | `(actual, target \| None)` \| None | °C; Ziel 0 oder None = Heizung aus |
| `layer` | `(current, total)` \| None | total darf None sein |
| `message` | str \| None | Fehlermeldung des Druckers |
| `duration_s` | int \| None | Druckdauer, für „Fertig“ |
| `ended_at` | datetime \| None | Ende des Drucks, wenn die Quelle es kennt |
| `state_since` | datetime \| None | Seit wann der Zustand gilt, wenn die Quelle es kennt |
| `thumbnail` | bytes + Mime-Typ \| None | |
| `last_job` | `(filename, ended_at)` \| None | für „Zuletzt: …“ in der Bereit-Ansicht |

Zustandsregeln, die `page.py` danach anwendet (für alle Quellen gleich):
- `finished` wird zu `idle` (mit `last_job` = dieser Druck), sobald seit dem Ende mehr als
  `finished_for` Minuten vergangen sind. Ende = `ended_at`, sonst `state_since`, sonst der
  Zeitpunkt, an dem der Server `finished` zum ersten Mal gesehen hat (im Speicher pro Seite;
  nach einem Neustart beginnt die Frist neu, das steht so in der Doku).
- `finished_for: 0` zeigt nie „Fertig“. Kein „für immer“-Wert. **Entscheidung (Claude):** ein
  großer Wert (z. B. 10080) erfüllt den Zweck, ein Extra-Schlüsselwort ist unnötig.
- `cancelled` (Klipper) und `stopped` (Prusa) gelten als `idle`, nicht als Fehler.

## Quellen im Einzelnen

### `source: moonraker` (direkt; einzige am echten Gerät prüfbare Quelle)

- Abfrage: `GET /printer/objects/query?webhooks&print_stats&virtual_sdcard&display_status&extruder&heater_bed&gcode_move`
- `webhooks.state != "ready"`: `shutdown`/`error` → `error` mit `webhooks.state_message`;
  `startup` → `offline` („startet“). Keine Verbindung → `offline`.
- `print_stats.state`: `standby` → idle, `printing` → printing, `paused` → paused,
  `complete` → finished, `cancelled` → idle, `error` → error (`print_stats.message`).
- Metadaten einmal pro Datei: `GET /server/files/metadata?filename=…` → `estimated_time`,
  `gcode_start_byte`, `gcode_end_byte`, `layer_count`, `object_height`, `layer_height`,
  `first_layer_height`, `thumbnails[]`.
- Fortschritt: dateibezogen wie Mainsail, `(file_position − gcode_start_byte) /
  (gcode_end_byte − gcode_start_byte)`, sonst `display_status.progress` bzw.
  `virtual_sdcard.progress`.
- Restzeit (**Entscheidung (Claude)**): Mittelwert aus Slicer-Schätzung (`estimated_time −
  print_duration`) und Datei-Schätzung (`print_duration / progress − print_duration`, erst ab
  1 % Fortschritt). Fehlt eine, gilt die andere. Mainsail mittelt die eingeschalteten Schätzungen,
  Fluidd rechnet die Datei-Schätzung ebenfalls erst ab 1 %.
- Schicht: `print_stats.info.current_layer/total_layer`, sonst Metadaten-Fallback wie Mainsail
  (`layer_count`, bzw. aus `gcode_move.gcode_position.z` und Schichthöhen).
- Vorschaubild: größtes PNG mit Breite ≤ 300 px, sonst das kleinste darüber;
  `GET /server/files/gcodes/<dirname(filename)>/<relative_path>`.
- Ende/letzter Druck: `GET /server/history/list?limit=1&order=desc` → `end_time`,
  `total_duration`, `filename`, `status`. Ist die History-Komponente aus, fehlen diese Felder.
- Auth: ohne Key (trusted_clients) oder `api_key:` → Header `X-Api-Key`.

### `source: octoprint` (direkt; Simulator: Docker-Image 1.11.8 mit Virtual Printer)

- `GET /api/job` und `GET /api/printer?exclude=sd` mit `X-Api-Key`.
- Zustand über `/api/printer` → `state.flags` (`printing`, `paused`, `pausing`, `error`,
  `closedOrError`, `ready`, `operational`), nicht über den Text. 409 von `/api/printer` = nicht
  verbunden → `offline`.
- OctoPrint kennt kein „fertig“: `operational` + `progress.completion` ≥ 100 + Datei gesetzt →
  `finished`. Ende = erstes Sehen durch den Server.
- Restzeit `progress.printTimeLeft`, Dauer `progress.printTime`.
- Vorschaubild: `GET /api/files/local/<path>` → `refs.thumbnail` (OctoPrint ≥ 2.0) oder
  `thumbnail` (Plugin PrusaSlicer Thumbnails, 1.x). Fehlt beides, kein Bild.
- Keine Schicht (das Plugin DisplayLayerProgress ist seit 2023 unverändert; nicht eingebaut).
- Header `X-OctoPrint-Api-Version` wird nicht gesetzt (alte Antwortform, gilt für 1.x und 2.x).

### `source: prusalink` (direkt; nur Fixtures)

- `GET /api/v1/status`, `GET /api/v1/job` (204 = kein Job). Auth: Digest (`user`, Standard
  `maker`, `password`) oder `api_key` → `X-Api-Key`.
- `printer.state`: `PRINTING` → printing, `PAUSED` → paused, `FINISHED` → finished,
  `STOPPED`/`IDLE`/`READY` → idle, `ERROR` → error, `ATTENTION` → paused mit Meldung
  „Eingriff nötig“ / „Attention needed“, `BUSY` → idle. **Entscheidung (Claude)** für
  `ATTENTION` und `BUSY` (z. B. Filamentwechsel braucht Hand, ist aber kein Fehler).
- Vorschaubild: `file.refs.thumbnail` aus `/api/v1/job` folgen, nie selbst bauen. MK3-PrusaLink:
  `/api/thumbnails/<path>.orig.png`. Bildformat bei Buddy-Firmware möglicherweise QOI → nur PNG/
  JPEG werden angenommen, sonst kein Bild.
- Keine Schicht.

### `source: hass` (Vorlagen)

```yaml
- type: printer
  source: hass
  integration: moonraker      # moonraker | octoprint | prusalink | bambu_lab | creality | custom
  device: voron               # Präfix; bei octoprint optional (Standard octoprint, siehe unten)
  # url: ${HA_URL}            # im Add-on automatisch
  # token: ${HA_TOKEN}
  # entities:                 # einzelne Felder überschreiben; bei custom alle Pflichtfelder
  #   state: sensor.mein_status
  #   progress: sensor.mein_fortschritt
```

Feldnamen in `entities:`: `state`, `progress`, `remaining`, `eta`, `filename`, `nozzle`,
`nozzle_target`, `bed`, `bed_target`, `layer`, `layer_total`, `thumbnail`.

Vorlagen (Entitäts-IDs mit `<d>` = `device`):

| Feld | moonraker | octoprint | prusalink | bambu_lab | creality |
|---|---|---|---|---|---|
| state | `sensor.<d>_current_print_state` | `sensor.octoprint_current_state` | `sensor.<d>` | `sensor.<d>_print_status` | `sensor.<d>_print_status` |
| progress | `sensor.<d>_progress` | `sensor.octoprint_job_percentage` | `sensor.<d>_progress` | `sensor.<d>_print_progress` | `sensor.<d>_print_progress` |
| remaining | `sensor.<d>_print_time_left` | – | – | `sensor.<d>_remaining_time` | `sensor.<d>_print_time_left` |
| eta | `sensor.<d>_print_eta` | `sensor.octoprint_estimated_finish_time` | `sensor.<d>_print_finish` | `sensor.<d>_end_time` | – |
| filename | `sensor.<d>_filename` | `sensor.octoprint_current_file` | `sensor.<d>_filename` | `sensor.<d>_task_name` | Attribut `file` am state-Sensor |
| nozzle / target | `sensor.<d>_extruder_temperature` / `number.<d>_extruder_target` | `sensor.octoprint_actual_tool0_temp` / `…_target_tool0_temp` | `sensor.<d>_nozzle_temperature` / `…_nozzle_target_temperature` | `sensor.<d>_nozzle_temperature` / `…_nozzle_target_temperature` | `sensor.<d>_nozzle_temperature` / Attribut `target` |
| bed / target | `sensor.<d>_bed_temperature` / `number.<d>_bed_target` | `sensor.octoprint_actual_bed_temp` / `…_target_bed_temp` | `sensor.<d>_heatbed_temperature` / `…_heatbed_target_temperature` | `sensor.<d>_bed_temperature` / `…_bed_target_temperature` | `sensor.<d>_bed_temperature` / Attribut `target` |
| layer / total | `sensor.<d>_current_layer` / `…_total_layer` | – | – | `sensor.<d>_current_layer` / `…_total_layer_count` | `sensor.<d>_working_layer` / `…_total_layers` |
| thumbnail | `camera.<d>_thumbnail` | – (nur Webcam) | `camera.<d>_preview` | `image.<d>_cover_image` | `image.<d>_current_print_preview` |
| zusätzlich | `sensor.<d>_printer_state` (Klippy) | | | | |

Zustandswörter → Schema:

| Schema | moonraker | octoprint | prusalink | bambu_lab | creality |
|---|---|---|---|---|---|
| printing | printing | printing, printing_sd, printing_streaming, starting*, resuming, finishing | printing | running, prepare, slicing, init | printing, processing, self-testing |
| paused | paused | paused, pausing | paused, attention | pause | paused |
| finished | complete | operational + progress ≥ 100 | finished | finish | completed |
| error | error (oder Klippy `shutdown`/`error`) | error, offline_after_error | error | failed | error |
| idle | standby, cancelled | operational, cancelling, transferring_file | idle, ready, stopped, busy | idle | idle, stopped |
| offline | Klippy `startup`; `unavailable` | offline, open_serial, detect_serial, connecting; `unavailable` | `unavailable` | offline, `unavailable` | off, `unavailable` |

Eigene Zuordnung (**Entscheidung (Claude)**): Schlüssel `states:` bildet Rohwörter auf das
Schema ab, z. B. `states: {printing: [running, busy], finished: [done]}`. Bei
`integration: custom` ist `entities.state` Pflicht und `states:` der normale Weg (ohne `states:`
werden nur Schema-Wörter erkannt); bei den Vorlagen
ergänzt bzw. überschreibt es deren Tabelle Wort für Wort (Vorlage + `states:`, `states:` gewinnt).
Schema-Wörter selbst (`printing`, `paused`, …) gelten immer als sie selbst, so dass ein
HA-Template-Sensor, der direkt Schema-Wörter liefert, ohne `states:` auskommt.

Unbekannte Zustandswörter → `idle` mit dem Rohwert als kleine Zeile, und eine Log-Warnung
(einmal pro Wort). **Entscheidung (Claude)**: lieber etwas Neutrales zeigen als einen
erfundenen Zustand; der Rohwert hilft beim Melden.

Regeln beim Lesen aus HA:
- Einheiten aus `attributes.unit_of_measurement` beachten: Restzeit in s, min, h oder d (Bambu
  liefert durch `suggested_unit_of_measurement` meist h, Moonraker h, Creality s). Ohne Einheit
  → nicht verwenden.
- ETA-Sensoren sind Zeitstempel (ISO 8601). Restzeit = ETA − jetzt, wenn kein remaining da ist.
- Zieltemperatur kann Sensor, `number`-Entität oder Attribut sein; die Vorlage sagt, was.
- 404 einer Entität = Feld fehlt (wie bei energy), kein Fehler; fehlt aber `state`, Meldung
  „Entität fehlt: sensor.…“ (Konfigurationsfehler sichtbar machen).
- `state_since` = `last_changed` der state-Entität.
- Bild: `GET /api/camera_proxy/<id>` bzw. `/api/image_proxy/<id>` mit Bearer-Token.
  Moonraker-HA liefert das Bild nur während `printing` (bei Pause Fehler → kein Bild, ok).
- PrusaLink-HA: Temperatursensoren sind standardmäßig deaktiviert; die Doku sagt, wie man sie
  einschaltet. Fehlen sie, fehlt die Temperaturzeile.
- Zweite OctoPrint-Instanz: HA hängt `_2` an. **Entscheidung (Claude):** `device:` ersetzt bei
  der OctoPrint-Vorlage das Präfix `octoprint` (Standard `octoprint`), also `device: octoprint_2`.
- Abfrage Entität für Entität mit Zeitbudget wie bei energy (15 s gesamt, 5 s pro Aufruf). Es
  sind bis zu 13 Aufrufe; das Bild kommt zuletzt und darf wegfallen, wenn das Budget knapp ist.
- Keine Auto-Erkennung über `/api/template`: braucht einen Admin-Token. **Entscheidung (Claude).**
  Optional als Hilfe: Wenn `state` ein ENUM-Sensor mit `options`-Attribut ist, das zu einer
  anderen Vorlage passt, steht ein Hinweis im Log („sieht aus wie bambu_lab“).

## Layout

Siehe gerenderte Mockups (`assets/2026-11-25-printer-mockup.html`, werden als Vorschau-Testfälle
übernommen). Kopf wie `ui.header` (Titel + Uhrzeit, rot bei Fehler).

- **Druckt mit Bild:** Bild 100×100 links oben; rechts Zustand (grün), Prozent groß, „noch
  1:23 h“, „fertig 15:55“, „Schicht 112/240“; Balken über die volle Breite; Dateiname; Trenn-
  linie; unten Düse und Bett „214°/215“.
- **Druckt ohne Bild:** Prozent sehr groß links, Restzeit und Fertig-Uhrzeit rechts.
- **Pausiert:** wie Druckt, Farbe orange, Restzeit grau, „seit HH:MM“ wenn `state_since` bekannt.
- **Fertig:** Ende-Uhrzeit groß (grün), „Dauer 3:12 h“, „vor 4 min“; Balken voll.
- **Fehler:** roter Kopf, Prozent rot, Meldung bis 3 Zeilen.
- **Bereit:** „Bereit“ groß, „Zuletzt: <Datei>“ und „fertig <Zeit>“ wenn bekannt, unten Temps.
- **Offline:** Hinweis „Drucker nicht erreichbar“ (grau, kein Alarm: ein ausgeschalteter
  Drucker ist normal). HA nicht erreichbar / Token abgelehnt wie bei energy (orange).
- Temperatur: Icon orange und „Ist°/Soll“, wenn Ziel > 0; sonst Icon grau, nur Ist.
- Zeiten: Restzeit unter 1 h als „noch 23 min“, sonst „noch 1:23 h“; ab 24 h „noch 1 d 3 h“.
  Fertig-Uhrzeit an einem anderen Tag als heute mit Wochentag („fertig Mo 07:40“).
- Lange Dateinamen werden mit … gekürzt (CSS), keine Zeilenumbrüche.
- Das Vorschaubild kommt als Data-URI ins HTML; der Renderer lädt nichts nach (netguard bleibt
  unberührt).

Texte (DE/EN): Druckt/Printing, Pausiert/Paused, Fertig/Finished, Fehler/Error, Bereit/Ready,
Drucker nicht erreichbar/Printer not reachable, noch/left, fertig/done, Schicht/Layer,
Dauer/Took, Zuletzt/Last, Düse/Nozzle, Bett/Bed, heizt/heating, seit/since, vor … min/… min ago.
Die genaue Formulierung ist Sache der Umsetzung (siehe energy für Stil).

## Konfiguration (vollständig)

```yaml
- type: printer
  source: moonraker | octoprint | prusalink | hass     # Pflicht
  url: http://drucker.local:7125                        # Pflicht (bei hass: HA-URL; im Add-on automatisch)
  # api_key: ${MOONRAKER_KEY}       # moonraker (optional), octoprint (Pflicht), prusalink (alternativ zu password)
  # user: maker                     # prusalink, Standard maker
  # password: ${PRUSALINK_PASSWORD} # prusalink
  # token: ${HA_TOKEN}              # hass
  # integration: moonraker          # hass, Pflicht
  # device: voron                   # hass, Pflicht außer bei octoprint
  # entities: {...}                 # hass, optional (bei custom Pflicht: mindestens state)
  # states: {printing: [running]}   # hass, optional (bei custom der normale Weg)
  # title: Drucker                  # Standard „Drucker“ / „Printer“
  # lang: en
  # thumbnail: false                # Standard true
  # finished_for: 120               # Minuten, Standard 120, 0 = nie „Fertig“
  # refresh: 10                     # Standard 10 s (DEFAULT_REFRESH), Minimum 5 (MIN_REFRESH)
```

Validierung lehnt unbekannte Schlüssel und Schlüssel der falschen Quelle ab (wie `energy`).
`SKIP_UNCHANGED = True`.

## Tests und Prüfung

TDD wie bei energy/ai. Ehrlich getrennt:

| Ebene | Was | Status heute |
|---|---|---|
| Unit mit Fixtures | Jeder Provider, jede HA-Vorlage, Zustandsregeln, Zeitformate, finished_for, Validierung, Log ohne Secrets | wird gebaut |
| Browser-Render | Jeder Zustand aus den Mockups, Text passt in die Box (wie energy-Tests), Vorschaubilder für Doku | wird gebaut |
| Simulator Moonraker | `mainsail-crew/virtual-klipper-printer` (Docker): echter Moonraker, simulierter MCU; Druck einer kleinen Datei mit Vorschaubild | manuell, Ergebnis ins Doku-Testprotokoll |
| Simulator OctoPrint | `octoprint/octoprint:1.11.8` mit Virtual Printer | manuell; OctoPrint-2.0-Bildweg nur, wenn sich 2.0 per pip lokal starten lässt |
| Echtes Gerät | Drucker des Nutzers, direkt über Moonraker; optional über HA-Moonraker-Integration | mit dem Nutzer; Modell, Adresse, Frontend werden erst dann erfragt; IP nie ins Repo |
| PrusaLink, Bambu, Creality, OctoPrint-HA, PrusaLink-HA | nur Fixtures aus dem Quellcode | Doku sagt genau das |

Fixtures liegen als JSON neben den Tests, jede mit Kopfkommentar/README-Zeile „abgeleitet aus
<Quelle>@<Version>, nicht vom Gerät“. Nach dem Test am echten Drucker kommt eine anonymisierte
echte Moonraker-Antwort dazu (Dateinamen ersetzt, keine Hostnamen).

Simulator-Läufe passieren lokal per Docker auf dem Mac, nicht auf dem Heimserver.

## Doku

- `docs/en/templates/printer.md` und `docs/de/templates/printer.md` (gleiche Überschriften,
  Doku-Parität-Test), Einträge in beiden Katalog-READMEs, Vorschaubilder unter
  `docs/img/templates/printer-*.png` (aus den Render-Tests, eigenes Vorschaubild, kein fremdes
  Modell-Bild).
- Abschnitt „Getestet mit“ als Tabelle wie oben, mit Datum.
- Setup je Quelle: wo der API-Key herkommt (Moonraker `trusted_clients` oder API-Key; OctoPrint
  Anwendungsschlüssel; PrusaLink Passwort im Drucker-Menü), welche HA-Integration, welches
  `device:` (wie man das Präfix in HA findet), bei PrusaLink-HA die Temperatursensoren aktivieren.
- `pages/printer/README.md` als Entwicklernotiz (Quellen, Formeln, Zustandstabellen).
- CHANGELOG-Eintrag (Version bei Release festlegen).

## Was der Umsetzung überlassen ist

- Genaue Pixelmaße, Schriftgrößen und Kürzungsregeln, solange die Mockups getroffen werden und
  die Render-Tests Überläufe ausschließen.
- Aufteilung der Tests auf Dateien, Namen interner Funktionen.
- Ob der Bild-Cache pro Seite oder pro Provider-Modul liegt (Schlüssel: Quelle + URL + Datei;
  höchstens wenige Einträge).
- Exakte DE/EN-Formulierungen.

## Offene Punkte für den Nutzer (später, nicht vor dem Plan)

- Am Ende der Umsetzung (Gerätetest): Druckermodell, Moonraker-Adresse, Frontend (Mainsail/Fluidd), ob Moonraker
  einen API-Key verlangt, und ob/wo die HA-Moonraker-Integration eingerichtet wird.
- Versionsnummer und Release erst mit Okay.

## Quellen (gelesen 2026-11-25)

- Moonraker master b559b9a8: docs/external_api/introduction.md, file_manager.md, authorization.md, components/file_manager/metadata.py
- Klipper master 7558e8c2: docs/Status_Reference.md, klippy/extras/print_stats.py
- Mainsail develop ce96e4d7 (v2.19.0): src/store/printer/getters.ts; Fluidd develop 8509fc70 (v1.38.1): src/store/printer/getters.ts
- OctoPrint 2.0.2: docs/api/job.rst, printer.rst, datamodel.rst, general.rst; src/octoprint/server/api/files.py; serial_comm.py. Docker Hub octoprint/octoprint latest = 1.11.8
- OctoPrint-PrusaSlicerThumbnails 1.2.4
- Prusa-Firmware-Buddy v8.0.2: lib/WUI/nhttp/status_renderer.cpp, link_content/basic_gets.cpp, previews.cpp, req_parser.cpp; src/state/printer_state.cpp. Prusa-Link (MK3) master; Prusa-Link-Web spec/openapi.yaml
- HA core dev: components/octoprint (5f380806), components/prusalink (8dbdb49d), components/api, helpers/template
- moonraker-home-assistant v1.14.0; ha-bambulab v2.4.1; ha_creality_ws v0.9.10
- mainsail-crew/virtual-klipper-printer; mkuf/prind v1.21.0
