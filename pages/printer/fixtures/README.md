# Test fixtures of the printer page

JSON has no comments, so the origin of every fixture is listed here. Most follow the
documentation and source code named below with invented values (file names such as
`benchy_0.2mm_PLA.gcode`, no host names or addresses); the rows marked "captured from
virtual-klipper-printer" are answers of the Moonraker simulator, anonymised (the file name is our
own probe file); the `moonraker_device_*.json` rows are answers of a real Klipper printer,
anonymised (file name, filament and printer name and file uuid replaced; numbers, shapes and
Klipper's messages kept).

| File | Derived from | Captured |
|---|---|---|
| `moonraker_query_printing.json` | Moonraker master b559b9a8 `docs/external_api/printer.md` (`/printer/objects/query`); Klipper 7558e8c2 `docs/Status_Reference.md` (`webhooks`, `print_stats`, `virtual_sdcard`, `display_status`, `extruder`, `heater_bed`, `gcode_move`) | not captured from a device |
| `moonraker_metadata.json` | Moonraker master b559b9a8 `docs/external_api/file_manager.md` (`/server/files/metadata`) and `moonraker/components/file_manager/metadata.py` (thumbnails `.thumbs/<name>-<w>x<h>.png`) | not captured from a device |
| `moonraker_history.json` | Moonraker master b559b9a8 `docs/external_api/history.md` (`/server/history/list`) | not captured from a device |
| `moonraker_query_before_extrusion.json` | `GET /printer/objects/query?<QUERY>` while printing a file that has not extruded yet, after a pause and resume: `print_duration` is `-2.842170943040401e-14` (Klipper counts it only from the first extrusion) | captured from virtual-klipper-printer e272bcd (image `ghcr.io/mainsail-crew/virtual-klipper-printer` sha256:84da96e5, Klipper v0.14.0) on 2026-11-25, anonymised |
| `moonraker_query_shutdown.json` | `GET /printer/objects/query?<QUERY>` right after `POST /printer/emergency_stop`: `webhooks.state` `shutdown`, `state_message` the cause in the first line followed by Klipper's restart instructions | captured from virtual-klipper-printer e272bcd (image `ghcr.io/mainsail-crew/virtual-klipper-printer` sha256:84da96e5, Klipper v0.14.0) on 2026-11-25, anonymised |
| `moonraker_device_query_shutdown.json` | `GET /printer/objects/query?<QUERY>` of a real Klipper printer switched off while its host keeps running: `webhooks.state` `shutdown`, `state_message` "Lost communication with MCU 'mcu'" (Klipper `klippy/mcu.py` `check_timeout`), `print_stats.state` still `complete` from the last print, `extruder`/`heater_bed` the frozen last values | captured from a device on 2026-11-25, anonymised |
| `moonraker_device_history.json` | `GET /server/history/list?limit=1&order=desc` of the same printer: the last print, `status` `completed`, with Moonraker's full `metadata` | captured from a device on 2026-11-25, anonymised |
| `octoprint_job_printing.json` | OctoPrint 2.0.2 `docs/api/job.rst`, `docs/api/datamodel.rst` and `src/octoprint/server/api/job.py`: `GET /api/job` in the pre-2.0 shape (no `X-OctoPrint-Api-Version` header): `job.file` (`name`, `display`, `path`, `origin`, `size`, `date`), `progress`, `state` as text, top-level `error` | not captured from a device |
| `octoprint_printer_printing.json` | OctoPrint 2.0.2 `docs/api/printer.rst`, `src/octoprint/server/api/printer.py` and `src/octoprint/printer/standard.py` (`_get_state_flags`): `GET /api/printer?exclude=sd`, `temperature.tool0`/`bed`, `state.text`, all eleven `state.flags` | not captured from a device |
| `octoprint_file_v1.json` | `GET /api/files/local/<path>` of OctoPrint 1.x with the PrusaSlicer Thumbnails plugin 1.2.4 (`octoprint_prusaslicerthumbnails/__init__.py`): the plugin's additional metadata `thumbnail` (`plugin/prusaslicerthumbnails/thumbnail/<path with .png>?<YYYYmmddHHMMSS>`) and `thumbnail_src` at the top level | not captured from a device |
| `octoprint_file_v2.json` | OctoPrint 2.0.2 `src/octoprint/server/api/files.py` (`_analyse_and_convert_recursively`): core thumbnails as `refs.thumbnail`, an absolute address `<index>/downloads/thumbs/local/<quoted path>?_cb=<last modified>` | not captured from a device |
| `prusalink_status_printing.json` | Prusa-Firmware-Buddy v8.0.2 `lib/WUI/nhttp/status_renderer.cpp` and `src/state/printer_state.cpp`; Prusa-Link-Web `spec/openapi.yaml`: `GET /api/v1/status` while printing, `job` (`id`, `progress`, `time_remaining`, `time_printing`; only present while the firmware has a job), `storage`, `printer` (`state`, temperatures, `axis_z`, `flow`, `speed`, fans) | not captured from a device |
| `prusalink_job_printing.json` | Prusa-Firmware-Buddy v8.0.2 `lib/WUI/link_content/basic_gets.cpp` (`get_job_v1`): `GET /api/v1/job`, `file.name` the 8.3 name, `display_name` the long name, `path` the folder, `refs.icon`/`thumbnail` `/thumb/s`/`/thumb/l` + path, `refs.download`; 204 without a job | not captured from a device |
| `hass_moonraker.json` | moonraker-home-assistant v1.14.0 (source code): `/api/states/<id>` of a running print, device `voron` | not captured from a Home Assistant instance |
| `hass_octoprint.json` | Home Assistant core dev `homeassistant/components/octoprint` 5f380806 (`sensor.py`, `strings.json`): default prefix `octoprint` | not captured from a Home Assistant instance |
| `hass_prusalink.json` | Home Assistant core dev `homeassistant/components/prusalink` 8dbdb49d (source code): device `mk4`; the temperature sensors are disabled by default in HA and enabled here | not captured from a Home Assistant instance |
| `hass_bambu_lab.json` | ha-bambulab v2.4.1 (source code): device `x1c` (in HA the prefix usually carries the serial number) | not captured from a Home Assistant instance |
| `hass_creality.json` | ha_creality_ws v0.9.10 (source code): device `k1`; file name as attribute `file` of the state sensor, targets as attribute `target` of the temperature sensors | not captured from a Home Assistant instance |

The `hass_*.json` files map each entity id to the body of `GET /api/states/<id>` (`entity_id`, `state`, `attributes`, `last_changed`). Image entities (`camera.*`, `image.*`) are not in them: the page reads those only through `/api/camera_proxy` or `/api/image_proxy`.
