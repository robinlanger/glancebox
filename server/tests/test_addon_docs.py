"""The add-on guide stays in line with the code: examples load, facts match."""

import re
import textwrap
from pathlib import Path

import pytest
import yaml

from glancebox.addon import SECRET_FIELDS, HaInfo, ha_defaults
from glancebox.config import load_config
from glancebox.pages import load_page_types, validate_config

ROOT = Path(__file__).resolve().parents[2]
GUIDES = [ROOT / "ha-addon/DOCS.md", ROOT / "docs/en/home-assistant.md",
          ROOT / "docs/de/home-assistant.md"]
GUIDE_URL = "https://robinlanger.github.io/glancebox/home-assistant/"
EXTRA = {"OCTOPRINT_KEY": "k" * 24}       # the "More secrets" example of the guide
ENV = {"SUPERVISOR_TOKEN": "s", **{var: "x" * 24 for var in SECRET_FIELDS.values()}, **EXTRA}
FENCE = re.compile(r"^(?P<indent>[ \t]*)```yaml[ \t]*\n(?P<body>.*?)^(?P=indent)```[ \t]*$",
                   re.MULTILINE | re.DOTALL)


def _id(path: Path) -> str:
    return path.name + "@" + path.parent.name


def yaml_blocks(path: Path) -> list[str]:
    """Bodies of the ```yaml fences of ``path``, dedented (fences inside lists are indented)."""
    return [textwrap.dedent(m.group("body")) for m in FENCE.finditer(path.read_text())]


def as_config(block: str) -> str:
    """A block is a whole config.yaml (has ``pages:``) or a list of pages (starts with ``- ``)."""
    if re.search(r"^pages:", block, re.MULTILINE):
        return block
    return "pages:\n" + textwrap.indent(block, "  ")


def pages_of(block: str) -> list[dict]:
    return yaml.safe_load(as_config(block))["pages"]


@pytest.mark.parametrize("path", GUIDES, ids=_id)
def test_yaml_examples_load_in_addon_mode(path, tmp_path):
    blocks = yaml_blocks(path)
    assert blocks, "no examples"
    hook = ha_defaults(HaInfo("Europe/Berlin", "en", 50.0, 8.0), ENV)
    for i, block in enumerate(blocks):
        f = tmp_path / f"{i}.yaml"
        f.write_text(as_config(block))
        cfg = load_config(f, defaults=hook, environ=ENV)
        validate_config(cfg, load_page_types(cfg.pages_dirs))     # raises with the block's error


@pytest.mark.parametrize("path", GUIDES, ids=_id)
def test_guide_facts(path):
    text = path.read_text()
    port = yaml.safe_load((ROOT / "ha-addon/config.yaml").read_text())["ports"]["8080/tcp"]
    assert f":{port}" in text
    for var in SECRET_FIELDS.values():
        if var != SECRET_FIELDS["push_key"]:              # the push key is used automatically
            assert f"${{{var}}}" in text, var
    assert re.search(r"^## (Troubleshooting|Fehlerbehebung)$", text, re.MULTILINE)
    assert "time_format" in text
    assert "/healthz" in text
    # placeholders only (192.168.1.x, 192.168.x.x have no four numbers; the setup portal's own
    # address is fixed in the firmware)
    for ip in re.findall(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", text):
        assert ip.startswith("192.168.1.") or ip == "192.168.4.1", ip


def test_examples_cover_the_addon_specific_pages():
    for path in GUIDES[1:]:
        blocks = "\n".join(yaml_blocks(path))
        for needle in ("type: homeassistant", "type: energy", "source: hass", "type: weather",
                       "type: bahn", "provider: claude", "time_format: 12h", "${OCTOPRINT_KEY}"):
            assert needle in blocks, f"{path.name}: {needle}"
        # the point of the add-on: no url/token for pages that read from this Home Assistant
        ha_pages = [p for b in yaml_blocks(path) for p in pages_of(b)
                    if p.get("type") in ("homeassistant", "energy")]
        assert ha_pages and all("url" not in p and "token" not in p for p in ha_pages)


def test_docs_md_links_the_guide_and_stays_short():
    text = GUIDES[0].read_text()
    assert GUIDE_URL in text
    assert len(text.splitlines()) <= 120


def test_guide_has_numbered_steps():
    for path, word in ((GUIDES[1], "Step"), (GUIDES[2], "Schritt")):
        heads = re.findall(rf"^## {word} (\d):", path.read_text(), re.MULTILINE)
        assert heads == ["1", "2", "3", "4"], path
