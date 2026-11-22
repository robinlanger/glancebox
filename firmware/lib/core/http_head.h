#pragma once
#include <cstddef>
#include <cstdint>

#include "frame_poll.h"

namespace gb {

// Frame request over a plain WiFiClient (src/frame_client.cpp). The device reads the
// response head into a fixed buffer of this size within one total deadline, so a server
// that sends endless or slow header lines cannot keep the main loop blocked.
constexpr size_t kMaxHeadBytes = 1024;

struct HttpHead {
  int status;              // 100..599
  long contentLength;      // -1 if absent, malformed, contradictory or with Transfer-Encoding
  char etag[kEtagCap];     // "" if absent or too long (storeEtag rules)
  int nextIn;              // parseNextIn of X-Next-In, -1 if absent
  int32_t localSec;        // parseLocalTime of X-Local-Time, -1 if absent
};

// data: the response head up to and including the blank line (CRLF CRLF), nothing after it.
// Header names are case-insensitive; optional spaces around the value are ignored.
// False without a valid status line, without the final blank line, or when the head holds
// a NUL byte or a CR/LF that is not part of a CRLF line end. No dynamic allocation.
bool parseHttpHead(const char* data, size_t len, HttpHead* out);

struct ServerTarget {
  char userinfo[96];  // raw text before '@' ("user:pass"), "" if none; sent as Basic auth
  char host[96];      // a stored URL has at most 95 characters
  uint16_t port;
  char path[128];     // "" or "/base", no trailing slash
};
// Splits a normalized server URL (http://[userinfo@]host[:port][/path]); false if a part
// does not fit, the host is empty, the port is not 1..65535 or host, port or path hold a '?'
// (a query is not supported; inside the userinfo it is part of the Basic-auth text).
// The authority ends at the first '/'; userinfo ends at the first '@' in it, as in
// ESP8266HTTPClient.
bool parseServerTarget(const char* serverUrl, ServerTarget* out);

// The server URL for the screen and the serial log: without "userinfo@" (credentials), else
// unchanged. The authority ends at the first '/' after "://" (as in parseServerTarget), the
// userinfo at its last '@', so no part of it is shown. Always NUL-terminated when cap > 0,
// cut to cap - 1 characters.
void displayServerUrl(const char* serverUrl, char* out, size_t cap);

// Wraparound-safe: true once nowMs is at or past startMs + budgetMs.
bool deadlinePassed(uint32_t startMs, uint32_t nowMs, uint32_t budgetMs);

}  // namespace gb
