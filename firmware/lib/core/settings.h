#pragma once
#include <cstdint>
#include <optional>
#include <string>

namespace gb {

constexpr uint8_t kDefaultBrightness = 80;

// Persistent device settings. Fixed buffers: no heap churn on the device.
struct Settings {
  char serverUrl[96] = {};
  char updatePassword[33] = {};
  uint8_t brightness = kDefaultBrightness;
  // Night mode: minutes since midnight (0-1439); start == end means off.
  uint16_t nightStart = 0;
  uint16_t nightEnd = 0;
  uint8_t nightBrightness = 0;  // 0-100, 0 = backlight off
};

// Returns the normalized "http://host[:port][/path]" URL without trailing
// slash, or nullopt with *error set ("https_unsupported", "empty_host").
std::optional<std::string> normalizeServerUrl(std::string in, std::string* error);
bool validPassword(const std::string& pw);
uint8_t clampBrightness(int pct);
// Night brightness: 0..100 (0 allowed, unlike the day brightness).
uint8_t clampNightBrightness(int pct);

// Normalize and store the server URL. On failure *error is one of
// "https_unsupported", "unsupported_scheme", "empty_host", "invalid_chars" (one of ' " < > `,
// an inner space, a control character or a byte >= 0x80; not checked when the normalized
// URL equals the stored one), "too_long" and s is unchanged.
bool applyServerUrl(Settings& s, const std::string& raw, std::string* error);
// Store the update password (8..32 printable ASCII chars). On failure *error is one of
// "too_short", "too_long", "invalid_chars" and s is unchanged.
bool applyPassword(Settings& s, const std::string& pw, std::string* error);
// Partial update from the web page: an absent field leaves the setting unchanged.
struct SettingsPatch {
  std::optional<std::string> serverUrl, password, brightness, nightStart, nightEnd, nightBrightness;
};
// Applies all present fields to a copy; on any error s is unchanged, *field is the form name
// ("server_url", "password", "brightness", "night_start", "night_end", "night_brightness") and
// *error the code ("https_unsupported", "too_short", "bad_brightness", "bad_time",
// "bad_night_brightness", ...). Brightness: digits only, 5..100.
bool applySettingsPatch(Settings& s, const SettingsPatch& p, std::string* field, std::string* error);

// True when the device can run: valid server URL and update password.
bool settingsComplete(const Settings& s);
// WPA2 password for the setup Wi-Fi: the update password once the device is configured
// (and 8..63 chars, the WPA2 range), otherwise nullptr = open AP for the first setup.
const char* portalApPassword(const Settings& s);

// Flat JSON object {"server_url", "update_password", "brightness", "night_start",
// "night_end", "night_brightness"} plus newline.
std::string encodeSettings(const Settings& s);
// Strict parser for the encodeSettings format (unknown string/int keys are ignored,
// missing keys keep defaults). Returns false on any syntax error or overlong value;
// *out is written only on success.
bool parseSettings(const std::string& text, Settings* out);

}  // namespace gb
