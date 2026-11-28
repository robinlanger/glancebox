# weather

![Vorschau der Seite weather](../../img/templates/weather.png)

## Was sie zeigt

Das aktuelle Wetter für einen Ort: ein Symbol, die Temperatur in großen Ziffern und eine kurze Beschreibung. Darunter das Tageshoch (rot) und das Tagestief (blau) sowie die nächsten vier Stunden mit Temperatur und Regenwahrscheinlichkeit.

Beschreibung und Titel folgen der Sprache der Seite (`de` oder `en`).

## Was du brauchst

- Internetzugang für den Server. Die Daten kommen von [Open-Meteo](https://open-meteo.com), einem kostenlosen Wetterdienst. Kein Konto und kein Schlüssel.
- Einen Ortsnamen oder seine Koordinaten.

## Beispiel

```yaml
- type: weather
  location: Frankfurt am Main
  lang: de
```

## Optionen

| Schlüssel | Standard | Bedeutung |
| --- | --- | --- |
| `location` | | Ortsname, der einmalig über den Geocoding-Dienst von Open-Meteo gesucht wird. Nimm dies **oder** `latitude` und `longitude`. |
| `latitude`, `longitude` | | Koordinaten in Grad (zum Beispiel `50.11` und `8.68`). Immer beide setzen und nie zusammen mit `location`. |
| `title` | der gefundene Ortsname, sonst `Wetter` | Text in der Kopfzeile. |
| `lang` | oberstes `lang` | `de` oder `en`. Bestimmt die Beschreibung und den Standardtitel. |
| `refresh` | `duration`, mindestens `60` | Sekunden zwischen zwei neuen Bildern, **mindestens 60**. Bild und Uhrzeit bleiben aktuell, Open-Meteo wird aber höchstens alle 15 Minuten gefragt, weil sich das Wetter langsam ändert und der Dienst kostenlos ist. Bei einem Wert unter 60 startet der Server nicht. |
| `duration` | `interval` | Wie viele Sekunden die Seite auf dem Display bleibt. |
| `time_format` | oberstes `time_format` | `24h` oder `12h`. Mit `12h` stehen die vier Stunden als `3 PM` statt `15` und die Uhr in der Kopfzeile als `2:32 PM`. |

Die Zeitzone kommt aus `timezone` auf oberster Ebene. Die vier Stunden sind die nächsten vier vollen Stunden in dieser Zone, auch über Mitternacht hinweg.

## Einrichtung

1. Füge das Beispiel in die Liste `pages:` der `config.yaml` ein, mit deinem `location`.
2. Starte den Server neu: `docker compose restart`.
3. Öffne `http://<server>:8080/` und prüfe die Vorschau.

Ist es nicht der Ort, den du meinst, ergänze Land oder Region im Namen oder nimm stattdessen `latitude` und `longitude`.

## Datenschutz & Sicherheit

- Die Seite braucht keinen Schlüssel, es gibt also kein Geheimnis zu schützen.
- Mit `location` geht der Ortsname einmal pro Serverstart an Open-Meteo. Jede Abfrage der Vorhersage (höchstens alle 15 Minuten) sendet die Koordinaten des Ortes. Open-Meteo sieht außerdem die IP-Adresse deines Servers.
- Auf dem Server wird nichts gespeichert außer dem aktuellen Bild.
- Die Daten von Open-Meteo stehen unter CC BY 4.0, siehe [open-meteo.com/en/license](https://open-meteo.com/en/license).

## Wenn etwas nicht stimmt

- **Die Seite zeigt ein altes Bild:** Open-Meteo war nicht erreichbar. Das letzte Bild bleibt bis zu 10 Minuten stehen, danach überspringt das Display die Seite. Der Grund steht in `docker compose logs`.
- **`location not found` im Log:** Der Geocoding-Dienst kennt den Namen nicht. Versuche eine andere Schreibweise oder nimm `latitude` und `longitude`.
- **Der Server startet nicht und nennt `location`:** Nimm entweder `location` oder beide Koordinaten, nie beide Formen.
- **Der Server startet nicht und meldet `refresh`:** Der Wert liegt unter 60. Entferne ihn oder erhöhe ihn.
- **Stunden oder Uhrzeit stimmen nicht:** Setze `timezone` auf oberster Ebene (zum Beispiel `Europe/Berlin`).
