# Rettung

Was du tust, wenn etwas schiefgeht: eine Geräteseite, die den Zugriff verweigert, der Safe Mode nach einem fehlerhaften Update, der Boot-Zähler und der serielle Weg als letzte Möglichkeit.

## Die Geräteseite verweigert den Zugriff

- **Öffne die Geräteseite über ihre IP-Adresse**, zum Beispiel `http://192.168.1.50/`, oder im eigenen Netz des Safe Mode `http://192.168.4.1/`. Das Gerät antwortet nur auf seine IP-Adresse und seinen eigenen Gerätenamen; bei jedem anderen Namen (zum Beispiel einem, den dein Router vergeben hat) antwortet es `open this page by the device's IP address`. Das schützt es vor Webseiten, die es über einen falschen Namen erreichen wollen (DNS-Rebinding).
- **Nach fünf falschen Passwörtern hintereinander sperrt das Gerät die Passwortprüfung für 30 Sekunden**, für alle. In dieser Zeit lehnt es auch das richtige Passwort ab und sagt, wie viele Sekunden noch fehlen (HTTP-Status 429). Warte und gib dann das richtige Passwort ein. Das erste falsche Passwort nach einer Sperre sperrt erneut.

## Safe Mode

### Wann er startet

Die Firmware zählt jeden Start. Er gilt als gesund nach **60 Sekunden Laufzeit mit verbundenem WLAN und laufendem Webserver**, dann geht der Zähler auf 0 zurück. Schaffen das **3 Starts hintereinander** nicht (Absturz, Hänger, endlose Neustarts), startet der nächste Start den Safe Mode. Ein Server, der nicht erreichbar ist, löst den Safe Mode **nicht** aus.

Der Safe Mode hat fast keinen Code: WLAN, einen minimalen Webserver mit einer Update-Seite, die Update-Funktion und `/status`. Er dekodiert keine Bilder und fragt den Server nicht nach Frames.

### Was du siehst

Das Display zeigt **„Safe mode“** mit der Firmware-Version, der Zahl der Fehlstarts und, sobald das WLAN verbunden ist, der Adresse `http://<ip>/update`. Ist das gespeicherte WLAN innerhalb von 20 Sekunden nicht erreichbar, öffnet der Safe Mode zusätzlich ein eigenes Netz `GlanceBox-XXXX` (ohne Passwort). Verbinde dich damit und nutze die Adresse `192.168.4.1`. Hat das Gerät in seinen Einstellungen kein gültiges Update-Passwort, zeigt der Safe Mode zuerst das Einrichtungsportal, siehe [Einrichtung](setup.md).

`http://<ip>/status` zeigt `"safe_mode": true`.

### Safe Mode verlassen

Der Safe Mode liefert eine kleine Seite unter `http://<ip>/` und `http://<ip>/update` (deutsch oder englisch, je nach Browser). Sie enthält das Update-Formular und zwei Schaltflächen. Die Seite ist öffentlich, jede Aktion verlangt aber den Benutzer `admin` und dein Update-Passwort.

1. **Eine funktionierende Firmware hochladen** (das vorige Release ist eine gute Wahl, oder das neueste). Öffne im Browser die Seite, füge die MD5 ein (das erste Wort der `.md5`-Datei des Releases, siehe [Aktualisieren](updating.md#bevor-du-aktualisierst)), wähle die `.bin`-Datei und drücke **Hochladen**. Der Browser fragt nach `admin` und deinem Update-Passwort. Alternativ mit curl:

   ```sh
   curl -u admin:<passwort> -F md5=<md5> -F firmware=@glancebox-ultra-<version>.bin http://<ip>/update
   ```

   Nach dem Upload startet das Gerät mit sauberem Zähler in die neue Firmware. Die Einzelheiten des Befehls stehen unter [Aktualisieren](updating.md#update-mit-curl).
2. **Oder die normale Firmware wieder starten**, zum Beispiel wenn etwas Vorübergehendes den Safe Mode ausgelöst hat. Drücke auf der Seite **Normale Firmware starten** oder nimm curl:

   ```sh
   curl -u admin:<passwort> -X POST http://<ip>/boot-normal
   ```

   Der nächste Start läuft mit der normalen Firmware. Scheitert er wieder dreimal, bist du zurück im Safe Mode.

Ein einfacher Neustart (Schaltfläche **Neustart**, `POST /restart`) verlässt den Safe Mode **nicht**.

## Boot-Zähler und Stromunterbrechung

Der Zähler liegt in einem Speicherbereich, der Neustarts überlebt. Bei jedem Start prüft die Firmware außerdem, **warum** der Chip gestartet ist: Nach dem Einschalten beginnt sie immer neu zu zählen, auch wenn der Speicher eine kurze Stromunterbrechung überstanden hat. Daraus folgt:

- Stecker ziehen und wieder einstecken **setzt den Zähler zurück**. Nach einer Stromunterbrechung startet das Gerät wieder die normale Firmware und hat drei neue Versuche. Ein Signal am Reset-Pin des Chips (zum Beispiel von einem seriellen Adapter) zählt genauso.
- Abstürze, Watchdog-Resets und Neustarts per Software (die Schaltfläche **Neustart**, ein Update) behalten den Zähler. Drei davon innerhalb einer Minute zählen jeweils als Fehlstart.
- Scheitert die Firmware immer wieder und du unterbrichst jedes Mal den Strom, kommst du von allein nie in den Safe Mode. Spiele dann eine funktionierende Firmware auf (zum Beispiel direkt nach dem Einstecken, in der ersten Minute, sobald `/update` antwortet) oder nimm den seriellen Weg unten.

## Serielles Flashen

Die letzte Möglichkeit. Sie funktioniert auch bei komplett kaputter Firmware, weil sie mit dem eingebauten Bootloader des Chips spricht. Du brauchst denselben Adapter wie für die Sicherung, siehe [Flashen](flashing.md#schritt-1-original-firmware-sichern-optional).

### Was du brauchst

- Einen USB-Seriell-Adapter mit 3,3 V: einen Raspberry Pi Pico mit `debugprobe` (GP4 = TX, GP5 = RX) oder ein CH340-Modul auf 3,3 V.
- `esptool` (`pip install esptool`).
- Die Verkabelung aus [Flashen](flashing.md#verkabelung): GND an GND, TX des Adapters an RX des ESP, RX des Adapters an TX des ESP. **TX und RX kreuzen.**

### Pads und Foto (noch nicht an echter Hardware bestätigt)

> [!NOTE]
> **Noch nicht an echter Hardware bestätigt.** Ein Foto der Ultra-Platine mit den Pad-Beschriftungen kommt hierher, sobald der Maintainer ein Gerät geöffnet hat. Bis dahin nennen wir keine platinenspezifischen Positionen. Die nötigen Signale liegen immer am ESP-12F-Modul selbst: GND, TX (TXD0), RX (RXD0) und GPIO0. Nimm die Pinbelegung aus dem Datenblatt des Moduls, prüfe mit dem Durchgangsprüfer eines Multimeters gegen die Pins des Moduls und löte oder klemme nur an ein Pad, wenn du sicher bist, welches Signal es führt. Wenn du unsicher bist, rate nicht: Frag in einem Issue.

### Das Gerät in den Flash-Modus bringen

1. Ziehe das USB-Kabel vom Display ab.
2. Schließe die Drähte an: GND, TX, RX und **GPIO0 an GND**.
3. Stecke das USB-C-Kabel des Displays ein. Versorge das Display nicht über den Adapter.
4. Prüfe die Verbindung: `esptool.py --port <port> chip_id` zeigt `Chip is ESP8266`. Klappt die Verbindung nicht, unterbrich den Strom noch einmal mit GPIO0 an GND und prüfe TX und RX.

### Firmware flashen

```sh
esptool.py --port <port> -b 115200 write_flash 0x0 glancebox-ultra-<version>.bin
```

Entferne danach den GPIO0-Draht und unterbrich den Strom des Displays (abziehen, einstecken). Es startet die neue Firmware und öffnet das Einrichtungsportal, wenn keine Einstellungen gespeichert sind. Sind noch Einstellungen gespeichert und ist das gespeicherte WLAN nicht erreichbar, öffnet sich das Einrichtungsportal ebenfalls, und sein WLAN `GlanceBox-XXXX` fragt nach einem Passwort: Gib dein Update-Passwort ein. Der genaue Flash-Befehl samt Flash-Parametern steht noch aus, bis der Maintainer den seriellen Test selbst gemacht hat.

## Sicherung zurückspielen

Hast du eine Sicherung gemacht wie in [Flashen](flashing.md#sicherung-erstellen-und-prüfen) beschrieben, bringt dieser Weg das Display zur Original-Firmware zurück, samt Aktivierung:

1. Bring das Gerät wie oben in den Flash-Modus (GPIO0 beim Einschalten an GND).
2. Optional zuerst löschen: `esptool.py --port <port> erase_flash`.
3. Schreibe die Sicherung:

   ```sh
   esptool.py --port <port> -b 115200 write_flash 0 backup1.bin
   ```

4. Entferne den GPIO0-Draht und unterbrich den Strom des Displays. Es startet die Original-Firmware wie zuvor, mit deinen alten WLAN-Einstellungen.

Prüfst du vorher `shasum -a 256 backup1.bin` und stimmt die Summe mit der überein, die du dir notiert hast, weißt du, dass die Datei unversehrt ist.

Ohne Sicherung gibt es keinen Weg zurück zur Original-Firmware. Glance Box kannst du jederzeit wieder flashen.
