#include <unity.h>

#include <cstring>
#include <string>
#include <vector>

#include "anim.h"
#include "auth_throttle.h"
#include "boot_guard.h"
#include "frame_poll.h"
#include "http_head.h"
#include "ota_check.h"
#include "night.h"
#include "ota_flow.h"
#include "poll_timing.h"
#include "safe_policy.h"
#include "settings.h"
#include "web_util.h"

using namespace gb;

void setUp() {}
void tearDown() {}

void test_boot_fresh_magic() {
  BootDecision d = onBoot({0xDEADBEEF, 7}, ResetKind::Counted);
  TEST_ASSERT_EQUAL_HEX32(kBootMagic, d.next.magic);
  TEST_ASSERT_EQUAL_UINT8(1, d.next.failed);
  TEST_ASSERT_FALSE(d.safeMode);
}

void test_boot_third_failure_enters_safe() {
  for (uint8_t f = 0; f < 3; ++f) {
    BootDecision d = onBoot({kBootMagic, f}, ResetKind::Counted);
    TEST_ASSERT_FALSE(d.safeMode);
    TEST_ASSERT_EQUAL_UINT8(f + 1, d.next.failed);
  }
  TEST_ASSERT_TRUE(onBoot({kBootMagic, 3}, ResetKind::Counted).safeMode);
  BootDecision cap = onBoot({kBootMagic, 255}, ResetKind::Counted);
  TEST_ASSERT_TRUE(cap.safeMode);
  TEST_ASSERT_EQUAL_UINT8(255, cap.next.failed);
}

void test_reset_kind_mapping() {
  // Values of the SDK's rst_reason enum (user_interface.h).
  TEST_ASSERT_EQUAL(static_cast<int>(ResetKind::Fresh), static_cast<int>(resetKindFromReason(0)));  // power-on
  TEST_ASSERT_EQUAL(static_cast<int>(ResetKind::Fresh), static_cast<int>(resetKindFromReason(6)));  // reset pin
  for (uint32_t r : {1u, 2u, 3u, 4u, 5u, 99u}) {  // HW WDT, exception, SW WDT, soft restart, deep sleep, unknown
    TEST_ASSERT_EQUAL(static_cast<int>(ResetKind::Counted), static_cast<int>(resetKindFromReason(r)));
  }
}

void test_boot_fresh_start_resets_counter() {
  // RTC RAM can survive a brief power loss: a power-on must still start a fresh count.
  BootDecision d = onBoot({kBootMagic, 3}, ResetKind::Fresh);
  TEST_ASSERT_FALSE(d.safeMode);
  TEST_ASSERT_EQUAL_HEX32(kBootMagic, d.next.magic);
  TEST_ASSERT_EQUAL_UINT8(1, d.next.failed);
  TEST_ASSERT_FALSE(onBoot({0xDEADBEEF, 9}, ResetKind::Fresh).safeMode);
}

void test_boot_counted_reset_keeps_counting() {
  BootDecision d = onBoot({kBootMagic, 2}, ResetKind::Counted);
  TEST_ASSERT_FALSE(d.safeMode);
  TEST_ASSERT_EQUAL_UINT8(3, d.next.failed);
  TEST_ASSERT_TRUE(onBoot({kBootMagic, 3}, ResetKind::Counted).safeMode);
}

void test_boot_healthy_resets() {
  BootState s = markHealthy();
  TEST_ASSERT_EQUAL_HEX32(kBootMagic, s.magic);
  TEST_ASSERT_EQUAL_UINT8(0, s.failed);
}

void test_is_healthy_needs_all_three() {
  TEST_ASSERT_TRUE(isHealthy(60000, true, true));
  TEST_ASSERT_FALSE(isHealthy(59999, true, true));
  TEST_ASSERT_FALSE(isHealthy(60000, false, true));
  TEST_ASSERT_FALSE(isHealthy(60000, true, false));
}

void test_next_delay_success_clamped() {
  TEST_ASSERT_EQUAL_UINT32(2000, nextDelayMs(true, 0, 0));
  TEST_ASSERT_EQUAL_UINT32(30000, nextDelayMs(true, 45, 0));
  TEST_ASSERT_EQUAL_UINT32(10000, nextDelayMs(true, -1, 0));
}

void test_next_delay_backoff() {
  TEST_ASSERT_EQUAL_UINT32(2000, nextDelayMs(false, -1, 1));
  TEST_ASSERT_EQUAL_UINT32(4000, nextDelayMs(false, -1, 2));
  TEST_ASSERT_EQUAL_UINT32(30000, nextDelayMs(false, -1, 5));
  TEST_ASSERT_EQUAL_UINT32(30000, nextDelayMs(false, -1, 255));
}

void test_show_offline_at_120s() {
  TEST_ASSERT_FALSE(showOffline(119999));
  TEST_ASSERT_TRUE(showOffline(120000));
}

void test_accept_frame_length() {
  TEST_ASSERT_FALSE(acceptFrameLength(0));
  TEST_ASSERT_FALSE(acceptFrameLength(-1));
  TEST_ASSERT_TRUE(acceptFrameLength(1));
  TEST_ASSERT_TRUE(acceptFrameLength(24576));
  TEST_ASSERT_FALSE(acceptFrameLength(24577));
}

void test_normalize_server_url_adds_scheme_and_strips_slash() {
  std::string err;
  auto r = normalizeServerUrl(" homeserver:8080/ ", &err);
  TEST_ASSERT_TRUE(r.has_value());
  TEST_ASSERT_EQUAL_STRING("http://homeserver:8080", r->c_str());
  auto r2 = normalizeServerUrl("http://a.lan//", &err);
  TEST_ASSERT_EQUAL_STRING("http://a.lan", r2->c_str());
}

void test_normalize_server_url_rejects_https() {
  std::string err;
  TEST_ASSERT_FALSE(normalizeServerUrl("https://x.lan", &err).has_value());
  TEST_ASSERT_EQUAL_STRING("https_unsupported", err.c_str());
}

void test_normalize_server_url_rejects_empty_host() {
  std::string err;
  TEST_ASSERT_FALSE(normalizeServerUrl("http://", &err).has_value());
  TEST_ASSERT_FALSE(normalizeServerUrl("   ", &err).has_value());
  TEST_ASSERT_FALSE(normalizeServerUrl("http://:8080", &err).has_value());
}

void test_valid_password() {
  TEST_ASSERT_FALSE(validPassword("1234567"));
  TEST_ASSERT_TRUE(validPassword("12345678"));
  TEST_ASSERT_EQUAL_UINT8(5, clampBrightness(0));
  TEST_ASSERT_EQUAL_UINT8(100, clampBrightness(500));
  TEST_ASSERT_EQUAL_UINT8(42, clampBrightness(42));
}

void test_md5_hex() {
  TEST_ASSERT_TRUE(isValidMd5Hex("d41d8cd98f00b204e9800998ecf8427e"));
  TEST_ASSERT_TRUE(isValidMd5Hex("D41D8CD98F00B204E9800998ECF8427E"));
  TEST_ASSERT_FALSE(isValidMd5Hex("d41d8cd98f00b204e9800998ecf8427"));
  TEST_ASSERT_FALSE(isValidMd5Hex("g41d8cd98f00b204e9800998ecf8427e"));
}

void test_image_magic() {
  const uint8_t ok[] = {0xE9, 0x03, 0x02, 0x40};
  const uint8_t bad[] = {0x7F, 0x45, 0x4C, 0x46};
  TEST_ASSERT_TRUE(looksLikeEsp8266Image(ok, 4));
  TEST_ASSERT_FALSE(looksLikeEsp8266Image(ok, 3));
  TEST_ASSERT_FALSE(looksLikeEsp8266Image(bad, 4));
  TEST_ASSERT_TRUE(fitsOta(1000, 1000));
  TEST_ASSERT_FALSE(fitsOta(1001, 1000));
}

void test_settings_roundtrip_with_escapes() {
  Settings s;
  TEST_ASSERT_TRUE(applyServerUrl(s, "homeserver:8080/", nullptr));
  TEST_ASSERT_TRUE(applyPassword(s, "pa\"ss\\w:rd", nullptr));
  s.brightness = 42;
  std::string text = encodeSettings(s);
  TEST_ASSERT_EQUAL_STRING(
      "{\"server_url\":\"http://homeserver:8080\",\"update_password\":\"pa\\\"ss\\\\w:rd\","
      "\"brightness\":42,\"night_start\":0,\"night_end\":0,\"night_brightness\":0}\n",
      text.c_str());
  Settings back;
  TEST_ASSERT_TRUE(parseSettings(text, &back));
  TEST_ASSERT_EQUAL_STRING("http://homeserver:8080", back.serverUrl);
  TEST_ASSERT_EQUAL_STRING("pa\"ss\\w:rd", back.updatePassword);
  TEST_ASSERT_EQUAL_UINT8(42, back.brightness);
  TEST_ASSERT_TRUE(settingsComplete(back));
}

void test_settings_parse_tolerates_whitespace_unknown_keys_and_missing_brightness() {
  Settings s;
  TEST_ASSERT_TRUE(parseSettings(
      " {\n \"x\" : \"y\", \"n\": -3, \"update_password\" : \"abc\\u0041defgh\" ,"
      "\"server_url\":\"http://a.lan\"}\n",
      &s));
  TEST_ASSERT_EQUAL_STRING("abcAdefgh", s.updatePassword);
  TEST_ASSERT_EQUAL_STRING("http://a.lan", s.serverUrl);
  TEST_ASSERT_EQUAL_UINT8(kDefaultBrightness, s.brightness);
}

void test_settings_parse_rejects_corrupt_input() {
  const char* bad[] = {
      "",
      "{",
      "{\"server_url\":\"http://a.lan\"",
      "{\"server_url\":\"http://a.lan\"} trailing",
      "{\"server_url\":http}",
      "{\"brightness\":}",
      "{\"brightness\":1234567}",
      "{\"update_password\":\"ab\ncd\"}",
      "{\"update_password\":\"\\u0000\"}",
      "{\"update_password\":\"\\u00e9\"}",
      "{\"update_password\":\"\\q\"}",
      "{\"update_password\":\"0123456789012345678901234567890123\"}",
      "[1]",
  };
  for (const char* b : bad) {
    Settings s;
    s.brightness = 7;
    TEST_ASSERT_FALSE_MESSAGE(parseSettings(b, &s), b);
    TEST_ASSERT_EQUAL_UINT8(7, s.brightness);  // untouched on failure
  }
}

void test_settings_parse_clamps_brightness() {
  Settings s;
  TEST_ASSERT_TRUE(parseSettings("{\"brightness\":0}", &s));
  TEST_ASSERT_EQUAL_UINT8(5, s.brightness);
  TEST_ASSERT_TRUE(parseSettings("{\"brightness\":900}", &s));
  TEST_ASSERT_EQUAL_UINT8(100, s.brightness);
}

void test_settings_defaults_incomplete() {
  Settings s;
  TEST_ASSERT_EQUAL_STRING("", s.serverUrl);
  TEST_ASSERT_EQUAL_STRING("", s.updatePassword);
  TEST_ASSERT_EQUAL_UINT8(kDefaultBrightness, s.brightness);
  TEST_ASSERT_FALSE(settingsComplete(s));
  applyServerUrl(s, "a.lan", nullptr);
  TEST_ASSERT_FALSE(settingsComplete(s));
  applyPassword(s, "12345678", nullptr);
  TEST_ASSERT_TRUE(settingsComplete(s));
}

void test_apply_server_url_errors_leave_value() {
  Settings s;
  applyServerUrl(s, "a.lan", nullptr);
  std::string err;
  TEST_ASSERT_FALSE(applyServerUrl(s, "https://x", &err));
  TEST_ASSERT_EQUAL_STRING("https_unsupported", err.c_str());
  TEST_ASSERT_FALSE(applyServerUrl(s, "http://" + std::string(90, 'a'), &err));
  TEST_ASSERT_EQUAL_STRING("too_long", err.c_str());
  TEST_ASSERT_TRUE(applyServerUrl(s, "http://" + std::string(88, 'a'), &err));  // 95 chars fits
  TEST_ASSERT_FALSE(applyServerUrl(s, "", &err));
  TEST_ASSERT_EQUAL_STRING("required", err.c_str());
  TEST_ASSERT_EQUAL_UINT(95, std::string(s.serverUrl).size());
}

void test_apply_password_rules() {
  Settings s;
  std::string err;
  TEST_ASSERT_FALSE(applyPassword(s, "short", &err));
  TEST_ASSERT_EQUAL_STRING("too_short", err.c_str());
  TEST_ASSERT_FALSE(applyPassword(s, std::string(33, 'x'), &err));
  TEST_ASSERT_EQUAL_STRING("too_long", err.c_str());
  TEST_ASSERT_FALSE(applyPassword(s, "abcdefg\xc3\xa9", &err));
  TEST_ASSERT_EQUAL_STRING("invalid_chars", err.c_str());
  TEST_ASSERT_FALSE(applyPassword(s, "abcdefgh\t", &err));
  TEST_ASSERT_EQUAL_STRING("", s.updatePassword);
  TEST_ASSERT_TRUE(applyPassword(s, std::string(32, '~'), &err));
  TEST_ASSERT_EQUAL_UINT(32, std::string(s.updatePassword).size());
}

void test_prefers_german() {
  TEST_ASSERT_TRUE(prefersGerman("de"));
  TEST_ASSERT_TRUE(prefersGerman("de-DE,de;q=0.9,en;q=0.8"));
  TEST_ASSERT_TRUE(prefersGerman(" DE-at"));
  TEST_ASSERT_FALSE(prefersGerman("en-US,de;q=0.9"));
  TEST_ASSERT_FALSE(prefersGerman(""));
  TEST_ASSERT_FALSE(prefersGerman(nullptr));
  TEST_ASSERT_FALSE(prefersGerman("dex"));
}

void test_html_escape() {
  TEST_ASSERT_EQUAL_STRING("a&amp;b&lt;c&gt;&quot;d&#39;", htmlEscape("a&b<c>\"d'").c_str());
}

void test_origin_allowed() {
  TEST_ASSERT_TRUE(originAllowed("", "192.168.1.5"));
  TEST_ASSERT_TRUE(originAllowed("http://192.168.1.5", "192.168.1.5"));
  TEST_ASSERT_TRUE(originAllowed("HTTP://Box.lan", "box.lan"));
  TEST_ASSERT_FALSE(originAllowed("http://evil.example", "192.168.1.5"));
  TEST_ASSERT_FALSE(originAllowed("null", "192.168.1.5"));
  TEST_ASSERT_FALSE(originAllowed("http://192.168.1.5", ""));
}

void test_ota_begin_size() {
  TEST_ASSERT_EQUAL_UINT(0, otaBeginSize(0));
  TEST_ASSERT_EQUAL_UINT(0, otaBeginSize(0x1000));
  TEST_ASSERT_EQUAL_UINT(0x1000, otaBeginSize(0x2FFF));
  TEST_ASSERT_EQUAL_UINT(0x7A000, otaBeginSize(0x7B000));
}

namespace {
const OtaStartChecks kGood{true, true, true, true, true};

// Drives one successful upload part up to (not including) Update.end().
void uploadUntilEnd(OtaFlow& f) {
  f.onFileStart(kGood);
  TEST_ASSERT_TRUE(f.onChunk(true) == OtaFlow::Chunk::BeginAndWrite);
  f.onBegin(true);
  f.onWrite(true, false);
  TEST_ASSERT_TRUE(f.onChunk(false) == OtaFlow::Chunk::Write);  // later chunks: no header check
  f.onWrite(true, false);
  TEST_ASSERT_TRUE(f.onFileEnd() == OtaFlow::End::Finish);
}
}  // namespace

void test_ota_flow_success_commits_at_file_end() {
  OtaFlow f;
  uploadUntilEnd(f);
  TEST_ASSERT_TRUE(f.onFinished(true, OtaError::None));
  TEST_ASSERT_TRUE(f.committed());
  TEST_ASSERT_FALSE(f.mayDiscard());
  TEST_ASSERT_EQUAL(200, f.response().code);
}

void test_ota_flow_abort_after_commit_keeps_commit_and_success() {
  OtaFlow f;
  uploadUntilEnd(f);
  f.onFinished(true, OtaError::None);
  f.onAborted();  // client disconnected after the final boundary
  TEST_ASSERT_TRUE(f.committed());
  TEST_ASSERT_FALSE(f.mayDiscard());
  TEST_ASSERT_EQUAL(200, f.response().code);
}

void test_ota_flow_second_part_after_commit_never_touches_flash() {
  OtaFlow f;
  uploadUntilEnd(f);
  f.onFinished(true, OtaError::None);
  f.onFileStart(kGood);  // second file part in the same request
  TEST_ASSERT_TRUE(f.onChunk(true) == OtaFlow::Chunk::Skip);
  TEST_ASSERT_TRUE(f.onFileEnd() == OtaFlow::End::Skip);
  TEST_ASSERT_FALSE(f.mayDiscard());
  TEST_ASSERT_EQUAL(200, f.response().code);  // the committed image stands
}

void test_ota_flow_later_requests_refused_after_commit() {
  OtaFlow f;
  uploadUntilEnd(f);
  f.onFinished(true, OtaError::None);
  f.endRequest();
  TEST_ASSERT_TRUE(f.committed());
  f.onFileStart(kGood);
  TEST_ASSERT_TRUE(f.onChunk(true) == OtaFlow::Chunk::Skip);
  TEST_ASSERT_TRUE(f.onFileEnd() == OtaFlow::End::Skip);
  TEST_ASSERT_FALSE(f.mayDiscard());
  TEST_ASSERT_TRUE(f.error() == OtaError::Committed);
  TEST_ASSERT_EQUAL(400, f.response().code);
}

void test_ota_flow_unauthorized_never_writes() {
  OtaFlow f;
  f.onFileStart({true, false, true, true, true});
  TEST_ASSERT_FALSE(f.authorized());
  TEST_ASSERT_TRUE(f.onChunk(true) == OtaFlow::Chunk::Skip);
  TEST_ASSERT_TRUE(f.onFileEnd() == OtaFlow::End::Skip);
  TEST_ASSERT_EQUAL(401, f.response().code);
  OtaFlow g;
  g.onFileStart({false, true, true, true, true});
  TEST_ASSERT_TRUE(g.onChunk(true) == OtaFlow::Chunk::Skip);
  TEST_ASSERT_EQUAL(403, g.response().code);
}

void test_ota_flow_start_checks_reject_before_flash() {
  const OtaStartChecks bad[] = {{true, true, false, true, true},
                                {true, true, true, false, true},
                                {true, true, true, true, false}};
  const OtaError expect[] = {OtaError::Field, OtaError::Md5, OtaError::TooLarge};
  for (int i = 0; i < 3; ++i) {
    OtaFlow f;
    f.onFileStart(bad[i]);
    TEST_ASSERT_TRUE(f.authorized());
    TEST_ASSERT_TRUE(f.onChunk(true) == OtaFlow::Chunk::Skip);
    TEST_ASSERT_TRUE(f.error() == expect[i]);
    TEST_ASSERT_EQUAL(400, f.response().code);
    TEST_ASSERT_TRUE(f.mayDiscard());
  }
}

void test_ota_flow_not_an_image_rejected_on_first_chunk() {
  OtaFlow f;
  f.onFileStart(kGood);
  TEST_ASSERT_TRUE(f.onChunk(false) == OtaFlow::Chunk::Skip);
  TEST_ASSERT_TRUE(f.error() == OtaError::NotImage);
  TEST_ASSERT_TRUE(f.onChunk(true) == OtaFlow::Chunk::Skip);  // stays failed
  TEST_ASSERT_TRUE(f.onFileEnd() == OtaFlow::End::Skip);
  TEST_ASSERT_EQUAL(400, f.response().code);
}

void test_ota_flow_md5_mismatch_and_errors_discard() {
  OtaFlow f;
  uploadUntilEnd(f);
  TEST_ASSERT_FALSE(f.onFinished(false, OtaError::Md5Mismatch));
  TEST_ASSERT_FALSE(f.committed());
  TEST_ASSERT_TRUE(f.mayDiscard());
  TEST_ASSERT_EQUAL(400, f.response().code);
  TEST_ASSERT_EQUAL_STRING("md5 mismatch", otaErrorText(f.response().error));

  OtaFlow w;
  w.onFileStart(kGood);
  w.onChunk(true);
  w.onBegin(true);
  w.onWrite(false, false);
  TEST_ASSERT_TRUE(w.onChunk(true) == OtaFlow::Chunk::Skip);
  TEST_ASSERT_EQUAL(500, w.response().code);

  OtaFlow b;
  b.onFileStart(kGood);
  b.onChunk(true);
  b.onBegin(false);
  TEST_ASSERT_EQUAL(500, b.response().code);

  OtaFlow a;
  a.onFileStart(kGood);
  a.onChunk(true);
  a.onBegin(true);
  a.onAborted();
  TEST_ASSERT_TRUE(a.error() == OtaError::Aborted);
  TEST_ASSERT_TRUE(a.mayDiscard());
}

void test_ota_flow_empty_and_second_part_after_failure() {
  OtaFlow f;
  f.onFileStart(kGood);
  TEST_ASSERT_TRUE(f.onFileEnd() == OtaFlow::End::Skip);
  TEST_ASSERT_TRUE(f.error() == OtaError::Empty);
  f.onFileStart(kGood);  // second part cannot reset the failure
  TEST_ASSERT_TRUE(f.onChunk(true) == OtaFlow::Chunk::Skip);
  TEST_ASSERT_TRUE(f.error() == OtaError::Empty);
  f.endRequest();
  TEST_ASSERT_FALSE(f.started());
  TEST_ASSERT_FALSE(f.failed());
  uploadUntilEnd(f);  // a fresh request works again
  TEST_ASSERT_TRUE(f.onFinished(true, OtaError::None));
}

// ---- Task 13: health latch, safe-mode policy, frame poll state ----

void test_health_latch_marks_exactly_once() {
  HealthLatch h;
  TEST_ASSERT_FALSE(h.shouldMark(59999, true, true));
  TEST_ASSERT_FALSE(h.shouldMark(60000, false, true));
  TEST_ASSERT_FALSE(h.shouldMark(60000, true, false));
  TEST_ASSERT_FALSE(h.marked());
  TEST_ASSERT_TRUE(h.shouldMark(60000, true, true));
  TEST_ASSERT_TRUE(h.marked());
  TEST_ASSERT_FALSE(h.shouldMark(60001, true, true));
  TEST_ASSERT_FALSE(h.shouldMark(900000, true, true));
}

void test_safe_mode_portal_only_without_valid_password() {
  Settings s;  // missing/corrupt settings file -> defaults
  TEST_ASSERT_TRUE(safeModeNeedsPortal(s));
  std::string err;
  TEST_ASSERT_TRUE(applyPassword(s, "longenough", &err));
  // URL is irrelevant in safe mode: a valid password is enough to accept updates.
  TEST_ASSERT_FALSE(safeModeNeedsPortal(s));
  TEST_ASSERT_TRUE(applyServerUrl(s, "homeserver:8080", &err));
  TEST_ASSERT_FALSE(safeModeNeedsPortal(s));
  strcpy(s.updatePassword, "short");  // corrupt/invalid stored password
  TEST_ASSERT_TRUE(safeModeNeedsPortal(s));
}

void test_safe_mode_ap_fallback_after_connect_timeout() {
  TEST_ASSERT_FALSE(safeModeApFallback(false, kSafeModeConnectMs - 1));
  TEST_ASSERT_TRUE(safeModeApFallback(false, kSafeModeConnectMs));
  TEST_ASSERT_FALSE(safeModeApFallback(true, kSafeModeConnectMs * 10));
}

void test_parse_next_in() {
  TEST_ASSERT_EQUAL_INT(-1, parseNextIn(nullptr));
  TEST_ASSERT_EQUAL_INT(-1, parseNextIn(""));
  TEST_ASSERT_EQUAL_INT(15, parseNextIn("15"));
  TEST_ASSERT_EQUAL_INT(15, parseNextIn(" 15 "));
  TEST_ASSERT_EQUAL_INT(0, parseNextIn("0"));
  TEST_ASSERT_EQUAL_INT(-1, parseNextIn("-3"));
  TEST_ASSERT_EQUAL_INT(-1, parseNextIn("1.5"));
  TEST_ASSERT_EQUAL_INT(-1, parseNextIn("abc"));
  TEST_ASSERT_EQUAL_INT(9999, parseNextIn("99999999999999999999"));  // saturates, clamped later
  TEST_ASSERT_EQUAL_UINT32(30000, nextDelayMs(true, parseNextIn("99999999999999999999"), 0));
}

void test_store_etag() {
  char e[kEtagCap];
  TEST_ASSERT_TRUE(storeEtag(e, "\"abc\""));
  TEST_ASSERT_EQUAL_STRING("\"abc\"", e);
  std::string max(kEtagCap - 1, 'x');
  TEST_ASSERT_TRUE(storeEtag(e, max.c_str()));
  TEST_ASSERT_EQUAL_STRING(max.c_str(), e);
  std::string tooLong(kEtagCap, 'y');
  TEST_ASSERT_FALSE(storeEtag(e, tooLong.c_str()));  // never keep a truncated tag
  TEST_ASSERT_EQUAL_STRING("", e);
  TEST_ASSERT_FALSE(storeEtag(e, nullptr));
  TEST_ASSERT_EQUAL_STRING("", e);
}

void test_frame_error_text() {
  char b[kErrorTextCap];
  frameErrorText(500, b, sizeof(b));
  TEST_ASSERT_EQUAL_STRING("HTTP 500", b);
  frameErrorText(-1, b, sizeof(b));
  TEST_ASSERT_EQUAL_STRING("connection failed", b);
  frameErrorText(-11, b, sizeof(b));
  TEST_ASSERT_EQUAL_STRING("read timeout", b);
  frameErrorText(kErrFrameLength, b, sizeof(b));
  TEST_ASSERT_EQUAL_STRING("bad frame size", b);
  frameErrorText(kErrBodyRead, b, sizeof(b));
  TEST_ASSERT_EQUAL_STRING("frame incomplete", b);
  frameErrorText(kErrDecode, b, sizeof(b));
  TEST_ASSERT_EQUAL_STRING("bad JPEG", b);
  frameErrorText(kErrNoWifi, b, sizeof(b));
  TEST_ASSERT_EQUAL_STRING("no Wi-Fi", b);
  frameErrorText(-7, b, sizeof(b));
  TEST_ASSERT_EQUAL_STRING("network error -7", b);
  char tiny[4];
  frameErrorText(500, tiny, sizeof(tiny));
  TEST_ASSERT_EQUAL_STRING("HTT", tiny);
}

void test_poller_success_uses_next_in_and_resets_failures() {
  FramePoller p;
  p.begin(1000);
  PollOutcome o = p.onFailure(-1, 2000);
  TEST_ASSERT_EQUAL_UINT32(2000, o.delayMs);
  o = p.onFailure(-1, 4000);
  TEST_ASSERT_EQUAL_UINT32(4000, o.delayMs);
  TEST_ASSERT_EQUAL_UINT8(2, p.failures());
  o = p.onSuccess(12, 8000);
  TEST_ASSERT_EQUAL_UINT32(12000, o.delayMs);
  TEST_ASSERT_FALSE(o.drawOffline);
  TEST_ASSERT_FALSE(o.clearEtag);
  TEST_ASSERT_EQUAL_UINT8(0, p.failures());
  TEST_ASSERT_EQUAL_UINT32(2000, p.onFailure(-1, 9000).delayMs);  // backoff restarts
}

void test_poller_offline_after_120s_since_boot_or_last_success() {
  FramePoller p;
  p.begin(5000);  // never succeeded: the clock starts at begin()
  TEST_ASSERT_FALSE(p.onFailure(-1, 5000 + 119999).drawOffline);
  PollOutcome o = p.onFailure(-1, 5000 + 120000);
  TEST_ASSERT_TRUE(o.drawOffline);
  TEST_ASSERT_TRUE(o.clearEtag);  // screen no longer shows the frame of the stored ETag
  TEST_ASSERT_TRUE(p.offline());
  // Same error again: no redraw (no flicker every poll).
  o = p.onFailure(-1, 5000 + 150000);
  TEST_ASSERT_FALSE(o.drawOffline);
  TEST_ASSERT_FALSE(o.clearEtag);
  // Different error while offline: redraw with the new text.
  TEST_ASSERT_TRUE(p.onFailure(500, 5000 + 180000).drawOffline);
  TEST_ASSERT_FALSE(p.onFailure(500, 5000 + 210000).drawOffline);
  // Recovery leaves offline; a later outage needs another full 120 s.
  p.onSuccess(10, 300000);
  TEST_ASSERT_FALSE(p.offline());
  TEST_ASSERT_FALSE(p.onFailure(-1, 300000 + 119999).drawOffline);
  TEST_ASSERT_TRUE(p.onFailure(-1, 300000 + 120000).drawOffline);
}

void test_poller_offline_redrawn_after_partial_frames() {
  FramePoller p;
  p.begin(0);
  // Slow link: every 200 starts drawing, then misses the body deadline.
  PollOutcome o = p.onFailure(kErrBodyRead, 120000);
  TEST_ASSERT_TRUE(o.drawOffline);
  // Same error, but the partial frame overwrote the offline screen: redraw it.
  o = p.onFailure(kErrBodyRead, 150000);
  TEST_ASSERT_TRUE(o.drawOffline);
  TEST_ASSERT_TRUE(o.clearEtag);
  TEST_ASSERT_TRUE(p.onFailure(kErrDecode, 180000).drawOffline);
  TEST_ASSERT_TRUE(p.onFailure(kErrDecode, 210000).drawOffline);
  // Errors without drawing still do not flicker.
  TEST_ASSERT_TRUE(p.onFailure(-1, 240000).drawOffline);  // error changed
  TEST_ASSERT_FALSE(p.onFailure(-1, 270000).drawOffline);
  // Before 120 s a partial draw does not bring up the offline screen.
  FramePoller q;
  q.begin(0);
  TEST_ASSERT_FALSE(q.onFailure(kErrBodyRead, 1000).drawOffline);
}

void test_poller_millis_wraparound() {
  FramePoller p;
  p.begin(0xFFFFF000u);
  TEST_ASSERT_FALSE(p.onFailure(-1, 0x00001000u).drawOffline);  // 8 KB ms later, wrapped
  TEST_ASSERT_TRUE(p.onFailure(-1, 0xFFFFF000u + 120000u).drawOffline);
}

void test_poller_decode_error_clears_etag() {
  FramePoller p;
  p.begin(0);
  PollOutcome o = p.onFailure(kErrDecode, 1000);
  TEST_ASSERT_TRUE(o.clearEtag);  // a partial draw must be replaced by a full 200 next time
  TEST_ASSERT_FALSE(o.drawOffline);
  TEST_ASSERT_FALSE(p.onFailure(-1, 2000).clearEtag);  // the last good frame still stands
  // Stream decode: a body cut off mid-frame leaves a partial draw as well.
  TEST_ASSERT_TRUE(p.onFailure(kErrBodyRead, 3000).clearEtag);
  TEST_ASSERT_FALSE(p.onFailure(kErrFrameLength, 4000).clearEtag);  // rejected before drawing
}

void test_poller_failure_count_saturates() {
  FramePoller p;
  p.begin(0);
  for (int i = 0; i < 300; ++i) p.onFailure(-1, 1000);
  TEST_ASSERT_EQUAL_UINT8(255, p.failures());
  TEST_ASSERT_EQUAL_UINT32(30000, p.onFailure(-1, 1000).delayMs);
}

// ---- night mode ----

void test_parse_local_time() {
  TEST_ASSERT_EQUAL_INT32(0, parseLocalTime("00:00:00"));
  TEST_ASSERT_EQUAL_INT32(86399, parseLocalTime("23:59:59"));
  TEST_ASSERT_EQUAL_INT32(14 * 3600 + 46 * 60 + 40, parseLocalTime("14:46:40"));
  TEST_ASSERT_EQUAL_INT32(-1, parseLocalTime("24:00:00"));
  TEST_ASSERT_EQUAL_INT32(-1, parseLocalTime("12:60:00"));
  TEST_ASSERT_EQUAL_INT32(-1, parseLocalTime("12:00:60"));
  TEST_ASSERT_EQUAL_INT32(-1, parseLocalTime("1:00:00"));
  TEST_ASSERT_EQUAL_INT32(-1, parseLocalTime("12:00:00 "));
  TEST_ASSERT_EQUAL_INT32(-1, parseLocalTime("ab:cd:ef"));
  TEST_ASSERT_EQUAL_INT32(-1, parseLocalTime(""));
  TEST_ASSERT_EQUAL_INT32(-1, parseLocalTime(nullptr));
}

void test_parse_format_hhmm() {
  TEST_ASSERT_EQUAL_INT(1320, parseHhMm("22:00"));
  TEST_ASSERT_EQUAL_INT(0, parseHhMm("00:00"));
  TEST_ASSERT_EQUAL_INT(1439, parseHhMm("23:59"));
  TEST_ASSERT_EQUAL_INT(-1, parseHhMm("24:00"));
  TEST_ASSERT_EQUAL_INT(-1, parseHhMm("22:00:00"));
  TEST_ASSERT_EQUAL_INT(-1, parseHhMm("7:00"));
  TEST_ASSERT_EQUAL_INT(-1, parseHhMm(""));
  TEST_ASSERT_EQUAL_STRING("07:05", formatHhMm(425).c_str());
  TEST_ASSERT_EQUAL_STRING("00:00", formatHhMm(0).c_str());
  TEST_ASSERT_EQUAL_STRING("23:59", formatHhMm(1439).c_str());
}

void test_night_window() {
  TEST_ASSERT_FALSE(nightActive(0, 0, 0));          // start == end: off
  TEST_ASSERT_FALSE(nightActive(600, 600, 600));
  TEST_ASSERT_TRUE(nightActive(1320, 420, 1439));   // 23:59
  TEST_ASSERT_TRUE(nightActive(1320, 420, 0));      // 00:00
  TEST_ASSERT_TRUE(nightActive(1320, 420, 419));    // 06:59
  TEST_ASSERT_FALSE(nightActive(1320, 420, 420));   // 07:00
  TEST_ASSERT_FALSE(nightActive(1320, 420, 1319));  // 21:59
  TEST_ASSERT_TRUE(nightActive(1320, 420, 1320));   // 22:00
  TEST_ASSERT_TRUE(nightActive(60, 120, 60));       // same-day window
  TEST_ASSERT_TRUE(nightActive(60, 120, 119));
  TEST_ASSERT_FALSE(nightActive(60, 120, 120));
  TEST_ASSERT_FALSE(nightActive(60, 120, 59));
}

void test_local_clock() {
  LocalClock c;
  TEST_ASSERT_FALSE(c.known());
  c.sync(86390, 1000);  // 23:59:50
  TEST_ASSERT_TRUE(c.known());
  TEST_ASSERT_EQUAL_UINT32(86390, c.secondOfDay(1000));
  TEST_ASSERT_EQUAL_UINT32(86395, c.secondOfDay(6000));
  TEST_ASSERT_EQUAL_UINT32(10, c.secondOfDay(21000));  // past midnight
  LocalClock w;
  w.sync(0, 0xFFFFF000u);  // millis() about to overflow
  TEST_ASSERT_EQUAL_UINT32(10, w.secondOfDay(0xFFFFF000u + 10000u));
  LocalClock d;  // several days without resync
  d.sync(3600, 0);
  TEST_ASSERT_EQUAL_UINT32(3600 + 5, d.secondOfDay(3u * 86400000u + 5000u));
}

void test_effective_brightness() {
  Settings s;
  s.brightness = 80;
  s.nightStart = 1320;
  s.nightEnd = 420;
  s.nightBrightness = 0;
  TEST_ASSERT_EQUAL_UINT8(80, effectiveBrightness(s, false, 23 * 3600));  // time unknown
  TEST_ASSERT_EQUAL_UINT8(0, effectiveBrightness(s, true, 23 * 3600));
  TEST_ASSERT_EQUAL_UINT8(0, effectiveBrightness(s, true, 6 * 3600 + 59 * 60 + 59));
  TEST_ASSERT_EQUAL_UINT8(80, effectiveBrightness(s, true, 7 * 3600));
  TEST_ASSERT_EQUAL_UINT8(80, effectiveBrightness(s, true, 12 * 3600));
  Settings off;  // defaults: night mode off
  off.brightness = 60;
  TEST_ASSERT_EQUAL_UINT8(60, effectiveBrightness(off, true, 23 * 3600));
}

void test_backlight_duty_is_perceptual() {
  TEST_ASSERT_EQUAL_UINT16(0, backlightDuty(0));  // 0 % stays fully off
  TEST_ASSERT_EQUAL_UINT16(kBacklightPwmRange, backlightDuty(100));
  TEST_ASSERT_EQUAL_UINT16(kBacklightPwmRange, backlightDuty(250));  // clamped
  TEST_ASSERT_EQUAL_UINT16(1, backlightDuty(1));  // never off unless 0 %
  // Quadratic curve: low settings are clearly darker than a linear duty would be.
  TEST_ASSERT_EQUAL_UINT16(3, backlightDuty(5));
  TEST_ASSERT_EQUAL_UINT16(40, backlightDuty(20));
  TEST_ASSERT_EQUAL_UINT16(250, backlightDuty(50));
  for (int p = 1; p <= 100; p++) {
    TEST_ASSERT_TRUE(backlightDuty(static_cast<uint8_t>(p)) >=
                     backlightDuty(static_cast<uint8_t>(p - 1)));
  }
}

void test_preview_inactive_by_default() {
  BacklightPreview p;
  TEST_ASSERT_FALSE(p.active(0));
  TEST_ASSERT_FALSE(p.active(123456));
}

void test_preview_holds_3s_then_expires() {
  BacklightPreview p;
  p.set(40, 1000);
  TEST_ASSERT_TRUE(p.active(1000));
  TEST_ASSERT_TRUE(p.active(3999));
  TEST_ASSERT_FALSE(p.active(4000));
  TEST_ASSERT_EQUAL_UINT8(40, p.pct());
}

void test_preview_refresh_extends() {
  BacklightPreview p;
  p.set(10, 0);
  p.set(20, 2500);
  TEST_ASSERT_TRUE(p.active(5499));
  TEST_ASSERT_FALSE(p.active(5500));
  TEST_ASSERT_EQUAL_UINT8(20, p.pct());
}

void test_preview_millis_wraparound() {
  BacklightPreview p;
  p.set(50, 0xFFFFFC00u);  // 1024 ms before the wrap
  TEST_ASSERT_TRUE(p.active(0x00000100u));
  TEST_ASSERT_FALSE(p.active(0xFFFFFC00u + kPreviewHoldMs));
}

void test_preview_expires_and_saved_value_applies() {
  BacklightPreview p;
  p.set(30, 100);
  p.clear();
  TEST_ASSERT_FALSE(p.active(101));
}

void test_preview_clamps() {
  BacklightPreview p;
  p.set(250, 0);
  TEST_ASSERT_EQUAL_UINT8(100, p.pct());
}

static Settings patchBase() {
  Settings s;
  std::string err;
  applyServerUrl(s, "http://10.0.0.2:8090", &err);
  applyPassword(s, "oldpassword", &err);
  s.brightness = 80;
  s.nightStart = 1320;
  s.nightEnd = 420;
  s.nightBrightness = 0;
  return s;
}

void test_settings_patch_single_field() {
  Settings s = patchBase();
  SettingsPatch p;
  p.brightness = "30";
  std::string field, err;
  TEST_ASSERT_TRUE(applySettingsPatch(s, p, &field, &err));
  TEST_ASSERT_EQUAL_UINT8(30, s.brightness);
  TEST_ASSERT_EQUAL_STRING("http://10.0.0.2:8090", s.serverUrl);
  TEST_ASSERT_EQUAL_UINT16(1320, s.nightStart);
  TEST_ASSERT_EQUAL_STRING("oldpassword", s.updatePassword);
}

void test_settings_patch_night_start_only() {
  Settings s = patchBase();
  SettingsPatch p;
  p.nightStart = "21:30";
  std::string field, err;
  TEST_ASSERT_TRUE(applySettingsPatch(s, p, &field, &err));
  TEST_ASSERT_EQUAL_UINT16(1290, s.nightStart);
  TEST_ASSERT_EQUAL_UINT16(420, s.nightEnd);
  TEST_ASSERT_EQUAL_UINT8(0, s.nightBrightness);
}

void test_settings_patch_night_off() {
  Settings s = patchBase();
  SettingsPatch p;
  p.nightStart = "00:00";
  p.nightEnd = "00:00";
  std::string field, err;
  TEST_ASSERT_TRUE(applySettingsPatch(s, p, &field, &err));
  TEST_ASSERT_EQUAL_UINT16(0, s.nightStart);
  TEST_ASSERT_EQUAL_UINT16(0, s.nightEnd);
}

void test_settings_patch_atomic_on_error() {
  Settings s = patchBase();
  SettingsPatch p;
  p.brightness = "40";
  p.serverUrl = "https://x";
  std::string field, err;
  TEST_ASSERT_FALSE(applySettingsPatch(s, p, &field, &err));
  TEST_ASSERT_EQUAL_STRING("server_url", field.c_str());
  TEST_ASSERT_EQUAL_STRING("https_unsupported", err.c_str());
  TEST_ASSERT_EQUAL_UINT8(80, s.brightness);
}

void test_settings_patch_bad_brightness() {
  for (const char* bad : {"4", "101", "5a", ""}) {
    Settings s = patchBase();
    SettingsPatch p;
    p.brightness = bad;
    std::string field, err;
    TEST_ASSERT_FALSE(applySettingsPatch(s, p, &field, &err));
    TEST_ASSERT_EQUAL_STRING("brightness", field.c_str());
    TEST_ASSERT_EQUAL_STRING("bad_brightness", err.c_str());
    TEST_ASSERT_EQUAL_UINT8(80, s.brightness);
  }
}

void test_settings_patch_night_errors_name_field() {
  Settings s = patchBase();
  SettingsPatch p;
  p.nightBrightness = "101";
  std::string field, err;
  TEST_ASSERT_FALSE(applySettingsPatch(s, p, &field, &err));
  TEST_ASSERT_EQUAL_STRING("night_brightness", field.c_str());
  TEST_ASSERT_EQUAL_STRING("bad_night_brightness", err.c_str());
  SettingsPatch q;
  q.nightEnd = "25:00";
  TEST_ASSERT_FALSE(applySettingsPatch(s, q, &field, &err));
  TEST_ASSERT_EQUAL_STRING("night_end", field.c_str());
  TEST_ASSERT_EQUAL_STRING("bad_time", err.c_str());
}

void test_settings_patch_password() {
  Settings s = patchBase();
  SettingsPatch p;
  p.password = "short";
  p.passwordRepeat = "short";
  std::string field, err;
  TEST_ASSERT_FALSE(applySettingsPatch(s, p, &field, &err));
  TEST_ASSERT_EQUAL_STRING("password", field.c_str());
  TEST_ASSERT_EQUAL_STRING("too_short", err.c_str());
  p.password = "longenough1";
  p.passwordRepeat = "longenough1";
  TEST_ASSERT_TRUE(applySettingsPatch(s, p, &field, &err));
  TEST_ASSERT_EQUAL_STRING("longenough1", s.updatePassword);
}

void test_settings_patch_empty() {
  Settings s = patchBase();
  SettingsPatch p;
  std::string field, err;
  TEST_ASSERT_TRUE(applySettingsPatch(s, p, &field, &err));
  TEST_ASSERT_EQUAL_UINT8(80, s.brightness);
}

void test_server_url_empty_is_required() {
  std::string err;
  TEST_ASSERT_FALSE(normalizeServerUrl("", &err).has_value());
  TEST_ASSERT_EQUAL_STRING("required", err.c_str());
  TEST_ASSERT_FALSE(normalizeServerUrl("  \t ", &err).has_value());
  TEST_ASSERT_EQUAL_STRING("required", err.c_str());
  TEST_ASSERT_FALSE(normalizeServerUrl("http://", &err).has_value());
  TEST_ASSERT_EQUAL_STRING("empty_host", err.c_str());
}

static bool portalFails(const Settings& s, const PortalForm& f, const char* field, const char* code) {
  Settings next;
  std::string gotField, gotCode;
  if (applyPortalForm(s, f, &next, &gotField, &gotCode)) return false;
  return gotField == field && gotCode == code;
}

void test_portal_form_first_setup() {
  const Settings s{};
  Settings next;
  std::string field, err;
  TEST_ASSERT_TRUE(applyPortalForm(s, {"192.168.1.10:8090", "correct-horse", "correct-horse", "60", ""}, &next, &field, &err));
  TEST_ASSERT_EQUAL_STRING("http://192.168.1.10:8090", next.serverUrl);
  TEST_ASSERT_EQUAL_STRING("correct-horse", next.updatePassword);
  TEST_ASSERT_EQUAL_UINT8(60, next.brightness);
  TEST_ASSERT_TRUE(applyPortalForm(s, {"a.lan", "correct-horse", "correct-horse", "", ""}, &next, &field, &err));
  TEST_ASSERT_EQUAL_UINT8(kDefaultBrightness, next.brightness);  // empty = keep

  TEST_ASSERT_TRUE(portalFails(s, {"", "correct-horse", "correct-horse", "60", ""}, "server_url", "required"));
  TEST_ASSERT_TRUE(portalFails(s, {"https://a.lan", "correct-horse", "correct-horse", "", ""}, "server_url", "https_unsupported"));
  TEST_ASSERT_TRUE(portalFails(s, {"a.lan", "", "", "", ""}, "update_password", "too_short"));
  TEST_ASSERT_TRUE(portalFails(s, {"a.lan", "short", "short", "", ""}, "update_password", "too_short"));
  TEST_ASSERT_TRUE(portalFails(s, {"a.lan", "correct-horse", "correct-horse", "4", ""}, "brightness", "bad_brightness"));
  TEST_ASSERT_TRUE(portalFails(s, {"a.lan", "correct-horse", "correct-horse", "101", ""}, "brightness", "bad_brightness"));
  TEST_ASSERT_TRUE(portalFails(s, {"a.lan", "correct-horse", "correct-horse", "+50", ""}, "brightness", "bad_brightness"));
}

void test_portal_form_configured_device() {
  const Settings s = patchBase();  // http://10.0.0.2:8090, "oldpassword", brightness 80
  Settings next;
  std::string field, err;
  // Wi-Fi-only change: stored values resubmitted, no current password needed.
  TEST_ASSERT_TRUE(applyPortalForm(s, {"http://10.0.0.2:8090", "", "", "80", ""}, &next, &field, &err));
  TEST_ASSERT_EQUAL_STRING("oldpassword", next.updatePassword);
  // Any change needs the current password.
  TEST_ASSERT_TRUE(portalFails(s, {"http://10.0.0.3:8090", "", "", "", ""}, "current_password", "wrong_password"));
  TEST_ASSERT_TRUE(portalFails(s, {"http://10.0.0.2:8090", "", "", "70", "nope-nope"}, "current_password", "wrong_password"));
  TEST_ASSERT_TRUE(applyPortalForm(s, {"http://10.0.0.3:8090", "newpassword1", "newpassword1", "70", "oldpassword"}, &next, &field, &err));
  TEST_ASSERT_EQUAL_STRING("http://10.0.0.3:8090", next.serverUrl);
  TEST_ASSERT_EQUAL_STRING("newpassword1", next.updatePassword);
  TEST_ASSERT_EQUAL_UINT8(70, next.brightness);
  // Errors in a value come before the current-password check.
  TEST_ASSERT_TRUE(portalFails(s, {"", "", "", "", "oldpassword"}, "server_url", "required"));
}

void test_portal_form_keeps_stored_url_with_old_characters() {
  Settings s = patchBase();
  std::strcpy(s.serverUrl, "http://old'host");  // stored before the character check existed
  Settings next;
  std::string field, err;
  TEST_ASSERT_TRUE(applyPortalForm(s, {"http://old'host", "", "", "", ""}, &next, &field, &err));
  TEST_ASSERT_TRUE(portalFails(s, {"http://new'host", "", "", "", "oldpassword"}, "server_url", "invalid_chars"));
}

void test_apply_new_password_needs_equal_repeat() {
  Settings s = patchBase();
  std::string err;
  TEST_ASSERT_FALSE(applyNewPassword(s, "newpassword1", "newpassword2", &err));
  TEST_ASSERT_EQUAL_STRING("mismatch", err.c_str());
  TEST_ASSERT_FALSE(applyNewPassword(s, "newpassword1", "newpassword1 ", &err));  // nothing is trimmed
  TEST_ASSERT_EQUAL_STRING("mismatch", err.c_str());
  TEST_ASSERT_FALSE(applyNewPassword(s, "short", "longenough1", &err));  // mismatch comes first
  TEST_ASSERT_EQUAL_STRING("mismatch", err.c_str());
  TEST_ASSERT_FALSE(applyNewPassword(s, "short", "short", &err));
  TEST_ASSERT_EQUAL_STRING("too_short", err.c_str());
  TEST_ASSERT_EQUAL_STRING("oldpassword", s.updatePassword);
  TEST_ASSERT_TRUE(applyNewPassword(s, "newpassword1", "newpassword1", &err));
  TEST_ASSERT_EQUAL_STRING("newpassword1", s.updatePassword);
}

void test_settings_patch_password_needs_repeat() {
  Settings s = patchBase();
  std::string field, err;
  SettingsPatch p;
  p.password = "longenough1";  // repeat missing
  TEST_ASSERT_FALSE(applySettingsPatch(s, p, &field, &err));
  TEST_ASSERT_EQUAL_STRING("password_repeat", field.c_str());
  TEST_ASSERT_EQUAL_STRING("mismatch", err.c_str());
  p.passwordRepeat = "longenough2";
  TEST_ASSERT_FALSE(applySettingsPatch(s, p, &field, &err));
  TEST_ASSERT_EQUAL_STRING("mismatch", err.c_str());
  TEST_ASSERT_EQUAL_STRING("oldpassword", s.updatePassword);
  SettingsPatch q;
  q.passwordRepeat = "longenough1";  // repeat alone: no password field, nothing to apply
  TEST_ASSERT_TRUE(applySettingsPatch(s, q, &field, &err));
  TEST_ASSERT_EQUAL_STRING("oldpassword", s.updatePassword);
}

void test_portal_form_password_repeat() {
  const Settings fresh{};
  TEST_ASSERT_TRUE(portalFails(fresh, {"a.lan", "correct-horse", "correct-hores", "", ""},
                               "update_password_repeat", "mismatch"));
  TEST_ASSERT_TRUE(portalFails(fresh, {"a.lan", "correct-horse", "", "", ""},
                               "update_password_repeat", "mismatch"));
  const Settings s = patchBase();
  // Only the repeat field filled: an error, not a silent "keep".
  TEST_ASSERT_TRUE(portalFails(s, {"http://10.0.0.2:8090", "", "newpassword1", "", "oldpassword"},
                               "update_password_repeat", "mismatch"));
  Settings next;
  std::string field, err;
  TEST_ASSERT_TRUE(applyPortalForm(s, {"http://10.0.0.2:8090", "", "", "", ""}, &next, &field, &err));
  TEST_ASSERT_EQUAL_STRING("oldpassword", next.updatePassword);  // both empty = keep
  TEST_ASSERT_TRUE(applyPortalForm(s, {"http://10.0.0.2:8090", "newpassword1", "newpassword1", "", "oldpassword"},
                                   &next, &field, &err));
  TEST_ASSERT_EQUAL_STRING("newpassword1", next.updatePassword);
  // The new password never stands in for the current one.
  TEST_ASSERT_TRUE(portalFails(s, {"http://10.0.0.2:8090", "newpassword1", "newpassword1", "", "newpassword1"},
                               "current_password", "wrong_password"));
}

void test_wifi_quality() {
  TEST_ASSERT_TRUE(wifiQuality(-50) == WifiQuality::Excellent);
  TEST_ASSERT_TRUE(wifiQuality(-60) == WifiQuality::Excellent);
  TEST_ASSERT_TRUE(wifiQuality(-61) == WifiQuality::Good);
  TEST_ASSERT_TRUE(wifiQuality(-70) == WifiQuality::Good);
  TEST_ASSERT_TRUE(wifiQuality(-71) == WifiQuality::Fair);
  TEST_ASSERT_TRUE(wifiQuality(-80) == WifiQuality::Fair);
  TEST_ASSERT_TRUE(wifiQuality(-81) == WifiQuality::Weak);
}

void test_format_duration() {
  TEST_ASSERT_EQUAL_STRING("0 s", formatDuration(0, "d").c_str());
  TEST_ASSERT_EQUAL_STRING("59 s", formatDuration(59, "d").c_str());
  TEST_ASSERT_EQUAL_STRING("1 min", formatDuration(60, "d").c_str());
  TEST_ASSERT_EQUAL_STRING("59 min", formatDuration(3599, "d").c_str());
  TEST_ASSERT_EQUAL_STRING("1 h 0 min", formatDuration(3600, "d").c_str());
  TEST_ASSERT_EQUAL_STRING("23 h 59 min", formatDuration(86399, "d").c_str());
  TEST_ASSERT_EQUAL_STRING("1 T 21 h", formatDuration(163787, "T").c_str());
}

void test_apply_night() {
  Settings s;
  std::string err;
  TEST_ASSERT_TRUE(applyNight(s, "22:00", "07:00", "10", &err));
  TEST_ASSERT_EQUAL_UINT16(1320, s.nightStart);
  TEST_ASSERT_EQUAL_UINT16(420, s.nightEnd);
  TEST_ASSERT_EQUAL_UINT8(10, s.nightBrightness);
  TEST_ASSERT_TRUE(applyNight(s, "22:00", "07:00", "0", &err));
  TEST_ASSERT_EQUAL_UINT8(0, s.nightBrightness);
  TEST_ASSERT_FALSE(applyNight(s, "25:00", "07:00", "10", &err));
  TEST_ASSERT_EQUAL_STRING("bad_time", err.c_str());
  TEST_ASSERT_FALSE(applyNight(s, "22:00", "", "10", &err));
  TEST_ASSERT_EQUAL_STRING("bad_time", err.c_str());
  TEST_ASSERT_FALSE(applyNight(s, "21:00", "07:00", "101", &err));
  TEST_ASSERT_EQUAL_STRING("bad_night_brightness", err.c_str());
  TEST_ASSERT_FALSE(applyNight(s, "21:00", "07:00", "", &err));
  TEST_ASSERT_FALSE(applyNight(s, "21:00", "07:00", "5x", &err));
  TEST_ASSERT_FALSE(applyNight(s, "21:00", "07:00", "-1", &err));
  TEST_ASSERT_EQUAL_UINT16(1320, s.nightStart);  // unchanged on failure
  TEST_ASSERT_EQUAL_UINT8(0, s.nightBrightness);
}

void test_settings_night_roundtrip_and_old_file() {
  Settings s;
  s.nightStart = 1320;
  s.nightEnd = 420;
  s.nightBrightness = 5;
  Settings back;
  TEST_ASSERT_TRUE(parseSettings(encodeSettings(s), &back));
  TEST_ASSERT_EQUAL_UINT16(1320, back.nightStart);
  TEST_ASSERT_EQUAL_UINT16(420, back.nightEnd);
  TEST_ASSERT_EQUAL_UINT8(5, back.nightBrightness);
  Settings old;  // 0.1.0 file without night keys
  TEST_ASSERT_TRUE(parseSettings(
      "{\"server_url\":\"http://h:8090\",\"update_password\":\"abcdefgh\",\"brightness\":70}\n",
      &old));
  TEST_ASSERT_EQUAL_UINT8(70, old.brightness);
  TEST_ASSERT_EQUAL_UINT16(0, old.nightStart);
  TEST_ASSERT_EQUAL_UINT16(0, old.nightEnd);
  TEST_ASSERT_EQUAL_UINT8(0, old.nightBrightness);
  Settings bad;  // out-of-range minutes fall back to 0, brightness clamped
  TEST_ASSERT_TRUE(parseSettings(
      "{\"night_start\":5000,\"night_end\":-3,\"night_brightness\":250}\n", &bad));
  TEST_ASSERT_EQUAL_UINT16(0, bad.nightStart);
  TEST_ASSERT_EQUAL_UINT16(0, bad.nightEnd);
  TEST_ASSERT_EQUAL_UINT8(100, bad.nightBrightness);
}

void test_portal_ap_password_only_when_configured() {
  gb::Settings s{};                       // unconfigured: open AP
  TEST_ASSERT_NULL(gb::portalApPassword(s));
  std::string err;
  TEST_ASSERT_TRUE(gb::applyPassword(s, "correct-horse", &err));
  TEST_ASSERT_NULL(gb::portalApPassword(s));  // password alone: still not configured
  TEST_ASSERT_TRUE(gb::applyServerUrl(s, "http://192.168.1.10:8080", &err));
  TEST_ASSERT_EQUAL_STRING("correct-horse", gb::portalApPassword(s));
}

void test_server_url_rejects_markup_chars() {
  const char* bad[] = {"http://h/'x", "http://h/\"x", "http://h/<x", "http://h/>x",
                       "http://h/`x", "http://h/a b", "http://h/\x01", "http://h/\xc3\xa4",
                       "http://h/\x7f", "http://h/a\tb"};
  for (const char* url : bad) {
    gb::Settings s{};
    std::string err;
    TEST_ASSERT_FALSE_MESSAGE(gb::applyServerUrl(s, url, &err), url);
    TEST_ASSERT_EQUAL_STRING_MESSAGE("invalid_chars", err.c_str(), url);
    TEST_ASSERT_EQUAL_STRING("", s.serverUrl);
  }
}

void test_server_url_still_accepts_normal_urls() {  // surrounding spaces are trimmed as before
  gb::Settings s{};
  std::string err;
  TEST_ASSERT_TRUE(gb::applyServerUrl(s, "  http://192.168.1.10:8090/base/a-b_c.d~e  ", &err));
  TEST_ASSERT_EQUAL_STRING("http://192.168.1.10:8090/base/a-b_c.d~e", s.serverUrl);
}

void test_stored_url_with_old_chars_still_loads() {
  // Settings written by older firmware may hold characters that input now rejects.
  gb::Settings s{};
  std::strcpy(s.serverUrl, "http://h/a'b");
  std::strcpy(s.updatePassword, "abcdefgh");
  gb::Settings back;
  TEST_ASSERT_TRUE(gb::parseSettings(gb::encodeSettings(s), &back));
  TEST_ASSERT_EQUAL_STRING("http://h/a'b", back.serverUrl);
  TEST_ASSERT_TRUE(gb::settingsComplete(back));  // the device keeps running with it
}

namespace {
bool parseHead(const char* h, gb::HttpHead* head) { return gb::parseHttpHead(h, strlen(h), head); }
}  // namespace

void test_http_head_parses_frame_reply() {
  const char* h = "HTTP/1.1 200 OK\r\ncontent-length: 1234\r\nETag: \"abc\"\r\n"
                  "X-Next-In:30\r\nx-local-time:  13:05:09 \r\ncontent-type: image/jpeg\r\n\r\n";
  gb::HttpHead head;
  TEST_ASSERT_TRUE(gb::parseHttpHead(h, strlen(h), &head));
  TEST_ASSERT_EQUAL(200, head.status);
  TEST_ASSERT_EQUAL(1234, head.contentLength);
  TEST_ASSERT_EQUAL_STRING("\"abc\"", head.etag);
  TEST_ASSERT_EQUAL(30, head.nextIn);
  TEST_ASSERT_EQUAL(13 * 3600 + 5 * 60 + 9, head.localSec);
}

void test_http_head_304_without_length() {
  gb::HttpHead head;
  TEST_ASSERT_TRUE(parseHead("HTTP/1.1 304 Not Modified\r\nX-Next-In: 30\r\n\r\n", &head));
  TEST_ASSERT_EQUAL(304, head.status);
  TEST_ASSERT_EQUAL(-1, head.contentLength);
  TEST_ASSERT_EQUAL_STRING("", head.etag);
  TEST_ASSERT_EQUAL(30, head.nextIn);
  TEST_ASSERT_EQUAL(-1, head.localSec);
  // Status line without reason phrase, no headers at all.
  TEST_ASSERT_TRUE(parseHead("HTTP/1.0 404\r\n\r\n", &head));
  TEST_ASSERT_EQUAL(404, head.status);
  TEST_ASSERT_EQUAL(-1, head.nextIn);
}

void test_http_head_chunked_has_no_length() {
  gb::HttpHead head;
  TEST_ASSERT_TRUE(parseHead("HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n", &head));
  TEST_ASSERT_EQUAL(-1, head.contentLength);
  // Content-Length together with chunked: the length does not describe the body.
  TEST_ASSERT_TRUE(parseHead(
      "HTTP/1.1 200 OK\r\nContent-Length: 100\r\ntransfer-encoding: Chunked\r\n\r\n", &head));
  TEST_ASSERT_EQUAL(-1, head.contentLength);
  TEST_ASSERT_TRUE(parseHead(
      "HTTP/1.1 200 OK\r\ntransfer-encoding: chunked\r\nContent-Length: 100\r\n\r\n", &head));
  TEST_ASSERT_EQUAL(-1, head.contentLength);
}

void test_http_head_rejects_garbage() {
  gb::HttpHead head;
  TEST_ASSERT_FALSE(parseHead("", &head));
  TEST_ASSERT_FALSE(parseHead("HTTP/1.1\r\n\r\n", &head));
  TEST_ASSERT_FALSE(parseHead("FOO 200\r\n\r\n", &head));
  TEST_ASSERT_FALSE(parseHead("HTTP/1.1 099 Low\r\n\r\n", &head));
  TEST_ASSERT_FALSE(parseHead("HTTP/1.1 600 High\r\n\r\n", &head));
  TEST_ASSERT_FALSE(parseHead("HTTP/1.1 20 OK\r\n\r\n", &head));
  TEST_ASSERT_FALSE(parseHead("HTTP/1.1 2000 OK\r\n\r\n", &head));
  TEST_ASSERT_FALSE(parseHead("HTTP/1.1 200 OK\r\nContent-Length: 5\r\n", &head));  // no blank line
  TEST_ASSERT_FALSE(parseHead("HTTP/1.1 200 OK\r\nX-A: b\nc\r\n\r\n", &head));      // bare LF
  TEST_ASSERT_FALSE(parseHead("HTTP/1.1 200 OK\r\nX-A: b\rc\r\n\r\n", &head));      // bare CR
  const char nul[] = "HTTP/1.1 200 OK\r\nX-Next-In: 3\0\r\n\r\n";
  TEST_ASSERT_FALSE(gb::parseHttpHead(nul, sizeof(nul) - 1, &head));
  // Data after the blank line is not part of the head.
  TEST_ASSERT_FALSE(parseHead("HTTP/1.1 200 OK\r\n\r\nxy", &head));
}

void test_http_head_bad_length_is_minus_one() {
  gb::HttpHead head;
  TEST_ASSERT_TRUE(parseHead("HTTP/1.1 200 OK\r\nContent-Length: 12x\r\n\r\n", &head));
  TEST_ASSERT_EQUAL(-1, head.contentLength);
  TEST_ASSERT_TRUE(parseHead("HTTP/1.1 200 OK\r\nContent-Length: -5\r\n\r\n", &head));
  TEST_ASSERT_EQUAL(-1, head.contentLength);
  TEST_ASSERT_TRUE(
      parseHead("HTTP/1.1 200 OK\r\nContent-Length: 12345678901234567890\r\n\r\n", &head));
  TEST_ASSERT_EQUAL(-1, head.contentLength);
  TEST_ASSERT_TRUE(parseHead("HTTP/1.1 200 OK\r\nContent-Length:\r\n\r\n", &head));
  TEST_ASSERT_EQUAL(-1, head.contentLength);
  // Two different lengths: neither can be trusted.
  TEST_ASSERT_TRUE(
      parseHead("HTTP/1.1 200 OK\r\nContent-Length: 10\r\nContent-Length: 20\r\n\r\n", &head));
  TEST_ASSERT_EQUAL(-1, head.contentLength);
  TEST_ASSERT_TRUE(parseHead("HTTP/1.1 200 OK\r\nContent-Length:\t 42\t\r\n\r\n", &head));
  TEST_ASSERT_EQUAL(42, head.contentLength);
}

void test_http_head_etag_and_values_follow_existing_rules() {
  gb::HttpHead head;
  // 40 characters do not fit kEtagCap (storeEtag rule): no ETag.
  TEST_ASSERT_TRUE(parseHead(
      "HTTP/1.1 200 OK\r\nETag: \"01234567890123456789012345678901234567\"\r\n\r\n", &head));
  TEST_ASSERT_EQUAL_STRING("", head.etag);
  TEST_ASSERT_TRUE(parseHead(  // 39 characters fit
      "HTTP/1.1 200 OK\r\nETag: \"0123456789012345678901234567890123456\"\r\n\r\n", &head));
  TEST_ASSERT_EQUAL(39, strlen(head.etag));
  TEST_ASSERT_TRUE(parseHead("HTTP/1.1 200 OK\r\nX-Next-In: soon\r\nX-Local-Time: 25:00:00\r\n"
                             "X-Next-In-Extra: 5\r\nNot a header line\r\n\r\n",
                             &head));
  TEST_ASSERT_EQUAL(-1, head.nextIn);
  TEST_ASSERT_EQUAL(-1, head.localSec);
}

bool anim(const char* v, gb::AnimSpec* a) { return gb::parseAnim(v, strlen(v), a); }

void test_anim_parses_the_example() {
  gb::AnimSpec a;
  TEST_ASSERT_TRUE(anim("1;0b0d12;232a38;64,67,85,15,r,ffb020,48;64,133,85,15,l,34D399,22", &a));
  TEST_ASSERT_EQUAL_UINT8(2, a.count);
  TEST_ASSERT_EQUAL_HEX16(gb::animRgb565(0x0b, 0x0d, 0x12), a.background);
  TEST_ASSERT_EQUAL_HEX16(gb::animRgb565(0x23, 0x2a, 0x38), a.trackColor);
  TEST_ASSERT_EQUAL_INT16(64, a.tracks[0].rect.x);
  TEST_ASSERT_EQUAL_INT16(67, a.tracks[0].rect.y);
  TEST_ASSERT_EQUAL_INT16(85, a.tracks[0].rect.w);
  TEST_ASSERT_EQUAL_INT16(15, a.tracks[0].rect.h);
  TEST_ASSERT_FALSE(a.tracks[0].left);
  TEST_ASSERT_EQUAL_UINT8(48, a.tracks[0].speed);
  TEST_ASSERT_TRUE(a.tracks[1].left);
  TEST_ASSERT_EQUAL_HEX16(gb::animRgb565(0x34, 0xd3, 0x99), a.tracks[1].color);
}

void test_anim_rejects_every_broken_limit() {
  const char* bad[] = {
      "",                                                    // empty
      "2;0b0d12;232a38;64,67,85,15,r,ffb020,48",             // other version
      "1;0b0d12;232a38",                                     // no track
      ("1;0b0d12;232a38;64,10,85,15,r,ffb020,48;64,50,85,15,r,ffb020,48;64,90,85,15,r,ffb020,48;"
       "64,130,85,15,r,ffb020,48;64,170,85,15,r,ffb020,48"),  // five tracks
      "1;0b0d1;232a38;64,67,85,15,r,ffb020,48",              // 5 hex digits
      "1;0b0d12;232a38;64,67,85,15,r,ffb02g,48",             // not hex
      "1;0b0d12;232a38;200,67,85,15,r,ffb020,48",            // right edge beyond 240
      "1;0b0d12;232a38;64,230,85,15,r,ffb020,48",            // bottom edge beyond 240
      "1;0b0d12;232a38;64,67,15,15,r,ffb020,48",             // too narrow
      "1;0b0d12;232a38;64,67,85,7,r,ffb020,48",              // too low
      "1;0b0d12;232a38;64,67,85,33,r,ffb020,48",             // too high
      "1;0b0d12;232a38;64,67,85,15,x,ffb020,48",             // direction
      "1;0b0d12;232a38;64,67,85,15,r,ffb020,0",              // speed 0
      "1;0b0d12;232a38;64,67,85,15,r,ffb020,201",            // speed too high
      "1;0b0d12;232a38;64,67,85,15,r,ffb020,48;64,75,85,15,r,ffb020,48",  // overlap
      "1;0b0d12;232a38;64,67,85,15,r,ffb020,48;",            // trailing separator
      "1;0b0d12;232a38;64,67,85,15,r,ffb020",                // field missing
      "1;0b0d12;232a38;64,67,85,15,r,ffb020,48,1",           // field too many
      "1;0b0d12;232a38; 64,67,85,15,r,ffb020,48",            // blank inside
      "1;0b0d12;232a38;-4,67,85,15,r,ffb020,48",             // sign
      "1;0b0d12;232a38;64,67,85,15,r,ffb020,4800000000",     // digits overflow
      "1;0b0d12;232a38;064,67,85,15,r,ffb020,48",            // leading zero
  };
  for (const char* v : bad) {
    gb::AnimSpec a;
    a.count = 3;
    TEST_ASSERT_FALSE_MESSAGE(anim(v, &a), v);
    TEST_ASSERT_EQUAL_UINT8_MESSAGE(0, a.count, v);
  }
}

void test_anim_touching_tracks_are_allowed() {
  gb::AnimSpec a;
  TEST_ASSERT_TRUE(anim("1;0b0d12;232a38;64,10,85,15,r,ffb020,48;64,25,85,15,l,ffb020,48", &a));
  TEST_ASSERT_EQUAL_UINT8(2, a.count);
  TEST_ASSERT_TRUE(anim("1;0b0d12;232a38;0,0,240,8,r,ffb020,1;0,232,16,8,l,ffb020,200", &a));
}

void test_anim_never_reads_beyond_len() {
  // A buffer without NUL: bytes after len would extend the value into something else valid.
  const char full[] = "1;0b0d12;232a38;64,67,85,15,r,ffb020,48";
  const size_t n = strlen(full);
  std::vector<char> exact(full, full + n);  // heap block of exactly n bytes
  gb::AnimSpec a;
  TEST_ASSERT_TRUE(gb::parseAnim(exact.data(), n, &a));
  for (size_t cut = 0; cut < n; ++cut) {  // every truncation stays inside its len
    std::vector<char> part(full, full + cut);
    if (cut == 0) part.reserve(1);
    gb::parseAnim(part.empty() ? "" : part.data(), cut, &a);
  }
  // "48" cut to "4" is still valid: proves the digits after len are not read.
  TEST_ASSERT_TRUE(gb::parseAnim(full, n - 1, &a));
  TEST_ASSERT_EQUAL_UINT8(4, a.tracks[0].speed);
}

void test_anim_value_length_limit() {
  std::string v = "1;0b0d12;232a38";
  const int ys[] = {10, 50, 90, 130};
  for (int y : ys) v += ";100," + std::to_string(y) + ",140,32,l,ffffff,200";
  TEST_ASSERT_TRUE(v.size() <= gb::kAnimMaxValueLen);
  gb::AnimSpec a;
  TEST_ASSERT_TRUE(anim(v.c_str(), &a));
  TEST_ASSERT_EQUAL_UINT8(4, a.count);
  v += ";100,170,140,32,l,ffffff,200;100,210,140,32,l,ffffff,200";
  TEST_ASSERT_TRUE(v.size() > gb::kAnimMaxValueLen);
  a.count = 3;
  TEST_ASSERT_FALSE(anim(v.c_str(), &a));
  TEST_ASSERT_EQUAL_UINT8(0, a.count);
  // exactly kAnimMaxValueLen + 1 characters of otherwise valid text up to the limit
  std::string pad(gb::kAnimMaxValueLen + 1, '1');
  TEST_ASSERT_FALSE(anim(pad.c_str(), &a));
}

void test_anim_same_geometry() {
  gb::AnimSpec a, b;
  const char* base = "1;0b0d12;232a38;64,67,85,15,r,ffb020,48;64,133,85,15,l,34d399,22";
  TEST_ASSERT_TRUE(anim(base, &a));
  TEST_ASSERT_TRUE(anim("1;0b0d12;232a38;64,67,85,15,l,010203,99;64,133,85,15,r,040506,5", &b));
  TEST_ASSERT_TRUE(gb::animSameGeometry(a, b));
  TEST_ASSERT_TRUE(anim("1;0b0d12;232a38;64,68,85,15,r,ffb020,48;64,133,85,15,l,34d399,22", &b));
  TEST_ASSERT_FALSE(gb::animSameGeometry(a, b));  // other y
  TEST_ASSERT_TRUE(anim("1;0b0d12;232a38;64,67,85,15,r,ffb020,48", &b));
  TEST_ASSERT_FALSE(gb::animSameGeometry(a, b));  // other track count
  TEST_ASSERT_TRUE(anim("1;0b0d22;232a38;64,67,85,15,r,ffb020,48;64,133,85,15,l,34d399,22", &b));
  TEST_ASSERT_FALSE(gb::animSameGeometry(a, b));  // other background
  TEST_ASSERT_TRUE(anim("1;0b0d12;232a48;64,67,85,15,r,ffb020,48;64,133,85,15,l,34d399,22", &b));
  TEST_ASSERT_FALSE(gb::animSameGeometry(a, b));  // other track color
}

// --- animation: arrow position, block clipping, track state rules ---

void test_anim_advance_right_left_and_wrap() {
  TEST_ASSERT_EQUAL_UINT16(5000, gb::animAdvance(0, 100, 50, false));
  TEST_ASSERT_EQUAL_UINT16(13000, gb::animAdvance(0, 100, 50, true));      // leftward from 0
  TEST_ASSERT_EQUAL_UINT16(2000, gb::animAdvance(17000, 100, 30, false));  // wraps at 18000
  TEST_ASSERT_EQUAL_UINT16(0, gb::animAdvance(0, 0, 200, true));
  TEST_ASSERT_EQUAL_UINT16(gb::animAdvance(0, 1000, 200, false),
                           gb::animAdvance(0, 4000000000u, 200, false));   // capped, no overflow
  for (uint32_t ms = 0; ms < 2000; ms += 37) {
    TEST_ASSERT_TRUE(gb::animAdvance(17999, ms, 200, false) < gb::kAnimPhaseMod);
    TEST_ASSERT_TRUE(gb::animAdvance(0, ms, 200, true) < gb::kAnimPhaseMod);
  }
}

void test_anim_advance_left_wrap_small_steps() {
  // 40 ms at 50 px/s is 2 px; leftward from 1 px lands on 17 px, not on a huge number.
  TEST_ASSERT_EQUAL_UINT16(17000, gb::animAdvance(1000, 40, 50, true));
  TEST_ASSERT_EQUAL_UINT16(1000, gb::animAdvance(17000, 40, 50, false));
  // a full second at 200 px/s is 200 px = 11 patterns + 2 px
  TEST_ASSERT_EQUAL_UINT16(2000, gb::animAdvance(0, 1000, 200, false));
  TEST_ASSERT_EQUAL_UINT16(16000, gb::animAdvance(0, 1000, 200, true));
  TEST_ASSERT_EQUAL_UINT16(16000, gb::animAdvance(0, 0xFFFFFFFFu, 200, true));
}

namespace {

gb::AnimRect rect(int x, int y, int w, int h) {
  return {static_cast<int16_t>(x), static_cast<int16_t>(y), static_cast<int16_t>(w),
          static_cast<int16_t>(h)};
}

bool inside(const gb::AnimRect& r, int x, int y) {
  return x >= r.x && x < r.x + r.w && y >= r.y && y < r.y + r.h;
}

// Every cell of block: inside a hole covered by no part, otherwise by exactly one.
void assertExactCover(const gb::AnimRect& block, const gb::AnimRect* holes, size_t nHoles,
                      const gb::AnimRect* parts, size_t n) {
  for (size_t i = 0; i < n; ++i) {  // parts stay inside the block
    TEST_ASSERT_TRUE(parts[i].w > 0 && parts[i].h > 0);
    TEST_ASSERT_TRUE(parts[i].x >= block.x && parts[i].x + parts[i].w <= block.x + block.w);
    TEST_ASSERT_TRUE(parts[i].y >= block.y && parts[i].y + parts[i].h <= block.y + block.h);
  }
  for (int y = block.y; y < block.y + block.h; ++y) {
    for (int x = block.x; x < block.x + block.w; ++x) {
      bool inHole = false;
      for (size_t k = 0; k < nHoles; ++k) inHole = inHole || inside(holes[k], x, y);
      int covered = 0;
      for (size_t i = 0; i < n; ++i) covered += inside(parts[i], x, y) ? 1 : 0;
      TEST_ASSERT_EQUAL_INT(inHole ? 0 : 1, covered);
    }
  }
}

int area(const gb::AnimRect* parts, size_t n) {
  int a = 0;
  for (size_t i = 0; i < n; ++i) a += parts[i].w * parts[i].h;
  return a;
}

}  // namespace

void test_anim_clip_no_hole() {
  gb::AnimRect out[gb::kAnimClipMax];
  const gb::AnimRect block = rect(16, 32, 16, 16);
  TEST_ASSERT_EQUAL(1, gb::animClip(block, nullptr, 0, out, gb::kAnimClipMax));
  TEST_ASSERT_EQUAL_INT16(16, out[0].x);
  TEST_ASSERT_EQUAL_INT16(32, out[0].y);
  TEST_ASSERT_EQUAL_INT16(16, out[0].w);
  TEST_ASSERT_EQUAL_INT16(16, out[0].h);
}

void test_anim_clip_hole_covers_block() {
  gb::AnimRect out[gb::kAnimClipMax];
  const gb::AnimRect hole = rect(60, 60, 30, 30);
  TEST_ASSERT_EQUAL(0, gb::animClip(rect(64, 64, 16, 16), &hole, 1, out, gb::kAnimClipMax));
  const gb::AnimRect same = rect(64, 64, 16, 16);
  TEST_ASSERT_EQUAL(0, gb::animClip(rect(64, 64, 16, 16), &same, 1, out, gb::kAnimClipMax));
}

void test_anim_clip_track_through_a_block() {
  gb::AnimRect out[gb::kAnimClipMax];
  const gb::AnimRect hole = rect(64, 67, 85, 15);
  const gb::AnimRect block = rect(64, 64, 16, 16);  // rows 64 to 79
  const size_t n = gb::animClip(block, &hole, 1, out, gb::kAnimClipMax);
  TEST_ASSERT_TRUE(n >= 1);
  TEST_ASSERT_EQUAL_INT(48, area(out, n));
  for (size_t i = 0; i < n; ++i) {
    TEST_ASSERT_TRUE(out[i].y >= 64 && out[i].y + out[i].h <= 67);
  }
  assertExactCover(block, &hole, 1, out, n);
  // the block left of the track is not touched
  const gb::AnimRect left = rect(48, 64, 16, 16);
  TEST_ASSERT_EQUAL(1, gb::animClip(left, &hole, 1, out, gb::kAnimClipMax));
  TEST_ASSERT_EQUAL_INT16(48, out[0].x);
  TEST_ASSERT_EQUAL_INT16(16, out[0].w);
  TEST_ASSERT_EQUAL_INT16(16, out[0].h);
}

void test_anim_clip_corner_holes() {
  gb::AnimRect out[gb::kAnimClipMax];
  const gb::AnimRect block = rect(32, 48, 16, 16);
  const gb::AnimRect holes[] = {rect(28, 44, 9, 9), rect(43, 44, 9, 9), rect(28, 59, 9, 9),
                                rect(43, 59, 9, 9)};
  const size_t n = gb::animClip(block, holes, 4, out, gb::kAnimClipMax);
  TEST_ASSERT_TRUE(n <= gb::kAnimClipMax);
  assertExactCover(block, holes, 4, out, n);
  TEST_ASSERT_EQUAL_INT(256 - 4 * 25, area(out, n));
  // a hole in the middle and two edge strips
  const gb::AnimRect mixed[] = {rect(37, 53, 6, 6), rect(32, 48, 16, 2), rect(46, 48, 2, 16)};
  const size_t m = gb::animClip(block, mixed, 3, out, gb::kAnimClipMax);
  TEST_ASSERT_TRUE(m <= gb::kAnimClipMax);
  assertExactCover(block, mixed, 3, out, m);
}

void test_anim_clip_hole_outside() {
  gb::AnimRect out[gb::kAnimClipMax];
  const gb::AnimRect block = rect(64, 64, 16, 16);
  const gb::AnimRect holes[] = {rect(80, 64, 10, 16), rect(64, 80, 16, 10), rect(0, 0, 64, 64),
                                rect(70, 70, 0, 5)};  // touching edges, empty hole
  TEST_ASSERT_EQUAL(1, gb::animClip(block, holes, 4, out, gb::kAnimClipMax));
  assertExactCover(block, nullptr, 0, out, 1);
}

void test_anim_clip_overflow_falls_back_to_whole_block() {
  // Too small an output: draw the whole block (arrows are redrawn next tick) instead of
  // leaving pixels of the new frame out.
  gb::AnimRect out[2];
  const gb::AnimRect block = rect(32, 48, 16, 16);
  const gb::AnimRect hole = rect(37, 53, 6, 6);  // middle hole needs four parts
  TEST_ASSERT_EQUAL(1, gb::animClip(block, &hole, 1, out, 2));
  TEST_ASSERT_EQUAL_INT16(16, out[0].w);
  TEST_ASSERT_EQUAL(0, gb::animClip(block, &hole, 1, out, 0));
}

namespace {

const uint16_t kBg = 0x0862;     // #0b0d12
const uint16_t kTrack = 0x2147;  // #232a38

gb::AnimTrack trackAt(int y, uint8_t speed, bool left, uint16_t color) {
  gb::AnimTrack t;
  t.rect = rect(64, y, 85, 15);
  t.left = left;
  t.color = color;
  t.speed = speed;
  return t;
}

gb::AnimSpec spec1(uint8_t speed = 48, bool left = false, uint16_t color = 0xFD84) {
  gb::AnimSpec s{};
  s.count = 1;
  s.background = kBg;
  s.trackColor = kTrack;
  s.tracks[0] = trackAt(67, speed, left, color);
  return s;
}

gb::AnimSpec spec2() {
  gb::AnimSpec s = spec1();
  s.count = 2;
  s.tracks[1] = trackAt(133, 22, true, 0x369B);
  return s;
}

gb::AnimSpec specMoved() {
  gb::AnimSpec s = spec1();
  s.tracks[0].rect.y = 133;
  return s;
}

gb::AnimSpec specEmpty() {
  gb::AnimSpec s{};
  s.count = 0;
  return s;
}

void start(gb::AnimState* st, const gb::AnimSpec& s, uint32_t now) {
  st->onHead200(s);
  st->onDecoded(now);
}

}  // namespace

void test_anim_base_colors_match_rgb565() {
  TEST_ASSERT_EQUAL_HEX16(gb::animRgb565(0x0b, 0x0d, 0x12), kBg);
  TEST_ASSERT_EQUAL_HEX16(gb::animRgb565(0x23, 0x2a, 0x38), kTrack);
}

void test_anim_new_track_starts_only_after_decode() {
  gb::AnimState st;
  TEST_ASSERT_EQUAL_UINT8(0, st.count());
  st.onHead200(spec1());
  TEST_ASSERT_EQUAL_UINT8(0, st.count());  // nothing to cut out while decoding
  TEST_ASSERT_FALSE(st.tick(500, true));
  st.onDecoded(1000);
  TEST_ASSERT_EQUAL_UINT8(1, st.count());
  TEST_ASSERT_EQUAL_INT16(67, st.track(0).rect.y);
  TEST_ASSERT_EQUAL_UINT8(0, st.offsetPx(0));
  TEST_ASSERT_EQUAL_HEX16(kBg, st.background());
  TEST_ASSERT_EQUAL_HEX16(kTrack, st.trackColor());
  // one kept, one new: only the kept one runs during decoding
  st.onHead200(spec2());
  TEST_ASSERT_EQUAL_UINT8(1, st.count());
  st.onDecoded(2000);
  TEST_ASSERT_EQUAL_UINT8(2, st.count());
  TEST_ASSERT_EQUAL_INT16(133, st.track(1).rect.y);
}

void test_anim_same_rect_keeps_running_with_new_values() {
  gb::AnimState st;
  start(&st, spec1(48, false, 0xFD84), 0);
  for (uint32_t t = 40; t <= 200; t += 40) TEST_ASSERT_TRUE(st.tick(t, true));
  const uint8_t before = st.offsetPx(0);
  TEST_ASSERT_EQUAL_UINT8(9, before);  // 200 ms at 48 px/s = 9.6 px
  st.onHead200(spec1(22, true, 0x369B));
  TEST_ASSERT_EQUAL_UINT8(1, st.count());
  TEST_ASSERT_EQUAL_UINT8(22, st.track(0).speed);
  TEST_ASSERT_TRUE(st.track(0).left);
  TEST_ASSERT_EQUAL_HEX16(0x369B, st.track(0).color);
  TEST_ASSERT_EQUAL_UINT8(before, st.offsetPx(0));
  st.onDecoded(220);
  TEST_ASSERT_EQUAL_UINT8(1, st.count());
  TEST_ASSERT_EQUAL_UINT8(before, st.offsetPx(0));  // decoding does not reset the phase
}

void test_anim_missing_track_stops_before_decode() {
  gb::AnimState st;
  start(&st, spec2(), 0);
  TEST_ASSERT_EQUAL_UINT8(2, st.count());
  st.onHead200(spec1());
  TEST_ASSERT_EQUAL_UINT8(1, st.count());
  TEST_ASSERT_EQUAL_INT16(67, st.track(0).rect.y);
  st.onDecoded(1000);
  TEST_ASSERT_EQUAL_UINT8(1, st.count());
  // the second one missing instead of the first
  start(&st, spec2(), 2000);
  st.onHead200(specMoved());
  TEST_ASSERT_EQUAL_UINT8(1, st.count());
  TEST_ASSERT_EQUAL_INT16(133, st.track(0).rect.y);
}

void test_anim_200_without_description_stops_all() {
  gb::AnimState st;
  start(&st, spec2(), 0);
  st.onHead200(specEmpty());
  TEST_ASSERT_EQUAL_UINT8(0, st.count());
  st.onDecoded(1000);
  TEST_ASSERT_EQUAL_UINT8(0, st.count());
  TEST_ASSERT_FALSE(st.tick(2000, true));
}

void test_anim_base_color_change_stops_all_until_decoded() {
  gb::AnimState st;
  start(&st, spec1(), 0);
  gb::AnimSpec other = spec1();
  other.background = 0xFFFF;
  st.onHead200(other);
  TEST_ASSERT_EQUAL_UINT8(0, st.count());
  st.onDecoded(1000);
  TEST_ASSERT_EQUAL_UINT8(1, st.count());
  TEST_ASSERT_EQUAL_HEX16(0xFFFF, st.background());
  gb::AnimSpec otherTrack = other;
  otherTrack.trackColor = 0x0000;
  st.onHead200(otherTrack);
  TEST_ASSERT_EQUAL_UINT8(0, st.count());
}

void test_anim_304_same_geometry_takes_values() {
  gb::AnimState st;
  start(&st, spec1(48, false, 0xFD84), 0);
  TEST_ASSERT_TRUE(st.onHead304(spec1(60, true, 0x369B)));
  TEST_ASSERT_EQUAL_UINT8(1, st.count());
  TEST_ASSERT_EQUAL_UINT8(60, st.track(0).speed);
  TEST_ASSERT_TRUE(st.track(0).left);
  TEST_ASSERT_EQUAL_HEX16(0x369B, st.track(0).color);
}

void test_anim_304_other_geometry_or_missing_stops_and_asks_refetch() {
  gb::AnimState st;
  start(&st, spec1(), 0);
  TEST_ASSERT_FALSE(st.onHead304(specMoved()));
  TEST_ASSERT_EQUAL_UINT8(0, st.count());
  start(&st, spec1(), 1000);
  TEST_ASSERT_FALSE(st.onHead304(specEmpty()));
  TEST_ASSERT_EQUAL_UINT8(0, st.count());
  start(&st, spec1(), 2000);
  TEST_ASSERT_FALSE(st.onHead304(spec2()));  // more tracks than run
  TEST_ASSERT_EQUAL_UINT8(0, st.count());
  start(&st, spec1(), 3000);
  gb::AnimSpec other = spec1();
  other.trackColor = 0x0000;
  TEST_ASSERT_FALSE(st.onHead304(other));  // other base color
  TEST_ASSERT_EQUAL_UINT8(0, st.count());
}

void test_anim_304_never_starts_tracks() {
  gb::AnimState st;
  TEST_ASSERT_TRUE(st.onHead304(spec1()));  // straight after boot
  TEST_ASSERT_EQUAL_UINT8(0, st.count());
  start(&st, spec1(), 0);
  st.stopAll();
  TEST_ASSERT_TRUE(st.onHead304(spec1()));
  TEST_ASSERT_EQUAL_UINT8(0, st.count());
  TEST_ASSERT_FALSE(st.tick(1000, true));
}

void test_anim_decode_failure_stops_all() {
  gb::AnimState st;
  start(&st, spec1(), 0);
  st.onHead200(spec1());
  TEST_ASSERT_EQUAL_UINT8(1, st.count());
  st.onDecodeFailed();
  TEST_ASSERT_EQUAL_UINT8(0, st.count());
  st.onDecoded(1000);  // a stray completion without a new head starts nothing
  TEST_ASSERT_EQUAL_UINT8(0, st.count());
}

void test_anim_failed_fetch_keeps_running() {
  // A failed fetch reports no event: the tracks run on as long as the frame stands.
  gb::AnimState st;
  start(&st, spec1(), 0);
  for (uint32_t t = 40; t <= 4000; t += 40) TEST_ASSERT_TRUE(st.tick(t, true));
  TEST_ASSERT_EQUAL_UINT8(1, st.count());
}

void test_anim_status_screen_stops_until_a_new_frame() {
  gb::AnimState st;
  start(&st, spec2(), 0);
  st.stopAll();
  TEST_ASSERT_EQUAL_UINT8(0, st.count());
  TEST_ASSERT_FALSE(st.tick(1000, true));
  // a status screen in the middle of a decode: that frame does not start tracks either
  st.onHead200(spec2());
  st.stopAll();
  st.onDecoded(2000);
  TEST_ASSERT_EQUAL_UINT8(0, st.count());
  // the next complete frame does
  start(&st, spec2(), 3000);
  TEST_ASSERT_EQUAL_UINT8(2, st.count());
}

void test_anim_tick_every_40_ms_and_wraparound() {
  gb::AnimState st;
  start(&st, spec1(50), 0xFFFFFFF0u);
  TEST_ASSERT_FALSE(st.tick(0xFFFFFFF0u + 39, true));
  TEST_ASSERT_TRUE(st.tick(0x00000018u, true));  // 40 ms later, across the overflow
  TEST_ASSERT_EQUAL_UINT8(2, st.offsetPx(0));
  TEST_ASSERT_FALSE(st.tick(0x00000018u + 39, true));
  TEST_ASSERT_TRUE(st.tick(0x00000018u + 40, true));
  TEST_ASSERT_EQUAL_UINT8(4, st.offsetPx(0));
}

void test_anim_left_track_offset_wraps_down() {
  gb::AnimState st;
  start(&st, spec1(50, true), 0);
  TEST_ASSERT_TRUE(st.tick(40, true));
  TEST_ASSERT_EQUAL_UINT8(16, st.offsetPx(0));  // 0 - 2 px wraps to 16
  for (uint32_t t = 80; t <= 2000; t += 40) {
    TEST_ASSERT_TRUE(st.tick(t, true));
    TEST_ASSERT_TRUE(st.offsetPx(0) < gb::kAnimArrowSpacing);
  }
}

void test_anim_speed_change_does_not_jump() {
  gb::AnimState st;
  start(&st, spec1(50), 0);
  for (uint32_t t = 40; t <= 400; t += 40) TEST_ASSERT_TRUE(st.tick(t, true));
  TEST_ASSERT_EQUAL_UINT8(2, st.offsetPx(0));  // 20 px
  TEST_ASSERT_TRUE(st.onHead304(spec1(100)));
  TEST_ASSERT_EQUAL_UINT8(2, st.offsetPx(0));
  TEST_ASSERT_TRUE(st.tick(440, true));
  TEST_ASSERT_EQUAL_UINT8(6, st.offsetPx(0));
}

void test_anim_invisible_keeps_state_and_draws_nothing() {
  gb::AnimState st;
  start(&st, spec1(), 0);
  TEST_ASSERT_TRUE(st.tick(40, true));
  TEST_ASSERT_TRUE(st.tick(80, true));
  TEST_ASSERT_FALSE(st.tick(500, false));
  TEST_ASSERT_FALSE(st.tick(5000, false));
  TEST_ASSERT_EQUAL_UINT8(1, st.count());
  TEST_ASSERT_TRUE(st.tick(5040, true));
  TEST_ASSERT_TRUE(st.offsetPx(0) < gb::kAnimArrowSpacing);
  const gb::AnimStats s = st.stats(5040);
  TEST_ASSERT_EQUAL_UINT32(0, s.gapsOver100);  // the dark time is no gap
  TEST_ASSERT_EQUAL_UINT32(0, s.gapsOver250);
  TEST_ASSERT_EQUAL_UINT8(1, s.tracks);
}

void test_anim_gap_counters() {
  gb::AnimState st;
  start(&st, spec1(), 0);
  uint32_t t = 0;
  const uint32_t steps[] = {40, 40, 120, 300, 40};
  for (uint32_t d : steps) {
    t += d;
    TEST_ASSERT_TRUE(st.tick(t, true));
  }
  gb::AnimStats s = st.stats(t);
  TEST_ASSERT_EQUAL_UINT32(2, s.gapsOver100);
  TEST_ASSERT_EQUAL_UINT32(1, s.gapsOver250);
  TEST_ASSERT_EQUAL_UINT32(0, s.runS);  // 540 ms
  for (t += 40; t <= 3000; t += 40) TEST_ASSERT_TRUE(st.tick(t, true));
  TEST_ASSERT_FALSE(st.tick(3000, true));  // not due (last frame 2980), but counts run time
  s = st.stats(3000);
  TEST_ASSERT_EQUAL_UINT32(3, s.runS);
  st.stopAll();
  s = st.stats(10000);
  TEST_ASSERT_EQUAL_UINT8(0, s.tracks);
  TEST_ASSERT_EQUAL_UINT32(3, s.runS);  // stopped time does not count
  start(&st, spec1(), 10000);
  TEST_ASSERT_TRUE(st.tick(10040, true));  // the pause before is no gap
  for (t = 10080; t <= 12000; t += 40) TEST_ASSERT_TRUE(st.tick(t, true));
  s = st.stats(12000);
  TEST_ASSERT_EQUAL_UINT32(2, s.gapsOver100);
  TEST_ASSERT_EQUAL_UINT32(1, s.gapsOver250);
  TEST_ASSERT_EQUAL_UINT32(5, s.runS);
  TEST_ASSERT_EQUAL_UINT32(5, st.stats(12900).runS);  // counted up to now, not to the last tick
  TEST_ASSERT_EQUAL_UINT32(6, st.stats(13000).runS);
}

void test_anim_track_index_out_of_range_is_safe() {
  gb::AnimState st;
  start(&st, spec1(), 0);
  (void)st.track(200);
  TEST_ASSERT_TRUE(st.offsetPx(200) < gb::kAnimArrowSpacing);
}

void test_anim_same_geometry_garbage_count() {
  gb::AnimSpec a = spec1();
  gb::AnimSpec b = spec1();
  a.count = 250;  // must not read beyond tracks[]
  b.count = 250;
  for (size_t i = 1; i < gb::kAnimMaxTracks; ++i) {
    a.tracks[i] = trackAt(static_cast<int>(20 * i), 1, false, 0);
    b.tracks[i] = a.tracks[i];
  }
  TEST_ASSERT_TRUE(gb::animSameGeometry(a, b));
}

void test_http_head_carries_x_anim() {
  gb::HttpHead head;
  TEST_ASSERT_TRUE(parseHead("HTTP/1.1 304 Not Modified\r\nETag: \"a\"\r\n"
                             "X-Anim: 1;0b0d12;232a38;64,67,85,15,r,ffb020,48\r\n\r\n", &head));
  TEST_ASSERT_EQUAL_UINT8(1, head.anim.count);
  TEST_ASSERT_TRUE(parseHead("HTTP/1.1 200 OK\r\nContent-Length: 5\r\n\r\n", &head));
  TEST_ASSERT_EQUAL_UINT8(0, head.anim.count);   // absent: reset, nothing left over
  TEST_ASSERT_TRUE(parseHead("HTTP/1.1 200 OK\r\nX-Anim: 9;x\r\nContent-Length: 5\r\n\r\n", &head));
  TEST_ASSERT_EQUAL_UINT8(0, head.anim.count);   // invalid: the frame itself still counts
  TEST_ASSERT_EQUAL(5, head.contentLength);
}

void test_http_head_duplicate_x_anim_is_invalid() {
  gb::HttpHead head;
  TEST_ASSERT_TRUE(parseHead("HTTP/1.1 200 OK\r\n"
                             "X-Anim: 1;0b0d12;232a38;64,67,85,15,r,ffb020,48\r\n"
                             "X-Anim: 1;0b0d12;232a38;64,67,85,15,r,ffb020,48\r\n\r\n", &head));
  TEST_ASSERT_EQUAL_UINT8(0, head.anim.count);
  // an invalid first one followed by a valid one stays invalid
  TEST_ASSERT_TRUE(parseHead("HTTP/1.1 200 OK\r\nX-Anim: 9\r\n"
                             "X-Anim: 1;0b0d12;232a38;64,67,85,15,r,ffb020,48\r\n\r\n", &head));
  TEST_ASSERT_EQUAL_UINT8(0, head.anim.count);
}

void test_http_head_x_anim_name_case_blanks_and_length() {
  gb::HttpHead head;
  TEST_ASSERT_TRUE(parseHead("HTTP/1.1 200 OK\r\nx-anim:  1;0b0d12;232a38;64,67,85,15,r,ffb020,48  \r\n\r\n",
                             &head));
  TEST_ASSERT_EQUAL_UINT8(1, head.anim.count);
  std::string v = "1;0b0d12;232a38";
  const int ys[] = {10, 50, 90, 130};
  for (int y : ys) v += ";100," + std::to_string(y) + ",140,32,l,ffffff,200";
  const std::string ok = "HTTP/1.1 200 OK\r\nX-Anim: " + v + "\r\n\r\n";
  TEST_ASSERT_TRUE(parseHead(ok.c_str(), &head));
  TEST_ASSERT_EQUAL_UINT8(4, head.anim.count);
  v += ";100,170,140,32,l,ffffff,200;100,210,140,32,l,ffffff,200";
  const std::string longer = "HTTP/1.1 200 OK\r\nX-Anim: " + v + "\r\n\r\n";
  TEST_ASSERT_TRUE(parseHead(longer.c_str(), &head));
  TEST_ASSERT_EQUAL_UINT8(0, head.anim.count);
}

void test_server_target() {
  gb::ServerTarget t;
  TEST_ASSERT_TRUE(gb::parseServerTarget("http://192.168.1.10:8090", &t));
  TEST_ASSERT_EQUAL_STRING("192.168.1.10", t.host);
  TEST_ASSERT_EQUAL(8090, t.port);
  TEST_ASSERT_EQUAL_STRING("", t.path);
  TEST_ASSERT_EQUAL_STRING("", t.userinfo);

  TEST_ASSERT_TRUE(gb::parseServerTarget("http://box", &t));
  TEST_ASSERT_EQUAL_STRING("box", t.host);
  TEST_ASSERT_EQUAL(80, t.port);
  TEST_ASSERT_EQUAL_STRING("", t.path);

  TEST_ASSERT_TRUE(gb::parseServerTarget("http://box/base/x", &t));
  TEST_ASSERT_EQUAL_STRING("box", t.host);
  TEST_ASSERT_EQUAL_STRING("/base/x", t.path);

  TEST_ASSERT_TRUE(gb::parseServerTarget("http://box:65535/", &t));
  TEST_ASSERT_EQUAL(65535, t.port);
  TEST_ASSERT_EQUAL_STRING("", t.path);

  TEST_ASSERT_FALSE(gb::parseServerTarget("http://box:0", &t));
  TEST_ASSERT_FALSE(gb::parseServerTarget("http://box:70000", &t));
  TEST_ASSERT_FALSE(gb::parseServerTarget("http://box:", &t));
  TEST_ASSERT_FALSE(gb::parseServerTarget("http://box:80a", &t));
  TEST_ASSERT_FALSE(gb::parseServerTarget("http://", &t));
  TEST_ASSERT_FALSE(gb::parseServerTarget("https://box", &t));
  TEST_ASSERT_FALSE(gb::parseServerTarget("box", &t));
  TEST_ASSERT_FALSE(gb::parseServerTarget("http://box?k=v", &t));        // query
  TEST_ASSERT_FALSE(gb::parseServerTarget("http://box/base?k=v", &t));   // query
  const std::string longHost = "http://" + std::string(96, 'h');  // host[96] holds 95
  TEST_ASSERT_FALSE(gb::parseServerTarget(longHost.c_str(), &t));
  const std::string longPath = "http://box/" + std::string(130, 'p');
  TEST_ASSERT_FALSE(gb::parseServerTarget(longPath.c_str(), &t));
}

void test_server_target_userinfo() {
  // Kept for Basic auth: HTTPClient sent the raw text before '@' as credentials.
  gb::ServerTarget t;
  TEST_ASSERT_TRUE(gb::parseServerTarget("http://u:p@box", &t));
  TEST_ASSERT_EQUAL_STRING("u:p", t.userinfo);
  TEST_ASSERT_EQUAL_STRING("box", t.host);
  TEST_ASSERT_EQUAL(80, t.port);
  TEST_ASSERT_EQUAL_STRING("", t.path);

  TEST_ASSERT_TRUE(gb::parseServerTarget("http://u@box:8090/base", &t));
  TEST_ASSERT_EQUAL_STRING("u", t.userinfo);
  TEST_ASSERT_EQUAL_STRING("box", t.host);
  TEST_ASSERT_EQUAL(8090, t.port);
  TEST_ASSERT_EQUAL_STRING("/base", t.path);

  // '@' in the path is not userinfo.
  TEST_ASSERT_TRUE(gb::parseServerTarget("http://box/a@b", &t));
  TEST_ASSERT_EQUAL_STRING("", t.userinfo);
  TEST_ASSERT_EQUAL_STRING("box", t.host);
  TEST_ASSERT_EQUAL_STRING("/a@b", t.path);

  // 95 characters fit userinfo[96], 96 do not.
  const std::string fits = "http://" + std::string(95, 'u') + "@box";
  TEST_ASSERT_TRUE(gb::parseServerTarget(fits.c_str(), &t));
  TEST_ASSERT_EQUAL(95, strlen(t.userinfo));
  const std::string tooLong = "http://" + std::string(96, 'u') + "@box";
  TEST_ASSERT_FALSE(gb::parseServerTarget(tooLong.c_str(), &t));

  // HTTPClient split at the first '@'; a second one would end up in the host name.
  TEST_ASSERT_FALSE(gb::parseServerTarget("http://u:p@ss@box", &t));
  TEST_ASSERT_FALSE(gb::parseServerTarget("http://u:p@", &t));  // empty host
}

void test_deadline_wraparound() {
  TEST_ASSERT_FALSE(gb::deadlinePassed(0xFFFFFF00u, 0x00000010u, 8000));
  TEST_ASSERT_TRUE(gb::deadlinePassed(0xFFFFFF00u, 0x00002000u, 8000));
  TEST_ASSERT_FALSE(gb::deadlinePassed(1000, 8999, 8000));
  TEST_ASSERT_TRUE(gb::deadlinePassed(1000, 9000, 8000));
}

void test_frame_error_text_new_codes() {
  char b[gb::kErrorTextCap];
  gb::frameErrorText(gb::kErrHeadTooLarge, b, sizeof(b));
  TEST_ASSERT_EQUAL_STRING("reply too large", b);
  gb::frameErrorText(gb::kErrHeadTimeout, b, sizeof(b));
  TEST_ASSERT_EQUAL_STRING("server too slow", b);
  gb::frameErrorText(gb::kErrHeadMalformed, b, sizeof(b));
  TEST_ASSERT_EQUAL_STRING("bad reply", b);
}

void test_auth_throttle_locks_after_five() {
  gb::AuthThrottle t;
  for (int i = 0; i < 4; ++i) t.onFailure(1000);
  TEST_ASSERT_FALSE(t.locked(1000));
  t.onFailure(1000);
  TEST_ASSERT_TRUE(t.locked(1000));
  TEST_ASSERT_EQUAL(30, t.retryAfterS(1000));
  TEST_ASSERT_TRUE(t.locked(30999));
  TEST_ASSERT_FALSE(t.locked(31000));
  t.onFailure(31000);                    // after a lock one more failure locks again
  TEST_ASSERT_TRUE(t.locked(31000));
}

void test_auth_throttle_success_resets() {
  gb::AuthThrottle t;
  for (int i = 0; i < 4; ++i) t.onFailure(1000);
  t.onSuccess();
  for (int i = 0; i < 4; ++i) t.onFailure(2000);
  TEST_ASSERT_FALSE(t.locked(2000));
  TEST_ASSERT_EQUAL(0, t.retryAfterS(2000));
}

void test_auth_throttle_wraparound() {
  gb::AuthThrottle t;
  for (int i = 0; i < 5; ++i) t.onFailure(0xFFFFFF00u);
  TEST_ASSERT_TRUE(t.locked(0x10));
  TEST_ASSERT_EQUAL(30, t.retryAfterS(0x10));  // 30000 - 0x110 ms, rounded up
  TEST_ASSERT_FALSE(t.locked(0x8000));
}

void test_auth_throttle_retry_after_rounds_up() {
  gb::AuthThrottle t;
  for (int i = 0; i < 5; ++i) t.onFailure(0);
  TEST_ASSERT_EQUAL(1, t.retryAfterS(29999));
  TEST_ASSERT_EQUAL(29, t.retryAfterS(1000));
  TEST_ASSERT_EQUAL(0, t.retryAfterS(30000));
}

void test_host_allowed() {
  TEST_ASSERT_TRUE(gb::hostAllowed("192.168.1.50", "ESP-AB12CD"));
  TEST_ASSERT_TRUE(gb::hostAllowed("192.168.1.50:80", "ESP-AB12CD"));
  TEST_ASSERT_TRUE(gb::hostAllowed("esp-ab12cd", "ESP-AB12CD"));
  TEST_ASSERT_TRUE(gb::hostAllowed("ESP-AB12CD.local", "ESP-AB12CD"));
  TEST_ASSERT_FALSE(gb::hostAllowed("evil.example", "ESP-AB12CD"));
  TEST_ASSERT_FALSE(gb::hostAllowed("192.168.1.50.evil.example", "ESP-AB12CD"));
  TEST_ASSERT_FALSE(gb::hostAllowed("ESP-AB12CD.evil.example", "ESP-AB12CD"));
  TEST_ASSERT_FALSE(gb::hostAllowed("999.1.1.1", "ESP-AB12CD"));
  TEST_ASSERT_FALSE(gb::hostAllowed("", "ESP-AB12CD"));
  TEST_ASSERT_TRUE(gb::hostAllowed("192.168.1.50", ""));    // IPv4 needs no device name
  TEST_ASSERT_FALSE(gb::hostAllowed(".local", ""));
}

void test_host_allowed_edge_cases() {
  TEST_ASSERT_TRUE(gb::hostAllowed("192.168.4.1", "ESP-AB12CD"));  // safe-mode access point
  TEST_ASSERT_TRUE(gb::hostAllowed("esp-ab12cd.local:8080", "ESP-AB12CD"));
  TEST_ASSERT_FALSE(gb::hostAllowed("192.168.1", "ESP-AB12CD"));
  TEST_ASSERT_FALSE(gb::hostAllowed("192.168.1.50.", "ESP-AB12CD"));
  TEST_ASSERT_FALSE(gb::hostAllowed("192.168..50", "ESP-AB12CD"));
  TEST_ASSERT_FALSE(gb::hostAllowed("1.2.3.4.5", "ESP-AB12CD"));
  TEST_ASSERT_FALSE(gb::hostAllowed("0x7f.0.0.1", "ESP-AB12CD"));
  TEST_ASSERT_FALSE(gb::hostAllowed("1234.1.1.1", "ESP-AB12CD"));
  TEST_ASSERT_FALSE(gb::hostAllowed("192.168.1.50:", "ESP-AB12CD"));
  TEST_ASSERT_FALSE(gb::hostAllowed("192.168.1.50:80x", "ESP-AB12CD"));
  TEST_ASSERT_FALSE(gb::hostAllowed(":80", "ESP-AB12CD"));
  TEST_ASSERT_FALSE(gb::hostAllowed("ESP-AB12CD.lan", "ESP-AB12CD"));
  TEST_ASSERT_FALSE(gb::hostAllowed("xESP-AB12CD", "ESP-AB12CD"));
  TEST_ASSERT_FALSE(gb::hostAllowed("", ""));
}

void test_server_target_long_host() {
  // A stored URL holds up to 95 characters; 0.6.1 (HTTPClient) took hosts of that length.
  gb::ServerTarget t;
  const std::string host80(80, 'h');
  const std::string url80 = "http://" + host80 + ":8090";
  TEST_ASSERT_TRUE(gb::parseServerTarget(url80.c_str(), &t));
  TEST_ASSERT_EQUAL_STRING(host80.c_str(), t.host);
  TEST_ASSERT_EQUAL(8090, t.port);
  const std::string url95 = "http://" + std::string(95, 'h');
  TEST_ASSERT_TRUE(gb::parseServerTarget(url95.c_str(), &t));
  TEST_ASSERT_EQUAL(95, strlen(t.host));
}

void test_server_target_question_mark_only_in_userinfo() {
  // HTTPClient sent "u:p?x" as Basic auth; a '?' after the '@' is still refused.
  gb::ServerTarget t;
  TEST_ASSERT_TRUE(gb::parseServerTarget("http://u:p?x@box", &t));
  TEST_ASSERT_EQUAL_STRING("u:p?x", t.userinfo);
  TEST_ASSERT_EQUAL_STRING("box", t.host);
  TEST_ASSERT_EQUAL(80, t.port);
  TEST_ASSERT_EQUAL_STRING("", t.path);
  TEST_ASSERT_FALSE(gb::parseServerTarget("http://box/a?b=1", &t));
  TEST_ASSERT_FALSE(gb::parseServerTarget("http://box?x", &t));
  TEST_ASSERT_FALSE(gb::parseServerTarget("http://u:p@box?x", &t));
  TEST_ASSERT_FALSE(gb::parseServerTarget("http://u:p@box:80?x", &t));
  TEST_ASSERT_FALSE(gb::parseServerTarget("http://u?@box/a?b", &t));
}

void test_display_server_url_hides_userinfo() {
  char b[96];
  gb::displayServerUrl("http://user:pass@box:8090/base", b, sizeof(b));
  TEST_ASSERT_EQUAL_STRING("http://box:8090/base", b);
  gb::displayServerUrl("http://box:8090/base", b, sizeof(b));
  TEST_ASSERT_EQUAL_STRING("http://box:8090/base", b);
  gb::displayServerUrl("http://u:p?x@box", b, sizeof(b));
  TEST_ASSERT_EQUAL_STRING("http://box", b);
  // The first '/' after the scheme ends the authority (as in HTTPClient): this '@' is path.
  gb::displayServerUrl("http://u:p/x@box", b, sizeof(b));
  TEST_ASSERT_EQUAL_STRING("http://u:p/x@box", b);
  gb::displayServerUrl("http://box/a@b", b, sizeof(b));
  TEST_ASSERT_EQUAL_STRING("http://box/a@b", b);
  gb::displayServerUrl("http://u:p@ss@box/x", b, sizeof(b));  // nothing of the secret shown
  TEST_ASSERT_EQUAL_STRING("http://box/x", b);
  gb::displayServerUrl("", b, sizeof(b));
  TEST_ASSERT_EQUAL_STRING("", b);
}

void test_display_server_url_truncates_safely() {
  char b[12];
  std::memset(b, 'Z', sizeof(b));
  gb::displayServerUrl("http://user:pass@box:8090/base", b, 12);
  TEST_ASSERT_EQUAL_STRING("http://box:", b);  // 11 characters and the NUL
  char one[1] = {'Z'};
  gb::displayServerUrl("http://u:p@box", one, sizeof(one));
  TEST_ASSERT_EQUAL_CHAR('\0', one[0]);
  char guard[4] = {'Z', 'Z', 'Z', 'Z'};
  gb::displayServerUrl("http://u:p@box", guard, 0);  // cap 0: nothing written
  TEST_ASSERT_EQUAL_CHAR('Z', guard[0]);
  char five[6];
  gb::displayServerUrl("http://u:p@box", five, sizeof(five));
  TEST_ASSERT_EQUAL_STRING("http:", five);  // never part of the userinfo
}

void test_server_url_resubmitted_legacy_value_accepted() {
  // A stored URL from older firmware may hold a character input now rejects; saving other
  // settings resubmits it unchanged and must not fail.
  gb::Settings s{};
  std::strcpy(s.serverUrl, "http://h/a'b");
  std::string err;
  TEST_ASSERT_TRUE(gb::applyServerUrl(s, "http://h/a'b", &err));
  TEST_ASSERT_EQUAL_STRING("http://h/a'b", s.serverUrl);
  TEST_ASSERT_TRUE(gb::applyServerUrl(s, "  http://h/a'b  ", &err));  // trimmed first
  TEST_ASSERT_EQUAL_STRING("http://h/a'b", s.serverUrl);
  TEST_ASSERT_FALSE(gb::applyServerUrl(s, "http://h/a'c", &err));
  TEST_ASSERT_EQUAL_STRING("invalid_chars", err.c_str());
  TEST_ASSERT_EQUAL_STRING("http://h/a'b", s.serverUrl);

  gb::SettingsPatch p;
  p.serverUrl = "http://h/a'b";
  p.brightness = "40";
  std::string field;
  TEST_ASSERT_TRUE(gb::applySettingsPatch(s, p, &field, &err));
  TEST_ASSERT_EQUAL(40, s.brightness);
  TEST_ASSERT_EQUAL_STRING("http://h/a'b", s.serverUrl);
}

namespace {
int gCredentialChecks = 0;
bool credsGood() {
  ++gCredentialChecks;
  return true;
}
bool credsBad() {
  ++gCredentialChecks;
  return false;
}
gb::Access decide(gb::AuthThrottle& t, bool host, bool origin, bool header, bool (*creds)(),
                  uint32_t now = 1000) {
  return gb::decideAccess(host, origin, header, creds, t, now);
}
}  // namespace

void test_access_order_host_origin_lock_credentials() {
  gb::AuthThrottle t;
  for (int i = 0; i < 5; ++i) t.onFailure(1000);  // locked
  gCredentialChecks = 0;
  TEST_ASSERT_EQUAL(gb::Access::HostDenied, decide(t, false, false, true, credsBad));
  TEST_ASSERT_EQUAL(gb::Access::OriginDenied, decide(t, true, false, true, credsBad));
  TEST_ASSERT_EQUAL(gb::Access::Locked, decide(t, true, true, true, credsBad));
  TEST_ASSERT_EQUAL(gb::Access::Locked, decide(t, true, true, false, credsBad));
  TEST_ASSERT_EQUAL(0, gCredentialChecks);  // nothing before credentials looks at them

  gb::AuthThrottle fresh;
  TEST_ASSERT_EQUAL(gb::Access::HostDenied, decide(fresh, false, true, true, credsGood));
  TEST_ASSERT_EQUAL(gb::Access::OriginDenied, decide(fresh, true, false, true, credsGood));
  TEST_ASSERT_EQUAL(gb::Access::NeedAuth, decide(fresh, true, true, false, credsGood));
  TEST_ASSERT_EQUAL(0, gCredentialChecks);
  TEST_ASSERT_EQUAL(gb::Access::Granted, decide(fresh, true, true, true, credsGood));
  TEST_ASSERT_EQUAL(1, gCredentialChecks);
}

void test_access_missing_header_does_not_count() {
  gb::AuthThrottle t;
  for (int i = 0; i < 20; ++i) {
    TEST_ASSERT_EQUAL(gb::Access::NeedAuth, decide(t, true, true, false, credsBad));
  }
  TEST_ASSERT_FALSE(t.locked(1000));
  // Refused host/origin attempts do not count either.
  for (int i = 0; i < 20; ++i) decide(t, false, true, true, credsBad);
  for (int i = 0; i < 20; ++i) decide(t, true, false, true, credsBad);
  TEST_ASSERT_FALSE(t.locked(1000));
}

void test_access_wrong_password_counts_and_locks() {
  gb::AuthThrottle t;
  for (int i = 0; i < 4; ++i) {
    TEST_ASSERT_EQUAL(gb::Access::WrongPassword, decide(t, true, true, true, credsBad));
  }
  TEST_ASSERT_FALSE(t.locked(1000));
  TEST_ASSERT_EQUAL(gb::Access::WrongPassword, decide(t, true, true, true, credsBad));
  TEST_ASSERT_TRUE(t.locked(1000));
  gCredentialChecks = 0;
  // A correct password during the lock is refused and not even checked.
  TEST_ASSERT_EQUAL(gb::Access::Locked, decide(t, true, true, true, credsGood, 30999));
  TEST_ASSERT_EQUAL(0, gCredentialChecks);
  TEST_ASSERT_EQUAL(gb::Access::Granted, decide(t, true, true, true, credsGood, 31000));
}

void test_access_success_resets_counter() {
  gb::AuthThrottle t;
  for (int i = 0; i < 4; ++i) decide(t, true, true, true, credsBad);
  TEST_ASSERT_EQUAL(gb::Access::Granted, decide(t, true, true, true, credsGood));
  for (int i = 0; i < 4; ++i) {
    TEST_ASSERT_EQUAL(gb::Access::WrongPassword, decide(t, true, true, true, credsBad));
  }
  TEST_ASSERT_FALSE(t.locked(1000));
}

int main() {
  UNITY_BEGIN();
  RUN_TEST(test_boot_fresh_magic);
  RUN_TEST(test_boot_third_failure_enters_safe);
  RUN_TEST(test_reset_kind_mapping);
  RUN_TEST(test_boot_fresh_start_resets_counter);
  RUN_TEST(test_boot_counted_reset_keeps_counting);
  RUN_TEST(test_boot_healthy_resets);
  RUN_TEST(test_is_healthy_needs_all_three);
  RUN_TEST(test_next_delay_success_clamped);
  RUN_TEST(test_next_delay_backoff);
  RUN_TEST(test_show_offline_at_120s);
  RUN_TEST(test_accept_frame_length);
  RUN_TEST(test_normalize_server_url_adds_scheme_and_strips_slash);
  RUN_TEST(test_normalize_server_url_rejects_https);
  RUN_TEST(test_normalize_server_url_rejects_empty_host);
  RUN_TEST(test_valid_password);
  RUN_TEST(test_md5_hex);
  RUN_TEST(test_image_magic);
  RUN_TEST(test_settings_roundtrip_with_escapes);
  RUN_TEST(test_settings_parse_tolerates_whitespace_unknown_keys_and_missing_brightness);
  RUN_TEST(test_settings_parse_rejects_corrupt_input);
  RUN_TEST(test_settings_parse_clamps_brightness);
  RUN_TEST(test_settings_defaults_incomplete);
  RUN_TEST(test_apply_server_url_errors_leave_value);
  RUN_TEST(test_apply_password_rules);
  RUN_TEST(test_prefers_german);
  RUN_TEST(test_html_escape);
  RUN_TEST(test_origin_allowed);
  RUN_TEST(test_ota_begin_size);
  RUN_TEST(test_ota_flow_success_commits_at_file_end);
  RUN_TEST(test_ota_flow_abort_after_commit_keeps_commit_and_success);
  RUN_TEST(test_ota_flow_second_part_after_commit_never_touches_flash);
  RUN_TEST(test_ota_flow_later_requests_refused_after_commit);
  RUN_TEST(test_ota_flow_unauthorized_never_writes);
  RUN_TEST(test_ota_flow_start_checks_reject_before_flash);
  RUN_TEST(test_ota_flow_not_an_image_rejected_on_first_chunk);
  RUN_TEST(test_ota_flow_md5_mismatch_and_errors_discard);
  RUN_TEST(test_ota_flow_empty_and_second_part_after_failure);
  RUN_TEST(test_health_latch_marks_exactly_once);
  RUN_TEST(test_safe_mode_portal_only_without_valid_password);
  RUN_TEST(test_safe_mode_ap_fallback_after_connect_timeout);
  RUN_TEST(test_parse_next_in);
  RUN_TEST(test_store_etag);
  RUN_TEST(test_frame_error_text);
  RUN_TEST(test_poller_success_uses_next_in_and_resets_failures);
  RUN_TEST(test_poller_offline_after_120s_since_boot_or_last_success);
  RUN_TEST(test_poller_offline_redrawn_after_partial_frames);
  RUN_TEST(test_poller_millis_wraparound);
  RUN_TEST(test_poller_decode_error_clears_etag);
  RUN_TEST(test_poller_failure_count_saturates);
  RUN_TEST(test_parse_local_time);
  RUN_TEST(test_parse_format_hhmm);
  RUN_TEST(test_night_window);
  RUN_TEST(test_local_clock);
  RUN_TEST(test_effective_brightness);
  RUN_TEST(test_backlight_duty_is_perceptual);
  RUN_TEST(test_preview_inactive_by_default);
  RUN_TEST(test_preview_holds_3s_then_expires);
  RUN_TEST(test_preview_refresh_extends);
  RUN_TEST(test_preview_millis_wraparound);
  RUN_TEST(test_preview_expires_and_saved_value_applies);
  RUN_TEST(test_preview_clamps);
  RUN_TEST(test_settings_patch_single_field);
  RUN_TEST(test_settings_patch_night_start_only);
  RUN_TEST(test_settings_patch_night_off);
  RUN_TEST(test_settings_patch_atomic_on_error);
  RUN_TEST(test_settings_patch_bad_brightness);
  RUN_TEST(test_settings_patch_night_errors_name_field);
  RUN_TEST(test_settings_patch_password);
  RUN_TEST(test_settings_patch_empty);
  RUN_TEST(test_server_url_empty_is_required);
  RUN_TEST(test_portal_form_first_setup);
  RUN_TEST(test_portal_form_configured_device);
  RUN_TEST(test_portal_form_keeps_stored_url_with_old_characters);
  RUN_TEST(test_apply_new_password_needs_equal_repeat);
  RUN_TEST(test_settings_patch_password_needs_repeat);
  RUN_TEST(test_portal_form_password_repeat);
  RUN_TEST(test_wifi_quality);
  RUN_TEST(test_format_duration);
  RUN_TEST(test_apply_night);
  RUN_TEST(test_settings_night_roundtrip_and_old_file);
  RUN_TEST(test_portal_ap_password_only_when_configured);
  RUN_TEST(test_server_url_rejects_markup_chars);
  RUN_TEST(test_server_url_still_accepts_normal_urls);
  RUN_TEST(test_stored_url_with_old_chars_still_loads);
  RUN_TEST(test_http_head_parses_frame_reply);
  RUN_TEST(test_http_head_304_without_length);
  RUN_TEST(test_http_head_chunked_has_no_length);
  RUN_TEST(test_http_head_rejects_garbage);
  RUN_TEST(test_http_head_bad_length_is_minus_one);
  RUN_TEST(test_http_head_etag_and_values_follow_existing_rules);
  RUN_TEST(test_anim_parses_the_example);
  RUN_TEST(test_anim_rejects_every_broken_limit);
  RUN_TEST(test_anim_touching_tracks_are_allowed);
  RUN_TEST(test_anim_never_reads_beyond_len);
  RUN_TEST(test_anim_value_length_limit);
  RUN_TEST(test_anim_same_geometry);
  RUN_TEST(test_anim_advance_right_left_and_wrap);
  RUN_TEST(test_anim_advance_left_wrap_small_steps);
  RUN_TEST(test_anim_clip_no_hole);
  RUN_TEST(test_anim_clip_hole_covers_block);
  RUN_TEST(test_anim_clip_track_through_a_block);
  RUN_TEST(test_anim_clip_corner_holes);
  RUN_TEST(test_anim_clip_hole_outside);
  RUN_TEST(test_anim_clip_overflow_falls_back_to_whole_block);
  RUN_TEST(test_anim_base_colors_match_rgb565);
  RUN_TEST(test_anim_new_track_starts_only_after_decode);
  RUN_TEST(test_anim_same_rect_keeps_running_with_new_values);
  RUN_TEST(test_anim_missing_track_stops_before_decode);
  RUN_TEST(test_anim_200_without_description_stops_all);
  RUN_TEST(test_anim_base_color_change_stops_all_until_decoded);
  RUN_TEST(test_anim_304_same_geometry_takes_values);
  RUN_TEST(test_anim_304_other_geometry_or_missing_stops_and_asks_refetch);
  RUN_TEST(test_anim_304_never_starts_tracks);
  RUN_TEST(test_anim_decode_failure_stops_all);
  RUN_TEST(test_anim_failed_fetch_keeps_running);
  RUN_TEST(test_anim_status_screen_stops_until_a_new_frame);
  RUN_TEST(test_anim_tick_every_40_ms_and_wraparound);
  RUN_TEST(test_anim_left_track_offset_wraps_down);
  RUN_TEST(test_anim_speed_change_does_not_jump);
  RUN_TEST(test_anim_invisible_keeps_state_and_draws_nothing);
  RUN_TEST(test_anim_gap_counters);
  RUN_TEST(test_anim_track_index_out_of_range_is_safe);
  RUN_TEST(test_anim_same_geometry_garbage_count);
  RUN_TEST(test_http_head_carries_x_anim);
  RUN_TEST(test_http_head_duplicate_x_anim_is_invalid);
  RUN_TEST(test_http_head_x_anim_name_case_blanks_and_length);
  RUN_TEST(test_server_target);
  RUN_TEST(test_server_target_userinfo);
  RUN_TEST(test_deadline_wraparound);
  RUN_TEST(test_frame_error_text_new_codes);
  RUN_TEST(test_auth_throttle_locks_after_five);
  RUN_TEST(test_auth_throttle_success_resets);
  RUN_TEST(test_auth_throttle_wraparound);
  RUN_TEST(test_auth_throttle_retry_after_rounds_up);
  RUN_TEST(test_host_allowed);
  RUN_TEST(test_host_allowed_edge_cases);
  RUN_TEST(test_server_target_long_host);
  RUN_TEST(test_server_target_question_mark_only_in_userinfo);
  RUN_TEST(test_display_server_url_hides_userinfo);
  RUN_TEST(test_display_server_url_truncates_safely);
  RUN_TEST(test_server_url_resubmitted_legacy_value_accepted);
  RUN_TEST(test_access_order_host_origin_lock_credentials);
  RUN_TEST(test_access_missing_header_does_not_count);
  RUN_TEST(test_access_wrong_password_counts_and_locks);
  RUN_TEST(test_access_success_resets_counter);
  return UNITY_END();
}
