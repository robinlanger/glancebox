# homeassistant: live values of Home Assistant entities

User documentation: [docs/en/templates/homeassistant.md](../../docs/en/templates/homeassistant.md) ([Deutsch](../../docs/de/templates/homeassistant.md)). Developer notes below.

```yaml
- type: homeassistant
  url: ${HA_URL}            # http(s)://host:8123 without /api, required
  token: ${HA_TOKEN}        # long-lived access token, from .env only, required
  # title: Solar            # default: "Home Assistant"
  # layout: tiles           # tiles (max 4) | list (max 6); default: tiles for 1-4 entities
  # lang: en                # default: top-level lang
  refresh: 30
  entities:                 # 1-6 entries
    - sensor.pv_power       # label = friendly_name from HA
    - entity: sensor.grid_power
      label: Grid           # own label
      decimals: 1           # optional, 0-3
```

- One request per entity and refresh, one after the other: `GET {url}/api/states/{entity_id}` with `Authorization: Bearer <token>`. The response shape is documented at the top of `page.py`.
- Error mapping: 404 for an entity gives only that cell `fehlt` / `missing` (orange). 401 or 403 gives the `token` state (`Token abgelehnt` / `Token rejected`). Any other exception (connection, timeout, 5xx, broken or non-dict JSON) gives the `error` state with `Stand 14:05` / `As of 14:05` (`2:05 PM` with `time_format: 12h`). No old values are kept.
- The token is never logged: only `HTTPError`, `ConnectionError` and `Timeout` messages (URL and status) are logged, any other exception only by its type, because e.g. `InvalidHeader` quotes the header value.
- `format_state` turns a state into a `Cell(value, unit, tone)`: `unavailable`/`unknown`/`nan`/`inf` give `n. v.` / `n/a`, on/off becomes words per domain and `device_class`, numbers are rounded (W/Wh from 1000 become kW/kWh, real minus sign, comma for `de`).
- `size_class` picks the largest font size (`l`, `m`, `s`) whose estimated width fits the cell, so the renderer needs no JavaScript to fit wide values. The width comes from the bundled `DejaVuSans-Bold.ttf` (Pillow, measured at 1000 px and scaled, which matches Chromium to about 0.5 px); font sizes and cell widths in `_BOXES` mirror `template.html` and must change with it. Text too wide even for `s` is shortened with `…` by the template.
- `fetch` returns `lang`, `layout`, `state` (`ok`, `error`, `token`) and `items` (`label`, `value`, `unit`, `tone`, `size`).
- `test_live.py` (marker `homeassistant_live`) runs against a real or simulated Home Assistant when `HA_URL` and `HA_TOKEN` are set, otherwise it is skipped.
