"""Load and validate the YAML playlist configuration."""

from __future__ import annotations

import logging
import os
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml

log = logging.getLogger(__name__)

DEFAULT_INTERVAL = 30
_TOP_LEVEL_KEYS = {"interval", "timezone", "lang", "pages", "custom_pages_dir", "push_key"}
_RESERVED_PAGE_KEYS = {"type", "duration", "refresh"}
_ENV_REF = re.compile(r"^\$\{([A-Za-z_][A-Za-z0-9_]*)\}$")
MIN_PUSH_KEY_LENGTH = 16


class ConfigError(Exception):
    """The configuration file is missing, malformed or invalid."""


@dataclass(frozen=True)
class PageConfig:
    index: int
    type: str
    options: dict
    duration: int
    refresh: int
    refresh_explicit: bool = False


@dataclass(frozen=True)
class AppConfig:
    interval: int
    timezone: str
    lang: str
    pages: tuple[PageConfig, ...]
    pages_dirs: tuple[Path, ...]
    push_key: str | None = None


def _builtin_pages_dir() -> Path:
    env = os.environ.get("GLANCEBOX_PAGES_DIR")
    if env:
        return Path(env)
    # pages/ sits at the repo root, two levels above this package (server/glancebox/).
    return Path(__file__).resolve().parents[2] / "pages"


def expand_env(value: Any, where: str, environ: Mapping[str, str]) -> Any:
    """Replace every string that is exactly ``${NAME}`` by the environment variable NAME.

    Partial matches such as ``http://${HOST}:1`` stay literal. A missing or empty
    variable is an error naming the YAML path.
    """
    if isinstance(value, dict):
        return {
            k: expand_env(v, f"{where}.{k}" if where else str(k), environ) for k, v in value.items()
        }
    if isinstance(value, list):
        return [expand_env(v, f"{where}[{i}]", environ) for i, v in enumerate(value)]
    if isinstance(value, str):
        m = _ENV_REF.match(value)
        if m:
            name = m.group(1)
            resolved = environ.get(name)
            if not resolved:
                raise ConfigError(f"{where}: environment variable {name} is not set")
            return resolved
    return value


def _positive_int(value: Any, where: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ConfigError(f"{where} must be a positive integer, got {value!r}")
    return value


def _check_timezone(name: str) -> None:
    # Fail at startup, not on every render of a page that uses the time zone.
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as e:
        raise ConfigError(f"timezone: unknown time zone {name!r}") from e


def _parse_page(index: int, raw: Any, interval: int) -> PageConfig:
    where = f"pages[{index}]"
    if not isinstance(raw, dict):
        raise ConfigError(f"{where}: must be a mapping")
    page_type = raw.get("type")
    if not isinstance(page_type, str) or not page_type:
        raise ConfigError(f"{where}: missing required key 'type'")
    duration = interval
    if "duration" in raw:
        duration = _positive_int(raw["duration"], f"{where}: duration")
    refresh = duration
    refresh_explicit = "refresh" in raw
    if "refresh" in raw:
        refresh = _positive_int(raw["refresh"], f"{where}: refresh")
    options = {k: v for k, v in raw.items() if k not in _RESERVED_PAGE_KEYS}
    return PageConfig(index, page_type, options, duration, refresh, refresh_explicit)


def load_config(path: Path, defaults: Callable[[dict], dict] | None = None,
                environ: Mapping[str, str] | None = None) -> AppConfig:
    """Load ``path``. ``defaults`` (add-on mode) may fill in missing keys of the top-level mapping
    after ``${NAME}`` expansion and before validation; YAML values must win. ``${NAME}`` is
    looked up in ``environ`` (default: ``os.environ``)."""
    path = Path(path)
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as e:
        raise ConfigError(f"{path}: cannot read config: {e}") from e
    except yaml.YAMLError as e:
        raise ConfigError(f"{path}: invalid YAML: {e}") from e
    if not isinstance(data, dict):
        raise ConfigError(f"{path}: top level must be a mapping")
    data = expand_env(data, "", os.environ if environ is None else environ)
    if defaults is not None:
        data = defaults(data)
        if not isinstance(data, dict):
            raise ConfigError(f"{path}: defaults hook must return a mapping")

    unknown = sorted(set(data) - _TOP_LEVEL_KEYS, key=str)
    if unknown:
        raise ConfigError(f"{path}: unknown top-level key(s): {', '.join(map(str, unknown))}")

    interval = _positive_int(data.get("interval", DEFAULT_INTERVAL), "interval")
    timezone = data.get("timezone", "Europe/Berlin")
    lang = data.get("lang", "de")
    if not isinstance(timezone, str) or not isinstance(lang, str):
        raise ConfigError("timezone and lang must be strings")
    _check_timezone(timezone)

    raw_pages = data.get("pages")
    if not isinstance(raw_pages, list) or not raw_pages:
        raise ConfigError("config needs at least one page under 'pages'")
    pages = tuple(_parse_page(i, p, interval) for i, p in enumerate(raw_pages))

    pages_dirs = [_builtin_pages_dir()]
    custom = data.get("custom_pages_dir")
    if custom is not None:
        if not isinstance(custom, str):
            raise ConfigError("custom_pages_dir must be a string path")
        custom_dir = (path.resolve().parent / custom).resolve()
        if custom_dir.is_dir():
            pages_dirs.append(custom_dir)
        else:
            # Optional by design: the documented default /config/pages is often not mounted.
            log.warning("custom_pages_dir %s does not exist; using built-in pages only", custom_dir)

    push_key = data.get("push_key")
    if push_key is not None and (
        not isinstance(push_key, str) or len(push_key) < MIN_PUSH_KEY_LENGTH
    ):
        raise ConfigError(
            f"push_key must be a string of at least {MIN_PUSH_KEY_LENGTH} characters"
        )
    if push_key is not None and not push_key.isascii():
        # Starlette decodes request headers as latin-1, so a non-ASCII key could never match.
        raise ConfigError("push_key must contain only ASCII characters (for example letters, "
                          "digits, - and _; openssl rand -hex 24 makes a good one)")

    return AppConfig(interval, timezone, lang, pages, tuple(pages_dirs), push_key)
