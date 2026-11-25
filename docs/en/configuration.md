# Server configuration

The whole server is configured by one file, `config.yaml`. Start from `config-example.yaml`.

## Where the file lives

With the supplied `docker-compose.yml` the server reads `./config.yaml` from the project folder (mounted read-only at `/config/config.yaml`). Your own pages go into `./pages-custom` (mounted at `/config/pages`, see [Writing pages](writing-pages.md)). **Create that folder before the first start** (`mkdir pages-custom`), otherwise Docker creates it as root.

After every change restart the server:

```sh
docker compose restart
docker compose logs --tail 50
```

The server checks the file at startup. If something is wrong (a typo in a key, an unknown page type, a refresh below the minimum) it refuses to start and prints a clear message to the log.

## Top-level options

| Key | Default | Meaning |
| --- | --- | --- |
| `interval` | `30` | Default display time of a page in seconds. |
| `timezone` | `Europe/Berlin` | Time zone for clocks and times on pages (IANA name). |
| `lang` | `de` | Default language of the built-in pages (`de` or `en`). |
| `custom_pages_dir` | not set | Folder with your own page types. Relative paths are relative to the config file. It may be missing, the server then logs a warning and uses the built-in pages only. In Docker use `/config/pages`. |
| `push_key` | not set | Key for pushed data (needed by the `ai` page with provider `claude`). At least 16 characters, ASCII only (letters, digits, `-`, `_`); generate one with `openssl rand -hex 24`. Without it the push endpoint is off. Use it on your home network only (LAN). Put it in `.env` and write `push_key: ${GLANCEBOX_PUSH_KEY}`. |
| `pages` | required | The playlist, at least one page. |

Unknown top-level keys are rejected.

## Secrets and environment variables

Never write tokens or keys into `config.yaml`. Put them in a file called `.env` next to `docker-compose.yml`, one `NAME=value` per line, and refer to them in the config:

```yaml
push_key: ${GLANCEBOX_PUSH_KEY}
```

- Only a value that is exactly `${NAME}` is replaced. Inside a longer text such as `http://${HOST}:3001` it stays literal text.
- The server refuses to start if the variable is missing or empty and names the place in the file, for example `pages[2].token: environment variable KUMA_TOKEN is not set`.
- A replaced value is always text. Options that need a number, such as `refresh` or `budget`, cannot use `${NAME}`.
- Docker reads `.env` only when the container is created. After a change run `docker compose up -d`; `docker compose restart` does not apply it.
- The supplied `docker-compose.yml` loads `.env` with `env_file` and `path`/`required: false`, so the file may be missing. This form needs Docker Compose 2.24 or newer (`docker compose version`).

## Options every page has

```yaml
pages:
  - type: clock
    duration: 15
    refresh: 60
```

| Key | Default | Meaning |
| --- | --- | --- |
| `type` | required | Page type: `url`, `bahn`, `clock`, `weather`, `kuma`, `homeassistant`, `energy`, `printer`, `ai` or one of your own. The ready-made ones are described in the [template catalog](templates/README.md). |
| `duration` | `interval` | How many seconds the page stays on the display. |
| `refresh` | `duration` | A page is rendered again at most every `refresh` seconds. Use a larger value for data that changes slowly or for services that limit requests. A page type can have its own default and minimum, for example `energy`: default 5, at least 2; `printer`: default 10, at least 5. |

All other keys belong to the page type and are described below. Ready-made pages with preview pictures are in the [template catalog](templates/README.md).

## Page type: url

Renders a web page as it is, in a browser window of exactly 240x240 pixels.

```yaml
- type: url
  url: http://homeserver.lan/status-240
  wait_for: "#ready"
  wait_ms: 500
  duration: 15
  refresh: 30
```

| Key | Default | Meaning |
| --- | --- | --- |
| `url` | required | `http://` or `https://` address. |
| `wait_for` | none | CSS selector. The screenshot is taken only after an element matching it exists. Use this for pages that build their content with JavaScript. |
| `wait_ms` | `0` | Extra pause in milliseconds before the screenshot (after the page loaded and `wait_for` matched). |
| `timeout_s` | `15` | How long loading and `wait_for` may take before the page counts as failed. |

The server runs in a container. `localhost` there means the container itself, so use the LAN address or name of the other machine. Pages that need a login show the login screen. Tips for designing such pages are in [Writing pages](writing-pages.md#the-url-page-and-its-tips).

## Page type: bahn

Live departures for a German station, from [DBF](https://dbf.finalrewind.org) (db-infoscreen).

```yaml
- type: bahn
  station: "Frankfurt(Main)Hbf"
  via: [Wiesbaden, Mainz]
  platforms: "101,102"
  limit: 4
  title: "Frankfurt"
  refresh: 60
```

| Key | Default | Meaning |
| --- | --- | --- |
| `station` | required | Station name, EVA number or DS100 code. Find the exact name on dbf.finalrewind.org: the part of the address after the search. |
| `via` | all | Only trains that stop at one of these places **after** your station (text or list). Intermediate stops work better than final destinations, because they also catch trains that end earlier. |
| `platforms` | all | Only these platforms (text or list). |
| `limit` | `4` | Rows, 1 to 6. Fewer rows mean bigger text. |
| `title` | the station | Header text. |
| `dbf_url` | `https://dbf.finalrewind.org` | Address of a DBF instance, if you run your own. |
| `refresh` | `60` | **At least 60.** This is DBF's rule of one request per station and minute. If you do not set `refresh` it is raised to 60 automatically. If you set a value below 60 the server refuses to start. |

If DBF cannot be reached the page shows "Keine Daten", an empty list shows "Keine Abfahrten". Full description: [bahn](templates/bahn.md).

## Page type: clock

A large clock with weekday and date, meant as the starting point for your own pages. Full description: [clock](templates/clock.md).

```yaml
- type: clock
  lang: en
  refresh: 60
```

| Key | Default | Meaning |
| --- | --- | --- |
| `lang` | top-level `lang` | `de` or `en`. |

## Page type: weather

Current weather, today's high and low and the next 4 hours, from [Open-Meteo](https://open-meteo.com) (free, no key). Full description: [weather](templates/weather.md).

```yaml
- type: weather
  location: Frankfurt am Main     # or latitude: / longitude:
```

## Page type: kuma

The state of your server from an [Uptime Kuma](https://github.com/louislam/uptime-kuma) status page: a big "14/14 OK", or a red header with the services that are down. No token and no rights on your server. Full description, including how to install Uptime Kuma: [kuma](templates/kuma.md).

```yaml
- type: kuma
  url: http://homeserver.lan:3001
  slug: homelab
  refresh: 30
```

## Page type: homeassistant

Live values of up to six [Home Assistant](https://www.home-assistant.io/) entities, as tiles (1 to 4) or a list (up to 6). Needs a long-lived access token; put it and the address in `.env`, see [Secrets and environment variables](#secrets-and-environment-variables). The token has all the rights of its user, so use a separate user. Full description: [homeassistant](templates/homeassistant.md).

```yaml
- type: homeassistant
  url: ${HA_URL}
  token: ${HA_TOKEN}
  title: Solar
  refresh: 30
  entities:
    - sensor.pv_power
    - entity: sensor.grid_power
      label: Grid
```

## Page type: energy

Energy flow from Home Assistant in 1 to 4 rows (`grid`, `pv`, `battery`, `gas`, `water`, `wallbox`), each with a power or flow sensor. On firmware 0.7.0 or newer the display draws moving arrows in the direction of the flow; older firmware shows a still picture. Without `refresh` the page uses 5 seconds. Address and token as for `homeassistant`. Full description, signs and options: [energy](templates/energy.md).

```yaml
- type: energy
  url: ${HA_URL}
  token: ${HA_TOKEN}
  title: Power
  rows:
    - type: grid
      entity: sensor.grid_power
    - type: pv
      entity: sensor.pv_power
    - type: battery
      entity: sensor.battery_power
      soc: sensor.battery_level
```

## Page type: printer

State, progress, time left and temperatures of one 3D printer, with the slicer's preview picture. `source:` says where the status comes from: `moonraker` (Klipper), `octoprint`, `prusalink` directly from the printer, or `hass` with a preset for the printer's Home Assistant integration (`moonraker`, `octoprint`, `prusalink`, `bambu_lab`, `creality` or `custom`). Without `refresh` the page uses 10 seconds, at least 5. Keys and passwords belong in `.env`, see [Secrets and environment variables](#secrets-and-environment-variables). Not yet checked against a real printer. Full description, options and setup per source: [printer](templates/printer.md).

```yaml
- type: printer
  source: moonraker
  url: http://drucker.local:7125
  # api_key: ${MOONRAKER_KEY}
```

## Page type: ai

How much of an AI plan or budget you have used, one provider per page: `claude` (plan limits, sent by Claude Code on your computer), `anthropic-api`, `openai-api`, `xai-api` (cost or credit) and `copilot` (monthly usage). Keys belong in `.env`, see [Secrets and environment variables](#secrets-and-environment-variables). Full description and setup per provider: [ai](templates/ai.md).

```yaml
- type: ai
  provider: claude
  refresh: 30
```

## How the playlist behaves

- The page currently shown follows from the **clock**: the durations of all pages add up to one cycle, and the position in the cycle is the current time modulo that sum. The server keeps no state per device, so several displays show the same page at the same time.
- The display asks the server for the next picture after the time the server names. That time is always between 2 and 30 seconds. The picture only travels if it changed, otherwise the server answers "not modified".
- Pictures are baseline JPEGs of 240x240 pixels and at most 24 576 bytes. The server lowers the quality (from 85 down to 40) until a picture fits. Very detailed images (photos, fine gradients) may still fail, flat colors work best.
- If a page fails (data source down, template error), the server keeps showing its **last good picture for up to 10 minutes**. After that the page is skipped. If no page works at all, the display shows an error page instead of a black screen. Errors are in the log and on the preview page.

## Checking and operating the server

| Address | What it does |
| --- | --- |
| `http://<server>:8080/` | Preview of all pages with age and last error (refreshes itself). |
| `http://<server>:8080/preview/<n>.jpg` | The current picture of page number `n` (counting from 0). |
| `http://<server>:8080/healthz` | Small JSON for health checks (Docker uses it). Answers 503 while the renderer or its browser is down. |
| `http://<server>:8080/api/v1/frame` | What the display fetches. |

The server runs as a normal (non-root) user and has **no login**. Keep port 8080 inside your home network. To use another port change the left number in `ports:` of `docker-compose.yml`, for example `"9090:8080"`.

Updates of the server: `git pull` and `docker compose up -d --build`. Releases also publish a ready-made image, `ghcr.io/robinlanger/glancebox:<version>`, for amd64 and arm64.
