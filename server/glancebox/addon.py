"""Home Assistant add-on mode.

Active only when the Supervisor runs us: /data/options.json exists and SUPERVISOR_TOKEN is set.
Reads the add-on form's secrets into a private mapping for ``${NAME}`` in the playlist (never
into the process environment, and SUPERVISOR_TOKEN is removed from it), writes a starter
playlist, and fills in values Home Assistant already knows (time zone, language, home location,
its own API) wherever the YAML leaves them out. YAML values always win. Secret values are never
logged.
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Callable, Mapping, MutableMapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

log = logging.getLogger(__name__)

OPTIONS_PATH = Path("/data/options.json")
SUPERVISOR_CORE = "http://supervisor/core"
SUPERVISOR = "http://supervisor"
TIMEOUT = 5
RETRY_PAUSE = 3

# Add-on form field -> environment variable the playlist refers to as ${NAME}.
SECRET_FIELDS: dict[str, str] = {
    "push_key": "GLANCEBOX_PUSH_KEY",
    "anthropic_admin_key": "ANTHROPIC_ADMIN_KEY",
    "openai_admin_key": "OPENAI_ADMIN_KEY",
    "xai_management_key": "XAI_MANAGEMENT_KEY",
    "github_copilot_token": "GITHUB_COPILOT_TOKEN",
}
EXTRA_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")

STARTER_CONFIG = """\
# Glance Box playlist (Home Assistant add-on).
# Docs: https://robinlanger.github.io/glancebox/
# Time zone, language and location come from Home Assistant unless you set them here
# (timezone:, lang:, and location: on a weather page).
# Secrets go into the add-on's Configuration tab and are used here as ${NAME}.
# Restart the add-on after editing this file.

pages:
  - type: clock
  - type: weather
    refresh: 60
"""


def is_addon(environ: Mapping[str, str], options_path: Path = OPTIONS_PATH) -> bool:
    return bool(environ.get("SUPERVISOR_TOKEN")) and options_path.is_file()


def secrets_env(options: dict, environ: Mapping[str, str]) -> dict[str, str]:
    """Environment variables from the form: fixed fields plus the free list ``extra_secrets``."""
    env: dict[str, str] = {}
    for field, var in SECRET_FIELDS.items():
        value = options.get(field)
        if isinstance(value, str) and value:
            env[var] = value
    reserved = set(SECRET_FIELDS.values())
    for item in options.get("extra_secrets") or []:
        if not isinstance(item, dict):
            continue
        name, value = item.get("name"), item.get("value")
        if not isinstance(name, str) or not EXTRA_NAME_RE.match(name):
            log.warning("extra secret %r ignored: name must be A-Z, 0-9 and _", name)
        elif name in environ or name in reserved or name in env:
            log.warning("extra secret %s ignored: this name is already in use", name)
        elif isinstance(value, str) and value:
            env[name] = value
    return env


def ensure_config(path: Path, fallback_dir: Path) -> tuple[Path, bool]:
    """Path of the playlist to load and whether it is the user's file.

    Writes the starter playlist if ``path`` is missing, never overwrites. If ``path`` cannot be
    written, the starter goes to ``fallback_dir`` (not persistent) and the flag is False.
    """
    if path.exists():
        return path, True
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(STARTER_CONFIG, encoding="utf-8")
        log.info("wrote starter playlist to %s", path)
        return path, True
    except OSError as e:
        log.warning("cannot write %s (%s); using a temporary starter playlist", path, e)
    fallback_dir.mkdir(parents=True, exist_ok=True)
    fallback = fallback_dir / "config.yaml"
    fallback.write_text(STARTER_CONFIG, encoding="utf-8")
    return fallback, False


class AddonError(Exception):
    """Add-on mode cannot start (message is safe to show: no secrets)."""


@dataclass(frozen=True)
class HaInfo:
    time_zone: str
    language: str | None
    latitude: float
    longitude: float


def lang_from_ha(language: str | None) -> str:
    code = (language or "")[:2].lower()
    return code if code in ("de", "en") else "en"


def ha_defaults(info: HaInfo, environ: Mapping[str, str]) -> Callable[[dict], dict]:
    """Hook for ``load_config``: fill only what the YAML leaves out."""

    def page_defaults(page: object) -> object:
        if not isinstance(page, dict):
            return page
        page = dict(page)
        kind = page.get("type")
        via_ha = kind in ("homeassistant", "energy") or (
            kind == "printer" and page.get("source") == "hass")
        if kind == "weather" and not any(
                page.get(k) is not None for k in ("location", "latitude", "longitude")):
            page["latitude"], page["longitude"] = info.latitude, info.longitude
        elif via_ha and "url" not in page and "token" not in page:
            page["url"] = SUPERVISOR_CORE
            page["token"] = environ.get("SUPERVISOR_TOKEN", "")
        return page

    def hook(data: dict) -> dict:
        out = dict(data)
        if out.get("timezone") is None:
            out["timezone"] = info.time_zone
        if out.get("lang") is None:
            out["lang"] = lang_from_ha(info.language)
        push_key = environ.get(SECRET_FIELDS["push_key"])
        if push_key and "push_key" not in out:
            out["push_key"] = push_key
        if isinstance(out.get("pages"), list):
            out["pages"] = [page_defaults(p) for p in out["pages"]]
        return out

    return hook


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def fetch_ha_info(token: str, get: Callable[..., Any] = requests.get,
                  sleep: Callable[[float], None] = time.sleep, attempts: int = 10) -> HaInfo:
    """Time zone, language and home location from Home Assistant Core (via the Supervisor).

    Retries while Core is not reachable (it may still be starting); the error never carries the
    token or a response body.
    """
    for attempt in range(1, attempts + 1):
        try:
            resp = get(f"{SUPERVISOR_CORE}/api/config", headers=_headers(token), timeout=TIMEOUT)
            if resp.status_code in (401, 403):
                raise AddonError(
                    f"Home Assistant API refused access (HTTP {resp.status_code})")
            if resp.status_code < 500:
                resp.raise_for_status()
                data = resp.json()
                return HaInfo(str(data["time_zone"]), data.get("language"),
                              float(data["latitude"]), float(data["longitude"]))
            reason = f"HTTP {resp.status_code}"
        except requests.RequestException as e:
            reason = type(e).__name__
        except (KeyError, TypeError, ValueError):
            raise AddonError("Home Assistant API returned an unexpected config") from None
        log.warning("Home Assistant API not reachable (%s), attempt %d/%d",
                    reason, attempt, attempts)
        if attempt < attempts:
            sleep(RETRY_PAUSE)
    raise AddonError("Home Assistant API not reachable at startup")


def _supervisor_data(path: str, token: str, get: Callable[..., Any]) -> dict:
    resp = get(f"{SUPERVISOR}{path}", headers=_headers(token), timeout=TIMEOUT)
    resp.raise_for_status()
    data = resp.json().get("data")
    return data if isinstance(data, dict) else {}


def fetch_options(token: str, get: Callable[..., Any] = requests.get,
                  sleep: Callable[[float], None] = time.sleep, attempts: int = 10) -> dict:
    """The add-on form values (validated by the Supervisor, ``!secret`` resolved)."""
    for attempt in range(1, attempts + 1):
        try:
            return _supervisor_data("/addons/self/options/config", token, get)
        except (requests.RequestException, ValueError, AttributeError) as e:
            reason = type(e).__name__
        log.warning("cannot read the add-on options (%s), attempt %d/%d",
                    reason, attempt, attempts)
        if attempt < attempts:
            sleep(RETRY_PAUSE)
    raise AddonError("cannot read the add-on options from the Supervisor")


def connect_url(token: str, get: Callable[..., Any] = requests.get) -> str | None:
    """Address the display should use (``http://<HA LAN IP>:<host port>``), or None if unknown."""
    try:
        network = _supervisor_data("/network/info", token, get)
        info = _supervisor_data("/addons/self/info", token, get)
    except (requests.RequestException, ValueError, AttributeError) as e:
        log.warning("cannot determine the display address (%s)", type(e).__name__)
        return None
    ip = None
    for iface in network.get("interfaces") or []:
        if isinstance(iface, dict) and iface.get("primary"):
            ipv4 = iface.get("ipv4")
            addresses = ipv4.get("address") if isinstance(ipv4, dict) else None
            if isinstance(addresses, list) and addresses:
                ip = str(addresses[0]).split("/")[0]
                break
    ports = info.get("network")
    port = ports.get("8080/tcp") if isinstance(ports, dict) else None
    if not ip or not isinstance(port, int):
        return None
    return f"http://{ip}:{port}"


@dataclass
class AddonSetup:
    config_path: Path
    defaults: Callable[[dict], dict]
    connect: str | None
    config_note: str | None
    # Copy of the environment plus the form's secrets and SUPERVISOR_TOKEN; only for ${NAME} in
    # the playlist, never handed to a process.
    environ: dict[str, str]


def addon_setup(environ: MutableMapping[str, str], config_path: Path,
                fallback_dir: Path, get: Callable[..., Any] = requests.get,
                sleep: Callable[[float], None] = time.sleep) -> AddonSetup:
    """Everything add-on mode needs before ``load_config``.

    Removes ``SUPERVISOR_TOKEN`` from ``environ`` so Chromium and page code never inherit it.
    The token and the form's secrets go into ``AddonSetup.environ`` (pass it to
    ``load_config``, so ``${SUPERVISOR_TOKEN}`` keeps working), never into ``environ``.
    """
    # /data/options.json is root-only (0600) and we run as pwuser: ask the Supervisor instead.
    token = environ.pop("SUPERVISOR_TOKEN")
    options = fetch_options(token, get=get, sleep=sleep)
    # The token name stays reserved, so an extra secret cannot shadow it.
    merged = {**environ, **secrets_env(options, {**environ, "SUPERVISOR_TOKEN": token}),
              "SUPERVISOR_TOKEN": token}
    info = fetch_ha_info(token, get=get, sleep=sleep)
    path, own = ensure_config(config_path, fallback_dir)
    note = None if own else (
        f"The starter playlist could not be saved to {config_path}, so it runs from a temporary "
        "copy. Create config.yaml in the add-on's config folder (File editor) to keep your pages.")
    defaults = ha_defaults(info, merged)
    return AddonSetup(path, defaults, connect_url(token, get=get), note, environ=merged)
