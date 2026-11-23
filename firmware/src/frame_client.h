#pragma once
// Frame protocol client (spec 5.2): GET <server>/api/v1/frame?id=<chip id>&fw=<version>.
// Normal mode only; safe mode never calls into this file.
#include <Arduino.h>

#include "frame_poll.h"

struct FrameResult {
  int status;               // 200 (frame drawn), 304, other HTTP status, network error
                            // (-1, -2, -5) or gb::kErr* (see frame_poll.h)
  size_t len;               // Content-Length of a 200 response
  char etag[gb::kEtagCap];  // ETag of a drawn 200 frame ("" if absent, too long or not drawn)
  int nextIn;               // X-Next-In seconds, -1 if absent/malformed
  int32_t localSec;         // X-Local-Time as seconds of the day, -1 if absent/malformed
  bool refetch;             // 304 whose X-Anim did not match the running tracks: drop the
                            // ETag so the next request fetches the frame again
};

// One blocking request over a plain WiFiClient. Connect, request and response head share
// one 8 s deadline, and the head may be at most gb::kMaxHeadBytes long (gb::kErrHeadTimeout,
// gb::kErrHeadTooLarge), so a slow or hostile server cannot block the main loop.
// Userinfo in the server URL (user:pass@) is sent as Basic auth, as HTTPClient did.
// A 200 body is stream-decoded straight to the display (no frame buffer) within its own
// 8 s deadline. Failures mid-body return gb::kErrBodyRead / gb::kErrDecode and leave a
// partially drawn frame. The arrows keep moving while the head is read and the body decoded
// (displayAnimTick); only a 200 or 304 changes the running tracks.
FrameResult fetchFrame(const char* serverUrl, const char* etag);
