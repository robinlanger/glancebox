from datetime import datetime
from pathlib import Path

import pytest

from glancebox.config import AppConfig, ConfigError, PageConfig, load_config
from glancebox.frames import STALE_AFTER_S
from glancebox.pages import PageContext, load_page_types, validate_config

FIX = Path(__file__).parent / "fixtures" / "pages"
REAL = Path(__file__).resolve().parents[2] / "pages"
CTX = PageContext(now=datetime(2026, 1, 1, 12, 0), lang="de", timezone="Europe/Berlin")


def cfg_of(*pages: tuple[str, dict, dict], interval=30) -> AppConfig:
    out = []
    for i, (t, options, extra) in enumerate(pages):
        duration = extra.get("duration", interval)
        out.append(PageConfig(i, t, options, duration, extra.get("refresh", duration),
                              "refresh" in extra))
    return AppConfig(interval, "Europe/Berlin", "de", tuple(out), ())


def test_loads_script_page_with_relative_import():
    types = load_page_types([FIX / "good"])
    assert types["good"].kind == "script"
    assert types["good"].fetch({}, CTX) == {"ok": True, "lang": "de"}
    assert types["good"].template_path == FIX / "good" / "good" / "template.html"
    assert types["good"].min_refresh == 0


def test_broken_page_module_reports_dir():
    with pytest.raises(ConfigError, match="broken"):
        load_page_types([FIX / "broken"])


def test_missing_fetch_reports_dir(tmp_path):
    (tmp_path / "nofetch").mkdir()
    (tmp_path / "nofetch" / "page.py").write_text("X = 1\n")
    with pytest.raises(ConfigError, match="nofetch"):
        load_page_types([tmp_path])


def test_builtin_url_type_always_present():
    assert load_page_types([])["url"].kind == "url"


def test_custom_dir_overrides_builtin(tmp_path):
    (tmp_path / "bahn").mkdir()
    (tmp_path / "bahn" / "page.py").write_text(
        "def fetch(options, ctx):\n    return {'from': 'custom'}\n")
    types = load_page_types([REAL, tmp_path])
    assert types["bahn"].fetch({}, CTX) == {"from": "custom"}
    assert types["bahn"].min_refresh == 0
    assert load_page_types([REAL])["bahn"].min_refresh == 60


def test_unknown_type_names_index():
    types = load_page_types([])
    cfg = cfg_of(("url", {"url": "http://x"}, {}), ("nope", {}, {}))
    with pytest.raises(ConfigError, match=r"pages\[1\] \(nope\)"):
        validate_config(cfg, types)


def test_url_requires_url():
    with pytest.raises(ConfigError, match="url"):
        validate_config(cfg_of(("url", {}, {})), load_page_types([]))


@pytest.mark.parametrize("opts", [
    {"url": "ftp://x"}, {"url": 5},
    {"url": "http://x", "wait_ms": -1}, {"url": "http://x", "wait_ms": True},
    {"url": "http://x", "timeout_s": 0}, {"url": "http://x", "wait_for": 3},
])
def test_url_invalid_options(opts):
    with pytest.raises(ConfigError, match=r"pages\[0\] \(url\)"):
        validate_config(cfg_of(("url", opts, {})), load_page_types([]))


@pytest.mark.parametrize("url", ["htps://user:pw@h/x?token=abc", "http:///x?token=abc"])
def test_url_error_does_not_echo_secrets(url):
    with pytest.raises(ConfigError) as err:
        validate_config(cfg_of(("url", {"url": url}, {})), load_page_types([]))
    assert "abc" not in str(err.value) and "pw" not in str(err.value)


def test_url_valid_options():
    opts = {"url": "https://x", "wait_ms": 500, "wait_for": "#a", "timeout_s": 2.5}
    cfg = cfg_of(("url", opts, {}))
    assert validate_config(cfg, load_page_types([])).pages[0].options == opts


def test_bahn_refresh_below_60_rejected():
    types = load_page_types([REAL])
    with pytest.raises(ConfigError, match="60"):
        validate_config(cfg_of(("bahn", {"station": "X"}, {"refresh": 10})), types)


def test_bahn_default_refresh_raised_to_60():
    types = load_page_types([REAL])
    out = validate_config(cfg_of(("bahn", {"station": "X"}, {})), types)
    assert out.pages[0].refresh == 60
    assert out.pages[0].duration == 30


def test_bahn_requires_station_and_limit_range():
    types = load_page_types([REAL])
    with pytest.raises(ConfigError, match=r"pages\[0\] \(bahn\).*station"):
        validate_config(cfg_of(("bahn", {}, {})), types)
    with pytest.raises(ConfigError, match="limit"):
        validate_config(cfg_of(("bahn", {"station": "X", "limit": 7}, {})), types)


def test_validate_config_from_loaded_yaml(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text("pages:\n  - {type: bahn, station: X}\n")
    out = validate_config(load_config(p), load_page_types([REAL]))
    assert out.pages[0].refresh == 60


def test_builtin_min_refresh_keeps_frames_fresh():
    # A frame expires after STALE_AFTER_S; a longer MIN_REFRESH would let it vanish from the
    # playlist until the next allowed refresh.
    for name, page_type in load_page_types([REAL]).items():
        assert page_type.min_refresh <= STALE_AFTER_S, name


def write_page(tmp_path, body):
    (tmp_path / "hooked").mkdir()
    (tmp_path / "hooked" / "page.py").write_text(
        "def fetch(options, ctx):\n    return {}\n" + body)
    return load_page_types([tmp_path])


def test_default_refresh_applies_only_without_explicit_refresh(tmp_path):
    types = write_page(tmp_path, "DEFAULT_REFRESH = 5\nMIN_REFRESH = 2\n")
    implicit = validate_config(cfg_of(("hooked", {}, {"duration": 30})), types)
    assert implicit.pages[0].refresh == 5
    explicit = validate_config(cfg_of(("hooked", {}, {"refresh": 60})), types)
    assert explicit.pages[0].refresh == 60
    with pytest.raises(ConfigError, match="at least 2"):
        validate_config(cfg_of(("hooked", {}, {"refresh": 1})), types)


@pytest.mark.parametrize("line,hook", [
    ("DEFAULT_REFRESH = 0", "DEFAULT_REFRESH"),
    ("DEFAULT_REFRESH = True", "DEFAULT_REFRESH"),
    ('DEFAULT_REFRESH = "5"', "DEFAULT_REFRESH"),
    ("SKIP_UNCHANGED = 1", "SKIP_UNCHANGED"),
])
def test_default_refresh_and_skip_unchanged_must_be_well_formed(tmp_path, line, hook):
    with pytest.raises(ConfigError, match=hook):
        write_page(tmp_path, line + "\n")


def test_pages_without_the_hooks_behave_as_before():
    clock = load_page_types([REAL])["clock"]
    assert clock.default_refresh is None and clock.skip_unchanged is False


def test_strict_page_accepts_per_page_time_format(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text("pages:\n  - {type: printer, source: moonraker, "
                 "url: 'http://drucker.local:7125', time_format: 12h}\n")
    cfg = load_config(p)
    cfg = validate_config(cfg, load_page_types(cfg.pages_dirs))
    assert cfg.pages[0].time_format == "12h"
