# Writing your own pages

There are two ways to get your own content on the display: point the server at a web page (`url` page), or write a small page type with a Python file and an HTML template (script page). The first needs no programming at all.

## Two kinds of pages

| | `url` page | script page |
| --- | --- | --- |
| What you write | nothing, or a web page that you host yourself | `page.py` and `template.html` |
| Good for | dashboards or status pages that already exist | data from an API, a file or a sensor, shown in your own layout |
| Configuration | `type: url` and `url: ...` | `type: <folder name>` |

## The page contract

A script page is a folder with two files. The folder name is the page type:

```
pages-custom/
  mypage/
    page.py
    template.html
```

### page.py

```python
def fetch(options: dict, ctx) -> dict:
    return {"title": "Hello"}
```

- `fetch(options, ctx)` is **required**. It returns a dict. Every key becomes a variable in the template. It runs in a worker thread (blocking calls such as HTTP requests are fine) and must finish within 20 seconds.
- **Give every network call a timeout**, for example `requests.get(url, timeout=10)`. Better: `from glancebox import http` and `http.get_json(url, params=..., headers=...)`. It sets a 10-second timeout and the User-Agent `glancebox/<version>`, raises on HTTP errors and returns the parsed JSON. The 20-second limit only stops waiting for the result: a call that hangs keeps its worker thread busy, and a few of them can stall all script pages.
- `validate(options)` is optional. Raise `ValueError("...")` to reject a bad configuration. The server then refuses to start and shows your message with the page number.
- `MIN_REFRESH = 60` is optional (an integer). It sets the smallest allowed `refresh` for your page, for example to respect a rate limit.
- Other `.py` files in the same folder can be imported with `from .helper import something`.

`options` holds every key of the page entry in `config.yaml` except `type`, `duration` and `refresh`. `ctx` has four fields:

| Field | Meaning |
| --- | --- |
| `ctx.now` | the current time as a datetime with the time zone from `config.yaml` |
| `ctx.lang` | the top-level `lang` (`de` or `en`) |
| `ctx.timezone` | the time zone name |
| `ctx.pushed(channel)` | the latest data pushed to the server, see [Data pushed to the server](#data-pushed-to-the-server) |

If `fetch` raises an error, the page keeps its last good picture for up to 10 minutes and the error appears in the log and on the preview page. An error in `page.py` while loading (a typo) stops the server at startup with a clear message.

A page may instead catch the error and return data for a picture that says so. The built-in `bahn` page does this on purpose: when DBF cannot be reached it shows "Keine Daten" right away instead of keeping its last picture, because departure minutes that are 10 minutes old would be wrong.

### template.html

A Jinja2 template. Extend `base.html`, which sets up the 240x240 canvas, the dark background, the bundled DejaVu fonts (with umlauts) and these CSS variables: `--bg`, `--header-bg`, `--fg`, `--muted`, `--divider`, `--orange`, `--red`, `--yellow`, `--green`, `--blue`, `--header-alert`.

```html
{% extends "base.html" %}
{% block head %}<style>h1{font-size:28px;margin:20px}</style>{% endblock %}
{% block body %}<h1>{{ title }}</h1>{% endblock %}
```

Values are HTML-escaped automatically. The canvas is exactly 240x240 pixels and nothing scrolls, so anything that does not fit is cut off. On the SmallTV Ultra the housing hides roughly the bottom 6 pixel rows, so keep at least 8 px free at the bottom. The fonts are "DejaVu Sans" and "DejaVu Sans Condensed" (regular and bold). The condensed one gives you more characters per line.

## Building blocks

`base.html` also ships ready-made pieces for the common look. Import the macros in your template:

```html
{% extends "base.html" %}
{% import "ui.html" as ui %}
{% block body %}
{{ ui.header("Server", "14:05", alert=False) }}
<div style="position:absolute;top:50px;left:7px;right:7px">{{ ui.bar(82, "82 %") }}</div>
{% endblock %}
```

- `ui.header(title, clock, alert=False)`: the 34 px title bar with the title on the left and the clock on the right. `alert=True` makes it red (`--header-alert`).
- `ui.notice(message, sub=None, tone="muted")`: a centered message below the header. `tone` is `muted`, `warn` (orange) or `bad` (red).
- `ui.bar(percent, text, height=30)`: a bar filled to `percent` (limited to 0 to 100) with `text` on its right. Green below 75 %, orange from 75 %, red from 90 %.
- `ui.level(percent)`: only the class name (`ui-ok`, `ui-warn` or `ui-bad`) for colouring your own elements.

New CSS variables: `--green` (`rgb(60,200,110)`), `--blue` (`rgb(90,160,255)`) and `--header-alert` (`rgb(150,25,25)`).

## Data pushed to the server

Some data cannot be fetched by the server, because it only exists on another computer. Such a computer can push it to the server instead, and your page reads the latest push. This is meant for your home network (LAN) only.

Declare in `page.py` which channels your page reads and which top-level JSON keys the server keeps:

```python
PUSH_KEYS = {"claude": ("rate_limits",)}


def fetch(options, ctx):
    pushed = ctx.pushed("claude")
    if pushed is None:
        return {"text": "No data yet"}
    return {"text": str(pushed.data["rate_limits"]), "at": pushed.received_at}
```

- `PUSH_KEYS` maps each channel name to a tuple of key names. Channel names match `^[a-z0-9_-]{1,32}$`. A malformed `PUSH_KEYS` stops the server at startup with a clear message.
- `ctx.pushed(channel)` returns the latest push or `None` if nothing arrived since the server started. `.data` is a dict with only the declared keys. `.received_at` is the time of arrival in seconds since the epoch (Unix time).
- Every other key of a push is dropped. Nothing is written to disk: the data lives in RAM only, so it is gone after a restart.
- A push does not render the page at once. The page picks up new data on its next `refresh`. Pages that only read pushes need no network, so `refresh: 30` is cheap and recommended.

The endpoint is off until you set `push_key` (see [Configuration](configuration.md)). Put the key in `.env` next to `docker-compose.yml` and refer to it in `config.yaml`:

```
# .env
GLANCEBOX_PUSH_KEY=<at least 16 characters, e.g. from openssl rand -hex 24>
```

```yaml
push_key: ${GLANCEBOX_PUSH_KEY}
```

Then a computer on your home network sends the data like this:

```sh
curl -X POST "http://192.168.1.20:8080/api/v1/push/claude" \
  -H "Authorization: Bearer $GLANCEBOX_PUSH_KEY" \
  -H "Content-Type: application/json" \
  -d '{"rate_limits": {"five_hour": {"used_percentage": 12}}}'
```

| Status | Meaning |
| --- | --- |
| 204 | stored |
| 404 | no `push_key` set, or no page declares this channel |
| 401 | `Authorization: Bearer <key>` missing or wrong |
| 413 | body larger than 65 536 bytes |
| 422 | body is not a JSON object |

Keep the server on your home network. The push endpoint is protected only by the key and is not meant to be reachable from the internet. The server never logs the body or the key.

## Walkthrough: the clock page

The built-in `clock` page is the smallest useful example (`pages/clock/`). Its `page.py` does three things:

1. `validate` rejects a `lang` other than `de` or `en`.
2. `fetch` takes the language (the page's own `lang` option, or the top-level one), formats `ctx.now` and returns `{"time": "14:05", "weekday": "Dienstag", "date": "14.11.2026"}`.
3. Nothing else: no network, no state.

Its `template.html` extends `base.html` and uses `{{ time }}`, `{{ weekday }}` and `{{ date }}`, centered in the 240x240 area with a large, bold time. Copy it and change it:

```sh
mkdir -p pages-custom
cp -r pages/clock pages-custom/mypage
```

Edit `pages-custom/mypage/page.py` and `template.html`, add the page to `config.yaml`:

```yaml
pages:
  - type: mypage
    refresh: 30
```

and restart with `docker compose restart`. A page in `pages-custom` with the name of a built-in page (`clock`, `bahn`) replaces the built-in one.

## The url page and its tips

```yaml
- type: url
  url: http://homeserver.lan/status-240
  wait_for: "#ready"
```

The server loads the address in a headless Chromium with a window of exactly **240x240 pixels** and device scale factor 1, then takes a screenshot. So:

- **Design for 240x240.** A desktop page shrunk to this size is unreadable. Build a page just for the display: large text (at least 18 px), few elements, high contrast, no scrollbars. Use `html, body { width: 240px; height: 240px; overflow: hidden; }`.
- **Use `wait_for`** when the page fills itself with JavaScript. Give the finished content an element (for example `<div id="ready">`) and set `wait_for: "#ready"`. Use `wait_ms` only for a fixed extra pause, for example for an animation.
- **Keep the picture simple.** A picture must fit into 24 576 bytes as a JPEG. Flat areas and plain text compress very well, photos and fine gradients badly. If the server has to lower the quality a lot, text gets blurry.
- **The server has to reach the address from inside the container.** Use the LAN address or name, not `localhost`.
- **No login screens.** The server's browser has no saved logins. A page that needs a login shows the login. Make a read-only page for the display, and do not publish it to the internet, because the display image is served without any password.
- Every refresh loads the page again, so `refresh: 30` means one request to your page every 30 seconds.

Some targets are off limits for everything the browser loads, on `url` pages and on template pages alike: the Home Assistant internal names (`supervisor`, `hassio`, `homeassistant`, `observer`, any name ending in `.local.hass.io`), `localhost`, and the addresses `127.0.0.0/8`, `::1`, `172.30.32.0/23` (the add-on network) and `169.254.0.0/16`. The server aborts such requests, and only `http`, `https`, `data`, `blob` and `about` addresses load at all. One exception: a `url` page may load anything from its own host, so `url: http://homeassistant:8123/...` still works with its own images and scripts. The check looks at names and IP addresses as written, not at what a name resolves to.

## Previewing in the browser

Open `http://<server>:8080/`. It shows every page of your playlist as a 240x240 picture with its age and last error, and refreshes itself every 30 seconds. After a change to `page.py` or `template.html` restart the server (`docker compose restart`) and reload. If your page does not appear as a picture, the error text under it tells you why. `docker compose logs` has the details.

## The render command

To try a page without a display, render one page once to a file:

```sh
docker compose exec glancebox python -m glancebox render 0 -o /tmp/page0.png
docker compose cp glancebox:/tmp/page0.png .
```

`0` is the number of the page in `pages:` (counting from 0). The output is a PNG when the name ends in `.png`, otherwise a JPEG, exactly as the display would get it. The command uses the configuration of the running server (`--config` selects another file) and exits with an error message if the configuration or the rendering fails. Outside Docker, install the server (`pip install -e server` in a Python 3.12 environment with Playwright's Chromium) and run `python -m glancebox render 0 -o page0.png --config config.yaml`.
