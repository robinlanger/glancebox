# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/). Firmware and server share one version (`VERSION`).

## [Unreleased]

### Security
- Firmware: on a device that is already set up, the setup Wi-Fi `GlanceBox-XXXX` is now protected
  with WPA2; its Wi-Fi password is the update password. Before, anyone in range could join it while
  the saved network was gone and store new Wi-Fi credentials without the password. The first setup
  still uses an open Wi-Fi. The setup portal also no longer offers WiFiManager's restart, exit,
  close and info pages.
- Firmware: a server URL typed in the setup portal or on the device web page may no longer contain
  quotes, `<`, `>`, a backtick, inner spaces, control characters or non-ASCII characters. A URL
  already stored on the device keeps working.
- Firmware: the reply header of the frame request must now be complete within 8 seconds of
  starting the request, and it may be at most 1024 bytes long. Before, a wrong or
  impersonated server could send header lines slowly without end; the display then hung and its
  web page (settings, updates) no longer answered, even after a restart. The offline screen now
  shows "server too slow", "reply too large" or "bad reply" in these cases.

## [0.6.1]

Server and add-on update; the firmware is unchanged (no need to update the display).

### Changed
- The example configuration is now `config-example.yaml` (was `config.example.yaml`): Home
  Assistant read every `config.*.yaml` in the repository as an add-on and logged a warning.
  Existing `config.yaml` files are not affected.

### Fixed
- Home Assistant add-on: a refused API access (HTTP 401/403) now stops at once with "refused
  access" instead of being retried and reported as "not reachable".
- Home Assistant add-on: a repeated name under "More secrets" is ignored with a warning (the first
  one counts) instead of silently replacing the earlier value.
- Home Assistant add-on: `timezone:` or `lang:` left empty in `config.yaml` now uses the value from
  Home Assistant instead of failing.

## [0.6.0]

Server update with a new way to run it: the Home Assistant add-on. The firmware is unchanged
(no need to update the display). Docker users update the image as described in
docs/en/updating.md; Home Assistant OS users can install the add-on, see
docs/en/home-assistant.md.

### Added
- Home Assistant add-on (`ha-addon/`, repository file `repository.yaml`): the server installs from
  the add-on store, starts with a clock + weather playlist using Home Assistant's time zone,
  language and home location, keeps secrets in the add-on form, and shows the display address and
  page previews in the add-on's web UI (Ingress, behind the HA login). A `homeassistant` page needs no
  token there. In add-on mode the LAN port serves only frames, push and health.
- New look for the server overview (light and dark, same style as the device page). In the
  add-on it opens with a "Connect your display" card: the address to copy, three setup steps and
  a live status that shows whether a display is fetching pictures.

## [0.5.1]

Server update; the firmware is unchanged (no need to update the display). Update the Docker
image as described in docs/en/updating.md.

### Added
- ai page: option `show: remaining` shows how much of a limit is left instead of used. The bar
  starts full at 100 % and drains towards 0 %; the color still follows what is used, so red
  always means little is left. Over-use shows `0 %`, a reset window `100 %`, copilot shows what
  is left of the allowance (`88 / 300`). Default stays `used`. (#6)
- Project website at https://robinlanger.github.io/glancebox/ (English) and `/de/` (German):
  a landing page and a guided five-step setup, built from `docs/` with MkDocs Material and
  published by `.github/workflows/pages.yml`. It loads nothing from other hosts.
- The docs parity check also compares front-matter keys between English and German.

### Changed
- ai page: `claude` and `anthropic-api` appear in Claude's colors, dark like claude.ai: warm
  charcoal background, the title in Claude orange (serif), orange bars that turn red from 75 %
  used. Colors only, no logo. The other providers and pages keep their look.

## [0.5.0]

Firmware update for the display; the server is unchanged (no need to update the Docker image).
Update the display over the air as described in docs/en/updating.md.

### Added
- New device web page in an Apple-like look: status tiles (connection, last image, Wi-Fi in
  words, uptime) that refresh every 5 s, grouped settings, light and dark mode, one column on
  phones and two on wide screens. Nothing is loaded from the internet.
- Brightness and night brightness are sliders: the display follows while you drag
  (`POST /api/brightness-preview`, never saved), and the value is saved when you let go.
- Every setting is saved on its own (`POST /api/settings` with any subset of the fields), with a
  check mark or an error message per row; the server address offers Undo. Night mode has a
  switch. The password has its own Change button.
- Firmware upload in the browser computes the MD5 itself and shows a progress bar.

### Security
- Device pages can no longer be framed by other sites (`X-Frame-Options: DENY`,
  `frame-ancestors 'none'`), so the auto-saving controls cannot be clickjacked.
- The embedded CSS/JS are revalidated on every load (`no-cache` + `ETag`) instead of being cached
  for a year, so a script injected once over plain HTTP cannot persist.

### Changed
- The safe-mode page and the message pages use the same look (still no JavaScript in safe mode).
- CSS and JavaScript live in `firmware/web/` and are minified, gzipped and embedded at build time
  (`firmware/scripts/embed_web.py`, `tools/webasset.py`).

### Fixed
- Brightness settings now visibly dim the display. The backlight used a linear duty, so
  20 % looked about half as bright as 100 % and 5 % was only slightly darker. It now follows
  a quadratic curve with a finer PWM range (0 % is still off).

## [0.4.0]

### Added
- `homeassistant` page: live values of up to six Home Assistant entities (REST API with a
  long-lived access token from `.env`) as tiles (1–4) or a list (up to 6). Numbers are rounded,
  W/Wh from 1000 become kW/kWh, on/off becomes words such as `open`/`closed` with colours,
  unavailable entities show `n/a`, unknown ones `missing`. Own notices for no connection and a
  rejected token. Texts in `de` and `en`.
- `tools/ha-sim/`: a simulated Home Assistant (Docker Compose, template entities that change
  over the day) to develop and test the `homeassistant` page without a real smart home.

### Notes
- The firmware code is unchanged from 0.3.0; only its version number changes. This release is
  about the server and its pages.

## [0.3.0]

### Added
- Template library: the `weather` (Open-Meteo forecast), `kuma` (Uptime Kuma status page) and
  `ai` pages. `ai` selects its source with `provider:`: `claude` (5-hour and weekly limits,
  pushed from a Claude Code status line), `anthropic-api`, `openai-api` and `xai-api` (cost or
  balance, optional budget bar) and `copilot` (official GitHub billing usage, needs
  `monthly_allowance`, unit `ai-credits` or `premium-requests`). All pages support `de` and `en`.
- `${VAR}` in `config.yaml` (whole value only, an empty variable is an error) and an optional
  `.env` file that Docker Compose passes to the server, so secrets stay out of the config.
- Top-level `push_key` and `POST /api/v1/push/<channel>`: a key-protected inbox on the home
  network that pages use to receive data. It answers 404 without `push_key`.
- Shared UI macros (`ui.html`) for the page templates and the `glancebox.http.get_json` helper
  with timeout and `glancebox/<version>` User-Agent.
- Status-line scripts for Claude Code in `tools/statusline/` (shell and PowerShell) that push
  the rate limits to the server.
- Template catalog in the docs (`docs/en/templates/`, `docs/de/templates/`) with preview images
  in `docs/img/templates/`; the EN/DE docs parity check now covers subfolders.

## [0.2.0]

### Added
- Night mode: on the device web page set a nightly window (for example 22:00–07:00, may span
  midnight) and a night brightness from 0 to 100 %; 0 % turns the backlight off. `/status`
  reports `local_time` and `night`.
- Server: every frame response carries `X-Local-Time: HH:MM:SS` in the configured `timezone`;
  the display uses it as its clock. Night mode needs both firmware and server 0.2.0.

### Fixed
- The backlight is now fully dark while the display initialises (it was at 5 %).

## [0.1.0]

First release of Glance Box: a Docker server that renders pages to 240x240 JPEG frames and
firmware for the GeekMagic SmallTV Ultra (ESP8266) that shows them.

### Added
- Server (multi-arch image, amd64 and arm64, runs as non-root on port 8080): playlist of pages
  with per-page `duration` and `refresh`, headless rendering to baseline JPEG (240x240, at most
  24 576 bytes), frame endpoint `GET /api/v1/frame` with `ETag`/`304` and a clamped `X-Next-In`,
  last-good-frame fallback (600 s) and an error frame instead of a black screen.
- Built-in `bahn` page that respects the 60 s minimum refresh.
- Built-in `clock` page; host port of the Docker setup configurable with `GLANCEBOX_PORT` in `.env`.
- Firmware: Wi-Fi setup portal (`GlanceBox-XXXX` access point), stream-decoded JPEG frame loop,
  offline status screen after 120 s without a frame, DE/EN device web UI with `/status`.
- OTA updates over HTTP with Basic auth and a mandatory MD5; a wrong checksum or a bad image is
  rejected and the running image stays untouched.
- Boot-loop protection: boot counter in RTC memory, safe mode after 3 failed boots.
- Release pipeline (firmware `.bin` with `.md5`/`.sha256`, GHCR image, GitHub release) and the
  on-hardware OTA smoketest (`tools/ota-smoketest.sh`).
