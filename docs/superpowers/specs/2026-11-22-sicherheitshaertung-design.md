# Sicherheitshärtung: Design

Stand 2026-11-22, Basis: `main` bei 3fb5f85 (0.6.1).

## Anlass und Ziel

Glance Box ist ein öffentliches Projekt. Der Maintainer will bestmögliche Sicherheit für alle
Nutzer, besonders für das Home-Assistant-Add-on. Eine Prüfung von Server, Add-on, Firmware und
Lieferkette am 2026-11-22 ergab sieben Punkte. Dieses Dokument legt fest, wie sie behoben werden.

## Ziele

- Ein kompromittierter oder bösartiger Webinhalt in Chromium kommt nicht an den Supervisor-Token
  und die Schlüssel.
- Die Aussagen in `SECURITY.md` stimmen wieder mit dem Verhalten überein.
- Abhängigkeiten sind vollständig und mit Hashes festgelegt, Bauwerkzeuge per Digest/SHA.

## Nicht-Ziele

- TLS für das Display, Login für den Docker-Server, signierte Firmware. Das bleiben dokumentierte
  Grenzen aus `SECURITY.md`.
- Eigenes AppArmor-Profil für das Add-on. Ein fehlerhaftes Profil legt das Add-on bei allen
  Nutzern lahm, und Chromium unter AppArmor lässt sich nur in der Test-VM abnehmen. Folgearbeit.
- Versionssprung, Tag, Release. Beide Pakete enden auf einem Branch; das Release macht der
  Maintainer nach `docs/RELEASING.md`.

## Anti-Ziele

- Bestehende Installationen booten oder rendern nach dem Update nicht mehr (gespeicherte
  Einstellungen auf dem Gerät, bestehende `config.yaml`, bestehende `url`-Seiten im LAN).
- Geheimnisse oder Adressen mit Token landen in Logs, Fehlermeldungen oder Tests.
- Doku behauptet einen Schutz, der nicht gebaut oder nicht geprüft ist.

## Funde und Entscheidungen

| # | Fund | Entscheidung |
|---|---|---|
| 1 | Chromium läuft ohne Sandbox und erbt die ganze Umgebung (Supervisor-Token, Schlüssel). Skript-Code einer `url`-Seite kann ins interne HA-Netz anfragen. | Chromium bekommt nur eine Positivliste an Variablen. Add-on-Geheimnisse gehen nicht mehr in `os.environ`, sondern in eine eigene Zuordnung für `${NAME}`. `SUPERVISOR_TOKEN` wird nach dem Lesen aus `os.environ` entfernt. Sandbox wird versucht und fällt mit Logzeile zurück, wenn der Container sie nicht erlaubt. Anfragen aus Seiten an interne HA-Ziele werden abgebrochen. |
| 2 | Einrichtungs-WLAN nimmt auf eingerichtetem Gerät neue WLAN-Daten ohne Update-Passwort an. | Auf eingerichteten Geräten ist das Einrichtungs-WLAN mit WPA2 geschützt, Passwort = Update-Passwort. Erste Einrichtung bleibt offen. |
| 3 | Falscher Server kann das Gerät mit endlos langsamen Kopfzeilen blockieren. | Frame-Abruf über `WiFiClient` mit Gesamtfrist (8 s) und Kopf-Obergrenze (1024 Byte); Kopf-Parser in `lib/core`, nativ getestet. |
| 4 | Fehlertexte (Übersicht, Logs) können Adressen samt Token zeigen. | Eine Funktion `redact_urls` entfernt Zugangsdaten, Query und Fragment aus Adressen; angewandt auf gespeicherte Fehler und alle Log-Stellen mit Adressen. |
| 5 | Lieferkette: 11 Pins ohne Hashes, Basis-Image und Actions per Tag, kein Scan, Testwerkzeuge im Image. | Vollständige Lock-Dateien mit Hashes (Laufzeit und Dev getrennt), Image ohne Testwerkzeuge, Basis-Image per Digest, Actions per Commit-SHA, Dependabot, `pip-audit` in CI, Herkunftsnachweis (Attestation) im Release. |
| 6 | Firmware: kein Limit für Passwortversuche; offene WiFiManager-Routen; unmaskierte Werte im Portal; keine Host-Prüfung. | Sperre nach 5 Fehlversuchen für 30 s; `/restart`, `/exit`, `/close`, `/info` gesperrt; Server-Adresse lehnt `' " < > \`` und Steuerzeichen ab (nur bei Eingabe); Host-Kopfzeile muss IPv4, Gerätename oder Gerätename`.local` sein. |
| 7 | Kleine Härtungen. | uvicorn ohne Proxy-Kopfzeilen; CSP und weitere Schutz-Kopfzeilen auf der Übersicht; `docker-compose.yml` mit `cap_drop: ALL` und `no-new-privileges`. Die Sperrliste für Geheimnis-Namen entfällt, weil die Namen nach Punkt 1 nicht mehr in die Prozessumgebung kommen. |

## Wege, die erwogen wurden

- **A (gewählt): zwei Branches.** `security/server-hardening` (Server, Add-on, Lieferkette) und
  `security/firmware-hardening`. Der Server lässt sich so ohne Firmware veröffentlichen; die
  Firmware braucht erst Smoketest und 24-h-Dauertest auf echter Hardware.
- **B: ein Branch für alles.** Einfacher, aber der Release-Workflow baut die Firmware aus jedem
  Tag. Ungetestete Firmware-Änderungen würden mit dem nächsten Server-Release ausgeliefert.
- **C: nur dokumentieren.** Widerspricht dem Ziel.

## Bekannte Grenzen nach der Härtung

- In Docker und im Add-on verbietet das Standard-seccomp-Profil meist die Chromium-Sandbox. Dann
  bleibt der Rückfall ohne Sandbox; Schutz sind dann die bereinigte Umgebung und die Zielsperre.
- Ein Prozess mit derselben Benutzerkennung kann `/proc/<pid>/environ` des Servers lesen; dort
  steht der Supervisor-Token aus dem Start. Das verhindert nur die Sandbox.
- Die Zielsperre ist ein filternder Proxy im Server-Prozess, über den jeder Browser-Kontext
  seinen ganzen Verkehr schickt. Er prüft Namen und jede aufgelöste Adresse und verbindet zur
  geprüften Adresse; DNS-Rebinding, Weiterleitungen und WebSockets sind damit abgedeckt.
- Direktes UDP, etwa WebRTC, läuft nicht über den Proxy und wird nicht gefiltert.

## Was dem Bauenden überlassen ist

Genaue Fehlertexte, interne Hilfsnamen, die Wahl zwischen `uv` und `pip-tools` zum Erzeugen der
Lock-Dateien, und die aktuellen Digests und SHAs (zur Bauzeit nachschlagen, nicht raten).
