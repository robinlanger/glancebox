# ai-Seite: Claude-Limits auch ohne Terminal (Hook) – Design

Stand: 2026-11-24 · Ziel-Version: 0.8.0 · Größe: kleine Änderung (kurzes Design)

## Absicht

Die Seite `ai` mit `provider: claude` bekommt ihre Zahlen heute nur vom Statuszeilen-Skript.
Die Statuszeile gibt es nur in der Terminal-Oberfläche von Claude Code. Wer Claude Code über
eine andere App nutzt (T3 Code, Desktop-App, IDE-Erweiterung), sieht auf dem Display einen
veralteten Stand. Das soll für alle Nutzer behoben werden, nicht nur für ein einzelnes Setup.

## Ziele

- Die Limits (5 Stunden, Woche) aktualisieren sich auch dann, wenn Claude Code ohne Terminal
  läuft, spätestens etwa eine Minute nach einer Antwort.
- Einrichtung auf jedem Betriebssystem gleich: Skript ablegen, Hook in
  `~/.claude/settings.json` eintragen. `push.env` und `push_key` bleiben, wie sie sind.
- Bestehende Setups mit der Statuszeile laufen unverändert weiter.
- Nur dokumentierte Wege von Claude Code.

## Nicht-Ziele

- Nutzung von claude.ai im Browser oder am Handy erfassen (dafür bräuchte es einen Timer; die
  Doku nennt das als Möglichkeit, mehr nicht).
- Das dritte Limit „Woche pro Modell“ (`weekly_scoped`) anzeigen.
- Firmware-Änderungen. Änderungen am Aussehen der Seite.

## Anti-Ziele

- Kein Zugriff auf das Login-Token von Claude Code und kein Aufruf der undokumentierten
  Abfrage `api/oauth/usage`. Anthropics Bedingungen untersagen Dritt-Tools den Umgang mit dem
  claude.ai-Login.
- Der Hook darf Claude Code nie bremsen, nie etwas ausgeben und keine Tokens verbrauchen.

## Wege

| Weg | Bewertung |
| --- | --- |
| **A: Hook nach jeder Antwort** ruft `claude -p "/usage"` auf und schickt das Ergebnis | **Gewählt.** Dokumentiert, eine Einstellungszeile, ohne Nutzung keine Last. Deckt alles ab, was Claude Code nutzt. |
| B: Timer (launchd, systemd, Aufgabenplanung) | Deckt auch Browser und Handy ab, aber drei Installationswege und Last im Leerlauf. Bleibt als Hinweis in der Doku, weil das Skript einzeln aufrufbar ist. |
| C: Abfrage mit dem Login-Token | Verworfen, siehe Anti-Ziele. |
| D: Server fragt selbst | Nicht möglich, das Login liegt auf dem Rechner des Nutzers. |

## Geprüfte Grundlage (2026-11-24, Claude Code 2.1.330, macOS)

`claude -p "/usage" --output-format stream-json --verbose --no-session-persistence` gibt
JSON-Zeilen aus. Genau eine Zeile enthält `"usage_report"` (etwa 5 KB, Push-Limit 64 KB):

```json
{"type": "assistant", "usage_report": {"rate_limits": {"limits": [
  {"kind": "session", "group": "session", "percent": 5,
   "resets_at": "2026-11-24T20:20:00.457974+00:00"},
  {"kind": "weekly_all", "group": "weekly", "percent": 21,
   "resets_at": "2026-11-28T04:00:00.457999+00:00"},
  {"kind": "weekly_scoped", "group": "weekly", "percent": 16, "resets_at": "..."}]}}}
```

Kosten 0, keine Tokens, etwa 3 Sekunden. Anthropic nennt `usage_report` experimentell; es
erscheint nur mit claude.ai-Abo. `rate_limits` kann `null` sein. Quelle:
<https://code.claude.com/docs/en/agent-sdk/typescript>. Hooks aus den Benutzereinstellungen
laufen auch in T3 Code (ein `SessionStart`-Hook hat dort gefeuert).

## Entwurf

**Neue Skripte** `tools/statusline/glancebox-usage.sh` (nur `sh`, `curl`, `grep`) und
`glancebox-usage.ps1`, als Hook-Befehl für `Stop` und `PostToolUse`:

1. Kehrt sofort mit Status 0 und ohne Ausgabe zurück; die Arbeit läuft im Hintergrund.
2. Beendet sich, wenn die Umgebungsvariable `GLANCEBOX_USAGE=1` gesetzt ist. Das Skript setzt
   sie für den eigenen `claude`-Aufruf, damit dessen Hooks keine Schleife auslösen.
3. Drosselung: höchstens ein Abruf pro 60 Sekunden, über eine Zeitstempel-Datei neben
   `push.env`. Die Statuszeilen-Skripte aktualisieren denselben Zeitstempel, wenn sie senden;
   im Terminal ruft der Hook deshalb in der Regel nicht zusätzlich ab.
4. Ruft den Befehl oben auf, nimmt die Zeile mit `"usage_report"` und schickt sie wie bisher
   an `/api/v1/push/claude`. Ohne diese Zeile (altes Claude Code, API-Schlüssel, Fehler)
   sendet es nichts, die letzten Werte bleiben stehen.

**Server:** `PUSH_KEYS` der Seite `ai` wird `("rate_limits", "usage_report")`.
`providers/claude.py` liest beide Formate: Enthält der Push `usage_report`, kommen die Zeilen
aus `usage_report.rate_limits.limits` (`session` → „5 Stunden“, `weekly_all` → „Woche“,
`percent` 0 bis 100, `resets_at` als ISO-Zeit); sonst wie heute aus `rate_limits`. Alles
danach (Reset-Text, „zurückgesetzt“, Stand, fehlende Fenster, Hinweise) ist für beide gleich.
Unbekannte `kind`-Werte und fehlerhafte Felder werden übersprungen.

**Doku** (en + de, `docs/*/templates/ai.md`, `pages/ai/README.md`, Skript-Köpfe): neuer
Abschnitt „Claude Code in anderen Apps“ mit dem Hook-Eintrag, der Mindestversion, dem Hinweis
„experimentell“ und einem Absatz zum Timer. Der Hinweistext `Statuszeilen-Skript einrichten`
bleibt.

**Tests:** Provider-Tests für das neue Format (beide Fenster, nur eines, `rate_limits: null`,
Reset vorbei, Vorrang der Formate); Skript-Test wie `test_statusline.py` mit einem
`claude`-Ersatz im `PATH` (sendet die richtige Zeile, Drosselung, Schleifenschutz, nichts
ohne `usage_report`).

**Release:** 0.8.0, CHANGELOG mit dem, was geprüft wurde und was nicht.

## Meine Festlegungen (nicht mit Robin besprochen)

- Hook auf `Stop` **und** `PostToolUse`, damit lange Aufgaben zwischendurch aktualisieren.
- Drosselung fest auf 60 Sekunden, keine Einstellung dafür.
- Eigene Skripte statt eines Schalters im Statuszeilen-Skript.
- `weekly_scoped` wird nicht angezeigt.
- Version 0.8.0 (neue Funktion), ohne Firmware-Änderung.

## Dem Umsetzer überlassen

- Ablageort und Format der Zeitstempel-Datei; Umsetzung des Hintergrundlaufs unter Windows.
- Zuerst prüfen, noch vor dem restlichen Code: feuern `Stop` und `PostToolUse` in einer
  T3-Code-Sitzung, und liefert der Aufruf aus einem Hook heraus dieselbe Zeile?
- Prüfung unter Windows und Linux, soweit ohne eigene Geräte möglich; sonst im CHANGELOG als
  ungeprüft nennen.
