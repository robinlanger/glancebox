# Home Assistant add-on

If you run Home Assistant OS, you can run the Glance Box server as a Home Assistant add-on instead
of Docker Compose. This page takes you from the App store to your own playlist in four steps.

The names of menus and buttons below are those of Home Assistant 2026.11 (Home Assistant OS
18.4). There, add-ons are called **apps**: the menu is **Settings → Apps** and the store is the
**App store**. Older versions say "Add-ons" and "Add-on store"; newer versions may differ again.

## What you need

- **Home Assistant OS** (or a Supervised install). Home Assistant Container and Core have no
  add-ons; use the [Docker setup](guide/2-start-the-server.md) there.
- A display with the Glance Box firmware. You flash it **once in the browser**, no soldering:
  [Flash the firmware](guide/3-flash-the-firmware.md). After that, everything happens in Home Assistant.
- The display and Home Assistant in the same network.

## Step 1: Install the add-on

[![Add the repository to my Home Assistant](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Frobinlanger%2Fglancebox)

1. Click the button. It opens your Home Assistant and asks "Add app repository?". Click **Add**.
   Without the button: **Settings → Apps → Install app**. This opens the **App store**. There,
   **⋮ (top right) → Repositories → Add**, enter `https://github.com/robinlanger/glancebox` as the
   URL and click **Add**.
2. In the App store, open **Glance Box**. If it does not show up yet, reload the page.
3. Click **Install**. The download can take a few minutes; then the add-on page shows **Start**.

## Step 2: Start it and open the web UI

1. On the add-on page, click **Start**. The **Log** tab shows two lines with `Uvicorn running on`
   once the server is up (the add-on runs two servers). One of them names port 8080, the port
   inside the add-on that your network reaches on port 8090; the other is for the web UI.
2. Click **Open Web UI**. The add-on's overview opens: the box "Connect your display" and, under
   "Playlist", the starter pages **clock** and **weather**. Their previews appear after a short
   while; until then a page shows "no picture yet". The overview reloads itself every 30 seconds.
3. Optional: switch on **Show in sidebar** on the add-on page. It is off after the install, so
   Home Assistant does not add a sidebar entry by itself.

Time zone, language (German or English) and the home location for the weather come from Home
Assistant, so there is nothing to fill in.

## Step 3: Connect the display

1. In the box "Connect your display", copy the address, for example `http://192.168.1.x:8090`
   (the IP address of your Home Assistant and port 8090).
2. Enter it on the display:
    - **New display:** join the display's Wi-Fi **GlanceBox-XXXX**, pick your network and paste
      the address into the field **Server URL** ([Set up Wi-Fi](guide/4-set-up-wifi.md)).
    - **Display already set up:** open its device page `http://<display-ip>/`, enter the address
      under **Settings → Server URL** and click **Save**. Changes need the update password
      (user `admin`).

    Only `http://` works, not `https://`.
3. Back in the add-on's web UI, the grey "Waiting for your display" turns into a green "Display
   connected · last picture …" once the display has fetched its first picture. The display shows
   the clock, then the weather.

## Step 4: Choose your pages

The playlist is the file `config.yaml` in the add-on's config folder,
`/app_configs/<id>_glancebox/config.yaml`, where `<id>` is a short code Home Assistant gives this
repository (for example `9a6cf636_glancebox`). Older versions of Home Assistant and of the editor
add-ons show the folder as `/addon_configs/<id>_glancebox/`. Inside the add-on, and in its log,
the same file is called `/config/config.yaml`. It uses the same format as the
[configuration](configuration.md) of the Docker setup, with two differences:

- `timezone`, `lang` and the location of a `weather` page are optional; without them the values
  from Home Assistant are used. Values you set in `config.yaml` always win.
- A `homeassistant` or `energy` page, and a `printer` page with `source: hass`, needs neither
  `url` nor `token`; it reads from this Home Assistant.

To edit the file you need an editor add-on from the official App store, for example
**File editor**, **Studio Code Server** or **Terminal & SSH**; Home Assistant OS does not come
with one. File editor's own documentation says that its option "Enforce basepath", which is on
after the install, limits it to Home Assistant's own config folder. Switch it off in File
editor's **Configuration** tab and restart File editor (not yet tried in File editor itself; the
folder was checked in Terminal & SSH).

1. Open `/app_configs/<id>_glancebox/` in your editor.
    - **The folder is empty:** the add-on could not save the starter file. This is what happened
      on Home Assistant OS 18.4. The Log tab shows `cannot write /config/config.yaml ([Errno 13]
      Permission denied: ...); using a temporary starter playlist`, and the web UI shows the
      starter content under "Start config.yaml with this content". Create a new file
      `config.yaml` in that folder and paste the content.
    - **`config.yaml` is there:** the add-on wrote it on its first start with the starter pages.
      The Log tab of that start shows `wrote starter playlist to /config/config.yaml`.
2. Change the pages. A typical first playlist: the clock, the weather and some entities of your
   Home Assistant (replace the entity ids with your own):

    ```yaml
    pages:
      - type: clock
      - type: weather
        refresh: 60
      - type: homeassistant
        title: Home
        entities:
          - sensor.outside_temperature
          - sensor.pv_power
          - binary_sensor.front_door
    ```

3. Save the file and **restart the add-on** (Restart on the add-on page). The add-on reads
   `config.yaml` only when it starts; this is also needed after every change of a secret.
4. Open the web UI again. The playlist lists your pages with their previews. If a page has a
   problem, its error is shown in red under its preview.

If the add-on stops instead, the last lines of the Log tab name the reason, see
[Troubleshooting](#troubleshooting).

## Examples

Each block is a list of pages: put it under `pages:` in your `config.yaml`. All options of a page
type are described on its page in the [template catalog](templates/README.md).

### Entities: `homeassistant`

Shows up to six entities. No `url` or `token` needed.
[All options](templates/homeassistant.md)

```yaml
- type: homeassistant
  title: Solar
  entities:
    - entity: sensor.pv_power
      label: PV
    - entity: sensor.grid_power
      label: Grid
    - entity: sensor.battery_level
      label: Battery
```

### Energy flow: `energy`

[All options](templates/energy.md)

```yaml
- type: energy
  title: Power
  refresh: 5
  rows:
    - type: grid
      entity: sensor.grid_power
    - type: pv
      entity: sensor.pv_power
    - type: battery
      entity: sensor.battery_power
      soc: sensor.battery_level
```

### 3D printer from Home Assistant: `printer`

Reads the printer's entities from Home Assistant, here those of the Moonraker integration.
`device` is the entity prefix of your printer. [All options](templates/printer.md)

```yaml
- type: printer
  source: hass
  integration: moonraker
  device: voron
```

### Weather at another place: `weather`

Without `location` the page uses the home location of Home Assistant.
[All options](templates/weather.md)

```yaml
- type: weather
  location: Frankfurt am Main
```

### Departures: `bahn`

[All options](templates/bahn.md)

```yaml
- type: bahn
  station: "Frankfurt(Main)Hbf"
  limit: 4
  refresh: 60
```

### Claude usage: `ai`

Needs the **Push key** from the add-on's Configuration tab and the status-line script on your
computer. [All options](templates/ai.md)

```yaml
- type: ai
  provider: claude
```

### Time format, language and time zone

These go at the top of `config.yaml`, above `pages:`. `time_format: 12h` shows times of day as
`2:05 PM`; the default is `24h`. The add-on has no form field for it. `lang` and `timezone` are
only needed if they should differ from Home Assistant. A page can override `time_format` for
itself; here the departures stay in 24 hours.

```yaml
time_format: 12h
lang: en
timezone: America/New_York

pages:
  - type: clock
  - type: bahn
    station: "Frankfurt(Main)Hbf"
    time_format: 24h
```

## Secrets

The add-on's **Configuration** tab holds only secrets, all optional. Secrets never need to be
written into `config.yaml` in plain text.

- **Push key:** for the Claude usage page (`ai` with `provider: claude`). Used automatically.
- **Anthropic / OpenAI / xAI / GitHub Copilot keys:** for the `ai` page with the matching
  provider. In `config.yaml` write them as `${ANTHROPIC_ADMIN_KEY}`, `${OPENAI_ADMIN_KEY}`,
  `${XAI_MANAGEMENT_KEY}`, `${GITHUB_COPILOT_TOKEN}`.
- **More secrets:** name/value pairs for your own pages and for the key or password of a printer
  read directly, used as `${NAME}`. The name starts with a capital letter and may contain capital letters,
  digits and `_` (A-Z, 0-9, `_`). A name that is already in use, such as one of the built-in
  secrets above, is ignored.

Example: a printer read directly from OctoPrint. Add `OCTOPRINT_KEY` with your key under **More
secrets**, save, and use it like this:

```yaml
- type: printer
  source: octoprint
  url: http://printer.local
  api_key: ${OCTOPRINT_KEY}
```

Restart the add-on after changing a secret.

## Updating

- **Add-on:** Home Assistant shows an update for Glance Box when a new version is out. Install
  it like other add-on updates; your `config.yaml` stays.
- **Display firmware:** the release notes say whether a release brings new firmware. Only then
  update the display: [Updating the firmware](updating.md).

## Troubleshooting

| What you see | Likely cause | What to do |
| --- | --- | --- |
| The add-on stops right after Start | An error in `config.yaml` | Open the **Log** tab. Its last line names the problem, for example `pages[2] (homeassistant): ...`, `pages[0] (clok): unknown page type; available: ...`, `pages[0].api_key: environment variable OCTOPRINT_KEY is not set` (the secret is missing in the Configuration tab) or `refresh must be at least ...`. A YAML error (for example wrong indentation) starts with `/config/config.yaml: invalid YAML:` and takes a few lines with the line and column. Fix it and start the add-on again. |
| A change has no effect | The add-on was not restarted | Restart the add-on after every change of `config.yaml` or of a secret. |
| `config.yaml` cannot be found | The file is in the add-on's config folder, not in Home Assistant's own config folder | Look in `/app_configs/<id>_glancebox/` (older versions: `/addon_configs/<id>_glancebox/`). File editor is limited to Home Assistant's config folder while its option "Enforce basepath" is on. If the folder is empty, create `config.yaml` with the starter content from the web UI (Step 4). |
| The display shows nothing, or the web UI keeps saying "Waiting for your display" | The display has a wrong address | Check the address on the display: `http://`, the IP address of Home Assistant, port 8090. Display and Home Assistant must be in the same network. Open `http://192.168.1.x:8090/healthz` in a browser: it answers with one line of JSON that starts with `{"version":` and the version number. If it does not, the display cannot reach the add-on either. |
| `http://192.168.1.x:8090/` in a browser shows `{"detail":"Not Found"}` | Nothing is wrong | The overview exists only in the add-on's web UI inside Home Assistant. Port 8090 serves only the display. To check it, open `/healthz`. |
| The web UI says "The server address could not be determined" | The add-on's port is switched off | Open the add-on's **Configuration** tab, section **Network**, and enter a port (8090) for the display port. Save and restart the add-on. |
| The add-on does not start: `Cannot start app ... because port 8090 is already in use` | Another add-on or program uses port 8090 | Change the port in the **Configuration** tab, section **Network**, and use the new port in the display's address. |
| A page shows "Cannot reach Home Assistant", or a tile shows "missing" | Home Assistant did not answer, or an entity id does not exist | Check the entity id in **Settings → Devices & services → Entities**. The web UI shows the error in red under the page's preview. |
| The weather is for the wrong place | The home location in Home Assistant is not where you want the weather | Set `location:` on the `weather` page (see [Examples](#weather-at-another-place-weather)). |

## Security

- The add-on has **admin access to Home Assistant**. Home Assistant offers add-ons API access only
  as an administrator; the add-on uses it to read entity states and the home settings. The access
  token belongs to the add-on and is revoked when you uninstall it.
- The **display port (8090) has no login.** It only serves the pictures and accepts pushed data
  with the push key. Keep it in your LAN; do not forward it to the internet.
- The overview with previews is only in the add-on's web UI, behind your Home Assistant login.
