# bahn: departure board / Abfahrtstafel

User documentation / Benutzerdokumentation: [docs/en/templates/bahn.md](../../docs/en/templates/bahn.md), [docs/de/templates/bahn.md](../../docs/de/templates/bahn.md). Developer notes below / Entwicklerhinweise unten.

## English

Live departures for a German station from [DBF](https://dbf.finalrewind.org) (db-infoscreen).

```yaml
- type: bahn
  station: "Frankfurt(Main)Hbf"   # required
  via: [Wiesbaden, Mainz]         # optional: only trains calling at these places (string or list)
  platforms: "101,102"            # optional: only these platforms (string or list)
  limit: 4                        # 1-6 rows, default 4 (fewer rows = bigger text)
  title: "Frankfurt"              # header text, default: station
  dbf_url: https://dbf.finalrewind.org
  refresh: 60                     # seconds, minimum 60 (DBF rule)
```

Display: line badge (S green, long distance white/red, RB/RE red), minutes to departure
(yellow at 3 min or less), `+delay` (orange below 6 min, red above), `Gl. X` (orange if the
platform changed), cancelled trains struck through in red. If DBF cannot be reached the page
shows "Keine Daten"; an empty list shows "Keine Abfahrten". The layout is `template.html`.

Times of day follow `time_format` (top level or per page). With `12h` a departure 60 minutes
or more away shows `9:10` with `PM` in the grey unit field where `min` sits, the planned time
in line 2 reads `9:10 PM`, and the header clock and `Stand 7:49 PM` use the same format. The
DBF text `scheduled` goes through `glancebox.timefmt.convert_hhmm`, so text that is not
`HH:MM` is shown unchanged.

This is a deliberate exception to the server's rule that a failing page keeps its last good
picture for up to 10 minutes: old departure minutes would count down wrongly, so the page
reports the failure at once (and logs it) instead of raising an error.

## Deutsch

Live-Abfahrten für einen deutschen Bahnhof von [DBF](https://dbf.finalrewind.org) (db-infoscreen).

```yaml
- type: bahn
  station: "Frankfurt(Main)Hbf"   # Pflicht
  via: [Wiesbaden, Mainz]         # optional: nur Züge mit Halt an diesen Orten (Text oder Liste)
  platforms: "101,102"            # optional: nur diese Gleise (Text oder Liste)
  limit: 4                        # 1-6 Zeilen, Standard 4 (weniger Zeilen = größere Schrift)
  title: "Frankfurt"              # Kopfzeile, Standard: station
  dbf_url: https://dbf.finalrewind.org
  refresh: 60                     # Sekunden, mindestens 60 (DBF-Regel)
```

Anzeige: Linien-Badge (S grün, Fernverkehr weiß/rot, RB/RE rot), Minuten bis Abfahrt (gelb ab
3 Minuten oder weniger), `+Verspätung` (orange unter 6 Min., sonst rot), `Gl. X` (orange bei
Gleiswechsel), ausfallende Züge rot durchgestrichen. Ist DBF nicht erreichbar, zeigt die Seite
„Keine Daten“; eine leere Liste zeigt „Keine Abfahrten“. Das Layout steht in `template.html`.

Uhrzeiten folgen `time_format` (oben oder je Seite). Mit `12h` zeigt eine Abfahrt ab 60 Minuten
`9:10` mit `PM` im grauen Einheiten-Feld, wo sonst `min` steht, die Plan-Abfahrt in Zeile 2
lautet `9:10 PM`, und die Uhr in der Kopfzeile und `Stand 7:49 PM` nutzen dasselbe Format. Der
DBF-Text `scheduled` läuft durch `glancebox.timefmt.convert_hhmm`; Text, der nicht `HH:MM` ist,
erscheint unverändert.

Das ist eine bewusste Ausnahme von der Server-Regel, dass eine fehlerhafte Seite ihr letztes
gutes Bild bis zu 10 Minuten behält: Alte Abfahrtsminuten würden falsch weiterzählen, deshalb
meldet die Seite den Fehler sofort (und schreibt ihn ins Log), statt eine Ausnahme zu werfen.
