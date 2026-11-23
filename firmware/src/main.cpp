#include <Arduino.h>
#include <ESP8266WiFi.h>

#include "boot_guard.h"
#include "display.h"
#include "frame_client.h"
#include "frame_poll.h"
#include "http_head.h"
#include "night.h"
#include "portal.h"
#include "rtc_boot.h"
#include "safe_mode.h"
#include "settings_store.h"
#include "version.h"
#include "web_ui.h"

static_assert(gb::kResetReasonPowerOn == REASON_DEFAULT_RST, "rst_reason changed");
static_assert(gb::kResetReasonExtPin == REASON_EXT_SYS_RST, "rst_reason changed");

namespace {

gb::Settings settings;
gb::BootState bootState{0, 0};  // as stored in RTC memory
gb::HealthLatch health;
gb::FramePoller poller;

char etag[gb::kEtagCap] = "";
char lastError[gb::kErrorTextCap] = "";
char shownUrl[sizeof(gb::Settings::serverUrl)];  // server URL without credentials, for the screen
uint32_t framesOk = 0;
uint32_t frameErrors = 0;  // failed polls since boot (any status other than 200 and 304)
uint32_t lastSuccessMs = 0;
bool anySuccess = false;
uint32_t nextPollMs = 0;
gb::LocalClock localClock;      // synced from X-Local-Time, carried on with millis()
int lastBacklight = -1;         // last applied backlight %, -1 = not yet applied by the loop
uint32_t lastBacklightCheckMs = 0;
gb::BacklightPreview preview;   // live slider value from the web page, never saved

void formatIp(char* buf, size_t cap) {
  const IPAddress ip = WiFi.localIP();
  snprintf(buf, cap, "%u.%u.%u.%u", ip[0], ip[1], ip[2], ip[3]);
}

void showBootScreen() {
  char ip[20];
  formatIp(ip, sizeof(ip));
  gb::displayServerUrl(settings.serverUrl, shownUrl, sizeof(shownUrl));
  const char* lines[] = {ip, shownUrl, "waiting for first frame..."};
  displayStatus("Glance Box " GB_VERSION, lines, 3);
}

void showOfflineScreen() {
  char ip[20];
  formatIp(ip, sizeof(ip));
  gb::displayServerUrl(settings.serverUrl, shownUrl, sizeof(shownUrl));
  const char* lines[] = {"Server not reachable", ip, shownUrl, lastError};
  displayStatus("Glance Box offline", lines, 4);
}

// One request/response cycle. No String building here: buffers are fixed-size.
void pollFrame() {
  int status = gb::kErrNoWifi;
  int nextIn = -1;
  if (WiFi.status() == WL_CONNECTED) {
    const FrameResult r = fetchFrame(settings.serverUrl, etag);
    status = r.status;
    nextIn = r.nextIn;
    if (r.status > 0 && r.localSec >= 0) localClock.sync(static_cast<uint32_t>(r.localSec), millis());
    if (status == 200) {  // already drawn (stream decode)
      memcpy(etag, r.etag, sizeof(etag));
      ++framesOk;
    } else if (status == 304 && r.refetch) {
      etag[0] = '\0';  // the running arrows do not fit this frame: fetch it again
    }
  }
  const uint32_t now = millis();  // after the request, which may take seconds
  gb::PollOutcome o;
  if (status == 200 || status == 304) {
    o = poller.onSuccess(nextIn, now);
    lastSuccessMs = now;
    anySuccess = true;
  } else {
    ++frameErrors;
    gb::frameErrorText(status, lastError, sizeof(lastError));
    Serial.printf("frame poll failed: %s (%d)\n", lastError, status);
    o = poller.onFailure(status, now);
  }
  if (o.clearEtag) etag[0] = '\0';
  if (o.drawOffline) showOfflineScreen();
  nextPollMs = now + o.delayMs;
}

// Night mode: apply the effective backlight at most once per second, only on change.
// A live preview from the web page wins (checked every loop) until it expires.
void updateBacklight(uint32_t now) {
  const bool previewing = preview.active(now);
  if (!previewing && lastBacklight >= 0 && now - lastBacklightCheckMs < 1000) return;
  lastBacklightCheckMs = now;
  const uint8_t pct =
      previewing ? preview.pct()
                 : gb::effectiveBrightness(settings, localClock.known(),
                                           localClock.known() ? localClock.secondOfDay(now) : 0);
  if (pct == lastBacklight) return;
  displaySetBacklight(pct);
  lastBacklight = pct;
}

}  // namespace

void setup() {
  // 1. Boot guard first: before display, Wi-Fi or anything else that could crash.
  const gb::BootState stored = rtcBootRead();
  const gb::ResetKind kind = gb::resetKindFromReason(ESP.getResetInfoPtr()->reason);
  const gb::BootDecision boot = gb::onBoot(stored, kind);
  rtcBootWrite(boot.next);
  bootState = boot.next;

  // 2. Too many failed boots: minimal safe mode (never returns).
  if (boot.safeMode) safeModeRun(stored.failed, boot.next.failed);

  // 3. Normal firmware.
  Serial.begin(115200);
  displayBegin(gb::kDefaultBrightness);
  const char* starting[] = {"starting..."};
  displayStatus("Glance Box " GB_VERSION, starting, 1);
  settingsLoad(settings);  // corrupt/missing file: defaults, portal asks for values
  displaySetBrightness(settings.brightness);

  portalRun(settings);
  StatusProvider st;
  st.framesOk = []() { return framesOk; };
  st.frameErrors = []() { return frameErrors; };
  st.anim = []() { return displayAnimStats(); };
  st.lastFrameAgeS = []() -> int32_t {
    return anySuccess ? static_cast<int32_t>((millis() - lastSuccessMs) / 1000) : -1;
  };
  st.safeMode = []() { return false; };
  st.bootFailed = []() { return bootState.failed; };
  st.localMinute = []() -> int32_t {
    return localClock.known() ? static_cast<int32_t>(localClock.secondOfDay(millis()) / 60) : -1;
  };
  st.night = []() {
    return localClock.known() &&
           gb::nightActive(settings.nightStart, settings.nightEnd,
                           static_cast<uint16_t>(localClock.secondOfDay(millis()) / 60));
  };
  st.previewBrightness = [](uint8_t pct) { preview.set(pct, millis()); };
  st.settingsChanged = []() {
    preview.clear();
    lastBacklight = -1;  // re-apply the saved brightness on the next loop
  };
  webUiBegin(settings, st);

  showBootScreen();
  poller.begin(millis());
  nextPollMs = millis();
}

void loop() {
  webUiLoop();
  displayAnimTick();

  const uint32_t now = millis();
  if (health.shouldMark(now, WiFi.status() == WL_CONNECTED, webUiRunning())) {
    bootState = gb::markHealthy();
    rtcBootWrite(bootState);  // once per boot
  }

#ifdef GB_CRASH_TEST
  // Test build only: crash 5 s after boot to exercise the boot-loop guard.
  if (now >= 5000) abort();
#endif

  if (static_cast<int32_t>(now - nextPollMs) >= 0) pollFrame();
  updateBacklight(millis());
  delay(1);  // yield: watchdog, Wi-Fi stack
}
