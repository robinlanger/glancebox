#pragma once
#include <cstdint>

namespace gb {

// Global lock after repeated wrong passwords on the device web UI. Global on purpose:
// the device has no memory for per-client state. While locked, callers refuse every
// password check (even a correct one), so the lock cannot be used as an oracle.
class AuthThrottle {
 public:
  static constexpr uint8_t kMaxFailures = 5;
  static constexpr uint32_t kLockMs = 30000;

  bool locked(uint32_t nowMs);           // clears an expired lock (wraparound-safe)
  void onFailure(uint32_t nowMs);        // the 5th consecutive failure starts a lock
  void onSuccess();                      // resets the counter
  uint32_t retryAfterS(uint32_t nowMs);  // whole seconds left, rounded up; 0 if not locked

 private:
  uint8_t failures_ = 0;
  bool locked_ = false;
  uint32_t lockStartMs_ = 0;
};

}  // namespace gb
