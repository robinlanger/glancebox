# Eigene Seiten schreiben

Es gibt zwei Wege, eigene Inhalte aufs Display zu bringen: Du richtest den Server auf eine Webseite (`url`-Seite), oder du schreibst einen kleinen Seitentyp aus einer Python-Datei und einem HTML-Template (Skript-Seite). Der erste Weg braucht gar keine Programmierung.

## Zwei Arten von Seiten

| | `url`-Seite | Skript-Seite |
| --- | --- | --- |
| Was du schreibst | nichts, oder eine Webseite, die du selbst betreibst | `page.py` und `template.html` |
| Geeignet für | Dashboards oder Statusseiten, die es schon gibt | Daten aus einer API, einer Datei oder einem Sensor, in deinem eigenen Layout |
| Konfiguration | `type: url` und `url: ...` | `type: <Ordnername>` |

## Der Vertrag einer Seite

Eine Skript-Seite ist ein Ordner mit zwei Dateien. Der Ordnername ist der Seitentyp:

```
pages-custom/
  mypage/
    page.py
    template.html
```

### page.py

```python
def fetch(options: dict, ctx) -> dict:
    return {"title": "Hallo"}
```

- `fetch(options, ctx)` ist **Pflicht**. Es gibt ein Dict zurück. Jeder Schlüssel wird im Template zu einer Variablen. Die Funktion läuft in einem Worker-Thread (blockierende Aufrufe wie HTTP-Anfragen sind in Ordnung) und muss innerhalb von 20 Sekunden fertig sein.
- **Gib jedem Netzwerkaufruf ein Timeout mit**, zum Beispiel `requests.get(url, timeout=10)`. Besser: `from glancebox import http` und `http.get_json(url, params=..., headers=...)`. Das setzt ein Timeout von 10 Sekunden und den User-Agent `glancebox/<Version>`, wirft bei HTTP-Fehlern und gibt das geparste JSON zurück. Die 20-Sekunden-Grenze beendet nur das Warten auf das Ergebnis: Ein hängender Aufruf hält seinen Worker-Thread belegt, und schon wenige davon können alle Skript-Seiten blockieren.
- `validate(options)` ist optional. Wirf `ValueError("...")`, um eine fehlerhafte Konfiguration abzulehnen. Der Server startet dann nicht und zeigt deine Meldung mit der Seitennummer.
- `MIN_REFRESH = 60` ist optional (eine ganze Zahl). Es legt das kleinste erlaubte `refresh` für deine Seite fest, zum Beispiel um ein Anfragelimit einzuhalten.
- Andere `.py`-Dateien im selben Ordner kannst du mit `from .helper import etwas` importieren.

`options` enthält alle Schlüssel des Seiteneintrags in der `config.yaml` außer `type`, `duration` und `refresh`. `ctx` hat vier Felder:

| Feld | Bedeutung |
| --- | --- |
| `ctx.now` | die aktuelle Zeit als datetime mit der Zeitzone aus der `config.yaml` |
| `ctx.lang` | das `lang` von oberster Ebene (`de` oder `en`) |
| `ctx.timezone` | der Name der Zeitzone |
| `ctx.pushed(kanal)` | die letzten Daten, die an den Server geschickt wurden, siehe [Daten, die an den Server geschickt werden](#daten-die-an-den-server-geschickt-werden) |

Wirft `fetch` einen Fehler, behält die Seite bis zu 10 Minuten ihr letztes gutes Bild, und der Fehler erscheint im Log und auf der Vorschauseite. Ein Fehler in `page.py` beim Laden (ein Tippfehler) stoppt den Server beim Start mit einer klaren Meldung.

Eine Seite kann den Fehler stattdessen abfangen und Daten für ein Bild zurückgeben, das ihn anzeigt. Die eingebaute Seite `bahn` macht das absichtlich: Ist DBF nicht erreichbar, zeigt sie sofort „Keine Daten“, statt ihr letztes Bild zu behalten, denn 10 Minuten alte Abfahrtsminuten wären falsch.

### template.html

Ein Jinja2-Template. Erweitere `base.html`. Es richtet die 240x240-Fläche, den dunklen Hintergrund, die mitgelieferten DejaVu-Schriften (mit Umlauten) und diese CSS-Variablen ein: `--bg`, `--header-bg`, `--fg`, `--muted`, `--divider`, `--orange`, `--red`, `--yellow`, `--green`, `--blue`, `--header-alert`.

```html
{% extends "base.html" %}
{% block head %}<style>h1{font-size:28px;margin:20px}</style>{% endblock %}
{% block body %}<h1>{{ title }}</h1>{% endblock %}
```

Werte werden automatisch HTML-maskiert. Die Fläche ist genau 240x240 Pixel groß und nichts scrollt, was nicht passt, wird abgeschnitten. Beim SmallTV Ultra verdeckt das Gehäuse die untersten etwa 6 Pixelreihen. Lass deshalb unten mindestens 8 px frei. Die Schriften heißen „DejaVu Sans“ und „DejaVu Sans Condensed“ (normal und fett). Die schmale Variante bringt mehr Zeichen in eine Zeile.

## Bausteine

`base.html` bringt außerdem fertige Teile für das übliche Aussehen mit. Importiere die Makros in deinem Template:

```html
{% extends "base.html" %}
{% import "ui.html" as ui %}
{% block body %}
{{ ui.header("Server", "14:05", alert=False) }}
<div style="position:absolute;top:50px;left:7px;right:7px">{{ ui.bar(82, "82 %") }}</div>
{% endblock %}
```

- `ui.header(title, clock, alert=False)`: die 34 px hohe Titelleiste mit dem Titel links und der Uhr rechts. `alert=True` färbt sie rot (`--header-alert`).
- `ui.notice(message, sub=None, tone="muted")`: eine zentrierte Meldung unter der Titelleiste. `tone` ist `muted`, `warn` (orange) oder `bad` (rot).
- `ui.bar(percent, text, height=30)`: ein Balken, gefüllt bis `percent` (begrenzt auf 0 bis 100), mit `text` rechts darin. Grün unter 75 %, orange ab 75 %, rot ab 90 %.
- `ui.level(percent)`: nur der Klassenname (`ui-ok`, `ui-warn` oder `ui-bad`), um eigene Elemente einzufärben.

Neue CSS-Variablen: `--green` (`rgb(60,200,110)`), `--blue` (`rgb(90,160,255)`) und `--header-alert` (`rgb(150,25,25)`).

## Daten, die an den Server geschickt werden

Manche Daten kann der Server nicht selbst abholen, weil es sie nur auf einem anderen Rechner gibt. Dieser Rechner kann sie stattdessen an den Server schicken, und deine Seite liest die jeweils letzte Sendung. Das ist nur für dein Heimnetz (LAN) gedacht.

Lege in `page.py` fest, welche Kanäle deine Seite liest und welche JSON-Schlüssel der obersten Ebene der Server behält:

```python
PUSH_KEYS = {"claude": ("rate_limits",)}


def fetch(options, ctx):
    pushed = ctx.pushed("claude")
    if pushed is None:
        return {"text": "Noch keine Daten"}
    return {"text": str(pushed.data["rate_limits"]), "at": pushed.received_at}
```

- `PUSH_KEYS` ordnet jedem Kanalnamen ein Tupel von Schlüsselnamen zu. Kanalnamen passen auf `^[a-z0-9_-]{1,32}$`. Ein fehlerhaftes `PUSH_KEYS` stoppt den Server beim Start mit einer klaren Meldung.
- `ctx.pushed(kanal)` gibt die letzte Sendung zurück, oder `None`, wenn seit dem Start des Servers nichts angekommen ist. `.data` ist ein Dict mit nur den angegebenen Schlüsseln. `.received_at` ist der Zeitpunkt des Eingangs in Sekunden seit der Epoche (Unix-Zeit).
- Alle anderen Schlüssel einer Sendung werden verworfen. Nichts wird auf die Festplatte geschrieben: Die Daten liegen nur im Arbeitsspeicher und sind nach einem Neustart weg.
- Eine Sendung zeichnet die Seite nicht sofort neu. Die Seite übernimmt neue Daten bei ihrem nächsten `refresh`. Seiten, die nur Sendungen lesen, brauchen kein Netz, daher ist `refresh: 30` günstig und empfohlen.

Der Endpunkt ist aus, bis du `push_key` setzt (siehe [Konfiguration](configuration.md)). Leg den Schlüssel in `.env` neben `docker-compose.yml` ab und verweise in der `config.yaml` darauf:

```
# .env
GLANCEBOX_PUSH_KEY=<mindestens 16 Zeichen, z. B. aus openssl rand -hex 24>
```

```yaml
push_key: ${GLANCEBOX_PUSH_KEY}
```

Dann schickt ein Rechner in deinem Heimnetz die Daten so:

```sh
curl -X POST "http://192.168.1.20:8080/api/v1/push/claude" \
  -H "Authorization: Bearer $GLANCEBOX_PUSH_KEY" \
  -H "Content-Type: application/json" \
  -d '{"rate_limits": {"five_hour": {"used_percentage": 12}}}'
```

| Status | Bedeutung |
| --- | --- |
| 204 | gespeichert |
| 404 | kein `push_key` gesetzt, oder keine Seite gibt diesen Kanal an |
| 401 | `Authorization: Bearer <Schlüssel>` fehlt oder ist falsch |
| 413 | Inhalt größer als 65 536 Byte |
| 422 | Inhalt ist kein JSON-Objekt |

Lass den Server in deinem Heimnetz. Der Endpunkt ist nur durch den Schlüssel geschützt und nicht dafür gedacht, aus dem Internet erreichbar zu sein. Der Server schreibt weder den Inhalt noch den Schlüssel ins Log.

## Beispiel: die Seite clock

Die mitgelieferte Seite `clock` ist das kleinste sinnvolle Beispiel (`pages/clock/`). Ihre `page.py` macht drei Dinge:

1. `validate` lehnt jede andere `lang` als `de` oder `en` ab.
2. `fetch` nimmt die Sprache (die eigene Option `lang` der Seite oder die von oberster Ebene), formatiert `ctx.now` und gibt `{"time": "14:05", "weekday": "Dienstag", "date": "14.11.2026"}` zurück.
3. Mehr nicht: kein Netzwerk, kein Zustand.

Ihr `template.html` erweitert `base.html` und nutzt `{{ time }}`, `{{ weekday }}` und `{{ date }}`, zentriert in der 240x240-Fläche mit einer großen, fetten Uhrzeit. Kopiere sie und ändere sie ab:

```sh
mkdir -p pages-custom
cp -r pages/clock pages-custom/mypage
```

Bearbeite `pages-custom/mypage/page.py` und `template.html`, trage die Seite in die `config.yaml` ein:

```yaml
pages:
  - type: mypage
    refresh: 30
```

und starte mit `docker compose restart` neu. Eine Seite in `pages-custom` mit dem Namen einer mitgelieferten Seite (`clock`, `bahn`) ersetzt die mitgelieferte.

## Die url-Seite und ihre Tipps

```yaml
- type: url
  url: http://homeserver.lan/status-240
  wait_for: "#ready"
```

Der Server lädt die Adresse in einem Headless-Chromium mit einem Fenster von genau **240x240 Pixeln** und Skalierungsfaktor 1 und macht einen Screenshot. Deshalb:

- **Gestalte für 240x240.** Eine auf diese Größe geschrumpfte Desktop-Seite ist unlesbar. Baue eine Seite extra fürs Display: große Schrift (mindestens 18 px), wenige Elemente, hoher Kontrast, keine Scrollbalken. Nutze `html, body { width: 240px; height: 240px; overflow: hidden; }`.
- **Nutze `wait_for`**, wenn sich die Seite per JavaScript füllt. Gib dem fertigen Inhalt ein Element (zum Beispiel `<div id="ready">`) und setze `wait_for: "#ready"`. Nimm `wait_ms` nur für eine feste Extra-Pause, zum Beispiel bei einer Animation.
- **Halte das Bild einfach.** Ein Bild muss als JPEG in 24 576 Bytes passen. Flächen und einfacher Text lassen sich sehr gut komprimieren, Fotos und feine Farbverläufe schlecht. Muss der Server die Qualität stark senken, wird Text unscharf.
- **Der Server muss die Adresse aus dem Container heraus erreichen.** Nimm die LAN-Adresse oder den Namen, nicht `localhost`.
- **Keine Anmeldeseiten.** Der Browser des Servers hat keine gespeicherten Anmeldungen. Eine Seite mit Anmeldung zeigt die Anmeldung. Baue eine schreibgeschützte Seite fürs Display, und stelle sie nicht ins Internet, denn das Display-Bild wird ohne jedes Passwort ausgeliefert.
- Jede Aktualisierung lädt die Seite neu, also bedeutet `refresh: 30` alle 30 Sekunden eine Anfrage an deine Seite.

Manche Ziele sind für alles gesperrt, was der Browser lädt, bei `url`-Seiten wie bei Vorlagen-Seiten: die internen Namen von Home Assistant (`supervisor`, `hassio`, `homeassistant`, `observer`, jeder Name, der auf `.local.hass.io` endet), `localhost` und jeder Name, der auf `.localhost` endet, und die Adressen `0.0.0.0/8`, `127.0.0.0/8`, `169.254.0.0/16`, `172.30.32.0/23` und `fd0c:ac1e:2100::/48` (das Add-on-Netz), `172.30.232.0/23` (das Docker-Netz von Home Assistant OS), `::`, `::1` und `fe80::/10`. Adressen in deinem eigenen LAN, auch die LAN-Adresse deines Home-Assistant-Rechners, bleiben erreichbar. Der gesamte Verkehr einer Seite, auch Weiterleitungen und WebSockets, läuft über einen kleinen filternden Proxy im Server. Er prüft den Namen und jede Adresse, in die der Name aufgelöst wird, und verbindet nur zu der Adresse, die er geprüft hat. Ein öffentlicher Name, der auf eine interne Adresse zeigt, wird also ebenfalls abgewiesen. Eine abgewiesene Anfrage der Seite scheitert wie bei einem nicht erreichbaren Server (ein Bild bleibt leer), und im Log steht `page request blocked: <host>`. Wird die Adresse einer `url`-Seite selbst abgewiesen oder ist sie nicht erreichbar, schlägt die Aktualisierung fehl, und das Display behält das letzte gute Bild. Eine Ausnahme: Eine `url`-Seite darf alles von ihrem eigenen Host laden, `url: http://homeassistant:8123/...` funktioniert also weiter samt eigenen Bildern und Skripten. Ist dieser Host ein Name mit Punkt (keine IP-Adresse und keiner der internen Namen oben), werden die Adressen, in die er aufgelöst wird, trotzdem geprüft. Ein Name, der auf `127.0.0.1` zeigt, öffnet also nicht den Loopback. Ein Name ohne Punkt, etwa der Hostname eines anderen Add-ons (`a0d7b954-grafana`, `core-mosquitto`), wird nicht nach Adresse geprüft, eine `url`-Seite kann also ein anderes Add-on zeigen.

## Vorschau im Browser

Öffne `http://<server>:8080/`. Dort siehst du jede Seite deiner Playlist als 240x240-Bild mit Alter und letztem Fehler, und die Seite aktualisiert sich alle 30 Sekunden selbst. Starte nach einer Änderung an `page.py` oder `template.html` den Server neu (`docker compose restart`) und lade die Seite neu. Erscheint deine Seite nicht als Bild, sagt dir der Fehlertext darunter, warum. Die Einzelheiten stehen in `docker compose logs`.

## Der Befehl render

Um eine Seite ohne Display auszuprobieren, rendere eine Seite einmal in eine Datei:

```sh
docker compose exec glancebox python -m glancebox render 0 -o /tmp/page0.png
docker compose cp glancebox:/tmp/page0.png .
```

`0` ist die Nummer der Seite in `pages:` (ab 0 gezählt). Die Ausgabe ist ein PNG, wenn der Name auf `.png` endet, sonst ein JPEG, genau so, wie es das Display bekäme. Der Befehl nutzt die Konfiguration des laufenden Servers (`--config` wählt eine andere Datei) und endet mit einer Fehlermeldung, wenn Konfiguration oder Rendern scheitern. Außerhalb von Docker installierst du den Server (`pip install -e server` in einer Python-3.12-Umgebung mit dem Chromium von Playwright) und führst `python -m glancebox render 0 -o page0.png --config config.yaml` aus.
