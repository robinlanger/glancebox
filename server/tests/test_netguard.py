import pytest

from glancebox.netguard import blocked


@pytest.mark.parametrize("url,page_host,expected", [
    ("data:image/png;base64,AAAA", None, False),
    ("https://example.org/a.png", None, False),
    ("http://192.168.1.20:3000/d/abc", "192.168.1.20", False),
    ("http://192.168.1.20:3000/api/x", "192.168.1.20", False),
    ("http://192.168.1.99/", "192.168.1.20", False),
    ("http://homeassistant:8123/lovelace", "homeassistant", False),
    ("http://homeassistant:8123/api/", "example.org", True),
    ("http://supervisor/core/api/config", "example.org", True),
    ("http://SUPERVISOR/core", None, True),
    ("http://172.30.32.2:8099/", None, True),
    ("http://172.30.33.5/", None, True),
    ("http://172.30.34.1/", None, False),
    ("http://127.0.0.1:8080/", None, True),
    ("http://[::1]/", None, True),
    ("http://169.254.169.254/latest", None, True),
    ("http://a0d7b954-ssh.local.hass.io/", None, True),
    ("file:///etc/passwd", None, True),
    ("ftp://example.org/x", None, True),
    ("http://[", None, True),
    ("http://[::ffff:127.0.0.1]/", None, True),
    ("http://", None, True),
])
def test_blocked(url, page_host, expected):
    assert blocked(url, page_host) is expected
