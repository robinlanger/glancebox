# Simulated Home Assistant

A throwaway Home Assistant instance with template entities whose values follow the clock.
It exists to develop and live-test the Glance Box `homeassistant` page without a real smart
home. Nothing here is part of Glance Box itself.

## Setup on a Docker host

Copy this directory to the host, e.g. into `~/homeassistant-sim`:

```bash
ssh <host> mkdir -p ~/homeassistant-sim
rsync -a tools/ha-sim/ <host>:homeassistant-sim/
```

If the host runs Pi-hole (or another resolver that refuses queries from the Docker network),
the container cannot resolve names for onboarding and integrations. Point it at the router
instead with a local `~/homeassistant-sim/docker-compose.override.yml` (kept out of git, like
the Glance Box one):

```yaml
services:
  homeassistant-sim:
    dns: [<router-ip>]
```

Start it:

```bash
cd ~/homeassistant-sim && docker compose up -d
```

HA state (owner account, tokens, database) lives in the named volume `ha-data`. Only
`config/configuration.yaml` and `config/packages/` are mounted from this directory, read-only,
so editing them here and running `docker compose restart` picks up changes.

## Onboarding and token

1. Open `http://<host>:8123` and create the owner account in the onboarding.
2. Click your user name at the bottom left → tab **Security** → **Long-lived access tokens**
   → **Create token**, e.g. named `glancebox`.
3. Put the token only into local `.env` files, never into git or a chat. For the live test on
   the dev machine, in the repo root `.env` (git-ignored):

   ```
   HA_URL=http://<host-ip>:8123
   HA_TOKEN=...
   ```

## Entities

| Entity ID | Kind | Behaviour |
| --- | --- | --- |
| `sensor.temperatur_wohnzimmer` | temperature, °C | 20–22.5, daily curve |
| `sensor.luftfeuchte_wohnzimmer` | humidity, % | 45–60 |
| `sensor.temperatur_aussen` | temperature, °C | 2–14, daily curve |
| `sensor.luftfeuchte_aussen` | humidity, % | 60–95 |
| `sensor.hausverbrauch` | power, W | changes every minute, 250–3200 |
| `sensor.pv_leistung` | power, W | 0 at night, bell curve up to 4800 between 06:00 and 20:00 |
| `sensor.netz` | power, W | consumption − PV, negative while feeding in |
| `sensor.energie_heute` | energy, kWh | rises over the day |
| `sensor.speicher` | battery, % | 10–100, slowly |
| `sensor.akku_rauchmelder` | battery, % | constant 12 (low) |
| `sensor.kellersensor` | temperature, °C | `unavailable` every sixth minute |
| `binary_sensor.fenster_bad` | window | open when minute % 10 < 3 |
| `binary_sensor.haustur` | door | open when minute % 15 == 0 |
| `binary_sensor.bewegung_flur` | motion | on when minute % 4 == 0 |
| `light.licht_kuche` | light | on when minute % 6 < 3 |
| `light.licht_flur` | light | on from 17:00 to 01:00 |
| `switch.kaffeemaschine` | switch | on when minute % 20 < 5 |

Lights and the switch only follow their time pattern; turning them on or off does nothing.

## Controllable energy sensors

`config/packages/energy.yaml` adds fake energy sensors that you set by hand, for testing the
energy-flow page (arrow direction and speed). Each sensor mirrors an `input_number` slider.
Moving the slider (Settings -> Devices & services -> Helpers, entities named `Sim ...`) changes
the sensor at once, no restart needed.

| Sensor | Slider | Range | Unit |
| --- | --- | --- | --- |
| `sensor.grid_power` | `input_number.sim_grid_power` | -10000 to 10000, step 10 | W (positive = import, negative = export) |
| `sensor.pv_power` | `input_number.sim_pv_power` | 0 to 10000, step 10 | W |
| `sensor.battery_power` | `input_number.sim_battery_power` | -5000 to 5000, step 10 | W (positive = discharging, negative = charging) |
| `sensor.wallbox_power` | `input_number.sim_wallbox_power` | -500 to 22000, step 10 | W |
| `sensor.battery_level` | `input_number.sim_battery_level` | 0 to 100 | % |
| `sensor.gas_flow` | `input_number.sim_gas_flow` | 0 to 5, step 0.1 | m³/h |
| `sensor.water_flow` | `input_number.sim_water_flow` | 0 to 30, step 0.5 | L/min |

The file also works in any other Home Assistant whose configuration includes `packages`
(`homeassistant: packages: !include_dir_named packages`).

## Cleanup

```bash
cd ~/homeassistant-sim && docker compose down -v
```

`-v` also removes the `ha-data` volume, i.e. the account and all tokens. No sudo needed.
