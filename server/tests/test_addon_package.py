"""The Home Assistant add-on files stay in line with the code and the release version."""

import re
import subprocess
from pathlib import Path

import yaml

from glancebox.addon import SECRET_FIELDS

ROOT = Path(__file__).resolve().parents[2]
ADDON = ROOT / "ha-addon"


def addon_config() -> dict:
    return yaml.safe_load((ADDON / "config.yaml").read_text())


def test_repository_file():
    repo = yaml.safe_load((ROOT / "repository.yaml").read_text())
    assert repo["name"] == "Glance Box"
    assert repo["url"] == "https://github.com/robinlanger/glancebox"


def test_addon_version_matches():
    assert addon_config()["version"] == (ROOT / "VERSION").read_text().strip()


def test_addon_schema_matches_secret_fields():
    schema = addon_config()["schema"]
    assert set(schema) - {"extra_secrets"} == set(SECRET_FIELDS)
    assert all(schema[k] == "password?" for k in SECRET_FIELDS)
    assert schema["extra_secrets"] == [{"name": "match(^[A-Z][A-Z0-9_]*$)", "value": "password"}]


def test_addon_permissions():
    c = addon_config()
    assert c["slug"] == "glancebox"
    assert c["image"] == "ghcr.io/robinlanger/glancebox"
    assert c["arch"] == ["amd64", "aarch64"]
    assert c["startup"] == "application"
    assert c["init"] is True
    assert c["ingress"] is True and c["ingress_port"] == 8099
    assert c["panel_icon"] == "mdi:monitor" and c["panel_admin"] is True
    assert c["homeassistant_api"] is True
    assert c["hassio_api"] is True and c["hassio_role"] == "default"
    assert c["map"] == [{"type": "app_config", "read_only": False}]
    assert c["ports"] == {"8080/tcp": 8090}
    for key in ("host_network", "docker_api", "full_access", "privileged", "host_pid",
                "apparmor", "auth_api", "devices", "kernel_modules"):
        assert key not in c, key


def test_translations_cover_schema():
    schema = addon_config()["schema"]
    for lang in ("en", "de"):
        tr = yaml.safe_load((ADDON / "translations" / f"{lang}.yaml").read_text())
        assert set(tr["configuration"]) == set(schema), lang
        assert all(tr["configuration"][k].get("name") for k in schema), lang


def test_only_one_addon_config():
    files = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True,
                           check=True).stdout.split()
    # The Supervisor reads every config.*.(yaml|yml|json) as an add-on (it warned about
    # config.example.yaml), so no other file may match that pattern.
    configs = [f for f in files if Path(f).name.startswith("config.")
               and Path(f).suffix in (".yaml", ".yml", ".json")
               and not any(part.startswith(".") for part in Path(f).parts)]
    assert configs == ["ha-addon/config.yaml"]


def test_runtime_lock_is_hashed_and_has_no_dev_tools():
    text = (ROOT / "server/requirements.lock").read_text()
    assert "--hash=sha256:" in text
    for dev in ("pytest", "ruff", "httpx"):
        assert not re.search(rf"^{dev}==", text, re.MULTILINE)


def test_workflows_pin_actions_by_commit():
    for wf in (ROOT / ".github/workflows").glob("*.yml"):
        for line in wf.read_text().splitlines():
            if "uses:" in line:
                assert re.search(r"@[0-9a-f]{40}\b", line), f"{wf.name}: {line.strip()}"


def test_base_image_pinned_by_digest():
    assert re.search(r"^FROM mcr\.microsoft\.com/playwright/python:\S+@sha256:[0-9a-f]{64}",
                     (ROOT / "Dockerfile").read_text(), re.MULTILINE)
