#!/bin/sh
# Started by the Übersicht widget every 60 s: one collector pass with the first Python 3.10 or newer.
# Without one, the first Python found runs anyway, so that run.py reports its version to the card.
# With --which it only prints the Python it would use (exit 0: 3.10+, 1: older, 127: none).
here="$(cd "$(dirname "$0")" && pwd)"
apple="${LIMIT_RINGS_APPLE_PYTHON:-/usr/bin/python3}"
xcode="${LIMIT_RINGS_XCODE_SELECT:-/usr/bin/xcode-select}"
candidates="${LIMIT_RINGS_PYTHONS:-/Library/Frameworks/Python.framework/Versions/Current/bin/python3 \
/opt/homebrew/bin/python3 /usr/local/bin/python3 $(command -v python3 2>/dev/null) /usr/bin/python3}"

first=""
chosen=""
suitable=""
for py in $candidates; do
    [ -x "$py" ] || continue
    # Apple's python3 is a stub that opens an install dialog while the developer tools are missing.
    if [ "$py" = "$apple" ] && ! "$xcode" -p >/dev/null 2>&1; then continue; fi
    [ -n "$first" ] || first="$py"
    if "$py" -c 'import sys; sys.exit(sys.version_info < (3, 10))' 2>/dev/null; then
        chosen="$py"
        suitable=1
        break
    fi
done
chosen="${chosen:-$first}"
[ -n "$chosen" ] || exit 127

# --which (used by the installer): name the Python this widget would use, without collecting
if [ "${1:-}" = "--which" ]; then
    printf '%s\n' "$chosen"
    [ -n "$suitable" ]
    exit
fi

# A pass that hangs (e.g. on a stalled disk) must not stop the widget: Übersicht starts the next pass only
# after this one ends. The collector keeps its state consistent when killed (atomic writes, lock file).
"$chosen" "$here/collector/run.py" &
pid=$!
# The watchdog must not hold stdout: Übersicht (and the tests) wait until the output is closed.
( sleep "${LIMIT_RINGS_DEADLINE:-50}"; kill "$pid" 2>/dev/null ) >/dev/null 2>&1 &
watchdog=$!
wait "$pid"
code=$?
kill "$watchdog" 2>/dev/null
[ "$code" -ge 128 ] && exit 124
exit "$code"
