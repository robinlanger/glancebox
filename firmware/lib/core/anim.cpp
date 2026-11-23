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

namespace {

bool sameRect(const AnimRect& a, const AnimRect& b) {
  return a.x == b.x && a.y == b.y && a.w == b.w && a.h == b.h;
}

}  // namespace

bool animSameGeometry(const AnimSpec& a, const AnimSpec& b) {
  if (a.count != b.count || a.background != b.background || a.trackColor != b.trackColor) {
    return false;
  }
  const size_t n = a.count < kAnimMaxTracks ? a.count : kAnimMaxTracks;
  for (size_t i = 0; i < n; ++i) {
    const AnimRect& x = a.tracks[i].rect;
    const AnimRect& y = b.tracks[i].rect;
    if (x.x != y.x || x.y != y.y || x.w != y.w || x.h != y.h) return false;
  }
  return true;
}

uint16_t animAdvance(uint16_t phase, uint32_t elapsedMs, uint8_t speed, bool left) {
  const uint32_t mod = kAnimPhaseMod;
  const uint32_t ms = elapsedMs > 1000u ? 1000u : elapsedMs;
  const uint32_t delta = (ms * static_cast<uint32_t>(speed)) % mod;  // <= 200000, no overflow
  const uint32_t p = static_cast<uint32_t>(phase) % mod;
  const uint32_t next = left ? (p + mod - delta) % mod : (p + delta) % mod;
  return static_cast<uint16_t>(next);
}

size_t animClip(const AnimRect& block, const AnimRect* holes, size_t nHoles, AnimRect* out,
                size_t cap) {
  if (cap == 0) return 0;
  if (block.w <= 0 || block.h <= 0) return 0;
  AnimRect parts[kAnimClipMax];
  size_t n = 0;
  parts[n++] = block;
  for (size_t k = 0; k < nHoles && holes != nullptr; ++k) {
    const AnimRect& h = holes[k];
    if (h.w <= 0 || h.h <= 0) continue;
    AnimRect next[kAnimClipMax];
    size_t m = 0;
    bool overflow = false;
    for (size_t i = 0; i < n && !overflow; ++i) {
      const AnimRect& p = parts[i];
      const int32_t px1 = p.x + p.w, py1 = p.y + p.h;
      const int32_t ix0 = p.x > h.x ? p.x : h.x;
      const int32_t iy0 = p.y > h.y ? p.y : h.y;
      const int32_t ix1 = px1 < h.x + h.w ? px1 : h.x + h.w;
      const int32_t iy1 = py1 < h.y + h.h ? py1 : h.y + h.h;
      AnimRect pieces[4];
      size_t c = 0;
      if (ix0 >= ix1 || iy0 >= iy1) {
        pieces[c++] = p;  // no overlap: part stays
      } else {
        const auto r = [](int32_t x, int32_t y, int32_t w, int32_t hh) {
          return AnimRect{static_cast<int16_t>(x), static_cast<int16_t>(y),
                          static_cast<int16_t>(w), static_cast<int16_t>(hh)};
        };
        if (iy0 > p.y) pieces[c++] = r(p.x, p.y, p.w, iy0 - p.y);         // above
        if (py1 > iy1) pieces[c++] = r(p.x, iy1, p.w, py1 - iy1);         // below
        if (ix0 > p.x) pieces[c++] = r(p.x, iy0, ix0 - p.x, iy1 - iy0);   // left
        if (px1 > ix1) pieces[c++] = r(ix1, iy0, px1 - ix1, iy1 - iy0);   // right
      }
      for (size_t j = 0; j < c; ++j) {
        if (m >= kAnimClipMax || m >= cap) {
          overflow = true;
          break;
        }
        next[m++] = pieces[j];
      }
    }
    if (overflow) {
      out[0] = block;
      return 1;
    }
    for (size_t i = 0; i < m; ++i) parts[i] = next[i];
    n = m;
    if (n == 0) break;
  }
  for (size_t i = 0; i < n; ++i) out[i] = parts[i];
  return n;
}

void AnimState::onHead200(const AnimSpec& next) {
  pending_ = next;
  if (pending_.count > kAnimMaxTracks) pending_.count = 0;
  havePending_ = true;
  if (pending_.count == 0 || next.background != background_ || next.trackColor != trackColor_) {
    count_ = 0;
    return;
  }
  uint8_t kept = 0;
  for (uint8_t i = 0; i < count_; ++i) {
    for (uint8_t j = 0; j < pending_.count; ++j) {
      if (!sameRect(tracks_[i].rect, pending_.tracks[j].rect)) continue;
      tracks_[kept] = pending_.tracks[j];  // new speed, direction and color at once
      phase_[kept] = phase_[i];
      ++kept;
      break;
    }
  }
  count_ = kept;
}

void AnimState::onDecoded(uint32_t nowMs) {
  if (!havePending_) {
    count_ = 0;
    return;
  }
  havePending_ = false;
  const bool wasRunning = count_ > 0;
  uint16_t phase[kAnimMaxTracks] = {};
  for (uint8_t j = 0; j < pending_.count; ++j) {
    for (uint8_t i = 0; i < count_; ++i) {
      if (sameRect(tracks_[i].rect, pending_.tracks[j].rect)) phase[j] = phase_[i];
    }
  }
  for (uint8_t j = 0; j < pending_.count; ++j) {
    tracks_[j] = pending_.tracks[j];
    phase_[j] = phase[j];
  }
  count_ = pending_.count;
  background_ = pending_.background;
  trackColor_ = pending_.trackColor;
  if (count_ > 0 && !wasRunning) {
    lastFrameMs_ = nowMs;
    drawnBefore_ = false;
    lastRunMs_ = nowMs;
  }
}

void AnimState::onDecodeFailed() {
  havePending_ = false;
  count_ = 0;
}

bool AnimState::onHead304(const AnimSpec& spec) {
  if (count_ == 0) return true;  // a 304 never starts tracks
  AnimSpec running{};
  running.count = count_;
  running.background = background_;
  running.trackColor = trackColor_;
  for (uint8_t i = 0; i < count_; ++i) running.tracks[i] = tracks_[i];
  if (spec.count == 0 || !animSameGeometry(running, spec)) {
    count_ = 0;
    return false;
  }
  for (uint8_t i = 0; i < count_; ++i) {
    tracks_[i].left = spec.tracks[i].left;
    tracks_[i].color = spec.tracks[i].color;
    tracks_[i].speed = spec.tracks[i].speed;
  }
  return true;
}

void AnimState::stopAll() {
  havePending_ = false;
  count_ = 0;
}

namespace {

void addMs(uint32_t* s, uint32_t* remMs, uint32_t ms) {
  *s += ms / 1000u;
  *remMs += ms % 1000u;
  if (*remMs >= 1000u) {
    *remMs -= 1000u;
    ++*s;
  }
}

}  // namespace

void AnimState::addRunTime(uint32_t nowMs) {
  if (visible_) addMs(&runS_, &runRemMs_, nowMs - lastRunMs_);
  lastRunMs_ = nowMs;
}

bool AnimState::tick(uint32_t nowMs, bool visible) {
  if (count_ == 0) return false;
  addRunTime(nowMs);
  visible_ = visible;
  if (!visible) {
    drawnBefore_ = false;  // the dark time is no gap
    return false;
  }
  const uint32_t elapsed = nowMs - lastFrameMs_;  // unsigned: correct across the overflow
  if (elapsed < kAnimFrameMs) return false;
  for (uint8_t i = 0; i < count_; ++i) {
    phase_[i] = animAdvance(phase_[i], elapsed, tracks_[i].speed, tracks_[i].left);
  }
  if (drawnBefore_) {
    if (elapsed > 100) ++gaps100_;
    if (elapsed > 250) ++gaps250_;
  }
  drawnBefore_ = true;
  lastFrameMs_ = nowMs;
  return true;
}

const AnimTrack& AnimState::track(uint8_t i) const {
  return tracks_[i < kAnimMaxTracks ? i : 0];
}

uint8_t AnimState::offsetPx(uint8_t i) const {
  return static_cast<uint8_t>(phase_[i < kAnimMaxTracks ? i : 0] / 1000u);
}

AnimStats AnimState::stats(uint32_t nowMs) const {
  uint32_t runS = runS_;
  uint32_t remMs = runRemMs_;
  if (count_ > 0 && visible_) addMs(&runS, &remMs, nowMs - lastRunMs_);
  AnimStats s;
  s.tracks = count_;
  s.gapsOver100 = gaps100_;
  s.gapsOver250 = gaps250_;
  s.runS = runS;
  return s;
}

}  // namespace gb
