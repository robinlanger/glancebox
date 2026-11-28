"""Clock page: the simplest possible page, meant as a template for your own.

A page type is a folder with two files:
  page.py        fetch(options, ctx) returns a dict of data (this file)
  template.html  a Jinja2 template that turns that dict into a 240x240 image
"""

from glancebox.timefmt import split_suffix

WEEKDAYS = {
    "de": ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"],
    "en": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
}


def validate(options: dict) -> None:
    """Optional. Raise ValueError to reject a bad config at startup."""
    if options.get("lang", "de") not in WEEKDAYS:
        raise ValueError("lang must be 'de' or 'en'")


def fetch(options: dict, ctx) -> dict:
    """Called on every refresh. ctx.now is timezone-aware, ctx.lang is the config default."""
    lang = options.get("lang", ctx.lang if ctx.lang in WEEKDAYS else "de")
    now = ctx.now
    date = now.strftime("%d.%m.%Y") if lang == "de" else now.strftime("%Y-%m-%d")
    # ctx.clock() is the time of day in the configured time_format: "09:05" or "9:05 AM".
    time, ampm = split_suffix(ctx.clock())
    # Everything returned here becomes a variable in template.html.
    return {"time": time, "ampm": ampm, "weekday": WEEKDAYS[lang][now.weekday()], "date": date}
