# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/). Firmware and server share one version (`VERSION`).

## [Unreleased]

## [0.7.1]

The `ai` page with `provider: claude` now also gets its limits when you use Claude Code without
its terminal view (T3 Code, the desktop app, an IDE extension): a hook script asks Claude Code
for its usage report after an answer and sends it. Server and scripts only; no firmware change.
If you use the status-line script, replace your copy of `glancebox-statusline.sh` (see Security).

Checked on macOS with Claude Code 2.1.330 (2026-11-24): a headless session (`claude -p`) fires
the hooks `Stop` and `PostToolUse`; the real script, started by a real `Stop` hook, delivered a
real usage report to a local test listener; a session with a tool call sent one report at once
and a second one a minute later, and left no process or marker file behind; the provider turned
a real report into the two rows.
Not checked: the PowerShell scripts (the new hook and the stamp line added to the status-line
script; never run, no Windows available), the changed status-line script in a live terminal
session, Linux, a live session in T3 Code or the desktop app, the display itself, and the Home
Assistant add-on.

### Added
- Hook scripts `tools/statusline/glancebox-usage.sh` (macOS, Linux) and `glancebox-usage.ps1`
  (Windows) for the Claude Code hooks `Stop` and `PostToolUse`. They return at once and print
  nothing; in the background they run `claude -p "/usage"` (about 3 seconds, no tokens, no saved
  session) and post the line with the usage report to `/api/v1/push/claude` with the same
  `push.env`. At most one fetch per minute (`usage.stamp` beside `push.env`); a hook inside
  that minute leaves one fetch waiting for its end, so the last answer of a burst is sent too.
  The status-line scripts write the same stamp when they send, and a waiting fetch is dropped
  when the stamp changes. The usage report is marked experimental by Anthropic; without one
  (older Claude Code, API key, error) nothing is sent and the page keeps its last values. Docs:
  "Claude Code in other apps" on the `ai` page.
- Second push format for `provider: claude`: the server now also keeps the key `usage_report`
  of a push and shows its 5-hour window (`session`) and week (`weekly_all`). The weekly limit
  per model is not shown. Pushes with `rate_limits` from the status line work as before.

### Security
- `glancebox-statusline.sh` no longer passes the push key on curl's command line, where other
  users of the same computer could read it with `ps` during a request. The key now goes to curl
  through its standard input. Replace your copy of the script.

## [0.7.0]

New page type `energy` with moving arrows drawn by the display. Update the server and the
firmware together: the arrows need the new firmware. With older firmware the page works as a
still picture.

Checked on one GeekMagic SmallTV Ultra against a Home Assistant with simulated sensors
(2026-11-23 to 2026-11-24): how the arrows look and move on both energy pages, no visible edge
around the tracks, the device page and an OTA update while the arrows run, the offline screen
when the server goes away, and a run of 20 hours (ended early, after the beta had run with no
problems): no restart, free memory stable, in 5.6 hours of animation 3 pauses over 100 ms and
none over 250 ms. A network outage of the server during the run did not need a restart. Night mode
with brightness 0 while the arrows run: checked afterwards, the display stays dark (2026-11-24).
Home Assistant add-on with the arm64 image, checked afterwards (2026-11-24): installed from the
add-on store on a Raspberry Pi 4 (Home Assistant OS 18.5), both energy pages read the simulated
sensors directly from this Home Assistant (no token in the config), and the display ran the arrows
from the add-on for almost 10 minutes with no pause over 100 ms. After a changed grid value the add-on sent that arrow in the other direction.

### Added
- Page type `energy`: energy flow from Home Assistant in 1 to 4 rows of the types `grid`, `pv`,
  `battery`, `gas`, `water` and `wallbox`, each with an icon, a track, the value and a status
  line (direction, battery level). Options: `title`, `animate`, `url`, `token` (not needed in
  the add-on), `lang`, `refresh` (default 5, at least 2) and per row `type`, `entity`, `soc`
  (battery level, battery only), `invert`, `full` (value for full arrow speed) and `min`
  (smaller values count as 0). Signs follow the Home Assistant energy dashboard: grid positive
  = import, battery positive = discharging.
- Firmware: draws moving arrows on the tracks described by the new `X-Anim` response header of
  the frame, also while the next frame is fetched and decoded. Frames without the header are
  shown as before.
- Firmware: `/status` has the new fields `frame_errors` (failed frame requests since boot),
  `anim_tracks` (tracks animated now), `anim_gaps_100` and `anim_gaps_250` (pauses of the
  animation longer than 100 or 250 ms) and `anim_run_s` (seconds of animation since boot).
- Own pages: `DEFAULT_REFRESH` in `page.py` sets the page's default `refresh` when the page
  entry has none.

## [0.7.0-beta.1]

**Beta (pre-release).** Try it if you like to test new things; the stable version stays 0.6.3.
Docker: use the image `ghcr.io/robinlanger/glancebox:0.7.0-beta.1` (`:latest` stays on 0.6.3).
Display: upload `glancebox-ultra-0.7.0-beta.1.bin` on the device page. The Home Assistant add-on
store does not offer betas.

First beta of 0.7.0. The changes are listed under 0.7.0.

## [0.6.3]

Firmware update for the device web page and the setup portal. The server and the Home Assistant
add-on are unchanged apart from the version number; update the display.

### Fixed
- Device web page: after the browser's password prompt, a slider no longer keeps following the
  pointer. Dragging a slider no longer brings up the prompt; it comes with the save when you let
  go. Until the browser knows the password, the display changes only on release (#20).
- Setup portal: a device with a valid update password but an invalid stored server URL now
  shows "Current update password" and keeps its password when the new-password fields are
  empty. On 0.6.2 such a device was stuck with "wrong password" (#22).

### Changed
- An empty Server URL field now reports "Server URL is required" instead of "host is missing",
  in the setup portal and on the device web page (#22).
- The setup portal checks server URL, update password, brightness and current password before
  it connects to Wi-Fi. An invalid form comes back at once with the error; before, the portal
  connected first, reported success and reopened with the error afterwards. The Server URL
  field shows the example `http://192.168.x.x:8090` and is marked as required (#22).
- A new update password is asked for twice: in the setup portal and on the device web page,
  with and without JavaScript. It is stored only when both entries match. `POST /api/settings`
  now needs `password_repeat` next to `password` to set a new password; a call with only
  `password` gets HTTP 400 (#21).

### Security
- The setup portal no longer writes entered passwords back into the page source (before, they
  appeared there after a failed Wi-Fi connection). WiFiManager's separate parameter pages
  `/param` and `/paramsave`, which took the same fields without the check, are blocked (#22).

## [0.6.2]

Security release for server, Home Assistant add-on and firmware, after a review of the whole
project. Update the server or add-on and the display. The firmware changes passed the unit tests
and the build; they were not yet tested on a real device when this version was tagged.

### Security
- Chromium (which renders the pages) now starts with only a short list of harmless environment
  variables (`PATH`, `HOME`, locale, time zone and similar). Tokens and keys are no longer
  inherited by it.
- Chromium first tries to start with its sandbox. Where the container does not allow it (usual
  under Docker's default seccomp profile and in the add-on), it starts without it as before and
  logs one warning.
- Pages can no longer make the browser reach Home Assistant internal targets (`supervisor`,
  `homeassistant`, `localhost`, any `*.localhost` or `*.local.hass.io` name, the Home Assistant
  internal networks `172.30.32.0/23`, `172.30.232.0/23` and `fd0c:ac1e:2100::/48`, loopback,
  link-local, `0.0.0.0/8`, `::`). All page traffic, including redirects and WebSockets, goes
  through a filtering proxy inside the server that checks the name and every address it resolves
  to and connects only to the address it checked, so a name that resolves to an internal address
  is refused too. Addresses in your own LAN, including the LAN address of the Home Assistant host,
  stay reachable. A `url` page may still load everything from its own host; if that host is a
  name with a dot, it must not resolve to one of the blocked addresses. A host name without a
  dot is not checked by address, so a `url` page may show another add-on by its host name (for
  example `http://a0d7b954-grafana:3000/`). If the `url` page itself is refused or cannot be
  reached, the refresh fails and the display keeps its last picture. Service workers are
  disabled, and a proxy connection lasts at most 120 seconds.
- Addresses in error texts and logs no longer show credentials or query strings: in every
  `http(s)://` address, `user:password@` becomes `***@` and `?…` or `#…` becomes `?***`; the
  `url: /path?…` form in connection errors is masked the same way. This covers the last error
  shown on the overview page, the server log, invalid-YAML and invalid `url` messages, and the
  logs of the `homeassistant`, `kuma` and `bahn` pages. A secret that is part of the path itself
  (webhook-style addresses) is not masked. A failed page refresh logs one warning: the error
  line followed by the traceback, both masked the same way.
- The overview page sends a Content Security Policy: only its own inline script (with a fresh
  nonce on every load) may run, images only from the server itself, no forms, no `<base>`. In
  Docker mode no other site may embed it in a frame; the add-on page stays embeddable so Home
  Assistant can show it in the sidebar. The page and the previews also send
  `X-Content-Type-Options: nosniff`, the page `Referrer-Policy: no-referrer`.
- The server ignores `X-Forwarded-For` and similar proxy headers, so a client cannot claim a
  different address, and sends no `Server` header.
- The supplied `docker-compose.yml` drops all Linux capabilities (`cap_drop: [ALL]`) and sets
  `no-new-privileges`. CI runs the browser tests in the image with the same restrictions. If you
  keep your own compose file, you can add the same two settings.
- Supply chain: the image installs the server's Python dependencies from a lock file with a hash
  for every package, and no longer contains the test tools (`pytest`, `ruff`, `httpx`). Not every
  download is hashed: installing the server package itself fetches its build tool (`setuptools`)
  without a hash, and CI pins its tools `uv` and `pip-audit` by version only. The base image and
  all GitHub Actions are pinned by digest or commit. CI checks the dependencies for known
  vulnerabilities (`pip-audit`), and Dependabot proposes updates weekly. Release images and
  firmware files carry a signed build provenance attestation; `SECURITY.md` shows how to check it
  with `gh attestation verify`.
- Firmware: on a device that is already set up, the setup Wi-Fi `GlanceBox-XXXX` is now protected
  with WPA2; its Wi-Fi password is the update password. Before, anyone in range could join it while
  the saved network was gone and store new Wi-Fi credentials without the password. The first setup
  still uses an open Wi-Fi. The setup portal also no longer offers WiFiManager's restart, exit,
  close and info pages.
- Firmware: a server URL typed in the setup portal or on the device web page may no longer contain
  quotes, `<`, `>`, a backtick, inner spaces, control characters or non-ASCII characters. A URL
  already stored on the device keeps working, and other settings can still be saved with it.
- Firmware: the display no longer shows a user name and password that are part of the server URL
  (`http://user:password@host`); the boot and offline screens show the URL without them.
- Firmware: the reply header of the frame request must now be complete within 8 seconds of
  starting the request, and it may be at most 1024 bytes long. Before, a wrong or
  impersonated server could send header lines slowly without end; the display then hung and its
  web page (settings, updates) no longer answered, even after a restart. The offline screen now
  shows "server too slow", "reply too large" or "bad reply" in these cases.
- Firmware: after five wrong passwords in a row the device web page refuses every password for
  30 seconds (HTTP 429, the page says how long to wait). The lock applies to all clients at once.
  The page also answers only when it is opened by the device's IP address or its own device name;
  any other name gets "open this page by the device's IP address". This blocks websites that try to
  reach the device through DNS rebinding. Open the page by its IP address, as before.

### Changed
- Home Assistant add-on: the secrets from the Configuration tab are available only as `${NAME}`
  in `config.yaml`, no longer as environment variables. Your own `page.py` that reads one with
  `os.environ` must get it through a `${NAME}` option instead. `SUPERVISOR_TOKEN` is removed from
  the environment at start; the `homeassistant` page still gets it automatically, and
  `${SUPERVISOR_TOKEN}` in `config.yaml` still works.

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
