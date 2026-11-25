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

## moonraker

`providers/moonraker.py`, the printer directly through Moonraker (Klipper). Derived from Moonraker master b559b9a8, Klipper 7558e8c2, Mainsail ce96e4d7 and Fluidd 8509fc70 (documentation and source code); **not yet checked against a device**. Optional `api_key:` is sent as `X-Api-Key` on every request; without it Moonraker must list this server under `trusted_clients`.

Requests (each within the fetch's `Budget`):

1. `GET /printer/objects/query?webhooks&print_stats&virtual_sdcard&display_status&extruder&heater_bed&gcode_move`, every fetch. A missing object or field only leaves its part out; only `print_stats.state` is required (when Klippy is ready).
2. `GET /server/files/metadata?filename=<print_stats.filename>`, once per file while a job is shown (`printing`, `paused`, `complete`, `error`).
3. `GET /server/files/gcodes/<dirname(filename)>/<relative_path>` for the thumbnail, every path part percent-encoded (`Teile/Halter #2 groß.gcode` → `…/gcodes/Teile/.thumbs/Halter%20%232%20gro%C3%9F-300x300.png`). Chosen: the largest PNG at most 300 px wide, else the smallest wider PNG; a path without extension counts as PNG, a `.jpg` only when there is no PNG.
4. `GET /server/history/list?limit=1&order=desc`, only when nothing is printing (`complete`, `standby`, `cancelled`). A 404 (history component off) or any other failure only leaves the end time and "Zuletzt" out.

Metadata, image and history are optional: when they fail, or the budget is used up after the query, the page shows the print without them (progress then from `display_status`).

Formulas (as Mainsail/Fluidd):

- **Progress:** `(file_position − gcode_start_byte) / (gcode_end_byte − gcode_start_byte)`, clamped to 0–1, when both bytes are known and end > start; else `display_status.progress`; else `virtual_sdcard.progress`.
- **Remaining:** slicer `estimated_time − print_duration` (when `estimated_time` > 0) and file `print_duration / progress − print_duration` (only from 1 % progress); each at least 0, the mean of those present, rounded.
- **Layer total:** `info.total_layer`, else `layer_count`, else `ceil((object_height − first_layer_height) / layer_height + 1)`.
- **Layer current:** `info.current_layer`, else (only when `print_duration` > 0) `ceil((z − first_layer_height) / layer_height + 1)` from `gcode_move.gcode_position`, limited to 0…total. The quotient is rounded to 4 decimals before `ceil` (`22.2 / 0.2` is `110.99999999999999`).

States:

| Moonraker | Page |
|---|---|
| no connection, timeout | `offline` (SourceError) |
| HTTP 401/403 | `auth` |
| HTTP 503 (Moonraker runs, Klippy not connected) | `offline`, "Klipper nicht verbunden" / "Klipper not connected" |
| other HTTP error, no `result.status`, no `print_stats.state` | `data` |
| `webhooks.state` `startup` | `offline`, "Klipper startet" / "Klipper is starting" |
| `webhooks.state` `shutdown`, `error` | `error` with `webhooks.state_message` |
| `print_stats.state` `printing` / `paused` | `printing` / `paused` with progress, remaining time, layer |
| `complete` | `finished`: `duration_s` from `print_stats.total_duration`, `ended_at` from the newest history job if it is the same file |
| `standby`, `cancelled` | `idle`; `last_job` from the newest history job if its `status` is `completed` |
| `error` | `error` with `print_stats.message` |
| anything else | `idle` with the raw word as `message` |

Kept in memory per `url` (module-level `_jobs`): the current file name, its metadata and the last `print_stats.state`. Metadata is dropped when the file name changes or a new print starts (`printing` after anything but `printing`/`paused`), so a file sliced again under the same name is read anew; failed metadata is tried again on the next fetch. The thumbnail lives in the shared cache of `_common` under `(moonraker, url, file, relative_path, print number)`.

## octoprint

`providers/octoprint.py`, the printer directly through the OctoPrint REST API. Derived from OctoPrint 2.0.2 (documentation and source code) and the PrusaSlicer Thumbnails plugin 1.2.4; **not yet run against OctoPrint**. `api_key:` is required (OctoPrint: Settings → Application Keys, or the global API key) and sent as `X-Api-Key` on every request, also for the thumbnail. No `X-OctoPrint-Api-Version` header is sent, so OctoPrint 2.x answers in the pre-2.0 shape that 1.x also uses.

Requests (each within the fetch's `Budget`):

1. `GET /api/printer?exclude=sd`, every fetch: `state.flags` (required) and `temperature.tool0`/`bed`.
2. `GET /api/job`, every fetch: `job.file` (`name`, `path`, `origin`, `date`), `progress.completion`/`printTime`/`printTimeLeft`, `state`, `error`. After a 409 from step 1 it only tells "offline" from "error".
3. `GET /api/files/local/<path>`, every path part percent-encoded, once per file path and upload time (`job.file.date`) while a job is shown and only for `origin: local`: the thumbnail reference is `refs.thumbnail` (OctoPrint 2.x core, an absolute address `…/downloads/thumbs/local/<path>?_cb=…`), else the top-level `thumbnail` of the PrusaSlicer Thumbnails plugin (`plugin/prusaslicerthumbnails/thumbnail/<path>.png?<timestamp>`, relative to `url`).
4. The thumbnail itself, through the shared cache under `(octoprint, url, address)`.

`same_host_url()` (`_common.py`) resolves the reference: a relative path is appended to `url` (one starting with `/` to its host), an absolute address is only used with the same scheme, host and port as `url` and without a user part; `//host/…` and anything else gives no thumbnail, so the API key never goes to another host. A file without a reference, a 404 for the file, or a failing image leaves only the thumbnail out; a failed file request other than 404 is tried again on the next fetch.

States (`state_of(flags, completion, has_file)`, the first matching row wins):

| OctoPrint | Page |
|---|---|
| no connection, timeout | `offline` (SourceError) |
| HTTP 401/403 | `auth` |
| other HTTP error, no JSON object, no `state.flags` | `data` |
| `/api/printer` 409 ("Printer is not operational") and `/api/job` `state` `Error` or `Offline after error` | `error` with `/api/job` `error` |
| `/api/printer` 409 otherwise (nothing connected, connecting) | `offline` |
| flag `error` or `closedOrError` | `error` with `/api/job` `error` |
| `paused` or `pausing` | `paused` |
| `cancelling` | `idle` |
| `printing`, `finishing` or `resuming` | `printing`: progress from `completion`, remaining time from `printTimeLeft`, no layer (OctoPrint core has none) |
| `operational`, `completion` ≥ 100 and a file | `finished`: `duration_s` from `printTime`; no end time (the page remembers when it first saw it) |
| `operational` or `ready` | `idle` (OctoPrint has no print history in its core, so no "Zuletzt") |
| no flag set | `offline` |

Kept in memory per `url` (module-level `_files`): the path and upload time of the last file asked for and its thumbnail address (or that it has none).

## hass

`providers/hass.py`, the printer through Home Assistant entities. Derived from the source code of Home Assistant core dev `components/octoprint` 5f380806 and `components/prusalink` 8dbdb49d, moonraker-home-assistant v1.14.0, ha-bambulab v2.4.1 and ha_creality_ws v0.9.10; **not checked against a Home Assistant instance**. `url` and `token` work as on `energy` (long-lived access token; in the add-on both are filled in when the page sets neither).

```yaml
- type: printer
  source: hass
  integration: moonraker      # moonraker | octoprint | prusalink | bambu_lab | creality | custom
  device: voron               # entity prefix; optional for octoprint, no effect with custom
  # entities:                 # replace single fields; custom: at least state
  #   nozzle_target: sensor.voron_ziel#temperature
  # states:                   # raw words on top of the preset
  #   printing: [calibrating_extrusion]
```

### Presets

`<d>` is `device`. For `octoprint` the prefix itself is `device` (default `octoprint`; a second OctoPrint instance in HA is `device: octoprint_2`). `#name` reads the attribute `name` of the entity instead of its state.

| Field | moonraker | octoprint | prusalink | bambu_lab | creality |
|---|---|---|---|---|---|
| `state` | `sensor.<d>_current_print_state` | `sensor.<d>_current_state` | `sensor.<d>` | `sensor.<d>_print_status` | `sensor.<d>_print_status` |
| `progress` | `sensor.<d>_progress` | `sensor.<d>_job_percentage` | `sensor.<d>_progress` | `sensor.<d>_print_progress` | `sensor.<d>_print_progress` |
| `remaining` | `sensor.<d>_print_time_left` | – | – | `sensor.<d>_remaining_time` | `sensor.<d>_print_time_left` |
| `eta` | `sensor.<d>_print_eta` | `sensor.<d>_estimated_finish_time` | `sensor.<d>_print_finish` | `sensor.<d>_end_time` | – |
| `filename` | `sensor.<d>_filename` | `sensor.<d>_current_file` | `sensor.<d>_filename` | `sensor.<d>_task_name` | `sensor.<d>_print_status#file` |
| `nozzle` | `sensor.<d>_extruder_temperature` | `sensor.<d>_actual_tool0_temp` | `sensor.<d>_nozzle_temperature` | `sensor.<d>_nozzle_temperature` | `sensor.<d>_nozzle_temperature` |
| `nozzle_target` | `number.<d>_extruder_target` | `sensor.<d>_target_tool0_temp` | `sensor.<d>_nozzle_target_temperature` | `sensor.<d>_nozzle_target_temperature` | `sensor.<d>_nozzle_temperature#target` |
| `bed` | `sensor.<d>_bed_temperature` | `sensor.<d>_actual_bed_temp` | `sensor.<d>_heatbed_temperature` | `sensor.<d>_bed_temperature` | `sensor.<d>_bed_temperature` |
| `bed_target` | `number.<d>_bed_target` | `sensor.<d>_target_bed_temp` | `sensor.<d>_heatbed_target_temperature` | `sensor.<d>_bed_target_temperature` | `sensor.<d>_bed_temperature#target` |
| `layer` | `sensor.<d>_current_layer` | – | – | `sensor.<d>_current_layer` | `sensor.<d>_working_layer` |
| `layer_total` | `sensor.<d>_total_layer` | – | – | `sensor.<d>_total_layer_count` | `sensor.<d>_total_layers` |
| `thumbnail` | `camera.<d>_thumbnail` | – (only the webcam) | `camera.<d>_preview` | `image.<d>_cover_image` | `image.<d>_current_print_preview` |
| also read | `sensor.<d>_printer_state` (Klippy) | | | | |

Notes from the sources: the prefix is the slugified device name in HA and can be renamed there. ha-bambulab names the device after type and serial number, so its prefix is usually longer than `x1c`; ha_creality_ws uses the host name or "<model> (Creality)". PrusaLink's four temperature sensors are disabled by default in HA (enable them under the device's entities); while they are off, the temperature line is missing. moonraker-home-assistant serves the thumbnail only while printing.

### State words

Raw words are compared stripped and in lower case. The schema words (`printing`, `paused`, `finished`, `error`, `idle`, `offline`) always count as themselves; the preset's table comes on top, `states:` on top of that (word by word, `states:` wins). With `integration: custom` only schema words and `states:` count.

| Schema | moonraker | octoprint | prusalink | bambu_lab | creality |
|---|---|---|---|---|---|
| printing | printing | printing, printing_sd, printing_streaming, starting, starting_sd, starting_streaming, resuming, finishing | printing | running, prepare, slicing, init | printing, processing, self-testing |
| paused | paused | paused, pausing | paused, attention | pause | paused |
| finished | complete | `operational` with progress ≥ 100 | finished | finish | completed |
| error | error; Klippy `shutdown`/`error` | error, offline_after_error | error | failed | error |
| idle | standby, cancelled | operational, cancelling, transferring_file | idle, ready, stopped, busy | idle | idle, stopped |
| offline | Klippy `startup` ("Klipper startet") | offline, open_serial, detect_serial, connecting | – | offline | off |

`unavailable` or `unknown` at the state entity is `offline` for every integration (Bambu's own word `unknown` too). Any other word is `idle` with the raw word as the small line, and one log warning per word (until restart). OctoPrint in HA before the ENUM sensor (PR #157213, December 2025) reported free text ("Operational", "Printing"); those single words still match, longer texts ("Printing from SD") show as an unknown word.

### Reading

- One `GET /api/states/<id>` per distinct entity with `Authorization: Bearer <token>`: state first, then the Klippy sensor (moonraker), then the other fields in the order of `FIELDS`; an entity that several fields share (Creality) is read once. Up to 12 calls, the image is the 13th.
- 404 at the state entity: orange "Entität fehlt: sensor.…" / "Entity missing: …". 404, `unavailable` or `unknown` at any other field only leaves that field out.
- 401/403: "Token abgelehnt" as on `energy`; no connection, a timeout, any other HTTP error or a body that is not an object: "Keine Verbindung zu Home Assistant". The fetch shares one budget of 15 s (5 s per call); used up before the last entity, it is "Keine Verbindung" as well.
- Remaining time uses the entity's `unit_of_measurement`: `s`, `min`, `h` or `d`; without a known unit (or read from an attribute, which has none) it is not used. A negative value is dropped.
- ETA: ISO 8601; a time without zone counts as local time; an ETA before now (HA keeps the last value after a print) or a text that is not a time is dropped.
- `state_since` is `last_changed` of the state entity, so "Fertig" counts from when HA saw the state change.
- Image: only for `printing`, `paused`, `finished` and `error`, with `thumbnail` not `false` and at least 2 s of budget left: `GET /api/camera_proxy/<camera.x>` or `/api/image_proxy/<image.x>` with the same header (other domains give no image). Cached in `_common` under `(hass, url, entity, file name)`; without a file name it is loaded on every fetch. Any failure only leaves the image out.
