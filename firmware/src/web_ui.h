#pragma once
// Device web UI on port 80: status page, settings, restart/reset, /status JSON and
// the verified OTA endpoint POST /update.
//
// OTA clients: send the md5 field BEFORE the file part, e.g.
//   curl -u admin:<pw> -F md5=<hex> -F firmware=@firmware.bin http://<ip>/update
// (md5 may also be given as query parameter: /update?md5=<hex>).
#include <ESP8266WebServer.h>

#include "settings.h"

// Dynamic status fields owned by the main loop. Any pointer may be null (field then
// reports 0 / false / null).
struct StatusProvider {
  uint32_t (*framesOk)() = nullptr;
  int32_t (*lastFrameAgeS)() = nullptr;  // < 0: no frame yet (reported as null)
  bool (*safeMode)() = nullptr;
  uint8_t (*bootFailed)() = nullptr;
  int32_t (*localMinute)() = nullptr;  // < 0 or unset: time unknown (reported as null)
  bool (*night)() = nullptr;           // unset: false (safe mode)
  // Normal mode hooks for the live controls (POST /api/...):
  void (*previewBrightness)(uint8_t pct) = nullptr;  // show pct now, do not save
  void (*settingsChanged)() = nullptr;               // settings were saved: re-apply backlight
};

// Normal mode: GET /, GET /update (redirect to the form), POST /settings, /restart, /reset,
// GET /status, POST /update, POST /api/brightness-preview (pct) and POST /api/settings (any
// subset of server_url, password, brightness, night_start, night_end, night_brightness; JSON
// answer {"ok":true} or {"ok":false,"field":...,"error":...}). GET /app.css, /app.js in both modes (ETag + no-cache).
void webUiBegin(gb::Settings& settings, const StatusProvider& status);
// Safe mode: GET / and /update (minimal page with the update form), GET /status,
// POST /update, POST /restart (same OTA code path).
// Further routes (e.g. /boot-normal) can be added via webUiServer() before or after.
void webUiBeginSafe(gb::Settings& settings, const StatusProvider& status);
void webUiLoop();

// Hooks for additional routes. Never call collectHeaders() on it: that replaces the
// header list of web_ui.cpp (kCollectedHeaders), and the Origin check then refuses
// every state-changing request.
ESP8266WebServer& webUiServer();
// Host (DNS rebinding) and Origin (CSRF) checks, the lock after five wrong passwords,
// then Basic auth "admin"/update password. Sends 403/429/401 itself and returns false when
// the request must not proceed. Routes added via webUiServer() get the Host check only
// through this call.
bool webUiAuthorize();
// Restart about 1 s from now (lets the response reach the client).
void webUiScheduleRestart();
bool webUiRunning();
