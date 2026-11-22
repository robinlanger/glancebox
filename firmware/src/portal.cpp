#include "portal.h"

#include <ESP8266WiFi.h>
#include <WiFiManager.h>

#include <optional>

#include "display.h"
#include "i18n.h"
#include "settings_store.h"
#include "web_util.h"

namespace {

constexpr unsigned long kConfiguredPortalTimeoutS = 180;
constexpr unsigned long kConnectTimeoutS = 20;

char apName[20];
char noticeHtml[320];   // shown on the portal page above the fields
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
  // The notice sits below the network list; the script scrolls it into view on a phone.
  String html = F("<p id='gbn' style='color:#b00'>");
  html += gb::htmlEscape(String(tr(Lang::En, msg)).c_str()).c_str();
  html += F("<br>");
  html += gb::htmlEscape(String(tr(Lang::De, msg)).c_str()).c_str();
  html += F("</p><script>document.getElementById('gbn').scrollIntoView()</script>");
  strlcpy(noticeHtml, html.c_str(), sizeof(noticeHtml));
  strlcpy(noticeScreen, String(tr(Lang::En, msg)).c_str(), sizeof(noticeScreen));
}

void clearNotice() {
  noticeHtml[0] = '\0';
  noticeScreen[0] = '\0';
}

// WiFiManager 2.0.17 keeps the page and save handlers protected; the pre-check below calls them.
class Portal : public WiFiManager {
 public:
  using WiFiManager::handleWifi;      // renders the Wi-Fi form (true = with network list)
  using WiFiManager::handleWifiSave;  // the library's /wifisave: answers, then connects
};

// Rejects routes of WiFiManager that need no exposure on the setup AP: its own
// unauthenticated OTA (/update, /u), Wi-Fi erase, restart, leaving the portal, the
// device info page, and the separate parameter page (/param, /paramsave), which would
// take the form fields without the check in our /wifisave handler. Choosing and saving a
// network (/wifi, /0wifi, our /wifisave) and the captive-portal redirect (onNotFound) use
// none of them. Our handlers are registered before WiFiManager's, and ESP8266WebServer
// uses the first matching handler.
void blockUnsafeRoutes(Portal& wm) {
  auto deny = [&wm]() { wm.server->send(403, F("text/plain"), F("disabled\n")); };
  wm.server->on("/update", HTTP_ANY, deny);
  wm.server->on("/u", HTTP_ANY, deny);
  wm.server->on("/erase", HTTP_ANY, deny);
  wm.server->on("/restart", HTTP_ANY, deny);
  wm.server->on("/exit", HTTP_ANY, deny);
  wm.server->on("/close", HTTP_ANY, deny);
  wm.server->on("/info", HTTP_ANY, deny);
  wm.server->on("/param", HTTP_ANY, deny);
  wm.server->on("/paramsave", HTTP_ANY, deny);
}

// Shows the error of a rejected form on the page and on the display.
void noticeFormError(const std::string& field, const std::string& error) {
  setNotice(msgForError(error, field == "update_password" || field == "update_password_repeat"));
}

// Applies the form that passed the check in /wifisave once the portal has returned: checks
// it again against the current settings, then stores and persists it.
// The AP is open only for the first setup; on a configured device it uses WPA2 with the
// update password, and any change still needs the current password as a second check.
bool applyPortalValues(gb::Settings& s, const gb::PortalForm& form) {
  gb::Settings next;
  std::string field, err;
  if (!gb::applyPortalForm(s, form, &next, &field, &err)) {
    noticeFormError(field, err);
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
    // Once a valid update password exists, every change needs it, even while the stored
    // server URL is invalid (complete == false); otherwise such a device could never be fixed.
    const bool hasPassword = gb::validPassword(s.updatePassword);
    char bright[4];
    snprintf(bright, sizeof(bright), "%u", s.brightness);

    Portal wm;
    WiFiManagerParameter pNotice(noticeHtml);
    WiFiManagerParameter pUrl("server_url", "Server URL", s.serverUrl, sizeof(s.serverUrl) - 1,
                              "placeholder='http://192.168.x.x:8090' required");
    // Required until a valid password is stored (like current_password, keyed on hasPassword):
    // a device with a password but an invalid server URL keeps the password when both are empty.
    const char* pwAttrs = hasPassword
                              ? "type='password' minlength='8' autocomplete='new-password'"
                              : "type='password' minlength='8' autocomplete='new-password' required";
    WiFiManagerParameter pPw("update_password",
                             hasPassword ? "Update password, user admin (empty = keep)"
                                         : "Update password, user admin (min. 8 characters)",
                             "", sizeof(s.updatePassword) - 1, pwAttrs);
    WiFiManagerParameter pRepeat("update_password_repeat", "Repeat update password", "",
                                 sizeof(s.updatePassword) - 1, pwAttrs);
    // Only shown (and required for changes) once an update password exists.
    WiFiManagerParameter pCurrent("current_password",
                                  "Current update password (needed to change the values below)",
                                  "", sizeof(s.updatePassword) - 1, "type='password'");
    WiFiManagerParameter pBright("brightness", "Brightness % (5-100)", bright, 3,
                                 "type='number' min='5' max='100'");
    wm.addParameter(&pNotice);
    if (hasPassword) wm.addParameter(&pCurrent);
    wm.addParameter(&pUrl);
    wm.addParameter(&pPw);
    wm.addParameter(&pRepeat);
    wm.addParameter(&pBright);

    // The form that passed the check in /wifisave; applied after the portal returns.
    std::optional<gb::PortalForm> submitted;

    // Checks the form before WiFiManager connects. Invalid: the form page comes back with the
    // error and WiFiManager never connects. Valid: the library's /wifisave answers and
    // connects. Passwords are never written back into the page.
    auto onWifiSave = [&]() {
      gb::PortalForm form;
      form.serverUrl = wm.server->arg(F("server_url")).c_str();
      form.password = wm.server->arg(F("update_password")).c_str();
      form.passwordRepeat = wm.server->arg(F("update_password_repeat")).c_str();
      form.brightness = wm.server->arg(F("brightness")).c_str();
      if (hasPassword) form.currentPassword = wm.server->arg(F("current_password")).c_str();

      // Rejected: the form page comes back with the error. An earlier valid form is dropped, so
      // only the latest intent counts (also when the portal times out now).
      auto reject = [&]() {
        submitted.reset();
        // Show the entered URL again if it is valid on its own, else the stored one.
        gb::Settings urlOnly = s;
        const bool urlOk = gb::applyServerUrl(urlOnly, form.serverUrl, nullptr);
        pUrl.setValue(urlOk ? urlOnly.serverUrl : s.serverUrl, sizeof(s.serverUrl) - 1);
        showPortalScreen();
        wm.handleWifi(true);
      };

      gb::Settings next;
      std::string field, err;
      if (!gb::applyPortalForm(s, form, &next, &field, &err)) {
        noticeFormError(field, err);
        return reject();
      }
      // WiFiManager writes the stored Wi-Fi name unescaped into later portal pages
      // (placeholder='{v}'), so a name that could break out of the markup is never stored.
      if (!gb::wifiNameSafe(wm.server->arg(F("s")).c_str())) {
        setNotice(Msg::ErrWifiNameChars);
        return reject();
      }
      clearNotice();
      submitted = form;
      showPortalScreen();
      wm.handleWifiSave();
      // handleWifiSave copied the raw request values into the fields; the page shows them
      // again if the connection fails. Keep only the checked values, never a password.
      char b[4];
      snprintf(b, sizeof(b), "%u", next.brightness);
      pUrl.setValue(next.serverUrl, sizeof(s.serverUrl) - 1);
      pBright.setValue(b, 3);
      pPw.setValue("", sizeof(s.updatePassword) - 1);
      pRepeat.setValue("", sizeof(s.updatePassword) - 1);
      pCurrent.setValue("", sizeof(s.updatePassword) - 1);
    };

    const char* menu[] = {"wifi"};
    wm.setMenu(menu, 1);
    wm.setTitle("Glance Box");
    wm.setShowInfoUpdate(false);
    wm.setShowInfoErase(false);
    wm.setConnectTimeout(kConnectTimeoutS);
    wm.setWebServerCallback([&wm, &onWifiSave]() {
      blockUnsafeRoutes(wm);
      // Registered before WiFiManager's own /wifisave, so it takes precedence.
      wm.server->on("/wifisave", HTTP_ANY, onWifiSave);
    });
    wm.setAPCallback([](WiFiManager*) { showPortalScreen(); });

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

    if (submitted) applyPortalValues(s, *submitted);
    // Invalid values on a configured device are dropped (old settings stay valid);
    // an unconfigured device reopens the portal with the error notice.
    if (connected && gb::settingsComplete(s)) break;
    if (!connected && complete && !submitted) {
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
