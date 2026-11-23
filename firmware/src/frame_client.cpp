#include "frame_client.h"

#include <ESP8266WiFi.h>
#include <libb64/cencode.h>

#include <cstdarg>

#include "display.h"
#include "http_head.h"
#include "poll_timing.h"
#include "version.h"

namespace {

constexpr uint32_t kTimeoutMs = 8000;
// Network error codes, kept from HTTPClient so frameErrorText shows the same texts.
constexpr int kErrConnect = -1;  // "connection failed"
constexpr int kErrSend = -2;     // request not sent completely
constexpr int kErrLost = -5;     // "connection lost"

// Holds the request until it is sent, then the response head. Static: off the 4 kB stack.
char gBuf[gb::kMaxHeadBytes];

// Appends formatted text to gBuf at *pos; false if it does not fit.
bool append(size_t* pos, const char* fmt, ...) {
  va_list ap;
  va_start(ap, fmt);
  const int n = vsnprintf(gBuf + *pos, sizeof(gBuf) - *pos, fmt, ap);
  va_end(ap);
  if (n < 0 || static_cast<size_t>(n) >= sizeof(gBuf) - *pos) return false;
  *pos += static_cast<size_t>(n);
  return true;
}

// "Authorization: Basic <base64(userinfo)>": the header ESP8266HTTPClient sent for a URL
// with userinfo (beginInternal: raw text before '@', no splitting, no percent-decoding,
// base64::encode(auth, false)). Same libb64 calls, encoded straight into gBuf.
bool appendBasicAuth(size_t* pos, const char* userinfo) {
  const size_t n = strlen(userinfo);
  if (!append(pos, "Authorization: Basic ")) return false;
  // Encoded text, its NUL from base64_encode_blockend, then room for the CRLF.
  if (*pos + base64_encode_expected_len_nonewlines(n) + 3 > sizeof(gBuf)) return false;
  base64_encodestate state;
  base64_init_encodestate_nonewlines(&state);
  char* out = gBuf + *pos;
  int written = base64_encode_block(userinfo, static_cast<int>(n), out, &state);
  written += base64_encode_blockend(out + written, &state);
  *pos += static_cast<size_t>(written);
  return append(pos, "\r\n");
}

// Builds the GET request in gBuf; returns its length, 0 if it does not fit.
size_t buildRequest(const gb::ServerTarget& t, const char* etag) {
  size_t pos = 0;
  bool ok = append(&pos, "GET %s/api/v1/frame?id=%06x&fw=%s HTTP/1.1\r\n", t.path,
                   static_cast<unsigned>(ESP.getChipId()), gbVersion());
  const unsigned port = t.port;
  ok = ok && (port == 80 ? append(&pos, "Host: %s\r\n", t.host)
                         : append(&pos, "Host: %s:%u\r\n", t.host, port));
  ok = ok && append(&pos, "User-Agent: glancebox/%s\r\nAccept-Encoding: identity\r\n",
                    gbVersion());
  if (ok && t.userinfo[0] != '\0') ok = appendBasicAuth(&pos, t.userinfo);
  if (ok && etag != nullptr && etag[0] != '\0') ok = append(&pos, "If-None-Match: %s\r\n", etag);
  ok = ok && append(&pos, "Connection: close\r\n\r\n");
  return ok ? pos : 0;
}

// Reads the response head byte by byte (never into the body) until the blank line.
// Returns 0 with *len set, or kErrHeadTooLarge / kErrHeadTimeout / kErrLost.
int readHead(WiFiClient& client, uint32_t startMs, size_t* len) {
  size_t n = 0;
  while (n < 4 || memcmp(gBuf + n - 4, "\r\n\r\n", 4) != 0) {
    if (n == sizeof(gBuf)) return gb::kErrHeadTooLarge;
    if (gb::deadlinePassed(startMs, millis(), kTimeoutMs)) return gb::kErrHeadTimeout;
    const int c = client.read();  // -1 if no byte is buffered yet; does not block
    if (c >= 0) {
      gBuf[n++] = static_cast<char>(c);
    } else if (!client.connected()) {
      return kErrLost;
    }
    displayAnimTick();  // only draws; the deadline above stays as it is
    yield();            // watchdog and Wi-Fi stack
  }
  *len = n;
  return 0;
}

// The whole exchange on an unconnected client. Returns the FrameResult status and fills
// r's other fields; never stops the client (fetchFrame does that on every path).
int exchange(WiFiClient& client, const gb::ServerTarget& t, const char* etag, FrameResult* r) {
  const size_t requestLen = buildRequest(t, etag);
  if (requestLen == 0) return gb::kErrBadUrl;

  // Connect, send and the response head share one deadline; the body has its own.
  const uint32_t startMs = millis();
  client.setTimeout(kTimeoutMs);
  if (!client.connect(t.host, t.port)) return kErrConnect;
  if (client.write(reinterpret_cast<const uint8_t*>(gBuf), requestLen) != requestLen) {
    return kErrSend;
  }

  size_t headLen = 0;
  const int headError = readHead(client, startMs, &headLen);
  if (headError != 0) return headError;
  gb::HttpHead head;
  if (!gb::parseHttpHead(gBuf, headLen, &head)) return gb::kErrHeadMalformed;
  r->nextIn = head.nextIn;
  r->localSec = head.localSec;
  if (head.status == 304) r->refetch = !displayAnimNotModified(head.anim);
  if (head.status != 200) return head.status;

  // -1 without a usable Content-Length (e.g. chunked): rejected.
  if (!gb::acceptFrameLength(static_cast<int32_t>(head.contentLength))) {
    return gb::kErrFrameLength;
  }
  r->len = static_cast<size_t>(head.contentLength);
  switch (displayJpegStream(client, r->len, kTimeoutMs, head.anim)) {
    case JpegStreamResult::Ok:
      gb::storeEtag(r->etag, head.etag);  // only after a full decode
      return 200;
    case JpegStreamResult::InputError:
      return gb::kErrBodyRead;
    case JpegStreamResult::DecodeError:
      return gb::kErrDecode;
  }
  return gb::kErrDecode;  // not reached: all results handled above
}

}  // namespace

FrameResult fetchFrame(const char* serverUrl, const char* etag) {
  FrameResult r{gb::kErrBadUrl, 0, "", -1, -1, false};
  static gb::ServerTarget target;  // ~322 bytes: static, off the 4 kB stack
  if (!gb::parseServerTarget(serverUrl, &target)) return r;  // no connection opened

  WiFiClient client;
  r.status = exchange(client, target, etag, &r);
  client.stop();  // the one exit after any connection attempt
  return r;
}
