# bahn

![Vorschau der Seite bahn](../../img/templates/bahn.png)

## Was sie zeigt

Die nächsten Abfahrten eines deutschen Bahnhofs, wie auf einer Abfahrtstafel. Jede Zeile hat die Linie als Badge (S-Bahn grün, Fernverkehr weiß und rot, RB/RE rot), das Ziel, die Minuten bis zur Abfahrt und das Gleis.

- Die Minuten werden ab 3 oder weniger gelb.
- Eine Verspätung steht als `+4`, orange unter 6 Minuten und rot ab 6.
- Das Gleis ist orange, wenn es gewechselt hat.
- Ausfallende Züge sind rot durchgestrichen und tragen „fällt aus“.

Die Texte auf der Seite sind deutsch („Keine Daten“, „Keine Abfahrten“, „fällt aus“, „Gl.“).

## Was du brauchst

- Internetzugang für den Server. Die Daten kommen von [DBF](https://dbf.finalrewind.org) (db-infoscreen), einem kostenlosen Dienst, der Daten der Deutschen Bahn aufbereitet. Kein Konto, kein Schlüssel.
- Den genauen Namen deines Bahnhofs, so wie DBF ihn kennt.

## Beispiel

```yaml
- type: bahn
  station: "Frankfurt(Main)Hbf"
  via: [Wiesbaden, Mainz]
  platforms: "101,102"
  limit: 4
  title: "Frankfurt"
  refresh: 60
```

## Optionen

| Schlüssel | Standard | Bedeutung |
| --- | --- | --- |
| `station` | Pflicht | Bahnhofsname, EVA-Nummer oder DS100-Kürzel. Den genauen Namen findest du auf dbf.finalrewind.org: der Teil der Adresse nach der Suche. |
| `via` | alle | Nur Züge, die **nach** deinem Bahnhof an einem dieser Orte halten (Text oder Liste). Zwischenhalte funktionieren besser als Endziele, weil sie auch Züge erfassen, die früher enden. |
| `platforms` | alle | Nur diese Gleise (Text oder Liste). |
| `limit` | `4` | Zeilen, 1 bis 6. Weniger Zeilen bedeuten größere Schrift. |
| `title` | der Bahnhof | Text der Kopfzeile. |
| `dbf_url` | `https://dbf.finalrewind.org` | Adresse einer DBF-Instanz, falls du eine eigene betreibst. |
| `refresh` | `60` | **Mindestens 60.** Das ist die Regel von DBF: eine Anfrage pro Bahnhof und Minute. Ohne `refresh` wird automatisch auf 60 angehoben. Bei einem Wert unter 60 startet der Server nicht. |
| `duration` | `interval` | Wie viele Sekunden die Seite auf dem Display bleibt. |
| `time_format` | oberstes `time_format` | `24h` oder `12h`. Mit `12h` zeigt eine Abfahrt in 60 Minuten oder mehr ihre Zeit als `9:10` mit `PM` im grauen Feld, wo sonst `min` steht, und die Plan-Zeit unter der Linie lautet `9:05 PM`. Die Minuten bis zur Abfahrt bleiben, wie sie sind. |

## Einrichtung

1. Öffne [dbf.finalrewind.org](https://dbf.finalrewind.org), suche deinen Bahnhof und kopiere den Namen aus der Adresse.
2. Füge das Beispiel mit deinem `station` in die Liste `pages:` der `config.yaml` ein. Beginne ohne `via` und `platforms` und ergänze sie, sobald die Tafel läuft.
3. Starte den Server neu: `docker compose restart`.
4. Öffne `http://<server>:8080/` und prüfe die Vorschau.

Mehrere Bahnhöfe sind mehrere Seiten, jede mit eigenem `station`.

## Datenschutz & Sicherheit

- Bei jeder Aktualisierung gehen der Bahnhofsname und deine Filter an DBF (oder an die Instanz in `dbf_url`). DBF sieht auch die IP-Adresse deines Servers.
- Die Seite braucht keinen Schlüssel, es gibt also kein Geheimnis zu schützen.
- Auf dem Server wird nichts gespeichert außer dem aktuellen Bild.

## Wenn etwas nicht stimmt

- **„Keine Daten“:** DBF war nicht erreichbar oder kannte den Bahnhof nicht. Die Seite zeigt das sofort statt eines alten Bildes, weil alte Minuten falsch weiterzählen würden. Den Grund findest du in `docker compose logs`. Prüfe den Bahnhofsnamen auf dbf.finalrewind.org.
- **„Keine Abfahrten“:** DBF kennt den Bahnhof, aber nichts passt zu den Filtern. Lockere `via` und `platforms`.
- **Der Server startet nicht und beschwert sich über `refresh`:** Der Wert liegt unter 60. Entferne ihn oder erhöhe ihn.
- **Ein erwarteter Zug fehlt:** Bei `via` zählen nur Züge, die **nach** deinem Bahnhof an diesem Ort halten. Nimm einen Zwischenhalt statt des Endziels.
- **Hinweise für Entwickler:** Code und Layout liegen in `pages/bahn/`.
