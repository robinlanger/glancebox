# Home-Assistant-Add-on

Wenn du Home Assistant OS nutzt, kannst du den Glance-Box-Server als Home-Assistant-Add-on
betreiben statt mit Docker Compose. Diese Seite führt dich in vier Schritten vom App-Store zu
deiner eigenen Playlist.

Die Namen von Menüs und Knöpfen unten sind die von Home Assistant 2026.11 (Home Assistant OS
18.4). Dort heißen Add-ons **Apps**: Das Menü ist **Einstellungen → Apps**, der Store heißt
**App-Store**. Ältere Versionen sagen „Add-ons“ und „Add-on-Store“; neuere nennen sie vielleicht
wieder anders.

## Was du brauchst

- **Home Assistant OS** (oder eine Supervised-Installation). Home Assistant Container und Core
  haben keine Add-ons; nutze dort das [Docker-Setup](guide/2-start-the-server.md).
- Ein Display mit der Glance-Box-Firmware. Du flashst es **einmal im Browser**, ohne Löten:
  [Firmware flashen](guide/3-flash-the-firmware.md). Danach läuft alles in Home Assistant.
- Display und Home Assistant im selben Netzwerk.

## Schritt 1: Add-on installieren

[![Repository zu meinem Home Assistant hinzufügen](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Frobinlanger%2Fglancebox)

1. Klick auf den Button. Er öffnet dein Home Assistant und fragt „App-Repository hinzufügen?“.
   Klick auf **Hinzufügen**.
   Ohne Button: **Einstellungen → Apps → App installieren**. Das öffnet den **App-Store**. Dort
   **⋮ (oben rechts) → Repositorys → Hinzufügen**, als URL `https://github.com/robinlanger/glancebox`
   eintragen und auf **Hinzufügen** klicken.
2. Öffne im App-Store **Glance Box**. Taucht es noch nicht auf, lade die Seite neu.
3. Klick auf **Installieren**. Der Download kann einige Minuten dauern; danach zeigt die Seite des
   Add-ons **Starten**.

## Schritt 2: Starten und Oberfläche öffnen

1. Klick auf der Seite des Add-ons auf **Starten**. Der Reiter **Protokoll** zeigt zwei Zeilen mit
   `Uvicorn running on`, sobald der Server läuft (das Add-on startet zwei Server). Eine davon
   nennt Port 8080, den Port im Add-on, den dein Netzwerk über Port 8090 erreicht; die andere
   gehört zur Oberfläche.
2. Klick auf **Benutzeroberfläche öffnen**. Die Übersicht des Add-ons öffnet sich: der Kasten
   „Connect your display“ und unter „Playlist“ die Starter-Seiten **clock** und **weather**. Ihre
   Vorschau erscheint nach kurzer Zeit; bis dahin steht bei einer Seite „no picture yet“. Die
   Übersicht lädt sich alle 30 Sekunden neu.
3. Optional: Schalte auf der Seite des Add-ons **In Seitenleiste anzeigen** ein. Nach der
   Installation ist es aus, von selbst legt Home Assistant also keinen Eintrag in der Seitenleiste
   an.

Zeitzone, Sprache (Deutsch oder Englisch) und der Heimstandort fürs Wetter kommen aus Home
Assistant, du musst also nichts ausfüllen.

## Schritt 3: Display verbinden

1. Kopiere im Kasten „Connect your display“ die Adresse, zum Beispiel `http://192.168.1.x:8090`
   (die IP-Adresse deines Home Assistant und Port 8090).
2. Trag sie im Display ein:
    - **Neues Display:** Verbinde dich mit dem WLAN **GlanceBox-XXXX** des Displays, wähle dein
      Netzwerk und füge die Adresse ins Feld **Server URL** ein
      ([WLAN einrichten](guide/4-set-up-wifi.md)).
    - **Display schon eingerichtet:** Öffne seine Geräteseite `http://<display-ip>/`, trag die
      Adresse unter **Einstellungen → Server-URL** ein und klick auf **Speichern**. Änderungen
      brauchen das Update-Passwort (Benutzer `admin`).

    Nur `http://` funktioniert, nicht `https://`.
3. Zurück in der Oberfläche des Add-ons wird aus dem grauen „Waiting for your display“ ein grünes
   „Display connected · last picture …“, sobald das Display sein erstes Bild geholt hat. Das
   Display zeigt die Uhr, dann das Wetter.

## Schritt 4: Seiten festlegen

Die Playlist ist die Datei `config.yaml` im Konfigurationsordner des Add-ons,
`/app_configs/<id>_glancebox/config.yaml`. `<id>` ist ein kurzer Code, den Home Assistant aus der
Adresse des Repositorys bildet; für dieses Repository ist er `9a6cf636`, der Ordner ist also
`/app_configs/9a6cf636_glancebox/`. Ältere Versionen von Home Assistant und der
Editor-Add-ons zeigen den Ordner als `/addon_configs/<id>_glancebox/`. Im Add-on selbst und in
seinem Protokoll heißt dieselbe Datei `/config/config.yaml`. Sie hat dasselbe Format wie die
[Konfiguration](configuration.md) des Docker-Setups, mit zwei Unterschieden:

- `timezone`, `lang` und der Ort einer `weather`-Seite sind optional; ohne sie gelten die Werte
  aus Home Assistant. Was du in der `config.yaml` einträgst, hat immer Vorrang.
- Eine `homeassistant`- oder `energy`-Seite und eine `printer`-Seite mit `source: hass` brauchen
  weder `url` noch `token`; sie lesen aus diesem Home Assistant.

Zum Bearbeiten brauchst du ein Editor-Add-on aus dem offiziellen App-Store, zum Beispiel
**File editor**, **Studio Code Server** oder **Terminal & SSH**; Home Assistant OS bringt keins
mit. Laut seiner eigenen Dokumentation beschränkt die Option „Enforce basepath“ den File editor
auf den Konfigurationsordner von Home Assistant; nach der Installation ist sie an. Schalte sie im
Reiter **Konfiguration** des File editor aus und starte den File editor neu (im File editor
selbst noch nicht ausprobiert; den Ordner haben wir in Terminal & SSH geprüft).

1. Öffne `/app_configs/<id>_glancebox/` in deinem Editor.
    - **Der Ordner ist leer:** Das Add-on konnte die Startdatei nicht speichern. So war es unter
      Home Assistant OS 18.4. Der Reiter Protokoll zeigt `cannot write /config/config.yaml
      ([Errno 13] Permission denied: ...); using a temporary starter playlist`, und die
      Oberfläche zeigt den Startinhalt unter „Start config.yaml with this content“. Leg in diesem
      Ordner eine neue Datei `config.yaml` an und füge den Inhalt ein.
    - **`config.yaml` ist da:** Das Add-on hat sie beim ersten Start mit den Starter-Seiten
      angelegt. Der Reiter Protokoll zeigt bei diesem Start `wrote starter playlist to
      /config/config.yaml`.
2. Ändere die Seiten. Eine typische erste Playlist: die Uhr, das Wetter und ein paar Entitäten
   deines Home Assistant (ersetze die Entitäts-IDs durch deine eigenen):

    ```yaml
    pages:
      - type: clock
      - type: weather
        refresh: 60
      - type: homeassistant
        title: Zuhause
        entities:
          - sensor.outside_temperature
          - sensor.pv_power
          - binary_sensor.front_door
    ```

3. Speichere die Datei und **starte das Add-on neu** (Neu starten auf der Seite des Add-ons). Das
   Add-on liest die `config.yaml` nur beim Start; das gilt auch nach jeder Änderung an einem
   Geheimnis.
4. Öffne die Oberfläche wieder. Die Playlist listet deine Seiten mit ihrer Vorschau. Hat eine
   Seite ein Problem, steht der Fehler rot unter ihrer Vorschau.

Stoppt das Add-on stattdessen, nennen die letzten Zeilen im Reiter Protokoll den Grund, siehe
[Fehlerbehebung](#fehlerbehebung).

## Beispiele

Jeder Block ist eine Liste von Seiten: Setz ihn unter `pages:` in deine `config.yaml`. Alle
Optionen eines Seitentyps stehen auf seiner Seite im [Vorlagen-Katalog](templates/README.md).

### Entitäten: `homeassistant`

Zeigt bis zu sechs Entitäten. Kein `url` oder `token` nötig.
[Alle Optionen](templates/homeassistant.md)

```yaml
- type: homeassistant
  title: Solar
  entities:
    - entity: sensor.pv_power
      label: PV
    - entity: sensor.grid_power
      label: Netz
    - entity: sensor.battery_level
      label: Akku
```

### Energiefluss: `energy`

[Alle Optionen](templates/energy.md)

```yaml
- type: energy
  title: Strom
  refresh: 5
  rows:
    - type: grid
      entity: sensor.grid_power
    - type: pv
      entity: sensor.pv_power
    - type: battery
      entity: sensor.battery_power
      soc: sensor.battery_level
```

### 3D-Drucker aus Home Assistant: `printer`

Liest die Entitäten des Druckers aus Home Assistant, hier die der Moonraker-Integration. `device`
ist das Entitäts-Präfix deines Druckers. [Alle Optionen](templates/printer.md)

```yaml
- type: printer
  source: hass
  integration: moonraker
  device: voron
```

### Wetter an einem anderen Ort: `weather`

Ohne `location` nimmt die Seite den Heimstandort aus Home Assistant.
[Alle Optionen](templates/weather.md)

```yaml
- type: weather
  location: Frankfurt am Main
```

### Abfahrten: `bahn`

[Alle Optionen](templates/bahn.md)

```yaml
- type: bahn
  station: "Frankfurt(Main)Hbf"
  limit: 4
  refresh: 60
```

### Claude-Limits: `ai`

Braucht den **Push-Key** aus dem Reiter Konfiguration des Add-ons und das Status-Line-Skript auf
deinem Rechner. [Alle Optionen](templates/ai.md)

```yaml
- type: ai
  provider: claude
```

### Zeitformat, Sprache und Zeitzone

Diese Schlüssel stehen oben in der `config.yaml`, über `pages:`. `time_format: 12h` zeigt
Uhrzeiten als `2:05 PM`; Standard ist `24h`. Das Add-on hat dafür kein Formularfeld. `lang` und
`timezone` brauchst du nur, wenn sie von Home Assistant abweichen sollen. Eine Seite kann
`time_format` für sich überschreiben; hier bleiben die Abfahrten in 24 Stunden.

```yaml
time_format: 12h
lang: en
timezone: America/New_York

pages:
  - type: clock
  - type: bahn
    station: "Frankfurt(Main)Hbf"
    time_format: 24h
```

## Geheimnisse

Der Reiter **Konfiguration** des Add-ons enthält nur Geheimnisse, alle optional. Geheimnisse
müssen nie im Klartext in der `config.yaml` stehen.

- **Push-Key:** für die Claude-Limits (`ai` mit `provider: claude`). Wird automatisch verwendet.
- **Anthropic-, OpenAI-, xAI- und GitHub-Copilot-Keys:** für die `ai`-Seite mit dem passenden
  Anbieter. In der `config.yaml` schreibst du sie als `${ANTHROPIC_ADMIN_KEY}`,
  `${OPENAI_ADMIN_KEY}`, `${XAI_MANAGEMENT_KEY}`, `${GITHUB_COPILOT_TOKEN}`.
- **Weitere Geheimnisse:** Paare aus Name und Wert für eigene Seiten und für Key oder Passwort
  eines direkt gelesenen Druckers, verwendet als `${NAME}`. Der Name beginnt mit einem
  Großbuchstaben und besteht aus Großbuchstaben, Ziffern und `_` (A-Z, 0-9, `_`). Ein Name, der
  schon vergeben ist, etwa der eines der festen Geheimnisse oben, wird ignoriert.

Beispiel: ein Drucker, der direkt aus OctoPrint gelesen wird. Trag unter **Weitere Geheimnisse**
`OCTOPRINT_KEY` mit deinem Key ein, speichere, und verwende ihn so:

```yaml
- type: printer
  source: octoprint
  url: http://printer.local
  api_key: ${OCTOPRINT_KEY}
```

Starte das Add-on nach jeder Änderung an einem Geheimnis neu.

## Aktualisieren

- **Add-on:** Home Assistant zeigt ein Update für Glance Box an, wenn eine neue Version erschienen
  ist. Installier es wie andere Add-on-Updates; deine `config.yaml` bleibt erhalten.
- **Display-Firmware:** Die Release Notes sagen, ob ein Release neue Firmware enthält. Nur dann
  aktualisierst du das Display: [Firmware aktualisieren](updating.md).

## Fehlerbehebung

| Was du siehst | Wahrscheinliche Ursache | Was du tust |
| --- | --- | --- |
| Das Add-on stoppt gleich nach dem Starten | Ein Fehler in der `config.yaml` | Öffne den Reiter **Protokoll**. Seine letzte Zeile nennt das Problem, zum Beispiel `pages[2] (homeassistant): ...`, `pages[0] (clok): unknown page type; available: ...`, `pages[0].api_key: environment variable OCTOPRINT_KEY is not set` (das Geheimnis fehlt im Reiter Konfiguration) oder `refresh must be at least ...`. Ein YAML-Fehler (zum Beispiel falsche Einrückung) beginnt mit `/config/config.yaml: invalid YAML:` und braucht ein paar Zeilen mit Zeile und Spalte. Behebe es und starte das Add-on wieder. |
| Eine Änderung wirkt nicht | Das Add-on wurde nicht neu gestartet | Starte das Add-on nach jeder Änderung an der `config.yaml` oder an einem Geheimnis neu. |
| Die `config.yaml` ist nicht zu finden | Die Datei liegt im Konfigurationsordner des Add-ons, nicht im Konfigurationsordner von Home Assistant | Schau in `/app_configs/<id>_glancebox/` (ältere Versionen: `/addon_configs/<id>_glancebox/`). Der File editor ist auf den Konfigurationsordner von Home Assistant beschränkt, solange seine Option „Enforce basepath“ an ist. Ist der Ordner leer, leg die `config.yaml` mit dem Startinhalt aus der Oberfläche an (Schritt 4). |
| Das Display zeigt nichts, oder die Oberfläche zeigt weiter „Waiting for your display“ | Das Display hat eine falsche Adresse | Prüf die Adresse im Display: `http://`, die IP-Adresse von Home Assistant, Port 8090. Display und Home Assistant müssen im selben Netzwerk sein. Öffne `http://192.168.1.x:8090/healthz` im Browser: Es antwortet mit einer Zeile JSON, die mit `{"version":` und der Versionsnummer beginnt. Wenn nicht, erreicht auch das Display das Add-on nicht. |
| `http://192.168.1.x:8090/` zeigt im Browser `{"detail":"Not Found"}` | Alles in Ordnung | Die Übersicht gibt es nur in der Oberfläche des Add-ons in Home Assistant. Port 8090 bedient nur das Display. Zum Prüfen öffne `/healthz`. |
| Die Oberfläche meldet „The server address could not be determined“ | Der Port des Add-ons ist abgeschaltet | Öffne im Add-on den Reiter **Konfiguration**, Abschnitt **Netzwerk**, und trag für den Display-Port einen Port ein (8090). Speichere und starte das Add-on neu. |
| Das Add-on startet nicht: `Cannot start app ... because port 8090 is already in use` | Ein anderes Add-on oder Programm nutzt Port 8090 | Ändere den Port im Reiter **Konfiguration**, Abschnitt **Netzwerk**, und verwende den neuen Port in der Adresse im Display. |
| Eine Seite zeigt „Keine Verbindung zu Home Assistant“, oder eine Kachel zeigt „fehlt“ | Home Assistant hat nicht geantwortet, oder eine Entitäts-ID gibt es nicht | Prüf die Entitäts-ID unter **Einstellungen → Geräte & Dienste → Entitäten**. Die Oberfläche zeigt den Fehler rot unter der Vorschau der Seite. |
| Das Wetter gilt für den falschen Ort | Der Heimstandort in Home Assistant ist nicht der Ort, für den du das Wetter willst | Setz `location:` auf der `weather`-Seite (siehe [Beispiele](#wetter-an-einem-anderen-ort-weather)). |

## Sicherheit

- Das Add-on hat **Admin-Zugriff auf Home Assistant**. Home Assistant gibt Add-ons API-Zugriff nur
  als Administrator; das Add-on liest damit Zustände von Entitäten und die Heim-Einstellungen. Der
  Zugangs-Token gehört dem Add-on und verfällt, wenn du es deinstallierst.
- Der **Display-Port (8090) hat keinen Login.** Er liefert nur die Bilder und nimmt Push-Daten mit
  dem Push-Key an. Nutze ihn nur im LAN und gib ihn nicht ins Internet frei.
- Die Übersicht mit Vorschau gibt es nur in der Benutzeroberfläche des Add-ons, hinter deinem
  Home-Assistant-Login.
