#!/bin/sh
# Installs or updates Limit Rings for Übersicht on macOS – and Übersicht itself if it is missing.
#   curl -fsSL https://github.com/Flexomatic81/limit-rings/releases/latest/download/install-macos.sh | sh
#   … | sh -s -- --uninstall        remove the widget, its login item and its cache (Übersicht stays)
#   … | sh -s -- --no-login-item    do not start Übersicht at login
#   … | sh -s -- --version v0.7.0   install that release instead of the latest
# Needs no admin rights and changes nothing outside your home folder. Never reads from stdin: under
# "curl … | sh" stdin is this script.
set -eu

RELEASES="${LIMIT_RINGS_RELEASE_BASE:-https://github.com/Flexomatic81/limit-rings/releases}"
UEBERSICHT_PAGE="${LIMIT_RINGS_UEBERSICHT_PAGE:-https://tracesof.net/uebersicht/}"
UEBERSICHT_TEAM="S3P44NRLCW"   # Developer ID team of Übersicht's author
SYSTEM_APPS="${LIMIT_RINGS_SYSTEM_APPS:-/Applications}"
USER_APPS="$HOME/Applications"
WIDGETS="$HOME/Library/Application Support/Übersicht/widgets"
WIDGET="limit-rings.widget"
AGENT="$HOME/Library/LaunchAgents/io.github.flexomatic81.limitrings.uebersicht.plist"
# SHA-256 of Übersicht's own welcome widget GettingStarted.jsx as shipped; only an unchanged one is removed
WELCOME_ORIGINALS="${LIMIT_RINGS_WELCOME_ORIGINALS:-1176cb4b78732ad1bb99ab9b2b4b9f7c03ae49e1082d74d879fccf177b273e3b}"

say() { printf 'Limit Rings: %s\n' "$*"; }
fail() { printf 'Limit Rings: %s\n' "$*" >&2; exit 1; }

STAGING="$HOME/Library/Application Support/Übersicht/limit-rings-staging"
LOCK="$HOME/Library/Application Support/Übersicht/limit-rings-install.lock"

tmp=""
locked=0
cleanup() {
    if [ -n "$tmp" ]; then rm -rf "$tmp"; fi
    if [ "$locked" = 1 ]; then rm -rf "$LOCK"; fi
}

take_lock() {
    mkdir -p "$(dirname "$LOCK")"
    if ! mkdir "$LOCK" 2>/dev/null; then
        # A run killed hard (reboot, kill -9) leaves its lock behind: take it over if its owner is gone.
        owner="$(cat "$LOCK/pid" 2>/dev/null || true)"
        case "$owner" in ''|*[!0-9]*) owner="" ;; esac
        if [ -n "$owner" ] && ! kill -0 "$owner" 2>/dev/null; then
            rm -rf "$LOCK"
            mkdir "$LOCK" 2>/dev/null || fail "another installer is starting – try again in a moment"
            say "took over the lock of an installer that was stopped"
        else
            fail "another installer seems to be running – if not, remove $LOCK and try again"
        fi
    fi
    echo "$$" > "$LOCK/pid"
    locked=1
}

# A widget moved aside by an interrupted run is the last working one: put it back before anything else.
recover_previous() {
    if [ -d "$STAGING/previous" ] && [ ! -e "$WIDGETS/$WIDGET" ]; then
        mkdir -p "$WIDGETS"
        mv "$STAGING/previous" "$WIDGETS/$WIDGET" || fail "could not restore the widget from $STAGING/previous"
        say "restored the widget left over from an interrupted run"
    fi
}

find_uebersicht() {
    for dir in "$SYSTEM_APPS" "$USER_APPS"; do
        if [ -d "$dir/Übersicht.app" ]; then printf '%s\n' "$dir/Übersicht.app"; return; fi
    done
}

install_uebersicht() {
    say "Übersicht is missing – downloading it from tracesof.net"
    url="$(curl -fsSL "$UEBERSICHT_PAGE" \
        | grep -o 'https://tracesof\.net/uebersicht/releases/Uebersicht-[0-9.]*\.app\.zip' | head -n 1)" || url=""
    [ -n "$url" ] || fail "could not find the Übersicht download on $UEBERSICHT_PAGE"
    curl -fsSL -o "$tmp/uebersicht.zip" "$url" || fail "the download of Übersicht failed"
    mkdir "$tmp/uebersicht"
    ditto -x -k "$tmp/uebersicht.zip" "$tmp/uebersicht" || fail "could not unpack Übersicht"
    set -- "$tmp/uebersicht"/*.app
    { [ $# -eq 1 ] && [ -d "$1" ]; } || fail "the Übersicht download has unexpected content – not installed"
    codesign --verify --deep --strict "$1" 2>/dev/null || fail "Übersicht's signature is not valid – not installed"
    spctl -a -t exec "$1" 2>/dev/null || fail "macOS does not accept Übersicht as notarized – not installed"
    codesign -dv "$1" 2>&1 | grep -qx "TeamIdentifier=$UEBERSICHT_TEAM" \
        || fail "Übersicht is not signed by its author (team $UEBERSICHT_TEAM) – not installed"
    mkdir -p "$USER_APPS"
    mv "$1" "$USER_APPS/Übersicht.app" || fail "could not move Übersicht to $USER_APPS"
    app="$USER_APPS/Übersicht.app"
    say "installed Übersicht in $USER_APPS (signature checked)"
}

install_widget() {
    base="$RELEASES/latest/download"
    if [ -n "$version" ]; then base="$RELEASES/download/$version"; fi
    say "downloading the widget from $base"
    curl -fsSL -o "$tmp/limit-rings-macos.zip" "$base/limit-rings-macos.zip" \
        || fail "the download of the widget failed – nothing changed"
    curl -fsSL -o "$tmp/limit-rings-macos.zip.sha256" "$base/limit-rings-macos.zip.sha256" \
        || fail "the download of the widget's checksum failed – nothing changed"
    (cd "$tmp" && shasum -a 256 -c limit-rings-macos.zip.sha256 >/dev/null 2>&1) \
        || fail "the checksum of the widget does not match – nothing changed"
    mkdir "$tmp/widget"
    ditto -x -k "$tmp/limit-rings-macos.zip" "$tmp/widget" || fail "could not unpack the widget – nothing changed"
    [ -f "$tmp/widget/$WIDGET/index.jsx" ] || fail "the widget download has unexpected content – nothing changed"
    mkdir -p "$WIDGETS"
    # Stage next to the widgets folder (same volume, so the moves are renames; Übersicht does not scan it).
    rm -rf "$STAGING/new"
    mkdir -p "$STAGING"
    mv "$tmp/widget/$WIDGET" "$STAGING/new" || fail "could not stage the widget – nothing changed"
    updated=0
    if [ -e "$WIDGETS/$WIDGET" ]; then
        updated=1
        # the user's settings (e.g. login off) survive the update
        if [ -f "$WIDGETS/$WIDGET/settings.json" ]; then
            cp -p "$WIDGETS/$WIDGET/settings.json" "$STAGING/new/settings.json" \
                || fail "could not keep your settings.json – nothing changed"
        fi
        rm -rf "$STAGING/previous"
        mv "$WIDGETS/$WIDGET" "$STAGING/previous" || fail "could not move the old widget aside – nothing changed"
    fi
    if ! mv "$STAGING/new" "$WIDGETS/$WIDGET"; then
        if [ "$updated" = 1 ] && mv "$STAGING/previous" "$WIDGETS/$WIDGET"; then
            fail "could not put the new widget into $WIDGETS – the old one is back in place"
        fi
        fail "could not put the widget into $WIDGETS – the previous one is kept in $STAGING/previous"
    fi
    rm -rf "$STAGING"
    if [ "$updated" = 1 ]; then say "updated the widget in $WIDGETS"; else say "installed the widget in $WIDGETS"; fi
}

check_python() {
    if py="$(sh "$WIDGETS/$WIDGET/run.sh" --which 2>/dev/null)"; then
        say "found Python 3.10 or newer: $py"
    else
        say "no Python 3.10 or newer found – install one from https://www.python.org/downloads/macos/ (the card reminds you until then)"
    fi
}

remove_welcome() {
    f="$WIDGETS/GettingStarted.jsx"
    [ -f "$f" ] || return 0
    sum="$(shasum -a 256 "$f" | cut -d ' ' -f 1)"
    case " $WELCOME_ORIGINALS " in
        *" $sum "*) rm -f "$f"; say "removed Übersicht's welcome widget" ;;
        *) say "kept GettingStarted.jsx – it was changed, so it may be yours" ;;
    esac
}

xml_escape() { printf '%s' "$1" | sed -e 's/&/\&amp;/g' -e 's/</\&lt;/g' -e 's/>/\&gt;/g'; }

write_login_item() {
    mkdir -p "$(dirname "$AGENT")"
    cat > "$AGENT" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>io.github.flexomatic81.limitrings.uebersicht</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/open</string>
        <string>-a</string>
        <string>$(xml_escape "$app")</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
</dict>
</plist>
EOF
    say "Übersicht starts at login (macOS may show \"Background item added\" once)"
}

start_uebersicht() {
    if pgrep -f "Übersicht.app/Contents/MacOS/" >/dev/null 2>&1; then
        say "Übersicht is running – the cards appear within a minute"
    else
        open -a "$app"
        say "started Übersicht – the cards appear within a minute"
    fi
}

uninstall_all() {
    rm -rf "${WIDGETS:?}/$WIDGET" "$STAGING" "$HOME/.cache/limit-rings"
    rm -f "$AGENT"
    say "removed the widget, its login item and ~/.cache/limit-rings (Übersicht itself stays)"
}

main() {
uninstall=0
login_item=1
version=""
while [ $# -gt 0 ]; do
    case "$1" in
        --uninstall) uninstall=1 ;;
        --no-login-item) login_item=0 ;;
        --version) [ $# -ge 2 ] || fail "--version needs a release tag such as v0.7.0"; version="$2"; shift ;;
        *) fail "unknown option $1 (known: --uninstall, --no-login-item, --version vX.Y.Z)" ;;
    esac
    shift
done
case "$version" in *[!v0-9.]*) version_bad=1 ;; *) version_bad=0 ;; esac
if [ -n "$version" ] && { [ "$version_bad" = 1 ] || ! printf '%s\n' "$version" | grep -Eqx 'v[0-9]+\.[0-9]+\.[0-9]+'; }; then
    fail "--version needs a release tag such as v0.7.0, not $version"
fi

[ "$(uname -s)" = Darwin ] || fail "this installer is for macOS – on Linux, install the KDE widget (see the README)"
{ [ -n "${HOME:-}" ] && [ -d "$HOME" ]; } || fail "HOME is not set"
trap cleanup EXIT
take_lock
recover_previous
tmp="$(mktemp -d "${TMPDIR:-/tmp}/limit-rings.XXXXXX")"

if [ "$uninstall" = 1 ]; then
    uninstall_all
    exit 0
fi
app="$(find_uebersicht)"
if [ -n "$app" ]; then say "found Übersicht at $app"; else install_uebersicht; fi
install_widget
check_python
remove_welcome
if [ "$login_item" = 1 ]; then write_login_item; fi
start_uebersicht
say "done – run the same command again to update; add \"-s -- --uninstall\" after sh to remove it"
}

# The only top-level command: a download cut off before this line runs nothing.
main "$@"
