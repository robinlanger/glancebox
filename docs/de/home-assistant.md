# Home-Assistant-Add-on

Wenn du Home Assistant OS nutzt, kannst du den Glance-Box-Server als Home-Assistant-Add-on
betreiben statt mit Docker Compose. Installieren, starten, eine Adresse ins Display eintragen,
fertig.

## Was du brauchst

- **Home Assistant OS** (oder eine Supervised-Installation). Home Assistant Container und Core
  haben keine Add-ons; nutze dort das [Docker-Setup](guide/2-start-the-server.md).
- Ein Display mit der Glance-Box-Firmware. Du flashst es **einmal im Browser**, ohne Löten:
  [Firmware flashen](guide/3-flash-the-firmware.md). Danach läuft alles in Home Assistant.

## Installieren

[![Repository zu meinem Home Assistant hinzufügen](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Frobinlanger%2Fglancebox)

Der Button öffnet dein Home Assistant und fügt dieses Repository zum Add-on-Store hinzu. Ohne
Button: **Einstellungen → Add-ons → Add-on-Store → ⋮ → Repositories**, dort
`https://github.com/robinlanger/glancebox` eintragen. Dann **Glance Box** öffnen, auf
**Installieren** und **Starten** klicken.

## Erster Start

Ohne Einstellungen legt das Add-on eine Start-Playlist an: eine **Uhr** und das **Wetter** am
Heimstandort deines Home Assistant. Zeitzone, Sprache (Deutsch oder Englisch) und Standort kommen
aus Home Assistant, du musst also nichts ausfüllen.

## Display verbinden

Klick auf der Seite des Add-ons auf **Benutzeroberfläche öffnen** (schalte dort **In Seitenleiste
anzeigen** ein, dann ist sie einen Klick entfernt). Der Kasten „Connect your display“
zeigt die Server-Adresse, zum Beispiel `http://192.168.x.x:8090`. Trag sie im Setup-Portal des
Displays ein ([WLAN einrichten](guide/4-set-up-wifi.md)) oder später auf seiner Geräteseite.

## Seiten ändern

Die Playlist ist die `config.yaml` im Konfigurationsordner des Add-ons. Im File editor oder in
Studio Code Server liegt sie unter `/addon_configs/<id>_glancebox/config.yaml`. Sie hat dasselbe
Format wie die [Konfiguration](configuration.md) des Docker-Setups, mit zwei Unterschieden:

- `timezone`, `lang` und der Ort einer `weather`-Seite sind optional; ohne sie gelten die Werte
  aus Home Assistant. Was du selbst einträgst, hat immer Vorrang.
- Eine `homeassistant`- oder `energy`-Seite braucht weder `url` noch `token`; sie liest aus diesem Home Assistant.

Ist der Ordner leer (das Add-on konnte die Startdatei dort nicht speichern), zeigt die Benutzeroberfläche
des Add-ons den Startinhalt: Lege damit im File editor die `config.yaml` an.

Starte das Add-on nach dem Bearbeiten neu.

## Geheimnisse

Der Tab **Konfiguration** des Add-ons enthält nur Geheimnisse, alle optional: den Push-Key für die
Claude-Limits (wird automatisch verwendet), die Keys für die Anbieter der `ai`-Seite (in der
`config.yaml` als `${ANTHROPIC_ADMIN_KEY}`, `${OPENAI_ADMIN_KEY}`, `${XAI_MANAGEMENT_KEY}`,
`${GITHUB_COPILOT_TOKEN}`) und „Weitere Geheimnisse“ für eigene Seiten (`${NAME}`). Geheimnisse
müssen nie im Klartext in der `config.yaml` stehen.

## Sicherheit

- Das Add-on hat **Admin-Zugriff auf Home Assistant**. Home Assistant gibt Add-ons API-Zugriff nur
  als Administrator; das Add-on liest damit Zustände von Entitäten und die Heim-Einstellungen. Der
  Zugangs-Token gehört dem Add-on und verfällt, wenn du es deinstallierst.
- Der **Display-Port (8090) hat keinen Login.** Er liefert nur die Bilder und nimmt Push-Daten mit
  dem Push-Key an. Nutze ihn nur im LAN und gib ihn nicht ins Internet frei.
- Die Übersicht mit Vorschau gibt es nur in der Benutzeroberfläche des Add-ons, hinter deinem
  Home-Assistant-Login.
