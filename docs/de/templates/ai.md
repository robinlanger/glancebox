# ai

![Vorschau der Seite ai mit Anbieter claude](../../img/templates/ai-claude.png)
![Vorschau der Seite ai mit Anbieter openai-api und Budget](../../img/templates/ai-cost.png)

## Was sie zeigt

Wie viel von einem KI-Abo oder -Budget verbraucht ist. Jede Seite zeigt einen Anbieter, den du mit `provider:` wählst. Wer mehrere nutzt, trägt mehrere Seiten ein.

| `provider` | Zeigt | Wie die Daten ankommen |
| --- | --- | --- |
| `claude` | Die Limits deines Claude-Abos: das 5-Stunden-Fenster und die Woche, jeweils in Prozent mit der Zeit des nächsten Resets | Claude Code auf deinem Rechner schickt sie an den Server (Push), über seine Statuszeile oder ein Hook-Skript |
| `anthropic-api` | Kosten der Claude-API im laufenden Monat in USD, auf Wunsch gegen dein eigenes Budget | Der Server fragt die Usage and Cost Analytics API von Anthropic mit einem Admin-Key |
| `openai-api` | Kosten der OpenAI-API im laufenden Monat in USD, auf Wunsch gegen dein eigenes Budget | Der Server fragt die Costs API von OpenAI mit einem Admin-Key |
| `xai-api` | Prepaid-Guthaben deines xAI-Teams in USD | Der Server fragt die Management API von xAI mit einem Management-Key |
| `copilot` | Verbrauch von GitHub Copilot im Monat (AI-Credits oder Premium-Requests) gegen das Kontingent deines Abos, das du selbst einträgst | Der Server fragt die Billing-Usage-API von GitHub mit einem Token, das nur lesen darf |

Für jedes Limit gibt es eine Zeile mit dem Namen und rechts der Zeit des Resets, darunter einen breiten Balken mit dem Wert darin. Der Balken ist grün, ab 75 % orange und ab 90 % rot.

**Verbraucht oder übrig:** Standardmäßig zählen die Balken hoch, wie viel verbraucht ist. Mit `show: remaining` zählen sie stattdessen herunter: Der Balken startet voll bei `100 %` und läuft gegen `0 %`, `58 %` heißt also, 58 % sind noch übrig. Die Farbe richtet sich weiter nach dem Verbrauch, Rot heißt also immer: nur noch wenig übrig. Mehr als aufgebraucht zeigt `0 %`, ein zurückgesetztes Fenster `100 %`, und bei `copilot` zeigt der Text, was vom Kontingent übrig ist, zum Beispiel `88 / 300`. `xai-api` hat keinen Balken, dort ändert die Option nichts.

**Claude-Look:** `claude` und `anthropic-api` erscheinen in Claudes Farben, dunkel wie claude.ai: der Titel in Claude-Orange, orange Balken, die ab 75 % Verbrauch rot werden. Das passiert automatisch; die anderen Anbieter behalten das normale Aussehen.

Für `claude`:

- **Reset:** weniger als einen Tag entfernt als `in 2:13` (Stunden:Minuten), sonst als Wochentag und Uhrzeit, zum Beispiel `Do 09:00`. Ist die Reset-Zeit schon vorbei, zeigt der Balken `0 %` und `zurückgesetzt` (mit `show: remaining`: ein voller Balken und `100 %`).
- **Alter:** unten zeigt die Seite immer, wann die Werte ankamen, zum Beispiel `Stand 13:58`, oder `Stand Sa 13:58`, wenn sie von einem früheren Tag sind.
- **Noch keine Daten:** bis die ersten Werte ankommen, zeigt die Seite den Hinweis `Noch keine Daten` mit `Statuszeilen-Skript einrichten`. Der Hinweis ist derselbe, wenn du das Hook-Skript nutzt.
- **Keine Limitdaten:** Werte kamen an, aber ohne brauchbare Limits, zum Beispiel nach dem `curl`-Test unter [Wenn etwas nicht stimmt](#wenn-etwas-nicht-stimmt). Die nächste Antwort von Claude Code bringt die echten Werte. Limits hat Claude Code nur mit einem Claude-Abo (Pro oder Max); mit einem API-Key schickt das Skript nichts, und die Seite bleibt bei `Noch keine Daten`.
- Hat dein Abo kein Wochenlimit, erscheint nur der 5-Stunden-Balken.

Für `anthropic-api`, `openai-api` und `xai-api`:

- **Betrag:** groß in der Mitte, als `18,40 $` (`Diesen Monat`) oder, bei `xai-api`, `Guthaben`. Der Monat ist der Kalendermonat in UTC, so wie die Anbieter abrechnen.
- **Budget:** mit `budget: 50` erscheint unter dem Betrag ein Balken `Budget` mit dem Anteil, der schon verbraucht ist, und dem Tag, an dem er neu beginnt (`1.12.`). Über 100 % bleibt der Balken voll, und der Text zeigt den echten Wert, zum Beispiel `120 %` (mit `show: remaining`: ein leerer Balken und `0 %`).
- **Alter:** unten zeigt `Stand 14:05`, wann der Server die Werte zuletzt bekommen hat. Bei `anthropic-api` ist es die Zeit des Datenexports von Anthropic, der etwa alle 4 Stunden aktualisiert wird.
- **Nur alle 5 Minuten:** Kostendaten ändern sich langsam. Der Server behält eine erfolgreiche Antwort 5 Minuten, egal was bei `refresh` steht. Nach einem Fehler fragt er frühestens nach 1 Minute erneut.
- **Keine Daten:** ist der Anbieter nicht erreichbar oder lehnt er den Key ab, wird die Kopfzeile rot, und die Seite zeigt `Keine Daten` mit der Uhrzeit, nie einen alten Betrag.

Für `copilot`:

- **Balken:** `AI-Credits` (oder `Premium-Requests`) mit verbraucht / Kontingent, zum Beispiel `1.234 / 1.500`, und rechts der Tag, an dem das Kontingent neu beginnt (`1.12.`, GitHub setzt am 1. um 00:00 UTC zurück). Darüber groß, was `Übrig` ist.
- **Dein Kontingent:** Die API von GitHub meldet nur, was du verbraucht hast, nicht, wie viel dein Abo enthält. Das trägst du selbst mit `monthly_allowance` ein, zum Beispiel `1500` für Copilot Pro (siehe [GitHub Copilot](#github-copilot)).
- **Nur selbst bezahlte Abos:** Der Verbrauch eines Copilot-Platzes, den eine Organisation oder Firma bezahlt, steht nicht in dieser API.
- Alter, der 5-Minuten-Takt und `Keine Daten` funktionieren wie bei den Kosten-Anbietern.

## Was du brauchst

Für `claude`:

- Ein Claude-Abo (Pro oder Max) und [Claude Code](https://code.claude.com/docs) auf einem Rechner im selben Heimnetz wie der Glance-Box-Server.
- `curl` auf diesem Rechner (macOS und Linux haben es). Unter Windows reicht PowerShell.
- Das Skript `tools/statusline/glancebox-statusline.sh` (macOS, Linux) oder `tools/statusline/glancebox-statusline.ps1` (Windows) aus diesem Repository auf diesem Rechner. Nutzt du Claude Code in einer anderen App statt im Terminal, brauchst du `tools/statusline/glancebox-usage.sh` oder `.ps1` (siehe [Claude Code in anderen Apps](#claude-code-in-anderen-apps)).

Für `anthropic-api`, `openai-api` und `xai-api`:

- Eine Organisation (Anthropic, OpenAI) oder ein Team (xAI) mit API-Abrechnung und das Recht, dort einen Admin- oder Management-Key anzulegen.
- Internetzugang für den Glance-Box-Server.

Für `copilot`:

- Ein Copilot-Abo, das du selbst gekauft hast (Pro, Pro+ oder Max), auf deinem GitHub-Konto.
- Ein Fine-grained Personal Access Token mit dem Leserecht `Plan` (siehe [GitHub Copilot](#github-copilot)).
- Internetzugang für den Glance-Box-Server.

Claude Code gibt seiner [Statuszeile](https://code.claude.com/docs/en/statusline) nach jeder Antwort einen kleinen JSON-Text. Darin stehen deine Limits (`rate_limits`). Das Skript reicht diesen Text im Hintergrund an den Server weiter und zeigt danach deine normale Statuszeile.

Die Statuszeile gibt es nur in der Terminal-Ansicht von Claude Code. In anderen Apps, die Claude Code ausführen, etwa T3 Code, der Desktop-App oder einer IDE-Erweiterung, übernimmt ein Hook-Skript ihre Aufgabe: Nach einer Antwort fragt es Claude Code nach denselben Limits und schickt sie weiter.

## Beispiel

```yaml
- type: ai
  provider: claude
  lang: de
  refresh: 30
```

Für die API-Kosten, mit dem Key in `.env` (siehe [Einrichtung](#einrichtung)):

```yaml
- type: ai
  provider: openai-api
  key: ${OPENAI_ADMIN_KEY}
  budget: 50
  lang: de
```

## Optionen

| Schlüssel | Standard | Bedeutung |
| --- | --- | --- |
| `provider` | | Woher die Werte kommen: `claude`, `anthropic-api`, `openai-api`, `xai-api` oder `copilot`. Pflicht. |
| `key` | | Nur `anthropic-api`, `openai-api`, `xai-api`, `copilot`, dort Pflicht: der Admin- oder Management-Key, bei `copilot` das GitHub-Token. Immer als `${NAME}` aus `.env`, nie direkt in `config.yaml`. |
| `budget` | keins | Nur `anthropic-api` und `openai-api`: dein Monatsbudget in USD, eine positive Zahl wie `50`. Ergänzt den Balken `Budget`. |
| `team_id` | | Nur `xai-api`, dort Pflicht: die ID deines xAI-Teams. |
| `username` | | Nur `copilot`, dort Pflicht: dein GitHub-Benutzername. |
| `monthly_allowance` | | Nur `copilot`, dort Pflicht: wie viel dein Abo pro Monat enthält, eine positive Zahl wie `1500`. |
| `unit` | `ai-credits` | Nur `copilot`: `ai-credits` (nutzungsbasierte Abrechnung, der Normalfall) oder `premium-requests` (ein Jahresabo, das bei Premium-Requests geblieben ist). |
| `show` | `used` | `used`: Die Balken zeigen, wie viel verbraucht ist. `remaining`: Sie zeigen, wie viel übrig ist (100 % → 0 %). Siehe [Was sie zeigt](#was-sie-zeigt). |
| `title` | Name des Anbieters (`Claude`, `Anthropic API`, `OpenAI API`, `xAI API`, `GitHub Copilot`) | Text der Kopfzeile. |
| `lang` | oberstes `lang` | `de` oder `en`. Legt alle Texte der Seite fest. |
| `refresh` | Standard-`refresh` | Für `claude` empfehlen wir `30`. Die Seite liest nur, was angekommen ist, das kostet nichts. Bei den API-Anbietern behält der Server eine erfolgreiche Antwort ohnehin 5 Minuten. |
| `duration` | `interval` | Wie viele Sekunden die Seite auf dem Display bleibt. |

## Einrichtung

### Claude

1. **Schlüssel für den Server.** Erzeuge einen Schlüssel mit `openssl rand -hex 24` und trage ihn in `.env` neben `docker-compose.yml` ein:

   ```
   GLANCEBOX_PUSH_KEY=<der Schlüssel>
   ```

   In `config.yaml` auf oberster Ebene ergänzen:

   ```yaml
   push_key: ${GLANCEBOX_PUSH_KEY}
   ```

2. **Die Seite.** Füge das Beispiel in die Liste `pages:` in `config.yaml` ein und führe `docker compose up -d` aus (ein einfaches `restart` liest `.env` nicht neu).

3. **Einstellungen auf deinem Rechner.** Lege die Datei `~/.config/glancebox/push.env` mit der Adresse des Servers und demselben Schlüssel an und mache sie nur für dich lesbar:

   ```sh
   mkdir -p ~/.config/glancebox
   cat > ~/.config/glancebox/push.env <<'EOF'
   GLANCEBOX_URL=http://192.168.1.10:8080
   GLANCEBOX_PUSH_KEY=<der Schlüssel>
   EOF
   chmod 600 ~/.config/glancebox/push.env
   ```

   Nimm die Adresse deines Servers im Heimnetz. Ist `XDG_CONFIG_HOME` gesetzt, gehört die Datei nach `$XDG_CONFIG_HOME/glancebox/push.env`.

4. **Das Skript.** Kopiere `tools/statusline/glancebox-statusline.sh` an einen Ort deiner Wahl, zum Beispiel `~/.claude/glancebox-statusline.sh`, und mache es mit `chmod +x` ausführbar.

5. **Claude Code.** Ergänze in `~/.claude/settings.json`:

   ```json
   {
     "statusLine": {
       "type": "command",
       "command": "~/.claude/glancebox-statusline.sh"
     }
   }
   ```

   Das Skript selbst gibt nichts aus, die Statuszeile bleibt also leer.

6. **Prüfen.** Frag Claude Code etwas. Öffne nach der Antwort `http://<server>:8080/` und warte auf das nächste Neuladen der Seite (bis zu 30 Sekunden).

### Eigene Statuszeile behalten

Hast du schon eine Statuszeile, gib ihren Befehl dem Skript als Argumente mit. Das Skript reicht ihr dasselbe JSON weiter, und ihre Ausgabe bleibt deine Statuszeile:

```json
{
  "statusLine": {
    "type": "command",
    "command": "~/.claude/glancebox-statusline.sh ~/.claude/my-statusline.sh"
  }
}
```

### Claude Code in anderen Apps

Die Statuszeile gibt es nur, wenn du Claude Code im Terminal nutzt. Arbeitest du über T3 Code, die Desktop-App von Claude, eine IDE-Erweiterung oder eine andere App, die Claude Code ohne seine Terminal-Ansicht ausführt, gibt es keine Statuszeile, und das Display bleibt bei den letzten Werten stehen. Für diesen Fall gibt es ein zweites Skript.

Nach einer Antwort von Claude Code fragt das Skript Claude Code im Hintergrund nach seinem Nutzungsbericht (dasselbe wie `/usage`) und schickt ihn an den Server. Das passiert höchstens einmal pro Minute, dauert etwa 3 Sekunden und kostet keine Tokens.

Du brauchst ein aktuelles Claude Code (geprüft mit Version 2.1.330, siehe `claude --version`) und ein Claude-Abo (Pro oder Max). Die Schritte 1 bis 3 unter [Claude](#claude) bleiben gleich; `push_key`, die Seite und `push.env` brauchst du wie dort beschrieben.

1. **Das Skript.** Kopiere `tools/statusline/glancebox-usage.sh` an einen Ort deiner Wahl, zum Beispiel `~/.claude/glancebox-usage.sh`, und mache es ausführbar:

   ```sh
   chmod +x ~/.claude/glancebox-usage.sh
   ```

2. **Claude Code.** Ergänze in `~/.claude/settings.json`:

   ```json
   {
     "hooks": {
       "Stop": [
         { "hooks": [{ "type": "command", "command": "~/.claude/glancebox-usage.sh" }] }
       ],
       "PostToolUse": [
         { "hooks": [{ "type": "command", "command": "~/.claude/glancebox-usage.sh" }] }
       ]
     }
   }
   ```

   `hooks` steht auf oberster Ebene der Datei, neben deinen anderen Einstellungen. Gibt es in der Datei schon einen Abschnitt `hooks`, ergänze darin `Stop` und `PostToolUse`. `Stop` läuft nach jeder Antwort, `PostToolUse` nach jedem Werkzeugschritt, so aktualisieren auch lange Aufgaben das Display zwischendurch. Das Skript gibt nichts aus und kehrt sofort zurück, Claude Code wartet also nicht darauf.

3. **Neue Sitzung.** Claude Code liest Hooks beim Start einer Sitzung. Öffne in deiner App eine neue Sitzung oder einen neuen Thread; eine schon offene führt das Skript nicht aus.

4. **Prüfen.** Frag Claude Code in der App etwas. Öffne nach der Antwort `http://<server>:8080/` und warte auf das nächste Neuladen der Seite (bis zu 30 Sekunden): `Stand` zeigt die Zeit der Antwort.

**Beides nutzen:** Arbeitest du auch im Terminal, behalte die Statuszeile. Beide schicken dieselben Limits. Direkt nachdem die Statuszeile gesendet hat, hält das Hook-Skript eine Minute still, es fragt also nicht doppelt ab.

**Experimentell:** Anthropic kennzeichnet diesen Nutzungsbericht als experimentell. Ein Update von Claude Code kann ihn ändern oder entfernen. Dann schickt das Skript nichts, und die Seite zeigt weiter die letzten Werte mit ihrer Uhrzeit (`Stand`). Mit einem API-Key statt eines Claude-Abos oder mit einem älteren Claude Code gibt es ebenfalls keinen Nutzungsbericht.

**Ohne Claude Code:** Der Hook läuft nur, wenn du Claude Code nutzt. Soll das Display auch deiner Nutzung von claude.ai im Browser oder am Handy folgen, kannst du das Skript über einen Zeitplaner deines Systems starten (cron, launchd oder die Windows-Aufgabenplanung), zum Beispiel alle 5 Minuten. Auch dort braucht das Skript `push.env` und muss `claude` finden. Dieses Projekt richtet das nicht ein und hat es nicht getestet.

### Windows

1. Lege `%APPDATA%\glancebox\push.env` mit denselben zwei Zeilen wie in Schritt 3 an.
2. Kopiere `tools\statusline\glancebox-statusline.ps1`, zum Beispiel nach `%USERPROFILE%\.claude\`.
3. In `%USERPROFILE%\.claude\settings.json`:

   ```json
   {
     "statusLine": {
       "type": "command",
       "command": "powershell -NoProfile -ExecutionPolicy Bypass -File C:/Users/<du>/.claude/glancebox-statusline.ps1"
     }
   }
   ```

   Schreib den Pfad mit Schrägstrichen `/`: Claude Code führt den Befehl unter Umständen über Git Bash aus, und Git Bash verschluckt Backslashes. Eine vorhandene Statuszeile kommt wie oben ans Ende des Befehls. Mit installiertem Git Bash kannst du auch das `.sh`-Skript wie unter macOS nehmen.

Für [Claude Code in anderen Apps](#claude-code-in-anderen-apps) kopiere zusätzlich `tools\statusline\glancebox-usage.ps1` und ergänze in derselben `settings.json`:

```json
{
  "hooks": {
    "Stop": [
      { "hooks": [{ "type": "command", "command": "powershell -NoProfile -ExecutionPolicy Bypass -File C:/Users/<du>/.claude/glancebox-usage.ps1" }] }
    ],
    "PostToolUse": [
      { "hooks": [{ "type": "command", "command": "powershell -NoProfile -ExecutionPolicy Bypass -File C:/Users/<du>/.claude/glancebox-usage.ps1" }] }
    ]
  }
}
```

Dieses Skript ist unter Windows noch nicht getestet. Probierst du es aus, prüfe nach einer Antwort `Stand` auf der Seite und sag uns in einem Issue, ob es funktioniert.

### Grenzen

- Die Werte werden nur aktuell, solange Claude Code läuft und antwortet, und nur, solange dein Rechner im Heimnetz ist. Unterwegs schlägt das Senden leise fehl, und die Seite zeigt weiter die letzten Werte mit ihrer Uhrzeit (`Stand 13:58`).
- Der Server hält die Werte nur im Arbeitsspeicher. Nach einem Neustart des Servers zeigt die Seite `Noch keine Daten`, bis Claude Code die nächste Antwort gibt.
- Eine neue Claude-Code-Sitzung schickt ihre Limits erst nach ihrer ersten Antwort.

### Anthropic API

> **Warnung:** Ein Anthropic-Admin-Key hat volle Rechte über die ganze Organisation: Mitglieder, Workspaces, alle API-Keys und ihre Limits. Wer ihn hat, kann in der Organisation alles tun, nicht nur Kosten lesen. Nutze ihn nur für eine Organisation, in der sonst nichts liegt (eine eigene Organisation nur dafür), oder verzichte auf diesen Anbieter.

1. Melde dich als Admin der Organisation in der Claude Console an, öffne die [Seite für Admin-Keys](https://platform.claude.com/settings/admin-keys), klicke **Create admin key** und gib einen Namen und ein Ablaufdatum an. Kopiere den Key (er beginnt mit `sk-ant-admin01-` und wird nur einmal gezeigt). Admin-Keys der Console haben keine wählbaren Rechte: Jeder Key hat vollen Zugriff.
2. Trage ihn in `.env` neben `docker-compose.yml` ein:

   ```
   ANTHROPIC_ADMIN_KEY=sk-ant-admin...
   ```

3. Füge die Seite in `config.yaml` ein und führe `docker compose up -d` aus:

   ```yaml
   - type: ai
     provider: anthropic-api
     key: ${ANTHROPIC_ADMIN_KEY}
     budget: 50   # optional
   ```

In einer Claude-Enterprise-Organisation kann der Primary Owner stattdessen einen Key nur mit dem Recht `read:analytics` anlegen (claude.ai → Organization settings → API). Er kann nur Berichte lesen und ist die deutlich sicherere Wahl; er kommt genauso in `ANTHROPIC_ADMIN_KEY`.

Die Seite nutzt die [Usage and Cost Analytics API](https://platform.claude.com/docs/en/manage-claude/usage-cost-analytics-api) (`/v1/organizations/analytics/cost`), die die ältere Cost API ablöst. Admin-Keys gibt es nur für Organisationen in der Claude Console, nicht für Einzelkonten oder das claude.ai-Team-Abo.

### OpenAI API

1. Lege auf der [Seite für Admin-Keys](https://platform.openai.com/settings/organization/admin-keys) einen neuen Admin-Key an. Das können nur Owner der Organisation. Gib ihm die engsten Rechte, die die Seite anbietet: **Read only** oder, falls es die Wahl gibt, nur Lesezugriff auf Nutzung und Kosten. Wähle nie vollen Zugriff nur für dieses Display.
2. Trage ihn in `.env` ein:

   ```
   OPENAI_ADMIN_KEY=sk-admin-...
   ```

3. Füge die Seite ein:

   ```yaml
   - type: ai
     provider: openai-api
     key: ${OPENAI_ADMIN_KEY}
     budget: 50   # optional
   ```

Ein normaler Projekt-API-Key funktioniert nicht; die Costs API braucht einen Admin-Key.

### xAI API

1. Öffne in der [xAI Console](https://console.x.ai/) **Settings → Management Keys** und lege einen Key an. Dein Konto braucht dafür das Recht `Management Keys` (Lesen und Schreiben); sonst frag den Admin des Teams. Der Management-Key ist ein anderer als der API-Key, den du für Grok nutzt.
2. Kopiere deine Team-ID von der Seite mit den Team-Einstellungen der Console (`console.x.ai/team/default/settings/team`).
3. Trage beides in `.env` ein:

   ```
   XAI_MANAGEMENT_KEY=...
   XAI_TEAM_ID=...
   ```

4. Füge die Seite ein:

   ```yaml
   - type: ai
     provider: xai-api
     key: ${XAI_MANAGEMENT_KEY}
     team_id: ${XAI_TEAM_ID}
   ```

Ein Management-Key kann die API-Keys und die Abrechnung des Teams verwalten, behandle ihn also wie ein Passwort.

### GitHub Copilot

1. Öffne auf GitHub **Settings → Developer settings → Personal access tokens → Fine-grained tokens** und klicke **Generate new token**. Gib ihm einen Namen und ein Ablaufdatum. Setze unter **Permissions → Account permissions** das Recht **Plan** auf **Read-only** und füge nichts weiter hinzu. Das Token kann dann dein Abo und deinen Verbrauch lesen, aber keinen Code und keine Einstellungen.

   Die Doku von GitHub widerspricht sich hier: Die [API-Referenz](https://docs.github.com/en/rest/billing/usage) sagt, ein Fine-grained Token mit `Plan` (lesen) funktioniert, eine [Anleitung](https://docs.github.com/en/billing/tutorials/automate-usage-reporting) sagt, diese Endpunkte brauchen ein klassisches Token. Probier zuerst das Fine-grained Token. Nur wenn die Seite bei `Keine Daten` bleibt und das Log `HTTP 403` zeigt, nimm ein klassisches Token (**Personal access tokens → Tokens (classic)**). Welchen Scope es braucht, nennt die Doku von GitHub nicht; frag GitHub mit `curl -sI -H "Authorization: Bearer <token>" https://api.github.com/users/<name>/settings/billing/ai_credit/usage` und lies die Zeile `X-Accepted-OAuth-Scopes`, dann gib dem Token nur diesen Scope und ein Ablaufdatum. **Achtung:** Die Scopes eines klassischen Tokens gelten für alle deine Repositorys und Organisationen, es darf also weit mehr als das Fine-grained Token.
2. Trage das Token und deinen Benutzernamen in `.env` ein:

   ```
   GITHUB_COPILOT_TOKEN=github_pat_...
   GITHUB_USER=dein-name
   ```

3. Schau nach, wie viel dein Abo pro Monat enthält, unter [Plans for GitHub Copilot](https://docs.github.com/en/copilot/get-started/plans) oder auf deiner Abrechnungsseite. Im November 2026 enthält Copilot Pro 1.500 AI-Credits, Pro+ 7.000 und Max 20.000. Ein Pro-Jahresabo, das bei Premium-Requests geblieben ist, hat 300 pro Monat (Pro+: 1.500); dann setze `unit: premium-requests`.
4. Füge die Seite ein:

   ```yaml
   - type: ai
     provider: copilot
     key: ${GITHUB_COPILOT_TOKEN}
     username: ${GITHUB_USER}
     monthly_allowance: 1500
     # unit: premium-requests   # nur für ein Jahresabo mit Premium-Requests
   ```

Die Seite nutzt die [Billing-Usage-API](https://docs.github.com/en/rest/billing/usage) von GitHub (`/users/{username}/settings/billing/ai_credit/usage` oder `.../premium_request/usage`). GitHub hat keine dokumentierte API, die meldet, wie viel dein Abo enthält; deshalb trägst du `monthly_allowance` selbst ein. Ein Teil des Kontingents (der Flex-Anteil) kann sich mit der Zeit ändern, prüfe die Zahl also ab und zu. Ein Copilot-Platz, den eine Organisation oder Firma bezahlt, erscheint hier nicht.

## Datenschutz & Sicherheit

- **Nur `rate_limits` oder `usage_report` wird gespeichert.** Das JSON der Statuszeile enthält auch Dinge wie den Arbeitsordner und die Sitzungs-ID. Der Server verwirft sofort alles außer `rate_limits`, schreibt nichts auf die Platte und protokolliert den Inhalt nicht.
- **Das Hook-Skript** schickt eine JSON-Zeile aus dem Nutzungsbericht von Claude Code. Der Server behält davon nur `usage_report` (deine Limits und die Kostenzähler des Abrufs) und verwirft den Rest, wie oben nur im Arbeitsspeicher.
- **Kein Anthropic-Token verlässt deinen Rechner.** Das Statuszeilen-Skript schickt nur den Text, den Claude Code der Statuszeile gibt, zusammen mit dem Glance-Box-Schlüssel. Auch das Hook-Skript liest dein Claude-Login nicht: Es startet `claude` so, wie du es tun würdest, und schickt die Zeile, die zurückkommt. Der Server meldet sich nie bei Anthropic an.
- **Der Push-Schlüssel** erlaubt nur, Werte an dein Display zu schicken. Bewahre ihn in `.env` auf dem Server und in `push.env` (`chmod 600`) auf deinem Rechner auf, nie in `config.yaml`.
- Der Server und sein Daten-Eingang sind nur für dein Heimnetz gedacht. Mach sie nicht aus dem Internet erreichbar.
- **API-Keys** (`anthropic-api`, `openai-api`, `xai-api`) sind mächtig: Sie können weit mehr als Kosten lesen. Das GitHub-Token für `copilot` braucht nur das Leserecht `Plan`; gib ihm nicht mehr (ein klassisches Ersatz-Token nur den einen Scope, den GitHub nennt). Bewahre sie nur in `.env` auf, schreib `${NAME}` in `config.yaml` und gib `.env` nie weiter. Der Server schickt sie nur an den Anbieter, im Kopf der Anfrage, und schreibt sie nie in sein Log. Die Beträge hält er 5 Minuten im Arbeitsspeicher und speichert nichts auf der Platte.

## Wenn etwas nicht stimmt

- **`Noch keine Daten` bleibt:** Claude Code schickt Limits nur mit einem Claude-Abo (Pro oder Max) und in aktuellen Versionen. Mit einem API-Key statt eines Abos oder mit einem älteren Claude Code schickt das Skript nichts, und die Seite bleibt bei `Noch keine Daten`; sonst ist dann nichts falsch. Andernfalls prüfe, dass `push_key` gesetzt ist und du nach der Änderung an `.env` `docker compose up -d` ausgeführt hast. Teste dann den Weg von deinem Rechner zum Server: `curl -i -X POST -H "Authorization: Bearer <der Schlüssel>" -H "Content-Type: application/json" -d '{"rate_limits":{}}' http://<server>:8080/api/v1/push/claude`. `204` ist richtig (die Seite zeigt dann `Keine Limitdaten` bis zur nächsten Antwort von Claude Code), `401` heißt, der Schlüssel stimmt nicht, `404` heißt, der Server hat keinen `push_key`. Klappt `curl`, prüfe `push.env` (beide Zeilen, keine Leerzeichen um `=`) und den Pfad in `settings.json`.
- **`Keine Limitdaten`:** ein Push kam an, aber ohne brauchbare Limitfenster, zum Beispiel der `curl`-Test oben mit `{"rate_limits":{}}`. Die nächste Antwort von Claude Code ersetzt ihn durch die echten Werte.
- **Die Statuszeile ist leer:** das ist ohne eigene Statuszeile normal. Um eine zu zeigen, gib ihren Befehl als Argumente mit.
- **Das Display aktualisiert sich nur, wenn ich im Terminal arbeite:** die Statuszeile läuft nur in der Terminal-Ansicht von Claude Code. Für T3 Code, die Desktop-App oder eine IDE-Erweiterung richte das Hook-Skript ein, wie unter [Claude Code in anderen Apps](#claude-code-in-anderen-apps) beschrieben.
- **Vom Hook kommt nichts an:** starte das Skript zuerst von Hand in einem Terminal mit `~/.claude/glancebox-usage.sh`. Es gibt nichts aus; nach etwa 5 Sekunden und dem nächsten Neuladen der Seite sollte `Stand` die aktuelle Uhrzeit zeigen. Das Skript fragt höchstens einmal pro Minute ab, warte also eine Minute nach dem letzten Senden, bevor du es probierst. Ändert sich `Stand` nicht, teste, ob Claude Code überhaupt einen Nutzungsbericht liefert: `claude -p "/usage" --output-format stream-json --verbose --no-session-persistence | grep -c usage_report` sollte `1` ausgeben. `0` heißt: ein älteres Claude Code, eine Anmeldung mit API-Key statt Claude-Abo oder ein Fehler; prüfe dann auch `push.env` mit dem `curl`-Test oben. Klappt es von Hand, aber nicht aus der App: Öffne eine neue Sitzung oder einen neuen Thread (Hooks werden beim Start gelesen) und prüfe, ob die App `claude` findet. Eine App, die du über das Dock oder das Startmenü startest, kennt den Ordner, in dem dein Terminal `claude` findet, unter Umständen nicht. `command -v claude` im Terminal zeigt diesen Ordner; setz ihn vor den Hook-Befehl, zum Beispiel `PATH=$HOME/.local/bin:$PATH ~/.claude/glancebox-usage.sh`.
- **`Keine Daten` mit roter Kopfzeile (API-Anbieter):** der Anbieter war nicht erreichbar oder hat die Anfrage abgelehnt. Im Log des Servers steht eine Zeile wie `ai openai-api: no data: HTTPError (HTTP 401)`. `401` oder `403` heißt, der Key ist falsch, abgelaufen oder hat nicht das nötige Recht; prüfe `.env` und führe nach einer Änderung `docker compose up -d` aus. Bei `xai-api` heißt `404` meist, dass `team_id` nicht stimmt. Bei `copilot` heißt `403`, dass dem Token das Recht `Plan` fehlt oder GitHub für dein Konto kein Fine-grained Token annimmt; dann probier ein klassisches Token wie unter [GitHub Copilot](#github-copilot) beschrieben. `404` heißt, dass `username` nicht stimmt. Die Seite versucht es beim nächsten Neuladen wieder.
- **Der Anthropic-Betrag wirkt zu niedrig:** Anthropic aktualisiert die Kostendaten etwa alle 4 Stunden; `Stand` zeigt die Zeit der Daten.
- **Der Server startet nicht und nennt `key`, `team_id` oder `budget`:** `key` (und bei `xai-api` `team_id`) muss gesetzt und nicht leer sein, etwa weil die Variable in `.env` fehlt; `budget` muss eine positive Zahl sein und geht nur mit `anthropic-api` und `openai-api`.
- **Der Server startet nicht und nennt `username`, `monthly_allowance` oder `unit` (`copilot`):** `username` muss gesetzt sein, `monthly_allowance` muss eine positive Zahl sein, und `unit` ist entweder `ai-credits` oder `premium-requests`.
- **`copilot` zeigt `0` verbraucht, obwohl du Copilot nutzt:** die API zählt nur ein Abo, das du selbst bezahlst. Prüfe auch, ob `unit` zu deiner Abrechnung passt: Seit Juni 2026 rechnen Monatsabos in AI-Credits ab.
- **Der Server startet nicht und nennt `provider`:** der Wert muss einer der Anbieter aus der Tabelle oben sein.
