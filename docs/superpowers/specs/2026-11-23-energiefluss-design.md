# Energiefluss-Seite mit bewegten Pfeilen: Design

Stand 2026-11-23, Basis: Branch `feat/energy-flow` auf `main` bei 47aceeb (0.6.3).
Ziel-Version: **0.7.0**, Server und Firmware werden gemeinsam veröffentlicht (Entscheidung Nutzer).

Was der Nutzer festgelegt hat, steht unten als **Entscheidung (Nutzer)**. Was ich beim Schreiben
festgelegt habe, steht als **Entscheidung (Fable)**, jeweils mit Grund und mit dem Preis, falls
sie falsch ist. Jede davon lässt sich einzeln zurücknehmen. Messwerte stammen vom Prototyp auf
dem echten Gerät (2026-11-23); alles andere ist als Annahme markiert.

## Absicht

Glance Box soll eine Seite bekommen, auf der man **sieht, wie Energie fließt**: Netz, PV,
Speicher, Gas, Wasser, Wallbox, je eine Zeile mit einem Symbol, einer Linie und Pfeilen, die sich
auf der Linie bewegen. Richtung und Tempo der Pfeile zeigen, wer liefert, wer verbraucht und wie
viel. Worte des Nutzers: eine bewegte Anzeige, auf der man den Energiefluss sieht.

Zielgruppe ist die Home-Assistant-Community. Die Seite soll der Moment sein, in dem jemand das
Display sieht und es haben will: ein klares Unterscheidungsmerkmal gegenüber Displays, die nur
alle paar Sekunden ein Standbild tauschen.

Dafür bekommt das Gerät zum ersten Mal eine eigene Zeichenaufgabe. Bisher gilt „der Server
rendert, das Gerät zeigt“. Das bleibt der Grundsatz; das Gerät zeichnet nur die Pfeile.

## Ziele

1. Neuer Seitentyp `energy` für das 240×240-Display mit 1 bis 4 Zeilen aus einer Liste von
   Zeilentypen: Netz, PV, Speicher, Gas, Wasser, Wallbox.
2. Mehrere Energieseiten in einer Playlist; jede ist ein normaler Eintrag unter `pages:`.
3. Pfeile laufen auf dem Gerät mit etwa 25 Bildern pro Sekunde, auch während das Gerät das
   nächste Bild holt und dekodiert.
4. Eine Regel für alle Zeilen: Pfeile **vom Symbol weg** = das Ding liefert; **zum Symbol hin** =
   es nimmt auf. Wert 0 = keine Pfeile, Zeile grau.
5. Tempo folgt dem Wert; je Zeile einstellbar, bei welchem Wert das volle Tempo erreicht ist.
6. Datenquelle ist Home Assistant, im Add-on ohne Token und im Docker-Betrieb mit URL und Token,
   wie bei der Seite `homeassistant`.
7. Alte Firmware zeigt die Seite als Standbild ohne Pfeile, statt zu scheitern. Alle anderen
   Seiten verhalten sich wie bisher.
8. Doku in Englisch und Deutsch, Vorschaubild im Katalog und in der README-Galerie.

## Nicht-Ziele

- Andere Hardware als die GeekMagic SmallTV Ultra (ESP8266). Die Doku behauptet nichts anderes.
- Weitere Zeilentypen (Wärmepumpe, Hausverbrauch, Strompreis, Tagessummen). Sie folgen erst,
  wenn die erste Fassung gebaut und echt getestet ist. **Entscheidung (Nutzer).**
- Andere Datenquellen als Home Assistant (MQTT, Push-Kanal, Wechselrichter direkt).
- Getrennte Sensoren für Bezug und Einspeisung in einer Zeile. Die erste Fassung erwartet einen
  Sensor mit Vorzeichen je Zeile. **Entscheidung (Fable)**, siehe „Konfiguration“.
- Pfeile in der Vorschau im Browser (Übersichtsseite, Ingress). Dort erscheint das Standbild.
- Eine öffentliche Schnittstelle, mit der eigene Seiten (`custom_pages_dir`) Animationen
  beschreiben. Das Format bleibt in der ersten Fassung intern, damit es sich noch ändern darf.
  **Entscheidung (Fable).**
- Ein Rahmenpuffer oder frei programmierbare Animationen auf dem Gerät. Das Gerät kann genau
  eine Sache: Pfeile auf einer waagerechten Spur.
- Flashen des Displays oder ein Release ohne ausdrückliches Okay des Nutzers.

## Anti-Ziele (wäre ein Misserfolg, auch wenn es technisch läuft)

- Das Display wird unzuverlässiger: Neustarts, Watchdog-Resets, ein Bild, das nicht mehr
  aktualisiert wird, eine Geräteseite oder ein OTA-Update, das wegen der Animation hängt.
- Flackern, sichtbare Kanten um die Spuren oder Pfeilreste auf einer anderen Seite, auf dem
  Offline-Bildschirm oder auf einem Statusbildschirm.
- Eine bestehende Seite sieht nach dem Update anders aus oder wird langsamer.
- Ein Gerät mit alter Firmware zeigt nach dem Server-Update nichts mehr, oder ein Gerät mit
  neuer Firmware kommt mit einem alten Server nicht zurecht.
- Pfeile zeigen in die falsche Richtung, ohne dass der Besitzer das mit einer Option beheben
  kann.
- Pfeile laufen weiter, obwohl die Seite einen Fehler zeigt („Keine Verbindung“).
- Doku oder Posts, die „Echtzeit“ versprechen oder ein Verhalten als geprüft ausgeben, das nur
  gebaut wurde.

## Randbedingungen

- **Protokoll:** Das Gerät holt `GET /api/v1/frame` mit `If-None-Match`; der Server antwortet 200
  mit JPEG oder 304, jeweils mit `ETag`, `X-Next-In` (2 bis 30 s, `schedule.clamp_next_in`) und
  `X-Local-Time`. Der Antwortkopf darf höchstens `gb::kMaxHeadBytes` = 1024 Byte lang sein, sonst
  bricht das Gerät ab (`kErrHeadTooLarge`). Unbekannte Kopfzeilen ignoriert `parseHttpHead`.
- **Gerät:** kein Rahmenpuffer; `display.cpp` schiebt die JPEG-Blöcke aus TJpgDec direkt auf den
  ST7789. `frame_client.cpp` arbeitet blockierend mit rohem `WiFiClient`, `Connection: close`
  und 8 s Frist für Kopf und für Rumpf.
- **Speicher:** Freier Heap im Prototyp etwa 41 kB, in der richtigen Firmware (mit Geräteseite)
  etwa 34 bis 36 kB. Die Animation darf keinen Heap brauchen (feste, statische Strukturen).
  `firmware/size-limit.txt` (1 011 696 Byte) wird nicht angehoben.
- **Reine Logik** gehört nach `firmware/lib/core` mit nativen Unity-Tests
  (`firmware/test/test_core`, `pio test -e native`); `firmware/src` verdrahtet nur.
- **Server:** Seiten sind Ordner mit `page.py` (`fetch`, `validate`, `MIN_REFRESH`) und
  `template.html`; Chromium rendert, `encode_jpeg` senkt die Qualität in Stufen von 85 bis 40,
  bis das Bild in 24 576 Byte passt. `Frame` hält heute nur JPEG, ETag und Zeit.
- **Zwei Sprachen:** Seitentexte `de`/`en`; Doku in `docs/en` und `docs/de` mit gleicher
  Überschriftenfolge (`python3 tools/check_docs_parity.py`, läuft in CI); Nutzersichtbares in
  `CHANGELOG.md` unter `## [Unreleased]`.
- **Keine persönlichen Daten** in Doku und Commits: keine echten LAN-Adressen, Tokens oder
  E-Mail-Adressen; Platzhalter wie `http://192.168.x.x:8090` und `sensor.grid_power`.
- Der `ultra`-Build läuft nicht nativ auf dem Mac (x86-Toolchain); gebaut wird wie bisher.
  Verhalten auf dem Gerät kann nur der Nutzer abnehmen.

## Was der Prototyp gezeigt hat

Wegwerf-Aufbau, nicht im Repo: Test-Firmware holt ein 240×240-Baseline-JPEG (etwa 8,9 kB, PIL,
Qualität 85) von einem kleinen Python-Server im LAN, der das Bild alle 6 s ändert (sonst 304),
`X-Next-In: 2`. Drei Spuren; Pfeile mit `TFT_eSPI::drawLine` (2 px); gelöscht wird, indem das
Spur-Rechteck mit der Hintergrundfarbe gefüllt und die Linie neu gezeichnet wird.

**Gemessen:**

| | v1: Pfeile nur zwischen den Abrufen | v2: Pfeile auch während des Abrufs |
| --- | --- | --- |
| Bildrate | 22 bis 24 fps | gleichmäßig 25 fps |
| 3 Spuren zeichnen | höchstens 5 ms je Bild | wie v1 |
| Abruf mit 304 | etwa 40 bis 140 ms | |
| Abruf mit neuem Bild (200) | im Mittel etwa 470 ms, höchstens 650 ms: Pfeile stehen so lange | Dekodieren hält die Pfeile nicht mehr an |
| Verbleibende Aussetzer | | in 90 s mit etwa 52 Abrufen: 11 Lücken über 100 ms, 5 über 250 ms, längste etwa 900 ms |
| Fehler | | `nerr=2` in diesem Fenster, **ungeklärt** |

v2 arbeitet so: Eine Tick-Funktion wird aus der Leseschleife des Antwortkopfs, aus der
Eingabefunktion von TJpgDec (während sie auf Bytes wartet) und aus der Ausgabefunktion
aufgerufen. Die Ausgabefunktion lässt die Spur-Rechtecke aus, sodass das Dekodieren nie über die
Pfeile malt.

**Urteil des Nutzers:** Bewegung „sehr flüssig, sieht richtig cool aus“; Pfeile sauber, keine
sichtbare Kante zwischen dem gefüllten Spur-Rechteck und dem JPEG-Hintergrund. Das Stocken von
etwa einer halben Sekunde bei v1 stört; er möchte es flüssiger, wenn es geht.

**Zugeordnet, aber nicht einzeln gemessen:** Die verbleibenden Aussetzer in v2 kommen vom
blockierenden `WiFiClient::connect()`. Das ist der einzige Abschnitt des Abrufs ohne Tick; eine
Messung nur dieses Aufrufs gibt es nicht.

**Nicht gemessen:**

- Alles mit der richtigen Firmware (Geräteseite aktiv, weniger Heap, andere Schleife).
- Der Prototyp lief mit `WIFI_NONE_SLEEP`. Die richtige Firmware setzt keinen Schlafmodus;
  Abrufzeiten und Aussetzer können dort anders sein.
- 4 Spuren (nur 3 gemessen).
- Jede Idee gegen die Verbindungs-Aussetzer (siehe „Stufe 2“).
- Kantenfreiheit bei einem von Chromium gerenderten Bild und bei JPEG-Qualität unter 85.

Vorsicht aus dem Prototyp: Eine Rechnung, die vorzeichenlose mit vorzeichenbehafteten Werten
mischte, ließ jedes Bild etwa 500 ms dauern. Die Zahlen oben sind nach dem Beheben gemessen. Für
den Bau heißt das: Die Positionsrechnung gehört nach `lib/core` und bekommt Tests für Linkslauf
und `millis()`-Überlauf.

## Ansätze

| | Ansatz | Bewertung |
| --- | --- | --- |
| **A** ✅ | Server rendert weiter das Standbild als JPEG (Symbole, Werte, Beschriftung, **leere** Spuren auf einfarbigem Grund) und schickt dazu eine kleine maschinenlesbare Beschreibung der Spuren (Rechteck, Richtung, Tempo, Farbe). Die Firmware zeichnet nur die Pfeile. | Flüssig (25 fps gemessen), Aussehen bleibt beim Server, kleine und prüfbare Firmware-Aufgabe, alte Firmware zeigt ein brauchbares Standbild. Kosten: erste Zeichenlogik auf dem Gerät, eine neue Kopfzeile, Eingriff in den Abruf. **Gewählt vom Nutzer.** |
| B | Nur der Server: schnelle Bildfolge. | `X-Next-In` ist auf 2 bis 30 s begrenzt; selbst mit geändertem Protokoll kostet ein neues Bild etwa 470 ms. Höchstens etwa 1 Bild pro Sekunde, ruckelig. Verworfen. |
| C | Die Firmware zeichnet die ganze Seite. | Braucht Schriften und Symbole auf dem Gerät; jede optische Änderung braucht ein Flashen; gibt „der Server rendert, das Gerät zeigt“ auf. Verworfen. |

## Aussehen und Verhalten

**Entscheidung (Nutzer):** Aufbau wie im Mockup des Prototyps.

- Kleine Kopfzeile: Seitentitel links, Uhrzeit rechts.
- Je Zeile: Symbol im Kreis links, waagerechte Spur mit Pfeilen, Wert und Einheit rechtsbündig,
  darunter eine kleine Statuszeile (z. B. „Einspeisung“, „lädt · 64 %“).
- Maße bei 3 Zeilen: Zeilenmitten bei y = 74, 140, 206; Kreis bei x = 34, r = 22; Spur von
  x = 64 bis 148, 3 px dick; Pfeile im Abstand von 18 px, etwa 10 px hoch, 2 px Strich; Wert fett
  etwa 24 px, rechtsbündig bei x = 226.
- Farben: Hintergrund `#0b0d12`, Spur `#232a38`, Netzbezug Orange `#ffb020`, Einspeisung Grün
  `#34d399`, PV Gelb `#ffd040`, Speicher `#2ec4b6`, Gas `#ff6b4a`, Wasser `#4da3ff`. Inaktiv:
  grau, Spur ohne Pfeile.
- Höchstens 4 Zeilen je Seite; 3 sahen im Mockup am besten aus.

Der Hintergrund weicht vom Standard der anderen Seiten ab (`base.html`: `#080a0e`); die Seite
setzt ihren eigenen. **Entscheidung (Claude):** Wallbox Violett `#a78bfa`, hebt sich von Netz, PV und
Speicher ab. **Kosten, falls falsch:** eine Farbkonstante.

### Pfeilregel

**Entscheidung (Nutzer):** eine Regel für alle Zeilen. Das Symbol steht links, also heißt „weg“
nach rechts und „hin“ nach links.

| Zeilentyp | Zustand | Pfeile | Farbe | Statuszeile de / en |
| --- | --- | --- | --- | --- |
| `grid` (Netz) | Bezug | weg (rechts) | Orange | Bezug / Import |
| | Einspeisung | hin (links) | Grün | Einspeisung / Export |
| `pv` | erzeugt | weg | Gelb | Erzeugung / Producing |
| `battery` (Speicher) | lädt | hin | Speicherfarbe | lädt · 64 % / charging · 64 % |
| | entlädt | weg | Speicherfarbe | entlädt · 64 % / discharging · 64 % |
| `gas` | Verbrauch | weg | Gasfarbe | Verbrauch / Usage |
| `water` (Wasser) | Verbrauch | weg | Wasserfarbe | Verbrauch / Usage |
| `wallbox` | lädt | hin | Violett `#a78bfa` | lädt / charging |
| jeder | Wert 0 | keine | grau | leer; beim Speicher nur der Ladestand |

Die Wortlaute der Statuszeile sind ein Vorschlag (**Fable**); der Umsetzer darf sie anpassen,
solange beide Sprachen dieselbe Aussage haben.

### Wert, Tempo, Vorzeichen

- **Entscheidung (Nutzer):** Tempo proportional zum Wert; je Zeile einstellbar, bei welchem Wert
  das volle Tempo erreicht ist, mit sinnvollen Standardwerten. Je Zeile eine Option `invert`,
  weil Zähler Vorzeichen unterschiedlich melden.
- **Entscheidung (Fable):** Der Wert wird ohne Vorzeichen angezeigt. Richtung, Farbe und
  Statuszeile sagen, wohin es fließt. **Grund:** „−1,1 kW“ neben einem Pfeil nach links sagt
  dasselbe zweimal und kostet Breite. **Kosten, falls falsch:** eine Zeile im Format.
- **Entscheidung (Fable):** „Wert 0“ heißt: der **angezeigte**, gerundete Wert ist 0. Dazu je
  Zeile eine Option `min` (Standard 0): Beträge darunter gelten als 0. **Grund:** Wechselrichter
  melden nachts oft wenige Watt; ohne Schwelle kriechen dann Pfeile. **Kosten, falls falsch:**
  eine Option, die niemand braucht.
- **Entscheidung (Fable):** Zeilentypen mit nur einer Richtung (`pv`, `gas`, `water`, `wallbox`)
  behandeln Werte mit dem falschen Vorzeichen als 0. **Grund:** Eine PV-Anlage „verbraucht“ auf
  dieser Seite nichts. **Kosten, falls falsch:** Ein falsch herum gemeldeter Sensor zeigt 0 statt
  eines Werts; die Doku nennt `invert` als erste Abhilfe.
- **Entscheidung (Fable):** Tempo = Mindesttempo + (Höchsttempo − Mindesttempo) ·
  min(1, Betrag / `full`), in Pixel pro Sekunde. Jeder Wert über 0 bewegt sich sichtbar.
  Vorschlag: 10 bis 80 px/s; die endgültigen Zahlen stellt der Umsetzer am echten Gerät mit dem
  Nutzer ein. **Grund:** Rein proportional stünde eine Spur bei kleinem Wert scheinbar still,
  obwohl sie farbig ist. **Kosten, falls falsch:** zwei Konstanten in `page.py`.
- Formatierung wie auf der Seite `homeassistant`: W und Wh ab 1000 als kW und kWh, Komma bei
  `de`, Einheit aus `unit_of_measurement`. `unavailable`/`unknown` zeigt „n. v.“ / „n/a“, eine
  unbekannte Entität „fehlt“ / „missing“; die Zeile ist dann inaktiv.

Vorzeichen vor `invert` und Standard für `full` (**Entscheidung (Fable)**, alles Vorschläge):

| Typ | positiver Wert heißt | `full` Standard | Bemerkung |
| --- | --- | --- | --- |
| `grid` | Bezug | 5000 W | |
| `pv` | Erzeugung | 5000 W | |
| `battery` | **entlädt** | 3000 W | beim Bau geprüft (2026-11-23): HA-Energie-Dashboard sagt „positive values indicate discharging“ (Frontend-Text); negativ = lädt |
| `wallbox` | lädt | 11000 W | |
| `gas` | Verbrauch | 2 (in der Einheit des Sensors) | geraten für m³/h |
| `water` | Verbrauch | 15 (in der Einheit des Sensors) | geraten für L/min |

Leistung wird vor dem Vergleich auf W umgerechnet (kW × 1000). Bei Gas und Wasser gibt es keine
übliche Einheit; `full` gilt dort in der Einheit, die der Sensor meldet, und die Doku rät, den
Wert selbst zu setzen. **Kosten, falls ein Standard falsch ist:** Pfeile zu schnell oder zu
langsam, bis der Besitzer `full` setzt.

### Ehrliche Hinweise für die Doku

- Leistung kommt meist etwa jede Sekunde. **Gas- und Wasserzähler melden oft nur Impulse oder
  alle paar Minuten**; ihre Pfeile reagieren entsprechend spät.
- Die Seite braucht einen Sensor für den **Durchfluss oder die Leistung**, nicht den Zählerstand.
  Wer nur einen Zählerstand hat, baut in Home Assistant einen Ableitungs-Helfer.
- Der Weg vom Sensor zum Display dauert mehrere Sekunden (Abfrage, Rendern, Abruf des Geräts).
  Die Pfeile zeigen Richtung und Größenordnung, kein Oszilloskop. Das Wort „Echtzeit“ kommt in
  Doku und Posts nicht vor.
- Pfeile brauchen die neue Firmware; mit älterer Firmware erscheint die Seite als Standbild.

## Konfiguration

**Entscheidung (Nutzer):** Zeilen frei wählbar aus den Zeilentypen, mehrere Energieseiten
möglich, Sensoren als Entitäts-IDs, Home Assistant als einzige Quelle.

**Entscheidung (Fable):** Seitentyp `energy`, Ordner `pages/energy/`; in der deutschen Doku
heißt die Seite „Energiefluss“. Form:

```yaml
pages:
  - type: energy
    title: Strom
    # animate: false        # nur Standbild, keine Pfeile
    # url: ${HA_URL}          # im Add-on weglassen
    # token: ${HA_TOKEN}      # im Add-on weglassen
    # lang: de
    refresh: 5
    rows:
      - type: grid
        entity: sensor.grid_power
        # invert: true        # wenn dein Zähler Einspeisung positiv meldet
        # full: 5000          # Wert für volles Tempo
        # min: 20             # darunter gilt die Zeile als 0
      - type: pv
        entity: sensor.pv_power
      - type: battery
        entity: sensor.battery_power
        soc: sensor.battery_level   # optional, Ladestand in %

  - type: energy
    title: Haus
    refresh: 5
    rows:
      - type: gas
        entity: sensor.gas_flow
      - type: water
        entity: sensor.water_flow
      - type: wallbox
        entity: sensor.wallbox_power
```

Das zweite Beispiel ist der vom Nutzer geplante Aufbau: Seite 1 „Strom“ mit Netz, PV, Speicher;
Seite 2 mit Gas, Wasser, Wallbox.

Prüfung in `validate` (Fehler stoppt den Serverstart mit Seitennummer, wie bei den anderen
Seiten):

- `url`, `token`, `lang`, `title` wie bei `homeassistant`.
- `rows`: Liste mit 1 bis 4 Einträgen; `type` aus der Liste oben; `entity` Pflicht und in der
  Form `domain.name`; `soc` nur bei `battery`; `invert` boolesch; `full` Zahl über 0; `min` Zahl
  ab 0. Unbekannte Schlüssel in einer Zeile sind ein Fehler (Tippfehler wie `inverted` fallen
  auf). Derselbe Typ darf mehrfach vorkommen (zwei PV-Anlagen).

**Entscheidung (Fable):** Ohne `refresh` gilt für diese Seite 5 s, kleinster Wert 2 s.
**Grund:** Heute ist der Standard für `refresh` die Anzeigedauer (30 s); eine Energieseite mit
30 s alten Werten wirkt kaputt, und das soll niemand erst in der Doku nachlesen müssen. Braucht
einen kleinen neuen Haken im Seitentyp (z. B. `DEFAULT_REFRESH` neben `MIN_REFRESH`).
**Kosten, falls falsch:** Der Server rendert die Seite alle 5 s, auch wenn sie gerade nicht
gezeigt wird (so arbeitet der Worker heute bei allen Seiten). Auf schwacher Hardware kostet das
Rechenzeit; siehe „Offene Punkte“.

**Entscheidung (Fable):** Ein Sensor mit Vorzeichen je Zeile; getrennte Sensoren für Bezug und
Einspeisung kommen nicht in die erste Fassung. **Grund:** hält Konfiguration und Prüfung klein;
der Nutzer will erst eine echte Erprobung. **Kosten, falls falsch:** Wer getrennte Sensoren hat,
braucht bis dahin einen Template-Sensor in HA. Das ist vermutlich der erste Wunsch aus der
Community und lässt sich ohne Umbau ergänzen.

**Add-on:** Kein neues Formularfeld; die Playlist bleibt YAML. `addon.ha_defaults` setzt heute
`url` und `token` nur für `type: homeassistant`, wenn beide fehlen; `energy` kommt dort dazu.

## Die Animationsbeschreibung

### Transport

- **A (gewählt): Kopfzeile `X-Anim` an der Antwort von `/api/v1/frame`.** Kommt im selben
  Abruf an, bevor der Rumpf beginnt; das Gerät kennt die Spuren also vor dem Dekodieren.
- B: eigener Endpunkt. Ein zweiter Abruf je Bild, also ein zweites `connect()`, und genau das
  ist die gemessene Ursache der Aussetzer. Dazu zwei Antworten, die zueinander passen müssen.
- C: JPEG-Kommentar. Fehlt bei 304, das Tempo könnte sich dann nur mit einem neuen Bild ändern;
  und TJpgDec gibt Kommentare nicht heraus, es bräuchte einen eigenen Vorab-Parser im Datenstrom.

**Entscheidung (Fable):** Weg A. **Kosten, falls falsch:** Die Beschreibung muss in den
1024-Byte-Kopf passen; das begrenzt sie auf wenige Spuren (hier gewollt).

### Format

```
X-Anim: 1;0b0d12;232a38;64,67,85,14,r,ffb020,48;64,133,85,14,l,34d399,22
```

`Version;Hintergrund;Spurfarbe` und danach 1 bis 4 Spuren `x,y,b,h,Richtung,Farbe,Tempo`:

| Feld | Bedeutung | Grenzen (das Gerät prüft sie) |
| --- | --- | --- |
| Version | `1` | jede andere Version: Kopfzeile gilt als nicht vorhanden |
| Hintergrund, Spurfarbe, Farbe | RGB, genau 6 Hex-Ziffern | |
| `x,y,b,h` | Spur-Rechteck in Pixeln | ganz innerhalb 240×240; Mindest- und Höchstmaße legt der Umsetzer fest (Richtwert b 16 bis 240, h 8 bis 32); Rechtecke überlappen nicht |
| Richtung | `r` oder `l` | |
| Tempo | Pixel pro Sekunde | 1 bis 200 |
| gesamt | | höchstens 4 Spuren, Wert höchstens 160 Zeichen, keine Leerzeichen |

Eine inaktive Zeile hat **keine** Spur in der Beschreibung; ihr graues Standbild steckt im JPEG.
Eine Seite ohne aktive Zeile, eine Fehlerseite und jede andere Seite senden kein `X-Anim`.

**Entscheidung (Fable):** Die Spurlinie (3 px, mittig im Rechteck) und die Pfeilform (Abstand
18 px, Höhe 10 px, Strich 2 px) sind Konstanten der Firmware; Position, Farben, Richtung und
Tempo kommen vom Server. **Grund:** kurze Kopfzeile, wenig Angriffsfläche. **Kosten, falls
falsch:** Eine andere Pfeilform braucht ein Firmware-Update; die Versionsnummer erlaubt später
ein reicheres Format.

**Entscheidung (Fable):** Richtung als Bildschirmrichtung (`r`/`l`), nicht als „weg/hin“.
**Grund:** Was „weg“ heißt, hängt davon ab, wo das Symbol steht, und das weiß nur der Server.

### 200, 304 und der ETag

Durchdacht an der Frage: Was passiert, wenn sich nur das Tempo ändert?

- Das Tempo kommt aus dem ungerundeten Wert, das Bild zeigt den gerundeten. 2,31 kW und 2,33 kW
  ergeben dasselbe Bild („2,3 kW“), aber leicht verschiedenes Tempo. Bild und Beschreibung
  ändern sich also **nicht** immer gemeinsam.
- **Entscheidung (Fable):** `X-Anim` steht an **jeder** Antwort für das Bild, auch an 304. Das
  Gerät übernimmt Tempo, Richtung und Farbe aus der jeweils letzten erfolgreichen Antwort. Der
  ETag bleibt der Hash des JPEG allein. **Grund:** Eine reine Tempoänderung kostet dann einen
  304 (gemessen 40 bis 140 ms) statt eines neuen Bilds. **Kosten, falls falsch:** Alternative
  wäre, die Beschreibung in den ETag einzurechnen; dann löst jede Tempoänderung ein neues Bild
  aus.
- Ändert sich die **Geometrie** (Zahl oder Lage der Spuren, Hintergrund, Spurfarbe), ändert sich
  immer auch das Bild, weil beides aus denselben Zahlen entsteht; das kommt also mit 200.
- Das Gerät verlässt sich darauf nicht (die Kopfzeile ist ungeprüfte Eingabe): Passt bei einem
  304 die Geometrie nicht zu den laufenden Spuren, oder fehlt `X-Anim`, obwohl Spuren laufen,
  hält es die Animation an, verwirft seinen ETag und holt beim nächsten Abruf das Bild neu.

### Verträglichkeit

| Firmware | Server | Ergebnis |
| --- | --- | --- |
| alt | neu | `X-Anim` wird ignoriert; die Energieseite ist ein Standbild mit leeren Spuren. Wert, Farbe und Statuszeile („Einspeisung“) bleiben lesbar. |
| neu | alt | keine Kopfzeile, keine Animation; alles wie heute. |
| neu | neu, andere Seiten | keine Kopfzeile, keine Animation; alles wie heute. |

Keine Protokollversion, keine Abfrage von `fw=`. Die Doku nennt die Firmware-Version, ab der
Pfeile laufen.

## Server

- **Eine Quelle für die Maße.** `page.py` rechnet die Lage der Zeilen und Spuren aus (für 1 bis 4
  Zeilen) und gibt sie dem Template; das Template setzt die Elemente absolut nach diesen Zahlen.
  Die Beschreibung entsteht aus denselben Zahlen. Es gibt keine zweite Tabelle, die mit dem CSS
  mitgepflegt werden muss.
- **Wie die Beschreibung zum Gerät kommt.** Der Seitentyp liefert sie zusammen mit seinen Daten
  (z. B. reservierter Schlüssel im Ergebnis von `fetch` oder eigene Funktion; Umsetzer).
  `Frame` bekommt ein Feld dafür; `jpeg_response` in `app.py` hängt `X-Anim` an 200 und 304.
  Der Server prüft die Beschreibung mit denselben Grenzen wie das Gerät, bevor er sie sendet;
  verletzt sie eine, sendet er keine und schreibt es ins Log.
- **Einfarbiger Grund unter den Spuren.** Im Spur-Rechteck zeichnet das Template nur die
  Hintergrundfarbe und die Spurlinie in genau den Maßen und Farben, die auch die Firmware
  benutzt: kein Verlauf, kein Schatten, keine Rundung. Symbolkreis und Wert halten Abstand zum
  Rechteck; der Wert bekommt eine Größenwahl wie bei `homeassistant` (`size_class`), damit er
  nie in die Spur ragt.
- **Entscheidung (Fable):** Ein Test rendert die Seite, dekodiert das fertige JPEG und prüft,
  dass im Spur-Rechteck und in einem schmalen Rand darum nur Hintergrund und Spurlinie liegen
  (mit kleiner Toleranz für JPEG-Rauschen). **Grund:** Das ist die Zusage, auf der „keine
  sichtbare Kante“ steht, und sie bricht leise, wenn jemand das CSS ändert. **Kosten, falls
  falsch:** ein Browser-Test mehr (`-m browser`).
- **Entscheidung (Fable):** Die Energieseite muss mit Qualität 85 in die 24 576 Byte passen;
  fällt `encode_jpeg` für sie auf eine niedrigere Stufe, ist das ein Testfehler. **Grund:** Nur
  Qualität 85 ist auf Kantenfreiheit geprüft; das Prototyp-Bild hatte 8,9 kB. **Kosten, falls
  falsch:** keine erkennbaren.
- **Fehlerzustände** wie bei `homeassistant`: Token abgelehnt und „Keine Verbindung“ als Hinweis
  mit Uhrzeit, ohne alte Werte und **ohne** `X-Anim`.
- **Gemeinsamer Code mit `homeassistant`** (Abruf von `/api/states/<id>`, Fehlerzuordnung,
  Zahlenformat, Protokollieren ohne Token): nicht kopieren, sondern teilen; wo er liegt,
  entscheidet der Umsetzer. Die Seite `homeassistant` darf sich dabei nicht sichtbar ändern.
- **Weniger neue Bilder.** Der ETag ist der Hash des JPEG; ein gleiches Bild ergibt 304. Ob
  Chromium und der Encoder für gleiche Daten Byte für Byte dasselbe JPEG liefern, ist **nicht
  geprüft**. Sicher ist: Die Uhr in der Kopfzeile ändert das Bild mindestens einmal pro Minute.
  **Entscheidung (Fable):** Liefert `fetch` dieselben Vorlagendaten wie beim letzten Mal, rendert
  der Server die Energieseite nicht neu, sondern behält das Bild (und aktualisiert nur die
  Beschreibung). **Grund:** macht 304 vom Zufall des Encoders unabhängig und spart Chromium-Läufe
  alle 5 s. **Kosten, falls falsch:** ein Vergleich im Worker; ob er für alle Seiten oder nur für
  diese gilt, entscheidet der Umsetzer.

## Firmware

### Aufteilung

Reine Logik in `firmware/lib/core` (neues Modul, z. B. `anim`), nativ getestet:

1. **Parser** für den Wert von `X-Anim` in eine feste Struktur (höchstens 4 Spuren, keine
   dynamische Speicheranforderung). Jeder Verstoß gegen eine Grenze verwirft die **ganze**
   Beschreibung; es wird nie ein Teil übernommen. `parseHttpHead` füllt die Struktur; eine
   doppelte `X-Anim`-Zeile gilt als ungültig.
2. **Position der Pfeile** aus Zeit, Tempo und Richtung, sicher gegen `millis()`-Überlauf, ohne
   Sprung bei einer Tempoänderung.
3. **Ausschneiden**: ein JPEG-Block minus die geschützten Rechtecke ergibt die Teilrechtecke,
   die noch gezeichnet werden.
4. **Zustand**: Was geschieht mit den Spuren bei 200, 304, Fehler, Statusbildschirm (Regeln
   unten).

In `firmware/src` nur das Zeichnen (`display.cpp`) und die Aufrufe des Ticks (`main.cpp`,
`frame_client.cpp`).

### Tick

Der Tick zeichnet höchstens alle 40 ms ein Bild der laufenden Spuren und kehrt sonst sofort
zurück. Er wird aufgerufen aus `loop()`, aus der Leseschleife des Antwortkopfs, aus der
Eingabefunktion von TJpgDec, während sie auf Bytes wartet, und aus der Ausgabefunktion
(wie im Prototyp v2). Er zeichnet nur; er ruft weder Netz- noch Webserver-Code auf und
verlängert keine Frist.

### Regeln für die Spuren

Die Spuren gehören zu dem Bild, das gerade vollständig auf dem Bildschirm steht.

| Ereignis | Verhalten |
| --- | --- |
| 200, Spur mit gleichem Rechteck läuft schon | läuft während des Dekodierens weiter; die Ausgabefunktion lässt ihr Rechteck aus; neue Werte für Tempo, Richtung, Farbe gelten sofort |
| 200, Spur ist neu (anderes Rechteck, Seitenwechsel) | startet erst, **nachdem** das Bild fertig dekodiert ist; bis dahin kein Ausschneiden |
| 200, eine laufende Spur fehlt in der neuen Beschreibung | hält vor dem Dekodieren an; das Bild malt über ihre Pfeile |
| 200 ohne `X-Anim` oder mit ungültigem | alle Spuren halten vor dem Dekodieren an; das Bild wird ganz gezeichnet |
| 304, gleiche Geometrie | Tempo, Richtung, Farbe übernehmen |
| 304, andere Geometrie oder kein `X-Anim`, obwohl Spuren laufen | anhalten, ETag verwerfen, neu holen |
| Dekodieren bricht ab (Teilbild) | alle Spuren halten an; der ETag wird wie heute verworfen |
| Abruf scheitert, Bild steht noch | Spuren laufen weiter, solange das Bild steht |
| Offline-Bildschirm oder ein anderer Statusbildschirm (`displayStatus`: Start, Portal, „Firmware update“, „Update OK“, „Update failed“) | alle Spuren halten an; erst ein vollständig dekodiertes neues Bild darf wieder welche starten |
| Hintergrundbeleuchtung 0 % (Nachtmodus) | es wird nicht gezeichnet; der Zustand bleibt erhalten |

**Entscheidung (Fable):** Neue Spuren starten erst nach dem Dekodieren. **Grund:** Sonst liefen
beim Seitenwechsel etwa eine halbe Sekunde lang die Pfeile der neuen Seite über die Reste der
alten. **Kosten, falls falsch:** Beim Seitenwechsel erscheinen die Pfeile einen Augenblick nach
dem Bild.

**Entscheidung (Fable):** Das Anhalten sitzt in `displayStatus` selbst und am Beginn des
Dekodierens, nicht an den einzelnen Aufrufern. Ein 304 darf nie Spuren starten, nur laufende
ändern. **Grund:** So kann kein heutiger oder künftiger Statusbildschirm vergessen werden; ein
OTA-Update zeichnet seinen Bildschirm aus der Geräteseite heraus, weit weg vom Abruf.
**Kosten, falls falsch:** keine erkennbaren.

**Entscheidung (Fable):** Scheitert ein Abruf, laufen die Pfeile weiter, bis der
Offline-Bildschirm kommt (heute nach 120 s ohne Erfolg). **Grund:** Der Wert daneben ist genauso
alt und bleibt auch stehen; stehende Pfeile mitten auf der Spur sähen nach einem Hänger des
Geräts aus. **Kosten, falls falsch:** Bis zu 2 Minuten lang wirkt die Seite lebendiger, als die
Daten sind. Rückweg: eine Zeile in der Zustandslogik (anhalten nach n Fehlversuchen).

### Speicher und Zeit

- Zustand der Animation: statisch, höchstens 4 Spuren, kein Heap. Der Kopfpuffer (1024 Byte,
  statisch) reicht unverändert.
- Zeichnen von 3 Spuren kostet gemessen höchstens 5 ms je Bild, also etwa ein Achtel der Zeit
  bei 25 fps. Für 4 Spuren und für die Geräteseite unter dieser Last gibt es keine Messung;
  beides gehört in den Gerätetest.
- Der freie Heap der richtigen Firmware (34 bis 36 kB) darf durch die erste Stufe nicht
  merklich sinken; `heap_free` der Geräteseite vor und nach vergleichen.

### Stufe 1 und Stufe 2

**Stufe 1 (Umfang von 0.7.0, Entscheidung Nutzer):** alles oben, also der Stand des Prototyps v2 in der
richtigen Firmware. Gemessen bleibt dabei ein gelegentliches Stocken beim Verbindungsaufbau.

**Stufe 2 (nicht Teil von 0.7.0; erst im echten Betrieb messen, dann entscheiden):** die Aussetzer durch `connect()` verringern. Keine
der Ideen ist gemessen:

- **Verbindung wiederverwenden** (Keep-Alive statt `Connection: close`). Zu klären: Der
  Server-Prozess (uvicorn) schließt ruhende Verbindungen nach einer Frist, die kürzer sein kann
  als der Abstand der Abrufe; ein Abruf auf einer inzwischen geschlossenen Verbindung muss ohne
  Fehlerzählung einmal neu verbinden; eine dauerhaft offene Verbindung kostet Heap und einen der
  wenigen TCP-Plätze, die auch die Geräteseite braucht.
- **Nicht blockierender Verbindungsaufbau**, bei dem der Tick weiterläuft.
- **`WIFI_NONE_SLEEP`** wie im Prototyp: mehr Stromaufnahme und Wärme, unbekannter Nutzen.
- **Seltener abrufen:** Mit `refresh: 5` fragt das Gerät etwa alle 5 s statt alle 2 s wie im
  Prototyp; die Zahl der Aussetzer pro Minute sinkt damit vermutlich von selbst.

**Entscheidung (Nutzer):** 0.7.0 erscheint mit Stufe 1. Im echten Betrieb wird gemessen; Stufe 2
ist eine spätere, eigene Arbeit. **Entscheidung (Claude):** Messgröße sind die Lücken über 250 ms
je Minute bei `refresh: 5` (dazu die über 100 ms zur Information). Mehr als eine Lücke über 250 ms
je Minute im Mittel ist der Anlass, Stufe 2 anzugehen; kein Hindernis für 0.7.0. Die Firmware
zählt die Lücken dafür und zeigt sie in `/status` (Name dem Umsetzer überlassen). **Grund:** Der Umbau
des Abrufs berührt die Zuverlässigkeit aller Seiten; das rechtfertigt nur ein gemessener Nutzen.
**Kosten, falls falsch:** eine Messrunde mehr vor dem Umbau.

Das ungeklärte `nerr=2` wird in Stufe 1 mitbeobachtet: Die Fehlerzahl je Stunde mit Animation
wird mit der ohne Animation verglichen (Dauertest). **Entscheidung (Claude):** Der Vergleich läuft
auf derselben Firmware; die Seite bekommt dafür die Option `animate: false` (Standard `true`),
dann schickt der Server kein `X-Anim` und das Gerät zeigt nur das Standbild. Die Option ist auch
für Nutzer nützlich, die keine Bewegung wollen, und wird dokumentiert.

## Tests und Abnahme

| Was | Wie |
| --- | --- |
| Parser, Positionsrechnung, Ausschneiden, Zustandsregeln | native Unity-Tests in `firmware/test/test_core`: gültige und ungültige Beschreibungen (zu viele Spuren, Rechteck außerhalb, Überlappung, Tempo 0 und zu hoch, falsche Version, zu lang, doppelte Kopfzeile), Linkslauf, `millis()`-Überlauf, jede Zeile der Regeltabelle |
| Größe der Firmware | `tools/check_fw_size.py` wie bisher |
| `validate`, Pfeilregel, Tempo, Vorzeichen, `invert`, `min`, Texte de/en, Fehlerzustände | Tests neben der Seite (`pages/energy/test_energy.py`), HA-Antworten gemockt |
| `X-Anim` an 200 und 304, fehlt bei anderen Seiten und Fehlerseiten, Antwortkopf bleibt unter 1024 Byte | `server/tests/test_app.py` |
| Gleiche Grenzen auf Server und Gerät | Paritätstest wie `test_frame_limit_parity.py` |
| Einfarbiger Grund unter den Spuren, Qualität 85 | Browser-Test (siehe „Server“) |
| Add-on setzt `url`/`token` für `energy` | `server/tests/test_addon.py` |
| Doku gleich in beiden Sprachen | `tools/check_docs_parity.py` |
| Gegen ein Home Assistant | Test-VM des Nutzers (HA OS, Add-on installiert) mit Schein-Sensoren; oder `tools/ha-sim/` |
| Auf dem Gerät | Firmware per OTA über `/update` der Geräteseite mit Update-Passwort, **erst nach Okay des Nutzers** |
| Dauerlauf | 24 h mit einer Energieseite in der Playlist |

**Schein-Sensoren.** In der Test-VM am besten Eingabe-Helfer (`input_number`) mit je einem
Template-Sensor (`device_class: power`, Einheit W) für Netz, PV, Speicher, Ladestand, Gas,
Wasser, Wallbox: So lassen sich Vorzeichenwechsel, 0 und Sprünge von Hand auslösen. `tools/ha-sim/`
(simuliertes HA in Docker) hat schon `sensor.netz` (mit Vorzeichen), `sensor.pv_leistung` und
`sensor.speicher` (%), aber keine Speicherleistung, kein Gas, Wasser oder Wallbox, und seine
Werte ändern sich nur einmal pro Minute. Es taugt für den Abruf und die Darstellung; für die
Pfeilregel müsste es um steuerbare Sensoren erweitert werden (dem Umsetzer überlassen).

**Abnahme auf dem Gerät (nur der Nutzer kann sie erteilen):**

1. Beide geplanten Seiten (Strom; Gas, Wasser, Wallbox) laufen in der Playlist neben
   bestehenden Seiten.
2. Jede Zeile der Pfeilregel einmal gesehen: Bezug, Einspeisung, PV, Speicher lädt und entlädt,
   Wallbox, Gas, Wasser, Wert 0.
3. Keine Kante um die Spuren, keine Pfeilreste nach dem Seitenwechsel, auf dem
   Offline-Bildschirm (Server stoppen) und beim OTA-Bildschirm.
4. Nachtmodus mit Helligkeit 0 und zurück.
5. Geräteseite bedienbar und OTA möglich, während eine Energieseite läuft.
6. Dauerlauf 24 h: keine Neustarts, `heap_free` stabil, Fehlerzahl nicht höher als ohne
   Animation (Vergleichslauf mit `animate: false`, gleiche Firmware, gleicher `refresh`).

Vor der Abnahme sagen Doku, CHANGELOG und Posts nichts über „getestet“.

## Doku und Bilder

- `docs/en/templates/energy.md` und `docs/de/templates/energy.md` nach dem Muster von
  `homeassistant.md` (was sie zeigt, was man braucht, Beispiel, Optionen, Einrichtung, Wenn
  etwas nicht stimmt), mit den ehrlichen Hinweisen von oben und der nötigen Firmware-Version.
- Eintrag im Katalog (`templates/README.md`, beide Sprachen), in `mkdocs.yml`, ein Verweis in
  `home-assistant.md`, Kachel in der Galerie von `README.md` und `README.de.md`,
  `pages/energy/README.md` mit Entwicklerhinweisen, `CHANGELOG.md`.
- **Entscheidung (Fable):** Das Vorschaubild für Katalog und Galerie entsteht in
  `tools/render_previews.py` aus dem Standbild, auf das die Pfeile nach der Beschreibung als
  feste Pfeile gemalt werden. **Grund:** Das Standbild allein zeigt leere Spuren und damit
  gerade nicht, was die Seite ausmacht. **Kosten, falls falsch:** ein paar Zeilen Pillow.
- Ein kurzer Film oder ein GIF vom echten Gerät wäre für die Zielgruppe das stärkste Bild; das
  kann nur der Nutzer aufnehmen (siehe Fragen).

## Offene Punkte zum Prüfen beim Bau

1. Liefert der Server für gleiche Daten Byte für Byte dasselbe JPEG? (Sonst trägt allein die
   Regel „gleiche Daten, kein neues Rendern“.)
2. Kantenfreiheit mit einem Chromium-Bild auf dem Gerät. JPEG arbeitet in Blöcken; Farbe des
   Symbolkreises und des Werts kann in Nachbarpixel streuen. Falls sichtbar: mehr Abstand, oder
   das Rechteck am Blockraster ausrichten.
3. Abrufzeiten und Aussetzer in der richtigen Firmware ohne `WIFI_NONE_SLEEP`.
4. Zeichenzeit und Aussehen mit 4 Zeilen (Zeilenabstand etwa 50 px bei Kreisen mit 44 px).
5. Rechenlast des Servers bei `refresh: 5` auf kleiner Hardware (Raspberry Pi mit HA OS;
   dort ist das Add-on bisher nicht erprobt).
6. Ursache von `nerr=2`.
7. ~~Vorzeichen-Konvention für Speicherleistung in der HA-Doku.~~ Geklärt beim Bau: positiv = entlädt (siehe Tabelle „Wert, Tempo, Vorzeichen“).

## Beobachtungen außerhalb des Auftrags

- Nach dem Statusbildschirm „Update failed“ behält `main.cpp` seinen ETag. Antwortet der Server
  danach mit 304, bleibt der Statusbildschirm stehen, bis sich das Bild ändert. Durch Lesen
  gefunden, nicht am Gerät geprüft. Die Regel „Statusbildschirm hält die Spuren an“ macht die
  Animation davon unabhängig; das Stehenbleiben selbst behebt sie nicht.
- Das Gerät fragt genau dann wieder, wenn der Server mit dem Rendern beginnt
  (`until_refresh`), und bekommt deshalb oft noch das alte Bild. Ein neuer Wert kann so bis zu
  zwei Abrufabstände alt sein. Bei 30 s fiel das nicht auf; bei 5 s lohnt ein Blick.
  **Entscheidung (Claude):** nicht Teil dieser Arbeit, weil es die Zeitplanung aller Seiten
  ändert (Anti-Ziel „eine bestehende Seite wird langsamer“).

## Dem Umsetzer überlassen

- Namen der Module, Funktionen und Strukturen in Firmware und Server; wie der Seitentyp die
  Beschreibung an den Worker übergibt; Name des Hakens für den Standard-`refresh`.
- Lage der Zeilen bei 1, 2 und 4 Zeilen; genaue Größe des Spur-Rechtecks um die Linie. Die Kopfzeile
  ist die kleinere aus dem Mockup (Titel links, Uhrzeit rechts), die der Nutzer gesehen und
  gutgeheißen hat.
- Symbole (eigene SVG im Template; bei übernommenen Symbolen die Lizenz beachten).
- Mindest- und Höchsttempo, Standard für `full`, Wortlaut der Statuszeilen: Vorschläge stehen oben, eingestellt wird am Gerät.
- Wie das Ausschneiden die Teilblöcke auf den Bildschirm schiebt, und wie Pfeile am Rand des
  Rechtecks abgeschnitten werden.
- Ob die Regel „gleiche Daten, kein neues Rendern“ für alle Seiten gilt oder nur für `energy`.
- Ob und wie `tools/ha-sim/` steuerbare Energiesensoren bekommt.
- Wortlaut von Doku und CHANGELOG, in beiden Sprachen gleich.

## Antworten des Nutzers (2026-11-23)

1. **Stufe 1 reicht für 0.7.0.** Stufe 2 wird erst nach Messung im echten Betrieb entschieden.
2. **Version 0.7.0**, Server und Firmware gemeinsam.
3. **Getrennte Sensoren für Bezug und Einspeisung:** später („erst das, dann mehr“); bleibt
   Nicht-Ziel.
4. **Film oder GIF vom Gerät** für README und Posts: nach der Abnahme, mit dem Nutzer.
