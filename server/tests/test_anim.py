import dataclasses

import pytest

from glancebox.anim import Anim, Track, encode, line_top

T1 = Track(64, 67, 85, 15, "r", "ffb020", 48)
T2 = Track(64, 133, 85, 15, "l", "34d399", 22)
OK = Anim("0b0d12", "232a38", (T1, T2))


def test_encode_example():
    assert encode(OK) == "1;0b0d12;232a38;64,67,85,15,r,ffb020,48;64,133,85,15,l,34d399,22"


def test_line_top_centres_three_pixels():
    assert line_top(67, 15) == 73 and line_top(67, 14) == 72


def test_encode_lowercases_colors():
    anim = Anim("0B0D12", "232A38", (t(color="FFB020"),))
    assert encode(anim) == "1;0b0d12;232a38;64,67,85,15,r,ffb020,48"


def t(**kw):
    return dataclasses.replace(T1, **kw)


@pytest.mark.parametrize(("anim", "match"), [
    (Anim("0b0d12", "232a38", ()), "tracks"),
    (Anim("0b0d12", "232a38", tuple(t(y=10 + 40 * i) for i in range(5))), "tracks"),
    (Anim("0b0d1", "232a38", (T1,)), "color"),
    (Anim("0b0d12", "#232a38", (T1,)), "color"),
    (Anim("0b0d12", "232a38", (t(color="ffb02g"),)), "color"),
    (Anim("0b0d12", "232a38", (t(x=200),)), "screen"),          # 200 + 85 > 240
    (Anim("0b0d12", "232a38", (t(y=230),)), "screen"),
    (Anim("0b0d12", "232a38", (t(x=-1),)), "screen"),
    (Anim("0b0d12", "232a38", (t(w=15),)), "width"),
    (Anim("0b0d12", "232a38", (t(h=7),)), "height"),
    (Anim("0b0d12", "232a38", (t(h=33),)), "height"),
    (Anim("0b0d12", "232a38", (t(direction="x"),)), "direction"),
    (Anim("0b0d12", "232a38", (t(speed=0),)), "speed"),
    (Anim("0b0d12", "232a38", (t(speed=201),)), "speed"),
    (Anim("0b0d12", "232a38", (T1, t(y=75))), "overlap"),        # rows 75..89 meet 67..81
    (Anim("0b0d12", "232a38", (t(x=True),)), "integer"),
])
def test_encode_rejects(anim, match):
    with pytest.raises(ValueError, match=match):
        encode(anim)


def test_longest_valid_value_fits():
    tracks = tuple(Track(100, 10 + 40 * i, 140, 32, "l", "ffffff", 200) for i in range(4))
    assert len(encode(Anim("ffffff", "ffffff", tracks))) <= 160
