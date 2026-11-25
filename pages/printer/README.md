# printer: one 3D printer's state, progress and times

Developer notes. The page shows one printer: state, progress, remaining time, finish time, layer, file name, thumbnail and nozzle/bed temperatures. `source:` selects where the status comes from: directly from the printer (Moonraker, OctoPrint, PrusaLink) or from Home Assistant entities (`hass`).

```yaml
- type: printer
  source: moonraker               # moonraker | octoprint | prusalink | hass, required
  url: http://drucker.local:7125  # required (for hass: the HA URL; filled in by the add-on)
  # api_key: ${MOONRAKER_KEY}     # moonraker (optional), octoprint (required), prusalink (instead of password)
  # user: maker                   # prusalink, default maker
  # password: ${PRUSALINK_PASSWORD}  # prusalink
  # token: ${HA_TOKEN}            # hass
  # integration: moonraker        # hass, required: moonraker | octoprint | prusalink | bambu_lab | creality | custom
  # device: voron                 # hass, required except for octoprint (no effect with custom)
  # entities: {...}               # hass, optional (custom: required, at least state); sensor.x or sensor.x#attribute
  # states: {printing: [running]} # hass, optional (custom: the usual way to map raw states)
  # title: Drucker                # default "Drucker" / "Printer"
  # lang: en                      # default: top-level lang
  # thumbnail: false              # default true
  # finished_for: 120             # minutes "Fertig" stays, default 120, 0 = never
  # refresh: 10                   # default 10 s (DEFAULT_REFRESH), at least 5 (MIN_REFRESH)
```

- Hooks used by the server: `DEFAULT_REFRESH = 10` (the page's default `refresh`), `MIN_REFRESH = 5` (lower values are rejected when set, raised when inherited) and `SKIP_UNCHANGED = True` (the same data is not rendered again, the device gets a 304).
- Validation rejects unknown keys and keys of another source, naming the allowed ones: `COMMON_KEYS` plus the source's `KEYS`.

## Provider contract

Each module in `providers/` is registered in `PROVIDERS` by `page.py` and has:

- `NAME`, `KEYS` (its options besides `COMMON_KEYS`),
- `validate(options)` raising `ValueError`,
- `fetch(options, ctx) -> PrinterStatus`; `options["lang"]` is already resolved. Everything that is not a printer state is raised as `SourceError`. Requests go through `glancebox.http` (`get_json`, `get_bytes`) within a `Budget` of 15 s overall and 5 s per call.

`PrinterStatus` (`providers/_common.py`); only `state` is required, any other field may be `None` and the page then leaves that part out:

| Field | Type | Meaning |
|---|---|---|
| `state` | `printing \| paused \| finished \| error \| idle \| offline` | required |
| `progress` | float 0–100 | clamped to 0–100, shown rounded down |
| `remaining_s`, `eta` | int, aware datetime | each is computed from the other when missing; a negative remaining time or an ETA in the past is dropped |
| `filename` | str | without path and `.gcode`/`.bgcode`/`.3mf` (`clean_filename`) |
| `nozzle`, `bed` | `(actual, target or None)` | °C; target `None` = heater off |
| `layer` | `(current, total or None)` | |
| `message` | str | error text, or the small note of `paused`/`idle` |
| `duration_s`, `ended_at`, `state_since` | int, datetime, datetime | for "Fertig", "seit HH:MM" |
| `thumbnail` | `Thumbnail(data, mime)` | raw bytes as the source sent them |
| `last_job` | `(filename, ended_at or None)` | "Zuletzt: …" in the idle view |

## State rules

`settle()` in `page.py`, the same for all sources:

- `finished` turns `idle` (with this print as `last_job`) once more than `finished_for` minutes have passed since its end; `finished_for: 0` never shows "Fertig". The end is `ended_at`, else `state_since`, else the moment this server first saw `finished`.
- That moment and the last finished print live in memory only, per `(source, url, integration, device)`. After a restart the period starts again and "Zuletzt" is empty until the source reports a last job itself.

## Errors

`SourceError(kind)` and what the page shows (`notice()`):

| kind | Display |
|---|---|
| `offline` (and `unreachable` of a direct source) | "Drucker nicht erreichbar" / "Printer not reachable", grey, blue header: a printer that is switched off is normal |
| `auth` | orange "Zugang abgelehnt" / "Access denied" with "API-Key prüfen" or (PrusaLink without `api_key`) "Passwort prüfen"; `hass`: "Token abgelehnt" as on `energy` |
| `unreachable` (`hass`) | orange "Keine Verbindung zu Home Assistant" with "Stand HH:MM" |
| `config` | orange, the detail text |
| `data` | orange "Antwort nicht lesbar" / "Unexpected answer" with "Stand HH:MM" |

`offline` of a direct source is logged only when the state changes, every other failure on each fetch; URLs and exception texts are redacted, keys and passwords never reach a log line.

## Thumbnail

Source → `get_bytes` (at most 512 KiB, only `image/png`/`image/jpeg`, no redirects) → `data_uri()`: Pillow opens and decodes it, scales it to at most 100×100 and re-encodes it as PNG; only that becomes the `data:` URI in the HTML. An image Pillow cannot open, or one larger than 4096 px per side, gives no thumbnail, and the page shows the same print without it. The renderer loads nothing: the template contains no external URL and no script.

## Layout

`template.html` follows `docs/superpowers/specs/assets/2026-11-25-printer-mockup.html` (240×240): thumbnail 100×100 at (8, 42) with the texts right of it from x = 116, or without a thumbnail the percentage large on the left; bar at y 150, file name at y 164 (one line, cut with "…"), divider at y 184 and the two temperature fields from y 192 (icon orange when the heater is on, else grey with only the actual value). Font sizes step down with the length of a text so the widest values (`100 %`, `noch 23:59 h`, `Dauer 23:59 h`, `Schicht 1234/1234`, `285°/285`, `Nozzle heating`) fit; only the file name and the title may be cut. The browser tests in `test_printer.py` check this on the rendered HTML and JPEG for the seven `MOCKUPS` cases and the edge cases in `EDGES`.
