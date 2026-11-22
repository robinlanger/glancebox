#include "frame_poll.h"

#include <cstdio>
#include <cstring>

#include "poll_timing.h"

namespace gb {

int parseNextIn(const char* h) {
  if (h == nullptr) return -1;
  while (*h == ' ' || *h == '\t') ++h;
  if (*h < '0' || *h > '9') return -1;
  int v = 0;
  while (*h >= '0' && *h <= '9') {
    if (v < 9999) v = v * 10 + (*h - '0');
    if (v > 9999) v = 9999;
    ++h;
  }
  while (*h == ' ' || *h == '\t') ++h;
  return *h == '\0' ? v : -1;
}

bool storeEtag(char (&dst)[kEtagCap], const char* src) {
  dst[0] = '\0';
  if (src == nullptr) return false;
  const size_t n = strlen(src);
  if (n >= kEtagCap) return false;
  memcpy(dst, src, n + 1);
  return true;
}

void frameErrorText(int status, char* buf, size_t cap) {
  if (cap == 0) return;
  const char* fixed = nullptr;
  switch (status) {
    case -1: fixed = "connection failed"; break;
    case -4: fixed = "not connected"; break;
    case -5: fixed = "connection lost"; break;
    case -11: fixed = "read timeout"; break;
    case kErrFrameLength: fixed = "bad frame size"; break;
    case kErrBodyRead: fixed = "frame incomplete"; break;
    case kErrDecode: fixed = "bad JPEG"; break;
    case kErrNoWifi: fixed = "no Wi-Fi"; break;
    case kErrBadUrl: fixed = "bad server URL"; break;
    case kErrHeadTooLarge: fixed = "reply too large"; break;
    case kErrHeadTimeout: fixed = "server too slow"; break;
    case kErrHeadMalformed: fixed = "bad reply"; break;
    default: break;
  }
  if (fixed != nullptr) {
    snprintf(buf, cap, "%s", fixed);
  } else if (status > 0) {
    snprintf(buf, cap, "HTTP %d", status);
  } else {
    snprintf(buf, cap, "network error %d", status);
  }
}

void FramePoller::begin(uint32_t nowMs) {
  lastSuccessMs_ = nowMs;
  failures_ = 0;
  offline_ = false;
  offlineStatus_ = 0;
}

PollOutcome FramePoller::onSuccess(int nextIn, uint32_t nowMs) {
  lastSuccessMs_ = nowMs;
  failures_ = 0;
  offline_ = false;
  return {nextDelayMs(true, nextIn, 0), false, false};
}

PollOutcome FramePoller::onFailure(int status, uint32_t nowMs) {
  if (failures_ < 255) ++failures_;
  // Decode and mid-body read errors happen while the frame is being drawn.
  const bool partialDraw = status == kErrDecode || status == kErrBodyRead;
  PollOutcome o{nextDelayMs(false, -1, failures_), false, partialDraw};
  // Redraw while offline when the error changed or a partial frame overwrote the screen.
  if (showOffline(nowMs - lastSuccessMs_) &&
      (!offline_ || status != offlineStatus_ || partialDraw)) {
    offline_ = true;
    offlineStatus_ = status;
    o.drawOffline = true;
    o.clearEtag = true;
  }
  return o;
}

}  // namespace gb
