#!/bin/sh
# Glance Box status-line script for Claude Code (macOS, Linux). Needs only sh and curl.
#
# Claude Code passes its status-line JSON on stdin. This script posts it in the background
# to the Glance Box push inbox (the server keeps only `rate_limits` and drops the rest) and
# never prints errors. Arguments, if given, are your existing status-line command: it gets
# the same stdin and its output and exit status become the status line.
#
# Settings: ${XDG_CONFIG_HOME:-$HOME/.config}/glancebox/push.env (chmod 600) with the lines
#   GLANCEBOX_URL=http://192.168.1.10:8080
#   GLANCEBOX_PUSH_KEY=<the push_key of the server>
#
# ~/.claude/settings.json:
#   "statusLine": {"type": "command", "command": "/path/to/glancebox-statusline.sh"}

input=$(cat)

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

# Before the first answer of a session the JSON has no rate_limits yet; sending it would
# replace the last good values on the display with nothing.
case "$input" in
  *'"rate_limits"'*)
    if [ -n "$GLANCEBOX_URL" ] && [ -n "$GLANCEBOX_PUSH_KEY" ]; then
      printf '%s' "$input" | curl -s -m 2 -o /dev/null -X POST \
        -H "Authorization: Bearer $GLANCEBOX_PUSH_KEY" \
        -H "Content-Type: application/json" \
        --data-binary @- "${GLANCEBOX_URL%/}/api/v1/push/claude" >/dev/null 2>&1 &
      # The usage hook (glancebox-usage.sh) skips its fetch for a minute after this.
      { date +%s > "${env_file%/*}/usage.stamp"; } 2>/dev/null
    fi
    ;;
esac

if [ $# -gt 0 ]; then
  printf '%s' "$input" | "$@"
  exit $?
fi
exit 0
