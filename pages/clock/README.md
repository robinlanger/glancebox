# clock: example page

User documentation: [docs/en/templates/clock.md](../../docs/en/templates/clock.md) ([Deutsch](../../docs/de/templates/clock.md)). Developer notes below.

The smallest useful page type. It shows the time (large), the weekday and the date. Use it as a starting point for your own pages.

The time follows `time_format` (top level or per page). With `12h` it reads `9:05` with a small `AM` / `PM` beside it, and the digits are 56 px instead of 72 px so `12:59 PM` fits. `fetch` gets the text from `ctx.clock()` and splits the suffix off with `glancebox.timefmt.split_suffix`, returning it as `ampm` (empty in 24 hours).

```yaml
- type: clock
  lang: en        # optional: de (default, or the top-level lang) or en
  refresh: 60     # seconds; no minimum, once a minute is enough
```

## Make your own page from it

Pages are loaded from `custom_pages_dir` (default `/config/pages` in Docker, mounted from `./pages-custom` by the compose file). Copy this folder there under a new name:

```sh
mkdir -p pages-custom
cp -r pages/clock pages-custom/mypage
```

Then edit `pages-custom/mypage/page.py` (return whatever data you need from `fetch(options, ctx)`) and `template.html` (a Jinja2 template extending `base.html`, 240x240 px). Use it in `config.yaml` with `type: mypage` and restart the server. A custom page with the same name as a built-in one replaces it.
