#pragma once
#include <Arduino.h>
#include <TFT_eSPI.h>

#include "anim.h"

// Initialise the ST7789 (inversion on) and the inverted PWM backlight on GPIO5.
void displayBegin(uint8_t brightnessPct);
void displaySetBrightness(uint8_t pct);
// Raw backlight 0..100 % (0 = fully off); used by night mode.
void displaySetBacklight(uint8_t pct);
enum class JpegStreamResult : uint8_t { Ok, InputError, DecodeError };
// Decodes a baseline 240x240 JPEG of exactly len bytes straight from the stream to (0,0),
// block by block (no frame buffer). Never reads beyond len bytes; gives up when the body
// is not complete within deadlineMs. On failure the frame is left partially drawn.
// anim: the X-Anim tracks of this frame (count 0: none). Tracks that keep running are
// left out of the decoded blocks; new ones start once the frame is complete; a failed
// decode stops all (gb::AnimState rules).
JpegStreamResult displayJpegStream(Stream& stream, size_t len, uint32_t deadlineMs,
                                   const gb::AnimSpec& anim);
// 304 with this X-Anim: takes speed, direction and color of the running tracks. False when
// tracks ran and anim does not match their geometry: all stopped, the caller must drop its
// ETag so the next request fetches the frame again.
bool displayAnimNotModified(const gb::AnimSpec& anim);
// Draws one frame of the running arrows when due (at most every gb::kAnimFrameMs) and the
// backlight is on; otherwise returns at once. Only draws: no network or web server calls.
void displayAnimTick();
gb::AnimStats displayAnimStats();
// Title (font 4) plus up to n lines (font 2), ASCII only. Stops all arrows first.
void displayStatus(const char* title, const char* const* lines, size_t n);
// Direct access for the spike test pattern.
TFT_eSPI& displayTft();
