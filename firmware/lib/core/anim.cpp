#include "anim.h"

namespace gb {

namespace {

struct Cursor {
  const char* p;
  size_t n;
  size_t i;

  bool atEnd() const { return i >= n; }
  bool take(char c) {
    if (i < n && p[i] == c) {
      ++i;
      return true;
    }
    return false;
  }
};

int hexVal(char c) {
  if (c >= '0' && c <= '9') return c - '0';
  if (c >= 'a' && c <= 'f') return c - 'a' + 10;
  if (c >= 'A' && c <= 'F') return c - 'A' + 10;
  return -1;
}

// Exactly six hex digits.
bool color(Cursor* c, uint16_t* out) {
  if (c->n - c->i < 6) return false;
  int v[6];
  for (size_t k = 0; k < 6; ++k) {
    v[k] = hexVal(c->p[c->i + k]);
    if (v[k] < 0) return false;
  }
  c->i += 6;
  *out = animRgb565(static_cast<uint8_t>(v[0] * 16 + v[1]), static_cast<uint8_t>(v[2] * 16 + v[3]),
                    static_cast<uint8_t>(v[4] * 16 + v[5]));
  return true;
}

// 1 to 3 decimal digits, no sign, no leading zero except "0" itself.
bool number(Cursor* c, int* out) {
  size_t digits = 0;
  int v = 0;
  while (c->i < c->n && c->p[c->i] >= '0' && c->p[c->i] <= '9') {
    if (digits == 3) return false;
    if (digits == 1 && v == 0) return false;  // leading zero
    v = v * 10 + (c->p[c->i] - '0');
    ++digits;
    ++c->i;
  }
  if (digits == 0) return false;
  *out = v;
  return true;
}

bool track(Cursor* c, AnimTrack* t) {
  int x, y, w, h, speed;
  if (!number(c, &x) || !c->take(',')) return false;
  if (!number(c, &y) || !c->take(',')) return false;
  if (!number(c, &w) || !c->take(',')) return false;
  if (!number(c, &h) || !c->take(',')) return false;
  if (c->take('r')) {
    t->left = false;
  } else if (c->take('l')) {
    t->left = true;
  } else {
    return false;
  }
  if (!c->take(',') || !color(c, &t->color) || !c->take(',')) return false;
  if (!number(c, &speed)) return false;
  if (w < kAnimMinW || w > kAnimMaxW || h < kAnimMinH || h > kAnimMaxH) return false;
  if (x + w > kAnimScreen || y + h > kAnimScreen) return false;
  if (speed < kAnimMinSpeed || speed > kAnimMaxSpeed) return false;
  t->rect = {static_cast<int16_t>(x), static_cast<int16_t>(y), static_cast<int16_t>(w),
             static_cast<int16_t>(h)};
  t->speed = static_cast<uint8_t>(speed);
  return true;
}

bool parseInto(const char* value, size_t len, AnimSpec* s) {
  Cursor c{value, len, 0};
  if (!c.take('1') || !c.take(';')) return false;
  if (!color(&c, &s->background) || !c.take(';')) return false;
  if (!color(&c, &s->trackColor) || !c.take(';')) return false;
  for (;;) {
    if (s->count >= kAnimMaxTracks) return false;
    if (!track(&c, &s->tracks[s->count])) return false;
    ++s->count;
    if (c.atEnd()) break;
    if (!c.take(';')) return false;
  }
  // Rows of two tracks may touch but not overlap.
  for (size_t a = 0; a < s->count; ++a) {
    for (size_t b = a + 1; b < s->count; ++b) {
      const AnimRect& ra = s->tracks[a].rect;
      const AnimRect& rb = s->tracks[b].rect;
      if (ra.y < rb.y + rb.h && rb.y < ra.y + ra.h) return false;
    }
  }
  return true;
}

}  // namespace

uint16_t animRgb565(uint8_t r, uint8_t g, uint8_t b) {
  return static_cast<uint16_t>(((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3));
}

bool parseAnim(const char* value, size_t len, AnimSpec* out) {
  if (out == nullptr) return false;
  out->count = 0;
  if (value == nullptr || len == 0 || len > kAnimMaxValueLen) return false;
  AnimSpec s{};
  s.count = 0;
  if (!parseInto(value, len, &s)) return false;
  *out = s;
  return true;
}

bool animSameGeometry(const AnimSpec& a, const AnimSpec& b) {
  if (a.count != b.count || a.background != b.background || a.trackColor != b.trackColor) {
    return false;
  }
  for (size_t i = 0; i < a.count; ++i) {
    const AnimRect& x = a.tracks[i].rect;
    const AnimRect& y = b.tracks[i].rect;
    if (x.x != y.x || x.y != y.y || x.w != y.w || x.h != y.h) return false;
  }
  return true;
}

}  // namespace gb
