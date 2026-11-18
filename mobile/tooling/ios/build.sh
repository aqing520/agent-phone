#!/usr/bin/env bash
# `flutter build ios` with these arguments. Reading a job's log takes a GitHub sign-in
# and its annotations don't, so on failure the compiler's errors go up as annotations
# as well (at most ten: GitHub's limit for one step).
set -uo pipefail

log="$(mktemp)"
flutter build ios "$@" 2>&1 | tee "$log"
status=${PIPESTATUS[0]}
if [ "$status" -ne 0 ]; then
  # Flutter prints Xcode's message with its file on the line after.
  awk '/\(Xcode\):|error:|Error:/ {
    line = $0
    if (getline following > 0) line = line " | " following
    print line
  }' "$log" | awk '!seen[$0]++' | cut -c1-600 | head -10 | sed -e 's/%/%25/g' -e 's/^/::error::/'
fi
exit "$status"
