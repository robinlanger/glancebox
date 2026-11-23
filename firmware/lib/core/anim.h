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

}  // namespace gb
