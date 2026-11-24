#!/bin/sh
# Glance Box usage hook for Claude Code (macOS, Linux). Needs only sh and curl.
#
# The status-line script runs only in Claude Code's terminal UI. Apps that drive Claude Code
# without it (T3 Code, the desktop app, IDE extensions) still run hooks. As a hook, this script
# fetches the plan limits with `claude -p "/usage"` in the background (about 3 seconds, no
# tokens) and posts the line with the usage report to the Glance Box push inbox. The usage
# report is marked experimental by Anthropic and may change. The script never reads stdin,
# never prints anything and always exits 0 at once. It fetches at most once a minute (the
# stamp file usage.stamp beside push.env; the status-line script writes it too).
# GLANCEBOX_USAGE_TIMEOUT (seconds, default 30) limits the `claude` call.
#
# Settings: ${XDG_CONFIG_HOME:-$HOME/.config}/glancebox/push.env (chmod 600) with the lines
#   GLANCEBOX_URL=http://192.168.1.10:8080
#   GLANCEBOX_PUSH_KEY=<the push_key of the server>
#
# ~/.claude/settings.json:
#   "hooks": {
#     "Stop": [{"hooks": [{"type": "command", "command": "/path/to/glancebox-usage.sh"}]}],
#     "PostToolUse": [{"hooks": [{"type": "command", "command": "/path/to/glancebox-usage.sh"}]}]
#   }

# The `claude` call below runs hooks too, this one included.
[ "$GLANCEBOX_USAGE" = 1 ] && exit 0

GLANCEBOX_URL=
GLANCEBOX_PUSH_KEY=
env_file="${XDG_CONFIG_HOME:-$HOME/.config}/glancebox/push.env"
if [ -r "$env_file" ]; then
  while IFS= read -r line || [ -n "$line" ]; do
    # Split at the first "=" only; base64 keys may end in "=" (IFS='=' would strip one).
    name=${line%%=*}
    value=$(printf '%s' "${line#*=}" | tr -d '\r')
    case "$name" in
      GLANCEBOX_URL) GLANCEBOX_URL=$value ;;
      GLANCEBOX_PUSH_KEY) GLANCEBOX_PUSH_KEY=$value ;;
    esac
  done < "$env_file"
fi
[ -n "$GLANCEBOX_URL" ] && [ -n "$GLANCEBOX_PUSH_KEY" ] || exit 0

dir=${env_file%/*}
stamp="$dir/usage.stamp"
lock="$dir/usage.lock"
# The lock makes check and write of the stamp one step, so two hooks that fire together
# fetch once. It is held for a moment only; one left behind by a killed run is removed
# after a minute.
if ! mkdir "$lock" 2>/dev/null; then
  [ -n "$(find "$lock" -prune -mmin +1 2>/dev/null)" ] && rmdir "$lock" 2>/dev/null
  exit 0
fi
now=$(date +%s)
last=$(cat "$stamp" 2>/dev/null)
# Only plain epoch seconds count (no leading zero: sh arithmetic would read it as octal).
case "$last" in
  '' | 0* | *[!0-9]*) ;;
  *)
    if [ ${#last} -le 12 ] && [ $((now - last)) -ge 0 ] && [ $((now - last)) -lt 60 ]; then
      rmdir "$lock" 2>/dev/null
      exit 0
    fi
    ;;
esac
{ printf '%s\n' "$now" > "$stamp"; } 2>/dev/null
rmdir "$lock" 2>/dev/null

timeout=${GLANCEBOX_USAGE_TIMEOUT:-30}
# At least 1 second: the runner below needs a moment to set its trap.
case "$timeout" in '' | 0* | *[!0-9]*) timeout=30 ;; esac

# Detached from stdin, stdout and stderr: a hook runner may wait until those are closed.
(
  cd "$dir" || exit 0
  out=$(mktemp) || exit 0
  # No `timeout` binary on macOS: a timer, and a runner that starts claude, stops the timer
  # when claude ends and stops claude when it is stopped itself. Nothing outlives the fetch.
  sleep "$timeout" &
  timer=$!
  (
    GLANCEBOX_USAGE=1 claude -p "/usage" --output-format stream-json --verbose \
      --no-session-persistence < /dev/null > "$out" 2>/dev/null &
    pid=$!
    trap 'kill "$pid" 2>/dev/null; exit 0' TERM
    wait "$pid"
    kill "$timer" 2>/dev/null
  ) &
  runner=$!
  # 0 only when the timer ran out; then claude still runs.
  wait "$timer" && kill "$runner" 2>/dev/null
  wait "$runner"
  # The usage report line, only with at least one limit ("limits":null or [] sends nothing).
  line=$(grep '"usage_report"' "$out" | grep '"limits":\[[^]]' | head -n 1)
  rm -f "$out"
  if [ -n "$line" ]; then
    printf '%s' "$line" | curl -s -m 5 -o /dev/null -X POST \
      -H "Authorization: Bearer $GLANCEBOX_PUSH_KEY" \
      -H "Content-Type: application/json" \
      --data-binary @- "${GLANCEBOX_URL%/}/api/v1/push/claude"
  fi
) < /dev/null > /dev/null 2>&1 &
exit 0
