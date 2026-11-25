# Test fixtures of the printer page

JSON has no comments, so the origin of every fixture is listed here. None of them was captured
from a device: the shapes follow the documentation and source code named below, the values are
invented (file names such as `benchy_0.2mm_PLA.gcode`, no host names or addresses).

| File | Derived from | Captured |
|---|---|---|
| `moonraker_query_printing.json` | Moonraker master b559b9a8 `docs/external_api/printer.md` (`/printer/objects/query`); Klipper 7558e8c2 `docs/Status_Reference.md` (`webhooks`, `print_stats`, `virtual_sdcard`, `display_status`, `extruder`, `heater_bed`, `gcode_move`) | not captured from a device |
| `moonraker_metadata.json` | Moonraker master b559b9a8 `docs/external_api/file_manager.md` (`/server/files/metadata`) and `moonraker/components/file_manager/metadata.py` (thumbnails `.thumbs/<name>-<w>x<h>.png`) | not captured from a device |
| `moonraker_history.json` | Moonraker master b559b9a8 `docs/external_api/history.md` (`/server/history/list`) | not captured from a device |
| `hass_moonraker.json` | moonraker-home-assistant v1.14.0 (source code): `/api/states/<id>` of a running print, device `voron` | not captured from a Home Assistant instance |
| `hass_octoprint.json` | Home Assistant core dev `homeassistant/components/octoprint` 5f380806 (`sensor.py`, `strings.json`): default prefix `octoprint` | not captured from a Home Assistant instance |
| `hass_prusalink.json` | Home Assistant core dev `homeassistant/components/prusalink` 8dbdb49d (source code): device `mk4`; the temperature sensors are disabled by default in HA and enabled here | not captured from a Home Assistant instance |
| `hass_bambu_lab.json` | ha-bambulab v2.4.1 (source code): device `x1c` (in HA the prefix usually carries the serial number) | not captured from a Home Assistant instance |
| `hass_creality.json` | ha_creality_ws v0.9.10 (source code): device `k1`; file name as attribute `file` of the state sensor, targets as attribute `target` of the temperature sensors | not captured from a Home Assistant instance |

The `hass_*.json` files map each entity id to the body of `GET /api/states/<id>` (`entity_id`, `state`, `attributes`, `last_changed`). Image entities (`camera.*`, `image.*`) are not in them: the page reads those only through `/api/camera_proxy` or `/api/image_proxy`.
