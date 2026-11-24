# Home Assistant add-on

If you run Home Assistant OS, you can run the Glance Box server as a Home Assistant add-on instead
of Docker Compose. Install, start, enter one address in the display, done.

## What you need

- **Home Assistant OS** (or a Supervised install). Home Assistant Container and Core have no
  add-ons; use the [Docker setup](guide/2-start-the-server.md) there.
- A display with the Glance Box firmware. You flash it **once in the browser**, no soldering:
  [Flash the firmware](guide/3-flash-the-firmware.md). After that, everything happens in Home Assistant.

## Install

[![Add the repository to my Home Assistant](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Frobinlanger%2Fglancebox)

The button opens your Home Assistant and adds this repository to the add-on store. Without it:
**Settings → Add-ons → Add-on store → ⋮ → Repositories**, add
`https://github.com/robinlanger/glancebox`. Then open **Glance Box**, click **Install** and
**Start**.

## First start

Without any settings the add-on creates a starter playlist: a **clock** and the **weather** at
your Home Assistant home location. Time zone, language (German or English) and location come
from Home Assistant, so there is nothing to fill in.

## Connect the display

On the add-on page click **Open web UI** (switch on **Show in sidebar** there to have it one
click away). The box "Connect your display" shows the server
address, for example `http://192.168.x.x:8090`. Enter it in the display's setup portal
([Set up Wi-Fi](guide/4-set-up-wifi.md)) or later on its device page.

## Change the pages

The playlist is `config.yaml` in the add-on's config folder. In the File editor or Studio Code
Server it is `/addon_configs/<id>_glancebox/config.yaml`. It uses the same format as the
[configuration](configuration.md) of the Docker setup, with two differences:

- `timezone`, `lang` and the location of a `weather` page are optional; without them the values
  from Home Assistant are used. Values you set always win.
- A `homeassistant` or `energy` page needs neither `url` nor `token`; it reads from this Home Assistant.

If that folder is empty (the add-on could not save the starter file there), the add-on's web UI
shows the starter content: create `config.yaml` with it in the File editor.

Restart the add-on after editing.

## Secrets

The add-on's **Configuration** tab holds only secrets, all optional: the push key for the Claude
usage page (used automatically), the keys for the `ai` page providers (in `config.yaml` as
`${ANTHROPIC_ADMIN_KEY}`, `${OPENAI_ADMIN_KEY}`, `${XAI_MANAGEMENT_KEY}`,
`${GITHUB_COPILOT_TOKEN}`), and "More secrets" for your own pages (`${NAME}`). Secrets never
need to be written into `config.yaml` in plain text.

## Security

- The add-on has **admin access to Home Assistant**. Home Assistant offers add-ons API access only
  as an administrator; the add-on uses it to read entity states and the home settings. The access
  token belongs to the add-on and is revoked when you uninstall it.
- The **display port (8090) has no login.** It only serves the pictures and accepts pushed data
  with the push key. Keep it in your LAN; do not forward it to the internet.
- The overview with previews is only in the add-on's web UI, behind your Home Assistant login.
