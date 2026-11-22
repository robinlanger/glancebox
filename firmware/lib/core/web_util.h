#pragma once
#include <cstdint>
#include <string>

namespace gb {

// True when the first language in an Accept-Language header is German ("de", "de-AT", ...).
bool prefersGerman(const char* acceptLanguage);
// Escapes & < > " ' for HTML text and attribute values.
std::string htmlEscape(const std::string& in);
// CSRF guard for state-changing requests: an absent Origin (curl, old clients) is
// allowed; otherwise it must be exactly "http://<Host>" (case-insensitive).
bool originAllowed(const std::string& origin, const std::string& host);
// Host header check against DNS rebinding: true for an IPv4 literal, for ownHostname and for
// ownHostname + ".local" (case-insensitive), each with an optional ":port". False if empty.
bool hostAllowed(const std::string& hostHeader, const std::string& ownHostname);

// Wi-Fi signal in words: >= -60 dBm excellent, >= -70 good, >= -80 fair, else weak.
enum class WifiQuality : unsigned char { Excellent, Good, Fair, Weak };
WifiQuality wifiQuality(int rssiDbm);
// Compact duration for the status tiles: "59 s", "5 min", "3 h 7 min", "1 <dayUnit> 21 h".
std::string formatDuration(uint32_t seconds, const char* dayUnit);

}  // namespace gb
