# weather: current weather and the next four hours

User documentation: [docs/en/templates/weather.md](../../docs/en/templates/weather.md) ([Deutsch](../../docs/de/templates/weather.md)). Developer notes below.

Data comes from [Open-Meteo](https://open-meteo.com) (free, no key, CC BY 4.0). One geocoding request per `location` (cached for the life of the process), one forecast request per coordinates at most every `FORECAST_CACHE_S` = 900 s (successful answers are cached per process, keyed by coordinates, lang and time zone). `MIN_REFRESH` is 60, so the frame and its header clock stay fresh within the 600 s frame expiry while Open-Meteo is asked at most every 15 minutes.

```yaml
- type: weather
  location: Frankfurt am Main     # or latitude: 50.11 and longitude: 8.68, never both
  # title: Zuhause                # default: geocoded name, else "Wetter"/"Weather"
  # lang: en                      # default: top-level lang
  # refresh: 60                   # default and minimum 60; forecast cached 900 s
```

- `fetch` lets errors propagate (failures are not cached, so once the cache expired every refresh asks again): the last image stays for up to 10 minutes.
- The four hours are the hourly slots after the current hour in the configured time zone, also across midnight and DST changes (Open-Meteo lists local wall-clock times; a repeated hour is read as the second pass). Each hour shows as `15`, or `3 PM` with `time_format: 12h`.
- `icons.html` holds one macro `icon(key, w, h)` with flat SVGs; keys are `clear`, `partly`, `cloudy`, `fog`, `rain`, `snow`, `thunder`, plus `clear-night` and `partly-night`.
