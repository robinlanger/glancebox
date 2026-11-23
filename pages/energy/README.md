# energy: energy flow with moving arrows

Developer notes. The page shows up to four rows (grid, PV, battery, gas, water, wallbox) from Home Assistant; the device draws moving arrows into each row's track itself.

```yaml
- type: energy
  url: ${HA_URL}              # http(s)://host:8123 without /api, required
  token: ${HA_TOKEN}          # long-lived access token, from .env only, required
  # title: Strom              # default: "Energie" / "Energy"
  # lang: en                  # default: top-level lang
  # animate: false            # default: true; false sends no X-Anim (still image only)
  # refresh: 5                # default 5 (DEFAULT_REFRESH), at least 2
  rows:                       # 1-4 entries
    - type: grid
      entity: sensor.grid_power
      # invert: true          # flip the sign if the meter reports the other way round
      # full: 5000            # value (W, or the sensor unit for gas/water) at full arrow speed
      # min: 20               # absolute values below count as 0
    - type: pv
      entity: sensor.pv_power
    - type: battery
      entity: sensor.battery_power
      soc: sensor.battery_level   # optional, battery only
```

- Hooks used by the server: `DEFAULT_REFRESH = 5` (the page's default `refresh`), `SKIP_UNCHANGED = True` (the same data is not rendered again, the device gets a 304) and the reserved key `_anim` in the result of `fetch` (a `glancebox.anim.Anim`, sent as the `X-Anim` header and removed before the template is rendered). `_anim` is missing when no row flows or `animate: false`.
- One source for the measurements: `geometry(n)` in `page.py` gives each row's centre and track rectangle (`x`, `y`, `w`, `h`, `line_y`). `build` passes these numbers to the template and the same numbers go into `X-Anim`, so the template never computes a position itself. `VALUE_LEFT`/`VALUE_RIGHT` (value box) and `SIZES` (value font sizes, used by `size_class`) also live in `page.py`.
- Promise to the firmware: inside each track rectangle the frame holds only the background `bg` and, in the rows `line_y` to `line_y + 2` across the full width, the track colour `track`. Nothing else (text, shadow, rounding) may reach the rectangle or 2 px around it. `test_track_area_is_flat_ground_and_line`, `test_inactive_row_keeps_the_same_ground` and `test_long_value_never_enters_the_track` (browser tests in `test_energy.py`) check this on the JPEG. The device fills the whole rectangle with `bg` and redraws the line on every animation frame, so a seam can only show in the 2 px ring outside it: the tests allow 16 there (a frame judged clean on the device measured 10) and 24 inside, which only catches foreign content such as text or icon strokes. The status line spans from the track's `x` to `VALUE_RIGHT` and starts 3 px below the track rectangle, so long texts like `discharging · 100 %` fit (`test_status_line_fits_without_ellipsis`).
- Flow rules (`flow` in `page.py`): sign before `invert` follows the Home Assistant energy dashboard: grid positive = import, battery positive = discharging. The value is shown without sign; direction, colour and status line say which way it flows. Arrows point away from the icon (right) for grid import, PV, battery discharging, gas and water, towards it (left) for grid export, battery charging and wallbox. PV, gas, water and wallbox treat values with the wrong sign as 0. A row is inactive (grey, no arrows) when its shown, rounded value is 0, below `min`, `unavailable`/`unknown` (`n. v.` / `n/a`) or the entity is missing (`fehlt` / `missing`). Power is compared in W (kW × 1000); speed = 10 + 70 · min(1, |value| / `full`) px/s.
- Error mapping as on the `homeassistant` page: 401/403 give the `token` state, any other failure the `error` state with `Stand HH:MM` / `As of HH:MM`; a 404 only marks that row as missing.
