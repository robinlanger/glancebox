"""Tests of the shared schema and helpers in providers/_common.py."""

import base64
import io
from datetime import UTC, datetime, timedelta

import pytest
import requests
from conftest import NOW
from PIL import Image


@pytest.mark.parametrize(("path", "name"), [
    ("benchy_0.2mm_PLA.gcode", "benchy_0.2mm_PLA"),
    ("Teile/Halter #2 groß.GCODE", "Halter #2 groß"),
    ("/usb/BOX.BGCODE", "BOX"), ("plate_1.gcode.3mf", "plate_1"), ("deckel.3mf", "deckel"),
    ("ohne_endung", "ohne_endung"), ("", None), (None, None),
])
def test_clean_filename(common, path, name):
    assert common.clean_filename(path) == name


def test_clean_filename_takes_windows_paths(common):
    assert common.clean_filename("C:\\Drucke\\deckel.gcode") == "deckel"


@pytest.mark.parametrize(("seconds", "de", "en"), [
    (0, "noch <1 min", "<1 min left"), (59, "noch <1 min", "<1 min left"),
    (1380, "noch 23 min", "23 min left"), (3599, "noch 59 min", "59 min left"),
    (4980, "noch 1:23 h", "1:23 h left"), (86399, "noch 23:59 h", "23:59 h left"),
    (97200, "noch 1 d 3 h", "1 d 3 h left"),
])
def test_remaining_text(common, seconds, de, en):
    assert (common.remaining_text(seconds, "de"), common.remaining_text(seconds, "en")) == (de, en)


def test_duration_text(common):
    assert common.duration_text(11520, "de") == "Dauer 3:12 h"
    assert common.duration_text(2700, "en") == "Took 45 min"


@pytest.mark.parametrize(("when", "de", "en"), [
    (datetime(2026, 11, 25, 15, 55), "15:55", "15:55"),
    (datetime(2026, 11, 24, 21, 14), "gestern 21:14", "yesterday 21:14"),
    (datetime(2026, 11, 30, 7, 40), "Mo 07:40", "Mon 07:40"),
    (datetime(2026, 11, 26, 0, 5), "Do 00:05", "Thu 00:05"),
    (datetime(2026, 11, 10, 7, 40), "10.11. 07:40", "Nov 10 07:40"),
])
def test_clock_text(common, when, de, en):
    when = when.replace(tzinfo=NOW.tzinfo)
    assert (common.clock_text(when, NOW, "de"), common.clock_text(when, NOW, "en")) == (de, en)


def test_clock_text_converts_to_the_zone_of_now(common):
    when = datetime(2026, 11, 25, 14, 55, tzinfo=UTC)
    assert common.clock_text(when, NOW, "de") == "15:55"


def test_ago_text(common):
    at = lambda **kw: NOW - timedelta(**kw)
    assert common.ago_text(at(seconds=20), NOW, "de") == "gerade eben"
    assert common.ago_text(at(minutes=4), NOW, "de") == "vor 4 min"
    assert common.ago_text(at(minutes=4), NOW, "en") == "4 min ago"
    assert common.ago_text(at(hours=3, minutes=10), NOW, "de") == "vor 3 h"
    assert common.ago_text(at(days=2), NOW, "en") == "2 d ago"
    assert common.ago_text(NOW + timedelta(minutes=5), NOW, "en") == "just now"   # clock skew


def test_numbers_at_the_edges(common):                       # Review Focus 4
    assert [common.clamp_progress(v) for v in (47.4, 104, -3, "12.5")] == [47.4, 100.0, 0.0, 12.5]
    assert [common.clamp_progress(v) for v in (float("nan"), "unknown", None, True)] == [None] * 4
    assert common.temp(214.2, 215) == (214.2, 215.0)
    assert common.temp("60", None) == (60.0, None) and common.temp(23.0, 0) == (23.0, None)
    assert common.temp(None, 215) is None and common.temp("unavailable", 0) is None
    assert common.remaining_text(-300, "de") == "noch <1 min"


def test_number_never_raises(common):
    assert [common.number(v) for v in (3, "4.5", float("inf"), "nan", [], {}, object())] == \
        [3.0, 4.5, None, None, None, None, None]


# --- thumbnails ----------------------------------------------------------------

def _image(fmt, size, mode="RGB"):
    buf = io.BytesIO()
    Image.new(mode, size, (200, 30, 30)).save(buf, fmt)
    return buf.getvalue()


def _decode(uri):
    return Image.open(io.BytesIO(base64.b64decode(uri.split(",", 1)[1])))


def test_data_uri_normalises_the_image(common):
    T = common.Thumbnail
    for thumb, ratio in ((T(_image("PNG", (300, 200)), "image/png"), 1.5),
                         (T(_image("JPEG", (300, 300)), "image/jpeg"), 1.0)):
        uri = common.data_uri(thumb)
        assert uri.startswith("data:image/png;base64,")
        img = _decode(uri)
        assert img.format == "PNG" and img.mode in ("RGB", "RGBA")
        assert max(img.size) <= 100 and img.size[0] / img.size[1] == pytest.approx(ratio, 0.02)
        assert common.data_uri(thumb) == uri                   # stable for SKIP_UNCHANGED


def test_broken_or_huge_image_gives_no_thumbnail(common):     # Review Focus 3
    T = common.Thumbnail
    for thumb in (T(b"qoif\x00\x00\x00\x10\x00\x00\x00\x10\x04\x00", "image/png"),
                  T(b"<html>404</html>", "image/png"),
                  T(_image("PNG", (300, 300))[:100], "image/png"),
                  T(_image("PNG", (5000, 10)), "image/png")):
        assert common.data_uri(thumb) is None
    assert common.data_uri(None) is None


def test_cached_thumbnail(common):
    thumb = common.Thumbnail(b"png", "image/png")
    calls = []

    def loader(result):
        def load():
            calls.append(result)
            if isinstance(result, Exception):
                raise result
            return result
        return load

    assert common.cached_thumbnail(("t", 1), loader(thumb)) is thumb
    assert common.cached_thumbnail(("t", 1), loader(None)) is thumb
    assert len(calls) == 1

    for result in (None, ValueError("broken")):
        calls.clear()
        assert common.cached_thumbnail(("t", 2), loader(result)) is None
        assert common.cached_thumbnail(("t", 2), loader(result)) is None
        assert len(calls) == 2                                  # failures are not cached

    for i in range(5):
        common.cached_thumbnail(("many", i), loader(thumb))
    assert len(common._thumbs) <= 4
    calls.clear()
    common.cached_thumbnail(("many", 4), loader(thumb))
    assert calls == []                                          # the newest stays


# --- budget and errors -----------------------------------------------------------

def test_budget(common):
    now = [100.0]
    budget = common.Budget(clock=lambda: now[0])
    assert budget.timeout() == 5
    now[0] += 12
    assert budget.left() == pytest.approx(3) and budget.timeout() == pytest.approx(3)
    now[0] += 3
    with pytest.raises(common.SourceError) as err:
        budget.timeout()
    assert err.value.kind == "unreachable"


def _http(status):
    resp = requests.Response()
    resp.status_code = status
    return requests.HTTPError(f"{status} Client Error for url: {URL}", response=resp)


URL = "http://drucker.local:7125/api/job?apikey=S3CRET"


@pytest.mark.parametrize(("exc", "direct", "kind"), [
    (_http(401), True, "auth"), (_http(403), False, "auth"),
    (requests.ConnectionError(f"Max retries exceeded with url: {URL}"), True, "offline"),
    (requests.ConnectionError(f"Max retries exceeded with url: {URL}"), False, "unreachable"),
    (requests.Timeout("read timed out"), True, "offline"),
    (requests.Timeout("read timed out"), False, "unreachable"),
    (_http(500), True, "data"), (_http(404), False, "unreachable"),
    (ValueError("Expecting value"), True, "data"), (ValueError("x"), False, "unreachable"),
    (TypeError("x"), True, "data"), (KeyError("result"), True, "data"),
    (KeyError("result"), False, "unreachable"),
])
def test_source_error_mapping(common, exc, direct, kind):
    err = common.source_error(exc, URL, direct=direct)
    assert isinstance(err, common.SourceError) and err.kind == kind
    assert err.cause is exc
    for text in (str(err), repr(err), err.url):
        assert "S3CRET" not in text and "apikey" not in text
    assert "drucker.local:7125/api/job" in str(err)


def test_source_error_keeps_a_source_error(common):
    err = common.SourceError("config", "Entität fehlt: sensor.x")
    assert common.source_error(err, URL, direct=True) is err
    assert err.detail == "Entität fehlt: sensor.x" and err.url is None
