#include "auth_throttle.h"

namespace gb {

bool AuthThrottle::locked(uint32_t nowMs) {
  if (!locked_) return false;
  if (nowMs - lockStartMs_ < kLockMs) return true;  // unsigned difference: wraparound-safe
  locked_ = false;
  // Not a clean slate: the first wrong password after a lock locks again.
  failures_ = kMaxFailures - 1;
  return false;
}

void AuthThrottle::onFailure(uint32_t nowMs) {
  if (locked(nowMs)) return;
  if (++failures_ < kMaxFailures) return;
  locked_ = true;
  lockStartMs_ = nowMs;
}

void AuthThrottle::onSuccess() { failures_ = 0; }

uint32_t AuthThrottle::retryAfterS(uint32_t nowMs) {
  if (!locked(nowMs)) return 0;
  const uint32_t leftMs = kLockMs - (nowMs - lockStartMs_);
  return (leftMs + 999) / 1000;
}

Access decideAccess(bool hostOk, bool originOk, bool hasAuthorization, bool (*credentialsOk)(),
                    AuthThrottle& throttle, uint32_t nowMs) {
  if (!hostOk) return Access::HostDenied;
  if (!originOk) return Access::OriginDenied;
  if (throttle.locked(nowMs)) return Access::Locked;
  if (!hasAuthorization) return Access::NeedAuth;  // not a failure: the browser asks first
  if (!credentialsOk()) {
    throttle.onFailure(nowMs);
    return Access::WrongPassword;
  }
  throttle.onSuccess();
  return Access::Granted;
}

}  // namespace gb
