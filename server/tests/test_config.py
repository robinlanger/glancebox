from pathlib import Path

import pytest

from glancebox.config import ConfigError, load_config


def write(tmp_path: Path, text: str) -> Path:
    p = tmp_path / "config.yaml"
    p.write_text(text)
    return p


def test_defaults(tmp_path):
    cfg = load_config(write(tmp_path, "interval: 30\npages:\n  - type: bahn\n    station: X\n"))
    page = cfg.pages[0]
    assert (page.index, page.type) == (0, "bahn")
    assert page.duration == 30
    assert page.refresh == 30
    assert page.refresh_explicit is False
    assert page.options == {"station": "X"}
    assert cfg.interval == 30
    assert cfg.timezone == "Europe/Berlin"
    assert cfg.lang == "de"
    assert len(cfg.pages_dirs) == 1 and cfg.pages_dirs[0].name == "pages"


def test_explicit_duration_and_refresh(tmp_path):
    cfg = load_config(write(tmp_path, "pages:\n  - {type: url, url: u, duration: 15}\n"
                                      "  - {type: url, url: u, duration: 15, refresh: 60}\n"))
    assert cfg.interval == 30
    assert (cfg.pages[0].duration, cfg.pages[0].refresh) == (15, 15)
    assert cfg.pages[1].refresh == 60
    assert cfg.pages[1].refresh_explicit is True


def test_empty_pages_rejected(tmp_path):
    with pytest.raises(ConfigError, match="at least one page"):
        load_config(write(tmp_path, "pages: []\n"))


def test_yaml_syntax_error_is_config_error(tmp_path):
    with pytest.raises(ConfigError, match="config.yaml"):
        load_config(write(tmp_path, "pages: [unclosed\n  - : :\n"))


def test_yaml_syntax_error_redacts_urls(tmp_path):
    with pytest.raises(ConfigError) as err:
        load_config(write(tmp_path, 'pages:\n  - url: "http://h/x?token=abc\n'))
    assert "http://h/x?***" in str(err.value) and "abc" not in str(err.value)


def test_missing_file_is_config_error(tmp_path):
    with pytest.raises(ConfigError, match="nope.yaml"):
        load_config(tmp_path / "nope.yaml")


def test_duration_must_be_positive(tmp_path):
    with pytest.raises(ConfigError, match=r"pages\[0\]"):
        load_config(write(tmp_path, "pages:\n  - {type: bahn, duration: 0}\n"))


def test_missing_type_rejected(tmp_path):
    with pytest.raises(ConfigError, match=r"pages\[1\].*type"):
        load_config(write(tmp_path, "pages:\n  - {type: url}\n  - {url: u}\n"))


def test_unknown_top_level_key_rejected(tmp_path):
    with pytest.raises(ConfigError, match="intervall"):
        load_config(write(tmp_path, "intervall: 5\npages:\n  - {type: url}\n"))


def test_invalid_interval_rejected(tmp_path):
    with pytest.raises(ConfigError, match="interval"):
        load_config(write(tmp_path, "interval: true\npages:\n  - {type: url}\n"))


def test_custom_pages_dir_relative_to_config(tmp_path):
    (tmp_path / "mine").mkdir()
    cfg = load_config(write(tmp_path, "custom_pages_dir: mine\npages:\n  - {type: url}\n"))
    assert cfg.pages_dirs[-1] == (tmp_path / "mine").resolve()
    assert len(cfg.pages_dirs) == 2


def test_pages_dir_env_override(tmp_path, monkeypatch):
    monkeypatch.setenv("GLANCEBOX_PAGES_DIR", str(tmp_path / "builtin"))
    cfg = load_config(write(tmp_path, "pages:\n  - {type: url}\n"))
    assert cfg.pages_dirs[0] == tmp_path / "builtin"


def test_missing_custom_pages_dir_is_a_warning(tmp_path, caplog):
    cfg = load_config(write(tmp_path, "custom_pages_dir: nope\npages:\n  - {type: url}\n"))
    assert len(cfg.pages_dirs) == 1  # only the built-in dir is left
    assert "custom_pages_dir" in caplog.text and "nope" in caplog.text


@pytest.mark.parametrize("tz", ["Europe/Berln", "../etc/passwd", ""])
def test_unknown_timezone_rejected(tmp_path, tz):
    with pytest.raises(ConfigError, match=r"timezone: unknown time zone"):
        load_config(write(tmp_path, f"timezone: '{tz}'\npages:\n  - type: bahn\n"))


def test_valid_timezone_accepted(tmp_path):
    cfg = load_config(write(tmp_path, "timezone: America/New_York\npages:\n  - type: bahn\n"))
    assert cfg.timezone == "America/New_York"


def test_env_whole_value_is_expanded(tmp_path, monkeypatch):
    monkeypatch.setenv("KUMA_URL", "http://kuma.lan:3001")
    cfg = load_config(write(tmp_path, "pages:\n  - type: clock\n    url: ${KUMA_URL}\n"))
    assert cfg.pages[0].options["url"] == "http://kuma.lan:3001"


def test_env_inside_longer_string_stays_literal(tmp_path, monkeypatch):
    monkeypatch.setenv("HOST", "x")
    cfg = load_config(write(tmp_path, "pages:\n  - type: clock\n    url: http://${HOST}:1\n"))
    assert cfg.pages[0].options["url"] == "http://${HOST}:1"


@pytest.mark.parametrize("value", [None, ""])
def test_env_missing_or_empty_names_path_and_variable(tmp_path, monkeypatch, value):
    monkeypatch.delenv("NOPE", raising=False)
    if value is not None:
        monkeypatch.setenv("NOPE", value)
    with pytest.raises(ConfigError, match=r"pages\[0\]\.token: environment variable NOPE"):
        load_config(write(tmp_path, "pages:\n  - type: clock\n    token: ${NOPE}\n"))


def test_push_key_from_env(tmp_path, monkeypatch):
    monkeypatch.setenv("GLANCEBOX_PUSH_KEY", "k" * 32)
    cfg = load_config(write(tmp_path, "push_key: ${GLANCEBOX_PUSH_KEY}\npages:\n  - type: clock\n"))
    assert cfg.push_key == "k" * 32


def test_load_config_uses_given_environ(tmp_path, monkeypatch):
    monkeypatch.delenv("MY_KEY", raising=False)
    p = tmp_path / "config.yaml"
    p.write_text("push_key: ${MY_KEY}\npages:\n  - type: clock\n")
    cfg = load_config(p, environ={"MY_KEY": "k" * 16})
    assert cfg.push_key == "k" * 16


def test_push_key_too_short(tmp_path):
    with pytest.raises(ConfigError, match="push_key"):
        load_config(write(tmp_path, "push_key: short\npages:\n  - type: clock\n"))


def test_push_key_must_be_ascii(tmp_path):
    # Starlette decodes headers as latin-1, so a non-ASCII key could never match.
    with pytest.raises(ConfigError, match="push_key must contain only ASCII"):
        load_config(write(tmp_path, f"push_key: {'ä' * 32}\npages:\n  - type: clock\n"))


def test_push_key_default_none(tmp_path):
    assert load_config(write(tmp_path, "pages:\n  - type: clock\n")).push_key is None


def test_defaults_hook_runs_after_env_and_before_validation(tmp_path, monkeypatch):
    monkeypatch.setenv("K", "x" * 16)
    p = tmp_path / "c.yaml"
    p.write_text("push_key: ${K}\npages:\n  - type: clock\n")
    seen = {}

    def hook(data):
        seen.update(data)
        return {**data, "timezone": "America/New_York", "lang": "en"}

    cfg = load_config(p, defaults=hook)
    assert seen["push_key"] == "x" * 16
    assert (cfg.timezone, cfg.lang) == ("America/New_York", "en")


def test_no_hook_keeps_old_defaults(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text("pages:\n  - type: clock\n")
    cfg = load_config(p)
    assert (cfg.timezone, cfg.lang) == ("Europe/Berlin", "de")


def test_defaults_hook_must_return_mapping(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text("pages:\n  - type: clock\n")
    with pytest.raises(ConfigError):
        load_config(p, defaults=lambda d: None)


def test_time_format_default_and_values(tmp_path):
    base = "pages:\n  - type: clock\n"
    assert load_config(write(tmp_path, base)).time_format == "24h"
    assert load_config(write(tmp_path, "time_format: 12h\n" + base)).time_format == "12h"
    assert load_config(write(tmp_path, "time_format: 24h\n" + base)).time_format == "24h"
    assert load_config(write(tmp_path, "time_format:\n" + base)).time_format == "24h"  # empty


@pytest.mark.parametrize("value", ["12", "12H", "am", "'12'", "true", "[12h]"])
def test_time_format_rejects_other_values(tmp_path, value):
    with pytest.raises(ConfigError, match="time_format must be '24h' or '12h'"):
        load_config(write(tmp_path, f"time_format: {value}\npages:\n  - type: clock\n"))


def test_time_format_per_page(tmp_path):
    cfg = load_config(write(tmp_path, "time_format: 12h\npages:\n  - type: clock\n"
                                      "  - {type: bahn, station: X, time_format: 24h}\n"))
    assert [p.time_format for p in cfg.pages] == [None, "24h"]
    assert "time_format" not in cfg.pages[1].options       # reserved, like duration/refresh


def test_time_format_per_page_rejects_other_values(tmp_path):
    with pytest.raises(ConfigError, match=r"pages\[0\]: time_format must be '24h' or '12h'"):
        load_config(write(tmp_path, "pages:\n  - {type: clock, time_format: am}\n"))
