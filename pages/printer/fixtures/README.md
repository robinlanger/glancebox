# Test fixtures of the printer page

JSON has no comments, so the origin of every fixture is listed here. None of them was captured
from a device: the shapes follow the documentation and source code named below, the values are
invented (file names such as `benchy_0.2mm_PLA.gcode`, no host names or addresses).

| File | Derived from | Captured |
|---|---|---|
| `moonraker_query_printing.json` | Moonraker master b559b9a8 `docs/external_api/printer.md` (`/printer/objects/query`); Klipper 7558e8c2 `docs/Status_Reference.md` (`webhooks`, `print_stats`, `virtual_sdcard`, `display_status`, `extruder`, `heater_bed`, `gcode_move`) | not captured from a device |
| `moonraker_metadata.json` | Moonraker master b559b9a8 `docs/external_api/file_manager.md` (`/server/files/metadata`) and `moonraker/components/file_manager/metadata.py` (thumbnails `.thumbs/<name>-<w>x<h>.png`) | not captured from a device |
| `moonraker_history.json` | Moonraker master b559b9a8 `docs/external_api/history.md` (`/server/history/list`) | not captured from a device |
