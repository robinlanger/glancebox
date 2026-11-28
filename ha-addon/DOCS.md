# Glance Box

This add-on runs the Glance Box server inside Home Assistant. It renders web pages into small
pictures, and your Glance Box display (a GeekMagic SmallTV Ultra with the Glance Box firmware)
shows them in rotation.

Step-by-step guide with examples and troubleshooting:
<https://robinlanger.github.io/glancebox/home-assistant/>

## Setup in five steps

1. **Flash the display once.** It needs the Glance Box firmware. You flash it once in the browser
   through the stock firmware's update page, no soldering:
   <https://robinlanger.github.io/glancebox/guide/3-flash-the-firmware/>.
2. **Start the add-on.** Without any settings it creates a starter playlist: a **clock** and the
   **weather** at your Home Assistant home location. Time zone, language (German or English) and
   location come from Home Assistant.
3. **Open the web UI** on this page (switch on **Show in sidebar** to have it one click away). It
   shows the box "Connect your display" and previews of your pages.
4. **Enter the address** from that box, for example `http://192.168.1.x:8090`, on the display: in
   the setup portal's field **Server URL**, or later on the display's device page. Only
   `http://` works. The web UI then says "Display connected".
5. **Edit `config.yaml` and restart the add-on.** The playlist is `config.yaml` in the add-on's
   config folder, `/app_configs/<id>_glancebox/config.yaml` (older Home Assistant versions:
   `/addon_configs/…`). You need an editor from the official App store for this, for example
   File editor, Studio Code Server or Terminal & SSH. File editor's documentation says its
   option "Enforce basepath" (on by default) limits it to Home Assistant's own config folder;
   switch it off first. If the folder is empty (on Home Assistant OS 18.4 the add-on could not
   save the starter file there), the web UI shows the starter content: create `config.yaml` with
   it. The add-on reads the file only at start, so restart it after every change.

All page types and options: <https://robinlanger.github.io/glancebox/templates/>.

## A typical first playlist

A `homeassistant` or `energy` page, or a `printer` page with `source: hass`, needs no `url` and
no `token`: it reads directly from this Home Assistant.

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

Anything you set in `config.yaml` wins over the values from Home Assistant (for example
`timezone:`, `lang:`, or `location:` on a weather page). For 12-hour times (`2:05 PM`) add
`time_format: 12h` above `pages:`; there is no form field for it.

## Configuration (secrets)

The Configuration tab holds only secrets. All fields are optional.

- **Push key**: for the Claude usage page (`ai` with `provider: claude`). Used automatically.
- **Anthropic / OpenAI / xAI / GitHub Copilot keys**: for the `ai` page with the matching provider.
  In `config.yaml` write them as `${ANTHROPIC_ADMIN_KEY}`, `${OPENAI_ADMIN_KEY}`,
  `${XAI_MANAGEMENT_KEY}`, `${GITHUB_COPILOT_TOKEN}`.
- **More secrets**: name/value pairs for your own pages, used as `${NAME}`. Also for the key or
  password of a `printer` page that reads the printer directly, for example `OCTOPRINT_KEY` used
  as `api_key: ${OCTOPRINT_KEY}`.

Restart the add-on after changing them.

## Troubleshooting

- **The add-on stops right after Start:** an error in `config.yaml`. The last lines of the
  **Log** tab name it. Fix it and start again.
- **A change has no effect:** restart the add-on.
- **The display stays empty:** check the address on the display: `http://`, the IP address of
  Home Assistant and port 8090. Open `http://192.168.1.x:8090/healthz` in a browser; it should
  answer with the version. (`/` on that port says `{"detail":"Not Found"}`; the overview is only
  in the web UI.)

More problems and their fixes:
<https://robinlanger.github.io/glancebox/home-assistant/#troubleshooting>

## Security

- **Admin access to Home Assistant:** the add-on uses Home Assistant's API so the
  `homeassistant` and `energy` pages work without a token. Home Assistant grants add-ons this access only as
  an administrator. The add-on only reads entity states and the home settings. The access token
  belongs to this add-on and is revoked when you uninstall it.
- **Display port (8090) has no login.** It serves only the pictures for the display and accepts
  pushed data with the push key. Keep it in your LAN; do not forward it to the internet.
- The overview with previews is only in the add-on's web UI, behind your Home Assistant login.
- **Chromium** (which renders the pages) does not get the Home Assistant access token or your
  secrets in its environment. It tries to run with its sandbox; where the add-on container does
  not allow that (usually the case), it runs without it and the log says so once. This does not
  make untrusted web pages safe: only add `url` pages you trust.
- **What pages can reach:** pages cannot reach the Supervisor or other Home Assistant internals.
  A `url` page may load everything from its own host, so it may show another add-on by its host
  name (for example `url: http://a0d7b954-grafana:3000/`).
- The limits of these protections are listed in
  [SECURITY.md](https://github.com/robinlanger/glancebox/blob/main/SECURITY.md), including that
  without the sandbox the server's start environment stays readable to other processes of the
  same user.
