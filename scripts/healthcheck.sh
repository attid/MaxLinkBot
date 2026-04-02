#!/bin/sh
set -eu

MARKER="${RUNTIME_UNHEALTHY_MARKER_PATH:-/tmp/maxlinkbot.unhealthy}"
HEARTBEAT="${RUNTIME_HEARTBEAT_PATH:-/tmp/maxlinkbot.heartbeat}"
MAX_AGE="${RUNTIME_HEARTBEAT_STALE_AFTER_SECONDS:-180}"

test ! -f "$MARKER"
test -f "$HEARTBEAT"

age=$(( $(date +%s) - $(stat -c %Y "$HEARTBEAT") ))
test "$age" -le "$MAX_AGE"
