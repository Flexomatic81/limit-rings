#!/usr/bin/env bash
# Installs the Limit Rings widget – it brings and runs its own collector – from this checkout. Safe to run repeatedly.
# --statusline: insert the status line hook without asking.
# --migrate-widgets: switch placed "Agent Stats" widgets to Limit Rings without asking (restarts the Plasma shell).
set -euo pipefail
# Every step is safe to repeat, so a run that broke off is completed by simply running the script again.
trap 'echo "install.sh stopped early – fix the cause above and run it again; it picks up where it stopped." >&2' ERR

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
units="$HOME/.config/systemd/user"
# shellcheck source=tools/install-lib.sh
. "$here/tools/install-lib.sh"
id="io.github.flexomatic81.limitrings"
share="$HOME/.local/share/limit-rings"
bin="$HOME/.local/bin/limit-rings-collect"
cache="$HOME/.cache/limit-rings"
statusline="$HOME/.claude/statusline-command.sh"
appletsrc="$HOME/.config/plasma-org.kde.plasma.desktop-appletsrc"
marker="# limit-rings: record limits for the plasmoid"
snippet="$(grep -v '^#' "$here/statusline-snippet.sh")"

# Names from before the rename – versions up to 0.1 were called "Agent Stats".
old_id="io.github.flexomatic81.agentstats"
old_share="$HOME/.local/share/agent-stats"
old_cache="$HOME/.cache/agent-stats"
old_marker="# agent-stats: record limits for the plasmoid"
old_marker_de="# agent-stats: Limits für das Plasmoid mitschneiden"   # written by older German versions

auto_statusline=no
auto_widgets=no
for arg in "$@"; do
    case "$arg" in
        --statusline) auto_statusline=yes ;;
        --migrate-widgets) auto_widgets=yes ;;
        *) echo "Unknown option: $arg" >&2; exit 2 ;;
    esac
done

echo "→ Checking requirements"
missing=no
if ! command -v kpackagetool6 >/dev/null 2>&1; then
    echo "  kpackagetool6 not found – it comes with KDE Plasma 6 (KDE Frameworks package \"kpackage\")." >&2
    missing=yes
fi
if ! command -v python3 >/dev/null 2>&1; then
    echo "  python3 not found – install it: $(install_hint python3 python python3 python3)" >&2
    missing=yes
elif ! py_version="$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2]); sys.exit(sys.version_info < (3, 10))')"; then
    echo "  Python $py_version is too old – Limit Rings needs 3.10 or newer: $(install_hint python3 python python3 python3)" >&2
    missing=yes
fi
if [[ $missing == yes ]]; then
    echo "Nothing was changed. Install what is missing and run install.sh again." >&2
    exit 1
fi

# Replaces file $1 with the output of the command "${@:3}" – atomically and keeping its mode – and keeps the
# first original as backup $2 (a retry never overwrites it). If the command or a write fails, $1 stays as it was.
# A symlinked $1 (e.g. from a dotfiles repo) stays a symlink: its target is replaced.
replace_file() {
    local file backup="$2" tmp
    file="$(readlink -f "$1")" || return 1
    tmp="$(mktemp "$file.XXXXXX")" || return 1
    if ! "${@:3}" > "$tmp" || ! chmod --reference="$file" "$tmp" \
        || ! { [[ -e "$backup" ]] || cp -p "$file" "$backup"; } || ! mv -f "$tmp" "$file"; then
        rm -f "$tmp"
        return 1
    fi
}

# Points placed widgets at the new plugin ID. Position and settings stay: they are keyed by applet, not by plugin.
switch_widgets() {
    replace_file "$appletsrc" "$appletsrc.bak-limit-rings" \
        awk -v old="plugin=$old_id" -v new="plugin=$id" '$0 == old { $0 = new } { print }' "$appletsrc" || return 1
    kpackagetool6 -t Plasma/Applet --remove "$old_id" >/dev/null 2>&1 || true
    echo "  widgets switched (backup: $appletsrc.bak-limit-rings)."
}

if [[ -d "$old_share" || -f "$units/agent-stats.timer" || -d "$old_cache" ]]; then
    echo "→ Migrating from Agent Stats"
fi
retire_timer agent-stats "$old_share" "$HOME/.local/bin/agent-stats-collect" \
    "$HOME"/.local/share/locale/*/LC_MESSAGES/plasma_applet_$old_id.mo
# Only reached once the old collector is gone (above, or in an earlier run), so nothing writes the old cache any more.
if [[ ! -d "$old_cache" ]]; then
    :
elif [[ ! -e "$cache" ]]; then
    mv "$old_cache" "$cache"
    echo "  cache moved to $cache (history and notification state kept)."
elif [[ -e "$old_cache/state.json" && -e "$cache/state.json" ]]; then
    echo "  Note: $old_cache and $cache both hold history – the old one is left untouched and no longer used."
    echo "  Remove it once you no longer need it: rm -r $old_cache"
else
    # Only one of them holds state (a collector run by hand, or a merge that broke off): take the old files over.
    for f in "$old_cache"/*; do
        if [[ -e "$f" && ! -e "$cache/${f##*/}" ]]; then mv "$f" "$cache/"; fi
    done
    rm -rf "$old_cache"
    echo "  cache merged into $cache (history and notification state kept)."
fi

# The new package goes in first: if building or installing fails, the old timer keeps collecting. Until it is
# retired below, the new collector does not collect next to it (widget.py checks for the timer).
echo "→ Widget"
pkg_dir="$(mktemp -d)"
python3 "$here/tools/build_plasmoid.py" --source git --repo-dir "$here" --dir "$pkg_dir/$id" >/dev/null
upgrade=no
if kpackagetool6 -t Plasma/Applet --show "$id" >/dev/null 2>&1; then
    upgrade=yes
    kpackagetool6 -t Plasma/Applet --upgrade "$pkg_dir/$id"
else
    kpackagetool6 -t Plasma/Applet --install "$pkg_dir/$id"
fi
rm -rf "$pkg_dir"

if [[ -d "$share" || -f "$units/limit-rings.timer" ]]; then
    echo "→ Removing the systemd timer of earlier versions (the widget runs the collector now)"
fi
retire_timer limit-rings "$share" "$bin"
# Translations now come with the package; copies from earlier versions would take precedence.
rm -f "$HOME"/.local/share/locale/*/LC_MESSAGES/plasma_applet_$id.mo

if [[ -f "$appletsrc" ]] && grep -qxF "plugin=$old_id" "$appletsrc"; then
    answer=n
    if [[ $auto_widgets == yes ]]; then
        answer=y
    elif [[ -t 0 ]]; then
        echo "  Placed \"Agent Stats\" widgets found. Switching them to Limit Rings keeps their position and"
        echo "  settings, but restarts the Plasma shell (panels disappear for a few seconds)."
        read -r -p "  Switch now? [y/N] " answer || answer=n
    fi
    if [[ $answer != [yY] ]]; then
        echo "  Not switched – the old widgets show no data until install.sh is re-run with --migrate-widgets."
    elif systemctl --user is-active --quiet plasma-plasmashell; then
        # plasmashell writes its configuration on exit, so edit it only while the shell is stopped.
        systemctl --user stop plasma-plasmashell
        # Whatever happens from here on (an error, Ctrl-C), the desktop must not be left without its shell.
        trap 'systemctl --user start plasma-plasmashell' EXIT
        trap 'exit 130' INT TERM HUP
        switch_widgets || echo "  Warning: switching failed – $appletsrc left as it was."
        trap - EXIT INT TERM HUP
        systemctl --user start plasma-plasmashell
    elif pgrep -u "$UID" -x plasmashell >/dev/null; then
        echo "  plasmashell is not run by systemd – quit it (kquitapp6 plasmashell), re-run install.sh with"
        echo "  --migrate-widgets, then start it again (kstart plasmashell)."
    else
        switch_widgets || echo "  Warning: switching failed – $appletsrc left as it was."
    fi
elif kpackagetool6 -t Plasma/Applet --show "$old_id" >/dev/null 2>&1; then
    kpackagetool6 -t Plasma/Applet --remove "$old_id"
fi

echo "→ Status line (fallback for Claude limits)"
if [[ ! -f "$statusline" ]]; then
    echo "  $statusline not found – skipped."
elif grep -qF -e "$old_marker" -e "$old_marker_de" "$statusline"; then
    if OLD="$old_marker" OLD_DE="$old_marker_de" MARKER="$marker" SNIPPET="$snippet" \
        replace_file "$statusline" "$statusline.bak-limit-rings" awk '
            { line = $0; sub(/^[ \t]+/, "", line); sub(/[ \t\r]+$/, "", line) }
            line == ENVIRON["OLD"] || line == ENVIRON["OLD_DE"] { print ENVIRON["MARKER"]; after = 1; next }
            after && index($0, "/.cache/agent-stats") { print ENVIRON["SNIPPET"]; after = 0; next }
            { after = 0; print }
        ' "$statusline"; then
        if grep -qF "$marker" "$statusline"; then
            echo "  switched from agent-stats to limit-rings (backup: $statusline.bak-limit-rings)."
        else
            echo "  Warning: $statusline has an old agent-stats line that was not recognised – please adjust it by hand."
        fi
        if grep -qF "/.cache/agent-stats" "$statusline"; then
            echo "  Warning: $statusline still refers to ~/.cache/agent-stats – please adjust it by hand."
        fi
    else
        echo "  Warning: $statusline could not be rewritten – left as it was."
    fi
elif grep -qF "$marker" "$statusline"; then
    echo "  already present."
elif ! grep -q '^input=\$(cat)' "$statusline"; then
    echo "  No line 'input=\$(cat)' found. Please insert manually right after it:"
    printf '    %s\n    %s\n' "$marker" "$snippet"
else
    answer=n
    if [[ $auto_statusline == yes ]]; then
        answer=y
    elif [[ -t 0 ]]; then
        echo "  To be inserted after 'input=\$(cat)':"
        printf '    %s\n    %s\n' "$marker" "$snippet"
        read -r -p "  Insert now? [y/N] " answer || answer=n
    else
        echo "  Not interactive – not inserted. Re-run with --statusline to insert it."
    fi
    if [[ $answer != [yY] ]]; then
        :
    elif MARKER="$marker" SNIPPET="$snippet" replace_file "$statusline" "$statusline.bak-limit-rings" awk '
            { print }
            !done && /^input=\$\(cat\)/ { print ENVIRON["MARKER"]; print ENVIRON["SNIPPET"]; done = 1 }
        ' "$statusline"; then
        echo "  inserted (backup: $statusline.bak-limit-rings)."
    else
        echo "  Warning: $statusline could not be changed – left as it was."
    fi
fi

if [[ -f "$statusline" ]] && grep -qF "$marker" "$statusline" && ! command -v jq >/dev/null 2>&1; then
    echo "  Note: the status line hook needs jq, which is missing: $(install_hint jq jq jq jq)"
fi

echo
if [[ $upgrade == yes ]]; then
    echo "Done. Restart Plasma to load the new version: systemctl --user restart plasma-plasmashell"
else
    echo "Done. Drag the \"Limit Rings\" widget from \"Add Widgets\" onto a panel or the desktop."
fi
