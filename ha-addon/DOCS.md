# Glance Box

This add-on runs the Glance Box server inside Home Assistant. It renders web pages into small
pictures, and your Glance Box display (a GeekMagic SmallTV Ultra with the Glance Box firmware)
shows them in rotation.

## Before you start: flash the display once

The display needs the Glance Box firmware. You flash it **once in the browser** through the stock
firmware's update page, no soldering: <https://robinlanger.github.io/glancebox/guide/3-flash-the-firmware/>.
After that, everything happens in Home Assistant.

## First start

Start the add-on. Without any settings it creates a starter playlist: a **clock** and the
**weather** at your Home Assistant home location. Time zone, language (German or English) and
location come from Home Assistant.

Click **Open web UI** on this page (switch on **Show in sidebar** to have it one click away). The box "Connect your display" shows the server address, for
example `http://192.168.x.x:8090`. Enter it in the display's setup portal (or later on its device
page). The display then shows your pages.

## Change the pages

The playlist is `config.yaml` in the add-on's config folder. In the File editor (or Studio Code
Server) it is under `/addon_configs/<id>_glancebox/config.yaml`. If that folder is empty (the add-on
could not save the starter file there), the web UI shows the starter content: create
`config.yaml` with it in the File editor. Restart the add-on after editing.
All page types and options are described at <https://robinlanger.github.io/glancebox/templates/>.

Home Assistant entities need no token here: a `homeassistant` page without `url` and `token` reads
directly from this Home Assistant.

```yaml
pages:
  - type: clock
  - type: weather
    refresh: 60
  - type: homeassistant
    title: Solar
    entities:
      - sensor.pv_power
```

Anything you set in `config.yaml` wins over the values from Home Assistant (for example
`timezone:`, `lang:`, or `location:` on a weather page).

## Configuration (secrets)

The Configuration tab holds only secrets. All fields are optional.

- **Push key**: for the Claude usage page (`ai` with `provider: claude`). Used automatically.
- **Anthropic / OpenAI / xAI / GitHub Copilot keys**: for the `ai` page with the matching provider.
  In `config.yaml` write them as `${ANTHROPIC_ADMIN_KEY}`, `${OPENAI_ADMIN_KEY}`,
  `${XAI_MANAGEMENT_KEY}`, `${GITHUB_COPILOT_TOKEN}`.
- **More secrets**: name/value pairs for your own pages, used as `${NAME}`.

Restart the add-on after changing them.

## Security

- **Admin access to Home Assistant:** the add-on uses Home Assistant's API so the
  `homeassistant` page works without a token. Home Assistant grants add-ons this access only as
  an administrator. The add-on only reads entity states and the home settings. The access token
  belongs to this add-on and is revoked when you uninstall it.
- **Display port (8090) has no login.** It serves only the pictures for the display and accepts
  pushed data with the push key. Keep it in your LAN; do not forward it to the internet.
- The overview with previews is only in the add-on's web UI, behind your Home Assistant login.
- **Chromium** (which renders the pages) does not get the Home Assistant access token or your
  secrets in its environment. It tries to run with its sandbox; where the add-on container does
  not allow that (usually the case), it runs without it and the log says so once. This does not
  make untrusted web pages safe: only add `url` pages you trust.
