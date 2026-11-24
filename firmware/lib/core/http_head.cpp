#include "http_head.h"

#include <cstring>

#include "night.h"

namespace gb {

namespace {

bool isBlank(char c) { return c == ' ' || c == '\t'; }

char lowerAscii(char c) { return (c >= 'A' && c <= 'Z') ? static_cast<char>(c - 'A' + 'a') : c; }

// Case-insensitive: does [p, p + n) equal the lower-case name?
bool spanIs(const char* p, size_t n, const char* name) {
  if (strlen(name) != n) return false;
  for (size_t i = 0; i < n; ++i) {
    if (lowerAscii(p[i]) != name[i]) return false;
  }
  return true;
}

// Copies [src, src + n) into dst as a C string; false (dst untouched) if it does not fit.
bool copySpan(const char* src, size_t n, char* dst, size_t cap) {
  if (n >= cap) return false;
  memcpy(dst, src, n);
  dst[n] = '\0';
  return true;
}

// "HTTP/<version> <3 digits>[ <reason>]" with a status of 100..599.
bool parseStatusLine(const char* p, size_t n, int* status) {
  if (n < 5 || memcmp(p, "HTTP/", 5) != 0) return false;
  size_t i = 5;
  while (i < n && p[i] != ' ') ++i;
  if (i == 5 || i + 4 > n) return false;  // no version, or no room for " NNN"
  ++i;
  int v = 0;
  for (size_t k = 0; k < 3; ++k, ++i) {
    if (p[i] < '0' || p[i] > '9') return false;
    v = v * 10 + (p[i] - '0');
  }
  if (i < n && p[i] != ' ') return false;  // more than three digits
  if (v < 100 || v > 599) return false;
  *status = v;
  return true;
}

// 1..9 decimal digits, nothing else (the frame limit is far below that).
bool parseLength(const char* p, size_t n, long* out) {
  if (n == 0 || n > 9) return false;
  long v = 0;
  for (size_t i = 0; i < n; ++i) {
    if (p[i] < '0' || p[i] > '9') return false;
    v = v * 10 + (p[i] - '0');
  }
  *out = v;
  return true;
}

// The whole head is made of CRLF-terminated lines and ends with the first blank line.
bool wellFormed(const char* data, size_t len) {
  if (len < 4 || memcmp(data + len - 4, "\r\n\r\n", 4) != 0) return false;
  for (size_t i = 0; i < len; ++i) {
    const char c = data[i];
    if (c == '\0') return false;
    if (c == '\r' && (i + 1 >= len || data[i + 1] != '\n')) return false;
    if (c == '\n' && (i == 0 || data[i - 1] != '\r')) return false;
    if (i + 4 < len && memcmp(data + i, "\r\n\r\n", 4) == 0) return false;  // blank line inside
  }
  return true;
}

}  // namespace

bool parseHttpHead(const char* data, size_t len, HttpHead* out) {
  if (out == nullptr) return false;
  out->status = 0;
  out->contentLength = -1;
  out->etag[0] = '\0';
  out->nextIn = -1;
  out->localSec = -1;
  out->anim.count = 0;
  if (data == nullptr || !wellFormed(data, len)) return false;

  long length = -1;
  bool lengthSeen = false;
  bool lengthBad = false;
  bool transferEncoding = false;
  bool animSeen = false;
  bool statusLine = true;
  size_t pos = 0;
  while (pos < len) {
    const char* line = data + pos;
    size_t n = 0;
    while (line[n] != '\r') ++n;  // wellFormed: every line ends with CRLF
    pos += n + 2;
    if (statusLine) {
      if (!parseStatusLine(line, n, &out->status)) return false;
      statusLine = false;
      continue;
    }
    if (n == 0) break;  // the blank line, which wellFormed put at the end

    const char* colon = static_cast<const char*>(memchr(line, ':', n));
    if (colon == nullptr) continue;  // not a header line: ignored
    const size_t nameLen = static_cast<size_t>(colon - line);
    const char* v = colon + 1;
    size_t vn = n - nameLen - 1;
    while (vn > 0 && isBlank(*v)) {
      ++v;
      --vn;
    }
    while (vn > 0 && isBlank(v[vn - 1])) --vn;

    if (spanIs(line, nameLen, "content-length")) {
      long parsed = -1;
      if (!parseLength(v, vn, &parsed) || (lengthSeen && parsed != length)) {
        lengthBad = true;
      } else {
        length = parsed;
        lengthSeen = true;
      }
    } else if (spanIs(line, nameLen, "transfer-encoding")) {
      transferEncoding = true;  // any transfer coding: the length does not describe the body
    } else if (spanIs(line, nameLen, "etag")) {
      char buf[kEtagCap];
      storeEtag(out->etag, copySpan(v, vn, buf, sizeof(buf)) ? buf : "");
    } else if (spanIs(line, nameLen, "x-next-in")) {
      char buf[16];
      out->nextIn = copySpan(v, vn, buf, sizeof(buf)) ? parseNextIn(buf) : -1;
    } else if (spanIs(line, nameLen, "x-local-time")) {
      char buf[16];
      out->localSec = copySpan(v, vn, buf, sizeof(buf)) ? parseLocalTime(buf) : -1;
    } else if (spanIs(line, nameLen, "x-anim")) {
      // An invalid or repeated X-Anim only drops the animation, never the head.
      if (animSeen) {
        out->anim.count = 0;
      } else {
        parseAnim(v, vn, &out->anim);
      }
      animSeen = true;
    }
  }
  if (lengthSeen && !lengthBad && !transferEncoding) out->contentLength = length;
  return true;
}

bool parseServerTarget(const char* url, ServerTarget* out) {
  if (url == nullptr || out == nullptr) return false;
  out->userinfo[0] = '\0';
  out->host[0] = '\0';
  out->port = 80;
  out->path[0] = '\0';

  static const char kScheme[] = "http://";
  for (size_t i = 0; i < sizeof(kScheme) - 1; ++i) {
    if (lowerAscii(url[i]) != kScheme[i]) return false;  // also stops at the NUL
  }
  const char* a = url + sizeof(kScheme) - 1;  // authority: [userinfo@]host[:port]
  const char* slash = strchr(a, '/');
  const char* aEnd = slash != nullptr ? slash : a + strlen(a);

  // Userinfo ends at the first '@', as in ESP8266HTTPClient::beginInternal.
  const char* at = static_cast<const char*>(memchr(a, '@', static_cast<size_t>(aEnd - a)));
  if (at != nullptr) {
    if (!copySpan(a, static_cast<size_t>(at - a), out->userinfo, sizeof(out->userinfo))) {
      return false;
    }
    a = at + 1;
    if (memchr(a, '@', static_cast<size_t>(aEnd - a)) != nullptr) return false;
  }
  // A query is not supported. A '?' in the userinfo is part of the Basic-auth text.
  if (strchr(a, '?') != nullptr) return false;

  const char* colon = static_cast<const char*>(memchr(a, ':', static_cast<size_t>(aEnd - a)));
  const char* hostEnd = colon != nullptr ? colon : aEnd;
  if (hostEnd == a) return false;
  if (!copySpan(a, static_cast<size_t>(hostEnd - a), out->host, sizeof(out->host))) return false;

  if (colon != nullptr) {
    const char* p = colon + 1;
    if (p == aEnd || aEnd - p > 5) return false;
    uint32_t port = 0;
    for (; p < aEnd; ++p) {
      if (*p < '0' || *p > '9') return false;
      port = port * 10 + static_cast<uint32_t>(*p - '0');
    }
    if (port == 0 || port > 65535) return false;
    out->port = static_cast<uint16_t>(port);
  }

  const char* pEnd = aEnd + strlen(aEnd);
  while (pEnd > aEnd && pEnd[-1] == '/') --pEnd;
  return copySpan(aEnd, static_cast<size_t>(pEnd - aEnd), out->path, sizeof(out->path));
}

void displayServerUrl(const char* url, char* out, size_t cap) {
  if (out == nullptr || cap == 0) return;
  out[0] = '\0';
  if (url == nullptr) return;
  const char* scheme = strstr(url, "://");
  const char* a = scheme != nullptr ? scheme + 3 : nullptr;
  const char* aEnd = a != nullptr ? a + strcspn(a, "/") : nullptr;
  const char* at = nullptr;  // last '@' of the authority
  for (const char* p = a; p != nullptr && p < aEnd; ++p) {
    if (*p == '@') at = p;
  }
  // Copies "<scheme>://" and then everything after the userinfo, cut to the room left.
  size_t n = 0;
  const char* parts[2] = {url, at != nullptr ? at + 1 : nullptr};
  const size_t lens[2] = {at != nullptr ? static_cast<size_t>(a - url) : strlen(url),
                          at != nullptr ? strlen(at + 1) : 0};
  for (int i = 0; i < 2; ++i) {
    const size_t take = lens[i] < cap - 1 - n ? lens[i] : cap - 1 - n;
    if (take > 0) memcpy(out + n, parts[i], take);
    n += take;
  }
  out[n] = '\0';
}

bool deadlinePassed(uint32_t startMs, uint32_t nowMs, uint32_t budgetMs) {
  return static_cast<uint32_t>(nowMs - startMs) >= budgetMs;
}

}  // namespace gb
