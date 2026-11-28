"""Weather page (weather): current conditions and the next four hours from Open-Meteo."""

from __future__ import annotations

import math
from datetime import datetime
from zoneinfo import ZoneInfo

from glancebox import http
from glancebox.timefmt import format_hour

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
# The frame (and its header clock) refreshes every minute; Open-Meteo is asked at most every
# FORECAST_CACHE_S, because the service is free and weather changes slowly.
MIN_REFRESH = 60
FORECAST_CACHE_S = 900

LANGS = ("de", "en")
DEFAULT_TITLE = {"de": "Wetter", "en": "Weather"}

# Successful geocoding lookups, keyed by (location, lang). Places do not move.
_geocode_cache: dict[tuple[str, str], tuple[float, float, str]] = {}
# Successful forecasts, keyed by (latitude, longitude, lang, timezone) -> (fetched at, data).
_forecast_cache: dict[tuple, tuple[float, dict]] = {}

DESCRIPTIONS = {
    0: ("Klar", "Clear"),
    1: ("Überwiegend klar", "Mostly clear"),
    2: ("Leicht bewölkt", "Partly cloudy"),
    3: ("Bedeckt", "Overcast"),
    45: ("Nebel", "Fog"),
    48: ("Reifnebel", "Rime fog"),
    51: ("Leichter Nieselregen", "Light drizzle"),
    53: ("Nieselregen", "Drizzle"),
    55: ("Starker Nieselregen", "Heavy drizzle"),
    56: ("Gefrierender Nieselregen", "Freezing drizzle"),
    57: ("Gefrierender Nieselregen", "Freezing drizzle"),
    61: ("Leichter Regen", "Light rain"),
    63: ("Regen", "Rain"),
    65: ("Starker Regen", "Heavy rain"),
    66: ("Gefrierender Regen", "Freezing rain"),
    67: ("Gefrierender Regen", "Freezing rain"),
    71: ("Leichter Schnee", "Light snow"),
    73: ("Schnee", "Snow"),
    75: ("Starker Schnee", "Heavy snow"),
    77: ("Schneegriesel", "Snow grains"),
    80: ("Leichte Schauer", "Light showers"),
    81: ("Schauer", "Showers"),
    82: ("Starke Schauer", "Heavy showers"),
    85: ("Schneeschauer", "Snow showers"),
    86: ("Starke Schneeschauer", "Heavy snow showers"),
    95: ("Gewitter", "Thunderstorm"),
    96: ("Gewitter mit Hagel", "Thunderstorm with hail"),
    99: ("Starkes Gewitter mit Hagel", "Severe thunderstorm with hail"),
}


def validate(options: dict) -> None:
    has_loc = options.get("location") is not None
    has_lat = options.get("latitude") is not None
    has_lon = options.get("longitude") is not None
    if has_loc and (has_lat or has_lon):
        raise ValueError("use either location or latitude and longitude, not both")
    if has_loc:
        loc = options["location"]
        if not isinstance(loc, str) or not loc.strip():
            raise ValueError("location must be a non-empty text")
    elif has_lat and has_lon:
        for key, limit in (("latitude", 90), ("longitude", 180)):
            v = options[key]
            if isinstance(v, bool) or not isinstance(v, (int, float)) or abs(v) > limit:
                raise ValueError(f"{key} must be a number between -{limit} and {limit}")
    else:
        raise ValueError("set location, or both latitude and longitude")
    if options.get("lang", "de") not in LANGS:
        raise ValueError("lang must be 'de' or 'en'")


def _geocode(location: str, lang: str) -> tuple[float, float, str]:
    key = (location, lang)
    if key not in _geocode_cache:
        data = http.get_json(GEOCODE_URL, params={
            "name": location, "count": 1, "language": lang, "format": "json"})
        results = (data or {}).get("results") or []
        if not results:
            raise ValueError(f"location not found: {location}")
        r = results[0]
        _geocode_cache[key] = (r["latitude"], r["longitude"], r.get("name") or location)
    return _geocode_cache[key]


def _forecast(lat: float, lon: float, lang: str, timezone: str, now: float) -> dict:
    key = (lat, lon, lang, timezone)
    hit = _forecast_cache.get(key)
    if hit is not None and 0 <= now - hit[0] < FORECAST_CACHE_S:
        return hit[1]
    data = http.get_json(FORECAST_URL, params={
        "latitude": lat, "longitude": lon,
        "current": "temperature_2m,weather_code,is_day",
        "hourly": "temperature_2m,precipitation_probability,weather_code,is_day",
        "daily": "temperature_2m_max,temperature_2m_min",
        "timezone": timezone, "forecast_days": 2})
    _forecast_cache[key] = (now, data)  # only reached on success; errors propagate
    return data


def _slot_times(stamps: list[str], tz: ZoneInfo) -> list[datetime]:
    """Local wall-clock strings -> aware datetimes. A repeated wall-clock hour (DST fall-back,
    Open-Meteo lists 02:00 twice) is the second pass, fold=1."""
    out: list[datetime] = []
    for stamp in stamps:
        t = datetime.fromisoformat(stamp)
        fold = 1 if out and t <= out[-1].replace(tzinfo=None) else 0
        out.append(t.replace(tzinfo=tz, fold=fold))
    return out


def _round(value: float) -> int:
    return math.floor(value + 0.5)  # half-up, also for negatives (-0.5 -> 0)


def icon_key(code: int, is_day: int) -> str:
    if code == 0:
        key = "clear"
    elif code in (1, 2):
        key = "partly"
    elif code in (45, 48):
        return "fog"
    elif 51 <= code <= 67 or 80 <= code <= 82:
        return "rain"
    elif 71 <= code <= 77 or code in (85, 86):
        return "snow"
    elif 95 <= code <= 99:
        return "thunder"
    else:
        return "cloudy"
    return key if is_day else key + "-night"


def _description(code: int, lang: str) -> str:
    de_en = DESCRIPTIONS.get(code)
    if de_en is None:
        return ""
    return de_en[0] if lang == "de" else de_en[1]


def fetch(options: dict, ctx) -> dict:
    lang = options.get("lang", ctx.lang if ctx.lang in LANGS else "de")
    if options.get("location") is not None:
        lat, lon, place = _geocode(options["location"].strip(), lang)
    else:
        lat, lon, place = options["latitude"], options["longitude"], None
    title = options.get("title") or place or DEFAULT_TITLE[lang]

    data = _forecast(lat, lon, lang, ctx.timezone, ctx.now.timestamp())

    cur = data["current"]
    code = int(cur["weather_code"])
    # Hourly times are local wall-clock strings in ctx.timezone; compare them as instants so
    # the repeated and the skipped hour of a DST change land in the right place.
    tz = ZoneInfo(ctx.timezone)
    now = ctx.now if ctx.now.tzinfo else ctx.now.replace(tzinfo=tz)
    this_hour = now.replace(minute=0, second=0, microsecond=0).timestamp()
    hourly = data["hourly"]
    hours = []
    for i, t in enumerate(_slot_times(hourly["time"], tz)):
        if t.timestamp() <= this_hour:
            continue
        rain = hourly["precipitation_probability"][i]
        hours.append({"hour": format_hour(t, ctx.time_format),
                      "temp": _round(hourly["temperature_2m"][i]),
                      "rain": _round(rain) if rain is not None else 0})
        if len(hours) == 4:
            break
    return {
        "title": title,
        "clock": ctx.clock(),
        "icon": icon_key(code, int(cur.get("is_day", 1))),
        "temp": _round(cur["temperature_2m"]),
        "desc": _description(code, lang),
        "high": _round(data["daily"]["temperature_2m_max"][0]),
        "low": _round(data["daily"]["temperature_2m_min"][0]),
        "hours": hours,
    }
