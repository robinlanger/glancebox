#include "display.h"

#include "night.h"
#include "poll_timing.h"
#include "settings.h"
#include "tjpgd.h"

namespace {
constexpr uint8_t kBacklightPin = 5;
constexpr int kHeight = 240;

TFT_eSPI tft;

// TJpgDec work pool: static, never heap (size verified by test_tjpgd).
alignas(4) uint8_t jpegPool[gb::kJpegPoolBytes];

// Arrows of the frame on the screen (static, no heap).
gb::AnimState anim;
bool backlightOn = false;  // set by displaySetBacklight: nothing is drawn while dark

// Chevron with its tip at (tx, cy), kAnimArrowStroke px wide towards its open side.
void drawChevron(int tx, int cy, bool left, uint16_t color) {
  const int d = left ? gb::kAnimArrowHalfHeight : -gb::kAnimArrowHalfHeight;
  const int step = left ? 1 : -1;
  for (int s = 0; s < gb::kAnimArrowStroke; ++s) {
    const int x = tx + s * step;
    tft.drawLine(x + d, cy - gb::kAnimArrowHalfHeight, x, cy, color);
    tft.drawLine(x + d, cy + gb::kAnimArrowHalfHeight, x, cy, color);
  }
}

void drawTrack(uint8_t i) {
  const gb::AnimTrack& t = anim.track(i);
  const gb::AnimRect& r = t.rect;
  tft.startWrite();
  tft.fillRect(r.x, r.y, r.w, r.h, anim.background());
  tft.fillRect(r.x, r.y + (r.h - gb::kAnimLineThickness) / 2, r.w, gb::kAnimLineThickness,
               anim.trackColor());
  tft.setViewport(r.x, r.y, r.w, r.h, false);  // clips the arrows at the track edges
  const int cy = r.y + r.h / 2;
  const int end = r.x + r.w + gb::kAnimArrowSpacing;
  for (int tx = r.x + anim.offsetPx(i) - gb::kAnimArrowSpacing; tx <= end;
       tx += gb::kAnimArrowSpacing) {
    drawChevron(tx, cy, t.left, t.color);
  }
  tft.resetViewport();
  tft.endWrite();
}

bool overlaps(const gb::AnimRect& a, const gb::AnimRect& b) {
  return a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
}

// Streaming source: never reads beyond len bytes; gives up at the deadline.
struct JpegSource {
  Stream* stream;
  size_t left;          // bytes of the body not consumed yet
  uint32_t startMs;
  uint32_t deadlineMs;  // overall budget for the whole body
  bool starved;         // stream ended or stalled before tjpgd got what it asked for
};

// Input callback: read (or skip, when buf is null) up to n bytes from the stream.
// Returns fewer than n only on failure; tjpgd then aborts with JDR_INP.
size_t jpegInput(JDEC* jd, uint8_t* buf, size_t n) {
  auto* src = static_cast<JpegSource*>(jd->device);
  if (n > src->left) n = src->left;
  uint8_t skip[64];
  size_t done = 0;
  while (done < n) {
    if (millis() - src->startMs >= src->deadlineMs) break;
    const int avail = src->stream->available();
    if (avail <= 0) {
      displayAnimTick();  // only draws; the deadline above stays as it is
      delay(0);           // yield: watchdog, TCP stack
      continue;
    }
    size_t want = n - done;
    if (want > static_cast<size_t>(avail)) want = static_cast<size_t>(avail);
    if (buf == nullptr && want > sizeof(skip)) want = sizeof(skip);
    const size_t got = src->stream->readBytes(buf != nullptr ? buf + done : skip, want);
    if (got == 0) break;
    done += got;
  }
  src->left -= done;
  if (done < n) src->starved = true;
  return done;
}

// Output callback: push one decoded RGB565 block, leaving out the rectangles of running
// tracks; stop below the visible area.
int jpegOutput(JDEC*, void* bitmap, JRECT* rect) {
  displayAnimTick();
  if (rect->top >= kHeight) return 0;
  const gb::AnimRect block{static_cast<int16_t>(rect->left), static_cast<int16_t>(rect->top),
                           static_cast<int16_t>(rect->right - rect->left + 1),
                           static_cast<int16_t>(rect->bottom - rect->top + 1)};
  auto* px = static_cast<uint16_t*>(bitmap);
  gb::AnimRect holes[gb::kAnimMaxTracks];
  size_t nHoles = 0;
  for (uint8_t i = 0; i < anim.count() && nHoles < gb::kAnimMaxTracks; ++i) {
    const gb::AnimRect& r = anim.track(i).rect;
    if (overlaps(block, r)) holes[nHoles++] = r;
  }
  if (nHoles == 0) {
    tft.pushImage(block.x, block.y, block.w, block.h, px);
    return 1;
  }
  gb::AnimRect parts[gb::kAnimClipMax];
  const size_t n = gb::animClip(block, holes, nHoles, parts, gb::kAnimClipMax);
  tft.startWrite();
  for (size_t k = 0; k < n; ++k) {
    const gb::AnimRect& p = parts[k];
    // Row by row straight from the block bitmap; pushPixels honours setSwapBytes like
    // pushImage.
    tft.setAddrWindow(p.x, p.y, p.w, p.h);
    const uint16_t* row = px + (p.y - block.y) * block.w + (p.x - block.x);
    for (int16_t y = 0; y < p.h; ++y, row += block.w) tft.pushPixels(row, p.w);
  }
  tft.endWrite();
  return 1;
}
}  // namespace

TFT_eSPI& displayTft() { return tft; }

void displaySetBacklight(uint8_t pct) {
  backlightOn = pct > 0;
  // Backlight is active-low: write the off-time of the perceptual on-time.
  analogWrite(kBacklightPin, gb::kBacklightPwmRange - gb::backlightDuty(pct));
}

void displaySetBrightness(uint8_t pct) { displaySetBacklight(gb::clampBrightness(pct)); }

void displayBegin(uint8_t brightnessPct) {
  analogWriteRange(gb::kBacklightPwmRange);
  displaySetBacklight(0);  // keep dark until the controller is initialised
  tft.init();
  tft.invertDisplay(true);
  tft.setSwapBytes(true);  // TJpgDec emits native-endian RGB565
  tft.fillScreen(TFT_BLACK);
  displaySetBrightness(brightnessPct);
}

void displayAnimTick() {
  if (!anim.tick(millis(), backlightOn)) return;
  for (uint8_t i = 0; i < anim.count(); ++i) drawTrack(i);
}

gb::AnimStats displayAnimStats() { return anim.stats(millis()); }

bool displayAnimNotModified(const gb::AnimSpec& spec) { return anim.onHead304(spec); }

JpegStreamResult displayJpegStream(Stream& stream, size_t len, uint32_t deadlineMs,
                                   const gb::AnimSpec& spec) {
  JpegSource src{&stream, len, millis(), deadlineMs, false};
  anim.onHead200(spec);  // stops the tracks this frame paints over
  JDEC jd;
  JRESULT rc = jd_prepare(&jd, jpegInput, jpegPool, sizeof(jpegPool), &src);
  if (rc == JDR_OK) rc = jd_decomp(&jd, jpegOutput, 0);
  if (rc == JDR_OK || rc == JDR_INTR) {  // INTR: below the visible area
    anim.onDecoded(millis());
    return JpegStreamResult::Ok;
  }
  anim.onDecodeFailed();
  return src.starved ? JpegStreamResult::InputError : JpegStreamResult::DecodeError;
}

void displayStatus(const char* title, const char* const* lines, size_t n) {
  anim.stopAll();
  tft.fillScreen(TFT_BLACK);
  tft.setTextColor(TFT_WHITE, TFT_BLACK);
  tft.setTextDatum(TL_DATUM);
  tft.drawString(title, 8, 8, 4);
  int y = 48;
  for (size_t i = 0; i < n; i++) {
    tft.drawString(lines[i], 8, y, 2);
    y += 20;
  }
}
