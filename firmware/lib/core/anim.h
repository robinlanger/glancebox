#pragma once
#include <cstddef>
#include <cstdint>

namespace gb {

// Limits of the X-Anim header. They must equal glancebox/anim.py (server/tests/test_anim_parity.py).
constexpr size_t kAnimMaxTracks = 4;
constexpr size_t kAnimMaxValueLen = 160;
constexpr int kAnimScreen = 240;
constexpr int kAnimMinW = 16;
constexpr int kAnimMaxW = 240;
constexpr int kAnimMinH = 8;
constexpr int kAnimMaxH = 32;
constexpr int kAnimMinSpeed = 1;
constexpr int kAnimMaxSpeed = 200;
constexpr int kAnimLineThickness = 3;
constexpr int kAnimArrowSpacing = 18;
constexpr int kAnimArrowHalfHeight = 5;
constexpr int kAnimArrowStroke = 2;

struct AnimRect {
  int16_t x, y, w, h;
};

struct AnimTrack {
  AnimRect rect;
  bool left;       // arrows move to the left
  uint16_t color;  // RGB565
  uint8_t speed;   // px/s
};

struct AnimSpec {
  uint8_t count;        // 0: no (valid) description
  uint16_t background;  // RGB565
  uint16_t trackColor;  // RGB565
  AnimTrack tracks[kAnimMaxTracks];
};

uint16_t animRgb565(uint8_t r, uint8_t g, uint8_t b);

// Parses "1;rrggbb;rrggbb;x,y,w,h,r|l,rrggbb,speed[;...]" (len bytes, no NUL needed; never reads
// beyond len). Any broken limit rejects the whole value: false and out->count == 0.
// No dynamic allocation.
bool parseAnim(const char* value, size_t len, AnimSpec* out);

// Same track count, same rectangles in order and same two base colors (direction, color and
// speed may differ).
bool animSameGeometry(const AnimSpec& a, const AnimSpec& b);

constexpr uint32_t kAnimFrameMs = 40;
constexpr uint16_t kAnimPhaseMod = kAnimArrowSpacing * 1000;  // phase in 1/1000 px, 0..17999
constexpr size_t kAnimClipMax = 16;

// New phase after elapsedMs at speed px/s. Unsigned arithmetic only; elapsedMs above 1000
// counts as 1000. left = true moves the arrows towards smaller x.
uint16_t animAdvance(uint16_t phase, uint32_t elapsedMs, uint8_t speed, bool left);

// block minus the holes: writes the parts still to draw to out, returns their number.
// Parts do not overlap and together cover exactly block without the holes. Should cap not
// suffice, the result is the whole block as one part (cap 0: none), so no pixel of the new
// frame is lost; the arrows are drawn again on the next tick.
// Callers pass cap = kAnimClipMax. Within the device limits (at most kAnimMaxTracks
// non-overlapping holes) that fallback cannot occur at this cap: a brute-force check over
// 3 million random cases peaked at 7 parts.
size_t animClip(const AnimRect& block, const AnimRect* holes, size_t nHoles, AnimRect* out,
                size_t cap);

struct AnimStats {
  uint8_t tracks;        // running now
  uint32_t gapsOver100;  // gaps between two drawn frames > 100 ms while tracks ran visibly
  uint32_t gapsOver250;  // ... > 250 ms
  uint32_t runS;         // seconds since boot with running tracks AND the display visible
                         // (same basis as the gaps: gaps per minute = gaps / (runS / 60))
};

// The tracks of the frame that stands completely on the screen (spec, "Regeln fuer die
// Spuren"). Fixed fields only, no heap.
class AnimState {
 public:
  // 200, before decoding: keeps running tracks whose rect is also in next (new speed,
  // direction and color at once) when both base colors are unchanged; stops all others.
  void onHead200(const AnimSpec& next);
  void onDecoded(uint32_t nowMs);  // frame complete: all tracks of that spec run
  void onDecodeFailed();           // partial frame: nothing runs
  // 304: only changes running tracks. False when tracks run and spec does not have their
  // geometry (or is empty): everything stopped, the caller must drop its ETag.
  bool onHead304(const AnimSpec& spec);
  void stopAll();  // status screen; also drops a pending 200, so only a new frame starts tracks
  // True when a frame is due: tracks run, visible, and >= kAnimFrameMs since the last one.
  // Advances the phases and counts the gaps. visible = false keeps the state, draws nothing.
  // Run time since the previous tick counts with the visibility that tick reported.
  bool tick(uint32_t nowMs, bool visible);
  uint8_t count() const { return count_; }
  const AnimTrack& track(uint8_t i) const;
  uint8_t offsetPx(uint8_t i) const;  // 0..17: x offset of the arrow pattern
  uint16_t background() const { return background_; }
  uint16_t trackColor() const { return trackColor_; }
  AnimStats stats(uint32_t nowMs) const;

 private:
  void addRunTime(uint32_t nowMs);

  AnimTrack tracks_[kAnimMaxTracks] = {};
  uint16_t phase_[kAnimMaxTracks] = {};
  uint8_t count_ = 0;
  uint16_t background_ = 0;
  uint16_t trackColor_ = 0;
  AnimSpec pending_ = {};
  bool havePending_ = false;
  uint32_t lastFrameMs_ = 0;  // last drawn frame, or the start
  bool drawnBefore_ = false;  // lastFrameMs_ is a drawn frame seen without a dark pause
  uint32_t lastRunMs_ = 0;    // run time counted up to here
  bool visible_ = true;       // visibility of the last tick (assumed visible before the first)
  uint32_t runS_ = 0;         // run time: whole seconds ...
  uint32_t runRemMs_ = 0;     // ... plus 0..999 ms (no 64-bit division on the ESP8266)
  uint32_t gaps100_ = 0;
  uint32_t gaps250_ = 0;
};

}  // namespace gb
