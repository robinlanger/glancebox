#include "web_util.h"

#include <cctype>

namespace gb {

bool prefersGerman(const char* al) {
  if (al == nullptr) return false;
  while (*al == ' ') ++al;
  if (std::tolower(static_cast<unsigned char>(al[0])) != 'd' ||
      std::tolower(static_cast<unsigned char>(al[1])) != 'e')
    return false;
  return !std::isalpha(static_cast<unsigned char>(al[2]));
}

std::string htmlEscape(const std::string& in) {
  std::string out;
  out.reserve(in.size());
  for (char c : in) {
    switch (c) {
      case '&': out += "&amp;"; break;
      case '<': out += "&lt;"; break;
      case '>': out += "&gt;"; break;
      case '"': out += "&quot;"; break;
      case '\'': out += "&#39;"; break;
      default: out += c;
    }
  }
  return out;
}

bool originAllowed(const std::string& origin, const std::string& host) {
  if (origin.empty()) return true;
  if (host.empty()) return false;
  const std::string expected = "http://" + host;
  if (origin.size() != expected.size()) return false;
  for (size_t i = 0; i < origin.size(); ++i) {
    if (std::tolower(static_cast<unsigned char>(origin[i])) !=
        std::tolower(static_cast<unsigned char>(expected[i])))
      return false;
  }
  return true;
}

namespace {

bool equalsIgnoreCase(const std::string& a, const std::string& b) {
  if (a.size() != b.size()) return false;
  for (size_t i = 0; i < a.size(); ++i) {
    if (std::tolower(static_cast<unsigned char>(a[i])) !=
        std::tolower(static_cast<unsigned char>(b[i])))
      return false;
  }
  return true;
}

bool allDigits(const std::string& s) {
  if (s.empty()) return false;
  for (char c : s) {
    if (!std::isdigit(static_cast<unsigned char>(c))) return false;
  }
  return true;
}

// Dotted quad of decimal parts 0..255, nothing else.
bool isIpv4Literal(const std::string& s) {
  size_t start = 0;
  for (int part = 0; part < 4; ++part) {
    const size_t dot = s.find('.', start);
    const bool last = part == 3;
    if (last != (dot == std::string::npos)) return false;
    const std::string p = s.substr(start, last ? std::string::npos : dot - start);
    if (!allDigits(p) || p.size() > 3) return false;
    int value = 0;
    for (char c : p) value = value * 10 + (c - '0');
    if (value > 255) return false;
    start = dot + 1;
  }
  return true;
}

}  // namespace

bool hostAllowed(const std::string& hostHeader, const std::string& ownHostname) {
  std::string name = hostHeader;
  const size_t colon = name.rfind(':');
  if (colon != std::string::npos) {
    const std::string port = name.substr(colon + 1);
    if (!allDigits(port) || port.size() > 5) return false;
    name.resize(colon);
  }
  if (name.empty()) return false;
  if (isIpv4Literal(name)) return true;
  if (ownHostname.empty()) return false;
  return equalsIgnoreCase(name, ownHostname) || equalsIgnoreCase(name, ownHostname + ".local");
}

std::string formatDuration(uint32_t seconds, const char* dayUnit) {
  const std::string s = std::to_string(seconds) + " s";
  if (seconds < 60) return s;
  const uint32_t min = seconds / 60;
  if (min < 60) return std::to_string(min) + " min";
  const uint32_t h = min / 60;
  if (h < 24) return std::to_string(h) + " h " + std::to_string(min % 60) + " min";
  return std::to_string(h / 24) + " " + dayUnit + " " + std::to_string(h % 24) + " h";
}

WifiQuality wifiQuality(int rssiDbm) {
  if (rssiDbm >= -60) return WifiQuality::Excellent;
  if (rssiDbm >= -70) return WifiQuality::Good;
  if (rssiDbm >= -80) return WifiQuality::Fair;
  return WifiQuality::Weak;
}

}  // namespace gb
