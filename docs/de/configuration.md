# Server-Konfiguration

Der ganze Server wird mit einer einzigen Datei eingestellt, `config.yaml`. Als Vorlage dient `config-example.yaml`.

## Wo die Datei liegt

Mit der mitgelieferten `docker-compose.yml` liest der Server `./config.yaml` aus dem Projektordner (schreibgeschützt unter `/config/config.yaml` eingebunden). Eigene Seiten kommen nach `./pages-custom` (unter `/config/pages` eingebunden, siehe [Seiten schreiben](writing-pages.md)). **Lege diesen Ordner vor dem ersten Start an** (`mkdir pages-custom`), sonst legt Docker ihn als root an.

Starte den Server nach jeder Änderung neu:

```sh
docker compose restart
docker compose logs --tail 50
```

Der Server prüft die Datei beim Start. Stimmt etwas nicht (Tippfehler bei einem Schlüssel, unbekannter Seitentyp, `refresh` unter dem Minimum), startet er nicht und schreibt eine klare Meldung ins Log.

## Optionen auf oberster Ebene

| Schlüssel | Standard | Bedeutung |
| --- | --- | --- |
| `interval` | `30` | Standard-Anzeigedauer einer Seite in Sekunden. |
| `timezone` | `Europe/Berlin` | Zeitzone für Uhren und Uhrzeiten auf Seiten (IANA-Name). |
| `lang` | `de` | Standardsprache der mitgelieferten Seiten (`de` oder `en`). |
| `custom_pages_dir` | nicht gesetzt | Ordner mit deinen eigenen Seitentypen. Relative Pfade gelten ab dem Ordner der Konfigurationsdatei. Er darf fehlen, der Server warnt dann im Log und nutzt nur die mitgelieferten Seiten. In Docker `/config/pages`. |
| `push_key` | nicht gesetzt | Schlüssel für gepushte Daten (nötig für die `ai`-Seite mit Provider `claude`). Mindestens 16 Zeichen, nur ASCII (Buchstaben, Ziffern, `-`, `_`), erzeugen mit `openssl rand -hex 24`. Ohne ihn ist der Push-Endpunkt aus. Nur im Heimnetz (LAN) verwenden. In `.env` ablegen und `push_key: ${GLANCEBOX_PUSH_KEY}` schreiben. |
| `pages` | Pflicht | Die Playlist, mindestens eine Seite. |

Unbekannte Schlüssel auf oberster Ebene werden abgelehnt.

## Geheimnisse und Umgebungsvariablen

Schreibe Tokens und Schlüssel nie direkt in die `config.yaml`. Lege sie in eine Datei `.env` neben der `docker-compose.yml`, eine Zeile `NAME=Wert` pro Eintrag, und verweise in der Konfiguration darauf:

```yaml
push_key: ${GLANCEBOX_PUSH_KEY}
```

- Ersetzt wird nur ein Wert, der genau `${NAME}` lautet. In einem längeren Text wie `http://${HOST}:3001` bleibt es einfach Text.
- Fehlt die Variable oder ist sie leer, startet der Server nicht und nennt die Stelle in der Datei, zum Beispiel `pages[2].token: environment variable KUMA_TOKEN is not set`.
- Ein ersetzter Wert ist immer Text. Optionen, die eine Zahl brauchen, etwa `refresh` oder `budget`, können `${NAME}` nicht nutzen.
- Docker liest `.env` nur beim Erstellen des Containers. Nach einer Änderung `docker compose up -d` ausführen; `docker compose restart` übernimmt sie nicht.
- Die mitgelieferte `docker-compose.yml` lädt `.env` per `env_file` mit `path`/`required: false`, die Datei darf also fehlen. Diese Form braucht Docker Compose 2.24 oder neuer (`docker compose version`).

## Optionen, die jede Seite hat

```yaml
pages:
  - type: clock
    duration: 15
    refresh: 60
```

| Schlüssel | Standard | Bedeutung |
| --- | --- | --- |
| `type` | Pflicht | Seitentyp: `url`, `bahn`, `clock`, `weather`, `kuma`, `homeassistant`, `energy`, `printer`, `ai` oder ein eigener. Die fertigen Seiten stehen im [Vorlagen-Katalog](templates/README.md). |
| `duration` | `interval` | Wie viele Sekunden die Seite auf dem Display bleibt. |
| `refresh` | `duration` | Eine Seite wird höchstens alle `refresh` Sekunden neu gerendert. Nimm einen größeren Wert für Daten, die sich langsam ändern, oder für Dienste, die Anfragen begrenzen. Ein Seitentyp kann einen eigenen Standard und ein eigenes Minimum haben, zum Beispiel `energy`: Standard 5, mindestens 2; `printer`: Standard 10, mindestens 5. |

Alle anderen Schlüssel gehören zum Seitentyp und stehen unten. Fertige Seiten mit Vorschaubildern findest du im [Vorlagen-Katalog](templates/README.md).

## Seitentyp: url

Rendert eine Webseite unverändert, in einem Browserfenster von genau 240x240 Pixeln.

```yaml
- type: url
  url: http://homeserver.lan/status-240
  wait_for: "#ready"
  wait_ms: 500
  duration: 15
  refresh: 30
```

| Schlüssel | Standard | Bedeutung |
| --- | --- | --- |
| `url` | Pflicht | Adresse mit `http://` oder `https://`. |
| `wait_for` | keiner | CSS-Selektor. Der Screenshot entsteht erst, wenn ein passendes Element existiert. Nutze das für Seiten, die ihren Inhalt mit JavaScript aufbauen. |
| `wait_ms` | `0` | Zusätzliche Pause in Millisekunden vor dem Screenshot (nachdem die Seite geladen ist und `wait_for` gepasst hat). |
| `timeout_s` | `15` | Wie lange Laden und `wait_for` dauern dürfen, bevor die Seite als fehlgeschlagen gilt. |

Der Server läuft in einem Container. `localhost` heißt dort der Container selbst, nimm also die LAN-Adresse oder den Namen des anderen Rechners. Seiten, die eine Anmeldung brauchen, zeigen den Anmeldebildschirm. Tipps zum Gestalten solcher Seiten stehen in [Seiten schreiben](writing-pages.md#die-url-seite-und-ihre-tipps).

## Seitentyp: bahn

Live-Abfahrten für einen deutschen Bahnhof von [DBF](https://dbf.finalrewind.org) (db-infoscreen).

```yaml
- type: bahn
  station: "Frankfurt(Main)Hbf"
  via: [Wiesbaden, Mainz]
  platforms: "101,102"
  limit: 4
  title: "Frankfurt"
  refresh: 60
```

| Schlüssel | Standard | Bedeutung |
| --- | --- | --- |
| `station` | Pflicht | Bahnhofsname, EVA-Nummer oder DS100-Kürzel. Den genauen Namen findest du auf dbf.finalrewind.org: der Teil der Adresse nach der Suche. |
| `via` | alle | Nur Züge, die **nach** deinem Bahnhof an einem dieser Orte halten (Text oder Liste). Zwischenhalte funktionieren besser als Endziele, weil sie auch Züge erfassen, die früher enden. |
| `platforms` | alle | Nur diese Gleise (Text oder Liste). |
| `limit` | `4` | Zeilen, 1 bis 6. Weniger Zeilen bedeuten größere Schrift. |
| `title` | der Bahnhof | Text der Kopfzeile. |
| `dbf_url` | `https://dbf.finalrewind.org` | Adresse einer DBF-Instanz, falls du eine eigene betreibst. |
| `refresh` | `60` | **Mindestens 60.** Das ist die DBF-Regel von einer Anfrage pro Bahnhof und Minute. Setzt du `refresh` nicht, wird es automatisch auf 60 angehoben. Setzt du einen Wert unter 60, startet der Server nicht. |

Ist DBF nicht erreichbar, zeigt die Seite „Keine Daten“, eine leere Liste zeigt „Keine Abfahrten“. Vollständige Beschreibung: [bahn](templates/bahn.md).

## Seitentyp: clock

Eine große Uhr mit Wochentag und Datum, gedacht als Ausgangspunkt für eigene Seiten. Vollständige Beschreibung: [clock](templates/clock.md).

```yaml
- type: clock
  lang: en
  refresh: 60
```

| Schlüssel | Standard | Bedeutung |
| --- | --- | --- |
| `lang` | `lang` von oberster Ebene | `de` oder `en`. |

## Seitentyp: weather

Aktuelles Wetter, Höchst- und Tiefstwert des Tages und die nächsten 4 Stunden, von [Open-Meteo](https://open-meteo.com) (kostenlos, ohne Key). Ausführlich: [weather](templates/weather.md).

```yaml
- type: weather
  location: Frankfurt am Main     # oder latitude: / longitude:
```

## Seitentyp: kuma

Der Zustand deines Servers aus einer Statusseite von [Uptime Kuma](https://github.com/louislam/uptime-kuma): groß „14/14 OK“ oder eine rote Kopfzeile mit den gestörten Diensten. Kein Token und keine Rechte auf deinem Server. Ausführlich, auch wie du Uptime Kuma installierst: [kuma](templates/kuma.md).

```yaml
- type: kuma
  url: http://homeserver.lan:3001
  slug: homelab
  refresh: 30
```

## Seitentyp: homeassistant

Live-Werte von bis zu sechs Entitäten aus [Home Assistant](https://www.home-assistant.io/), als Kacheln (1 bis 4) oder Liste (bis 6). Braucht einen langlebigen Zugangstoken; ihn und die Adresse trägst du in die `.env` ein, siehe [Geheimnisse und Umgebungsvariablen](#geheimnisse-und-umgebungsvariablen). Der Token hat alle Rechte seines Benutzers, nimm also einen eigenen Benutzer. Ausführlich: [homeassistant](templates/homeassistant.md).

```yaml
- type: homeassistant
  url: ${HA_URL}
  token: ${HA_TOKEN}
  title: Solar
  refresh: 30
  entities:
    - sensor.pv_power
    - entity: sensor.grid_power
      label: Netz
```

## Seitentyp: energy

Energiefluss aus Home Assistant in 1 bis 4 Zeilen (`grid`, `pv`, `battery`, `gas`, `water`, `wallbox`), jede mit einem Leistungs- oder Durchflusssensor. Ab Firmware 0.7.0 zeichnet das Display laufende Pfeile in Richtung des Flusses; ältere Firmware zeigt ein Standbild. Ohne `refresh` gelten für diese Seite 5 Sekunden. Adresse und Token wie bei `homeassistant`. Ausführlich, mit Vorzeichen und Optionen: [energy](templates/energy.md).

```yaml
- type: energy
  url: ${HA_URL}
  token: ${HA_TOKEN}
  title: Strom
  rows:
    - type: grid
      entity: sensor.grid_power
    - type: pv
      entity: sensor.pv_power
    - type: battery
      entity: sensor.battery_power
      soc: sensor.battery_level
```

## Seitentyp: printer

Zustand, Fortschritt, Restzeit und Temperaturen eines 3D-Druckers, mit dem Vorschaubild des Slicers. `source:` sagt, woher der Zustand kommt: `moonraker` (Klipper), `octoprint`, `prusalink` direkt vom Drucker oder `hass` mit einer Vorlage für die Home-Assistant-Integration des Druckers (`moonraker`, `octoprint`, `prusalink`, `bambu_lab`, `creality` oder `custom`). Ohne `refresh` gelten für diese Seite 10 Sekunden, mindestens 5. Keys und Passwörter gehören in die `.env`, siehe [Geheimnisse und Umgebungsvariablen](#geheimnisse-und-umgebungsvariablen). Noch nicht an einem echten Drucker geprüft. Ausführlich, mit Optionen und Einrichtung je Quelle: [printer](templates/printer.md).

```yaml
- type: printer
  source: moonraker
  url: http://drucker.local:7125
  # api_key: ${MOONRAKER_KEY}
```

## Seitentyp: ai

Wie viel von einem KI-Abo oder Budget verbraucht ist, ein Anbieter pro Seite: `claude` (Abo-Limits, die Claude Code auf deinem Rechner schickt), `anthropic-api`, `openai-api`, `xai-api` (Kosten oder Guthaben) und `copilot` (Verbrauch im Monat). Schlüssel gehören in die `.env`, siehe [Geheimnisse und Umgebungsvariablen](#geheimnisse-und-umgebungsvariablen). Ausführlich und mit Einrichtung je Anbieter: [ai](templates/ai.md).

```yaml
- type: ai
  provider: claude
  refresh: 30
```

## So verhält sich die Playlist

- Welche Seite gerade läuft, ergibt sich aus der **Uhrzeit**: Die Anzeigedauern aller Seiten ergeben zusammen einen Zyklus, und die Position im Zyklus ist die aktuelle Zeit modulo dieser Summe. Der Server merkt sich nichts pro Gerät, also zeigen mehrere Displays gleichzeitig dieselbe Seite.
- Das Display fragt nach der Zeit, die der Server nennt, nach dem nächsten Bild. Diese Zeit liegt immer zwischen 2 und 30 Sekunden. Das Bild wird nur übertragen, wenn es sich geändert hat, sonst antwortet der Server „nicht geändert“.
- Die Bilder sind Baseline-JPEGs mit 240x240 Pixeln und höchstens 24 576 Bytes. Der Server senkt die Qualität (von 85 bis auf 40), bis ein Bild passt. Sehr detailreiche Bilder (Fotos, feine Farbverläufe) können trotzdem scheitern, einfarbige Flächen funktionieren am besten.
- Fällt eine Seite aus (Datenquelle down, Fehler im Template), zeigt der Server **bis zu 10 Minuten lang ihr letztes gutes Bild** weiter. Danach wird die Seite übersprungen. Funktioniert gar keine Seite, zeigt das Display eine Fehlerseite statt eines schwarzen Bildschirms. Fehler stehen im Log und auf der Vorschauseite.

## Server prüfen und betreiben

| Adresse | Wozu |
| --- | --- |
| `http://<server>:8080/` | Vorschau aller Seiten mit Alter und letztem Fehler (aktualisiert sich selbst). |
| `http://<server>:8080/preview/<n>.jpg` | Das aktuelle Bild von Seite Nummer `n` (ab 0 gezählt). |
| `http://<server>:8080/healthz` | Kleines JSON für Gesundheitsprüfungen (Docker nutzt es). Antwortet mit 503, solange der Renderer oder sein Browser ausgefallen ist. |
| `http://<server>:8080/api/v1/frame` | Was das Display abruft. |

Der Server läuft als normaler Benutzer (nicht als root) und hat **keine Anmeldung**. Lass Port 8080 in deinem Heimnetz. Für einen anderen Port änderst du die linke Zahl bei `ports:` in der `docker-compose.yml`, zum Beispiel `"9090:8080"`.

Server aktualisieren: `git pull` und `docker compose up -d --build`. Zu jedem Release gibt es auch ein fertiges Image, `ghcr.io/robinlanger/glancebox:<version>`, für amd64 und arm64.
