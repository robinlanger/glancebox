#include "portal.h"

#include <ESP8266WiFi.h>
#include <WiFiManager.h>

#include "display.h"
#include "i18n.h"
#include "settings_store.h"

namespace {

constexpr unsigned long kConfiguredPortalTimeoutS = 180;
constexpr unsigned long kConnectTimeoutS = 20;

char apName[20];
char noticeHtml[200];   // shown on the portal page above the fields
char noticeScreen[48];  // shown on the display (ASCII, English)
bool apProtected;       // setup Wi-Fi uses WPA2 with the update password

void showPortalScreen() {
  // Five lines at most; an error notice takes precedence over the password hint.
  const char* last = noticeScreen[0] ? noticeScreen
                     : apProtected   ? "Wi-Fi password = update password"
                                     : nullptr;
  const char* lines[] = {"Connect to Wi-Fi:", apName, "then open", "http://192.168.4.1", last};
  displayStatus("Glance Box setup", lines, last ? 5 : 4);
}

void setNotice(Msg msg) {
  String html = F("<p style='color:#b00'>");
  html += tr(Lang::En, msg);
  html += F("<br>");
  html += tr(Lang::De, msg);
  html += F("</p>");
  strlcpy(noticeHtml, html.c_str(), sizeof(noticeHtml));
  strlcpy(noticeScreen, String(tr(Lang::En, msg)).c_str(), sizeof(noticeScreen));
}

void clearNotice() {
  noticeHtml[0] = '\0';
  noticeScreen[0] = '\0';
}

// Rejects routes of WiFiManager that need no exposure on the setup AP: its own
// unauthenticated OTA (/update, /u), Wi-Fi erase, restart, leaving the portal and the
// device info page. Choosing and saving a network (/wifi, /0wifi, /wifisave, /param,
// /paramsave) and the captive-portal redirect (onNotFound) use none of them.
// Our handlers are registered before WiFiManager's, and ESP8266WebServer uses the
// first matching handler.
void blockUnsafeRoutes(WiFiManager& wm) {
  auto deny = [&wm]() { wm.server->send(403, F("text/plain"), F("disabled\n")); };
  wm.server->on("/update", HTTP_ANY, deny);
  wm.server->on("/u", HTTP_ANY, deny);
  wm.server->on("/erase", HTTP_ANY, deny);
  wm.server->on("/restart", HTTP_ANY, deny);
  wm.server->on("/exit", HTTP_ANY, deny);
  wm.server->on("/close", HTTP_ANY, deny);
  wm.server->on("/info", HTTP_ANY, deny);
}

// Validates the portal values into a copy; on success stores and persists them.
// The AP is open only for the first setup; on a configured device it uses WPA2 with the
// update password, and any change still needs the current password as a second check.
bool applyPortalValues(gb::Settings& s, const char* url, const char* pw, const char* bright,
                       const char* current) {
  gb::Settings next = s;
  std::string err;
  if (!gb::applyServerUrl(next, url, &err)) {
    setNotice(msgForError(err, false));
    return false;
  }
  if ((pw[0] != '\0' || !gb::validPassword(next.updatePassword)) &&
      !gb::applyPassword(next, pw, &err)) {
    setNotice(msgForError(err, true));
    return false;
  }
  if (bright[0] != '\0') {
    char* end = nullptr;
    const long pct = strtol(bright, &end, 10);
    if (*end != '\0' || pct < 5 || pct > 100) {
      setNotice(Msg::ErrBrightness);
      return false;
    }
    next.brightness = gb::clampBrightness(static_cast<int>(pct));
  }
  const bool changed = gb::encodeSettings(next) != gb::encodeSettings(s);
  if (changed && gb::validPassword(s.updatePassword) &&
      strcmp(current, s.updatePassword) != 0) {
    setNotice(Msg::ErrWrongPassword);
    return false;
  }
  if (!settingsSave(next)) {
    setNotice(Msg::ErrSaveFailed);
    return false;
  }
  s = next;
  displaySetBrightness(s.brightness);
  clearNotice();
  return true;
}

}  // namespace

void portalRun(gb::Settings& s) {
  snprintf(apName, sizeof(apName), "GlanceBox-%04X", static_cast<unsigned>(ESP.getChipId() & 0xFFFF));
  clearNotice();
  WiFi.persistent(true);  // Wi-Fi credentials entered in the portal must be stored

  for (;;) {
    const bool complete = gb::settingsComplete(s);
    char bright[4];
    snprintf(bright, sizeof(bright), "%u", s.brightness);

    WiFiManager wm;
    WiFiManagerParameter pNotice(noticeHtml);
    WiFiManagerParameter pUrl("server_url", "Server URL (http://host:8080)", s.serverUrl,
                              sizeof(s.serverUrl) - 1);
    WiFiManagerParameter pPw("update_password",
                             complete ? "Update password, user admin (empty = keep)"
                                      : "Update password, user admin (min. 8 characters)",
                             "", sizeof(s.updatePassword) - 1, "type='password'");
    // Only shown (and required for changes) once an update password exists.
    WiFiManagerParameter pCurrent("current_password",
                                  "Current update password (needed to change the values below)",
                                  "", sizeof(s.updatePassword) - 1, "type='password'");
    WiFiManagerParameter pBright("brightness", "Brightness % (5-100)", bright, 3,
                                 "type='number' min='5' max='100'");
    wm.addParameter(&pNotice);
    if (complete) wm.addParameter(&pCurrent);
    wm.addParameter(&pUrl);
    wm.addParameter(&pPw);
    wm.addParameter(&pBright);

    const char* menu[] = {"wifi"};
    wm.setMenu(menu, 1);
    wm.setTitle("Glance Box");
    wm.setShowInfoUpdate(false);
    wm.setShowInfoErase(false);
    wm.setConnectTimeout(kConnectTimeoutS);
    wm.setWebServerCallback([&wm]() { blockUnsafeRoutes(wm); });
    wm.setAPCallback([](WiFiManager*) { showPortalScreen(); });
    bool paramsSaved = false;
    wm.setSaveParamsCallback([&paramsSaved]() { paramsSaved = true; });

    // Configured device: WPA2 with the update password, so nobody in range can store
    // new Wi-Fi credentials through /wifisave. First setup: open AP (nullptr).
    const char* apPassword = gb::portalApPassword(s);
    apProtected = apPassword != nullptr;
    bool connected;
    if (complete && wm.getWiFiIsSaved()) {
      wm.setConfigPortalTimeout(kConfiguredPortalTimeoutS);
      connected = wm.autoConnect(apName, apPassword);  // portal only if the saved network fails
    } else {
      wm.setConfigPortalTimeout(0);
      connected = wm.startConfigPortal(apName, apPassword);
    }

    if (paramsSaved) {
      applyPortalValues(s, pUrl.getValue(), pPw.getValue(), pBright.getValue(),
                        complete ? pCurrent.getValue() : "");
    }
    // Invalid values on a configured device are dropped (old settings stay valid);
    // an unconfigured device reopens the portal with the error notice.
    if (connected && gb::settingsComplete(s)) break;
    if (!connected && complete && !paramsSaved) {
      // Configured device, network temporarily gone: do not block forever.
      WiFi.persistent(false);
      WiFi.mode(WIFI_STA);
      WiFi.begin();
      break;
    }
  }

  WiFi.persistent(false);  // no further flash writes from mode/begin calls
  WiFi.setAutoReconnect(true);
}
