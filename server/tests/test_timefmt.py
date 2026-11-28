from datetime import datetime, time

import pytest

from glancebox.timefmt import TIME_FORMATS, convert_hhmm, format_hour, format_time, split_suffix


def test_formats():
    assert TIME_FORMATS == ("24h", "12h")


@pytest.mark.parametrize(("hm", "h24", "h12"), [
    ((0, 0), "00:00", "12:00 AM"), ((0, 59), "00:59", "12:59 AM"), ((1, 5), "01:05", "1:05 AM"),
    ((9, 5), "09:05", "9:05 AM"), ((11, 59), "11:59", "11:59 AM"), ((12, 0), "12:00", "12:00 PM"),
    ((12, 59), "12:59", "12:59 PM"), ((13, 0), "13:00", "1:00 PM"), ((23, 59), "23:59", "11:59 PM"),
])
def test_format_time(hm, h24, h12):
    for when in (time(*hm), datetime(2026, 11, 28, *hm)):
        assert format_time(when) == h24
        assert format_time(when, "24h") == h24
        assert format_time(when, "12h") == h12


@pytest.mark.parametrize(("hour", "h24", "h12"), [
    (0, "00", "12 AM"), (3, "03", "3 AM"), (12, "12", "12 PM"), (15, "15", "3 PM"),
    (23, "23", "11 PM")])
def test_format_hour(hour, h24, h12):
    assert (format_hour(time(hour, 30)), format_hour(time(hour, 30), "12h")) == (h24, h12)


@pytest.mark.parametrize(("text", "parts"), [
    ("2:05 PM", ("2:05", "PM")), ("12:00 AM", ("12:00", "AM")), ("14:05", ("14:05", "")),
    ("Tue 9:14 PM", ("Tue 9:14", "PM")), ("", ("", "")), ("PM", ("PM", "")),
    ("2:05 pm", ("2:05 pm", "")), ("Stand 14:05", ("Stand 14:05", ""))])
def test_split_suffix(text, parts):
    assert split_suffix(text) == parts


@pytest.mark.parametrize(("text", "h12"), [
    ("21:10", "9:10 PM"), ("00:05", "12:05 AM"), ("7:40", "7:40 AM"), ("12:00", "12:00 PM"),
    ("", ""), ("24:10", "24:10"), ("12:60", "12:60"), ("--:--", "--:--"), ("21.10", "21.10"),
    ("21:10:00", "21:10:00")])
def test_convert_hhmm(text, h12):
    assert convert_hhmm(text) == text
    assert convert_hhmm(text, "24h") == text
    assert convert_hhmm(text, "12h") == h12


def test_unknown_format_is_an_error():
    with pytest.raises(ValueError, match="time_format"):
        format_time(time(1, 2), "am")
