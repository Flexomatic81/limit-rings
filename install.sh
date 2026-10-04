#!/usr/bin/env bash
# Installs the collector, systemd timer and plasmoid. Safe to run repeatedly.
# --statusline: insert the status line hook without asking.
# --migrate-widgets: switch placed "Agent Stats" widgets to Limit Rings without asking (restarts the Plasma shell).
set -euo pipefail
# Every step is safe to repeat, so a run that broke off is completed by simply running the script again.
trap 'echo "install.sh stopped early – fix the cause above and run it again; it picks up where it stopped." >&2' ERR

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
id="io.github.flexomatic81.limitrings"
share="$HOME/.local/share/limit-rings"
bin="$HOME/.local/bin/limit-rings-collect"
cache="$HOME/.cache/limit-rings"
units="$HOME/.config/systemd/user"
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
    # Stop first (stop waits for a running pass) – otherwise the old collector keeps writing the old cache.
    systemctl --user stop agent-stats.timer agent-stats.service 2>/dev/null || true
    if systemctl --user is-active --quiet agent-stats.timer agent-stats.service; then
        echo "Error: the old agent-stats timer could not be stopped – nothing was migrated. Check:" >&2
        echo "  systemctl --user status agent-stats.timer agent-stats.service" >&2
        exit 1
    fi
    systemctl --user disable agent-stats.timer 2>/dev/null || true
    rm -f "$units/agent-stats.timer" "$units/agent-stats.service"
    systemctl --user daemon-reload
    rm -rf "$old_share"
    rm -f "$HOME/.local/bin/agent-stats-collect" "$HOME"/.local/share/locale/*/LC_MESSAGES/plasma_applet_$old_id.mo
    if [[ -d "$old_cache" && ! -e "$cache" ]]; then
        mv "$old_cache" "$cache"
        echo "  cache moved to $cache (history and notification state kept)."
    elif [[ -d "$old_cache" && ! -e "$cache/state.json" ]]; then
        # The new cache exists but holds no state yet (e.g. a collector run by hand): take the old files over.
        for f in "$old_cache"/*; do
            if [[ -e "$f" && ! -e "$cache/${f##*/}" ]]; then mv "$f" "$cache/"; fi
        done
        rm -rf "$old_cache"
        echo "  cache merged into $cache (history and notification state kept)."
    elif [[ -d "$old_cache" ]]; then
        echo "  Note: $old_cache and $cache both exist – the old one is left untouched."
    fi
fi

echo "→ Collector to $share"
mkdir -p "$share" "$(dirname "$bin")"
rm -rf "$share/limit_rings"
cp -r "$here/collector/limit_rings" "$share/"
find "$share" -name __pycache__ -prune -exec rm -rf {} +
cat > "$bin" <<'EOF'
#!/bin/sh
PYTHONPATH="$HOME/.local/share/limit-rings${PYTHONPATH:+:$PYTHONPATH}" exec /usr/bin/python3 -m limit_rings.collect "$@"
EOF
chmod 755 "$bin"

echo "→ Translations"
if command -v msgfmt >/dev/null 2>&1; then
    for po in "$here"/po/plasmoid/*.po; do
        dir="$HOME/.local/share/locale/$(basename "$po" .po)/LC_MESSAGES"
        mkdir -p "$dir"
        msgfmt -o "$dir/plasma_applet_$id.mo" "$po" \
            || echo "  Warning: ${po#"$here"/} could not be compiled – skipped."
    done
    for po in "$here"/po/collector/*.po; do
        dir="$share/limit_rings/locale/$(basename "$po" .po)/LC_MESSAGES"
        mkdir -p "$dir"
        msgfmt -o "$dir/limit-rings.mo" "$po" \
            || echo "  Warning: ${po#"$here"/} could not be compiled – skipped."
    done
else
    echo "  Warning: gettext (msgfmt) not found – widget and notifications stay in English."
fi

echo "→ systemd timer"
mkdir -p "$units"
cp "$here/systemd/limit-rings.service" "$here/systemd/limit-rings.timer" "$units/"
systemctl --user daemon-reload
systemctl --user enable --now limit-rings.timer
systemctl --user start limit-rings.service || echo "  Warning: first run failed – journalctl --user -u limit-rings.service"

echo "→ Plasmoid"
if kpackagetool6 -t Plasma/Applet --show "$id" >/dev/null 2>&1; then
    kpackagetool6 -t Plasma/Applet --upgrade "$here/plasmoid/$id"
else
    kpackagetool6 -t Plasma/Applet --install "$here/plasmoid/$id"
fi
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
        switch_widgets || echo "  Warning: switching failed – $appletsrc left as it was."
        systemctl --user start plasma-plasmashell
    elif pgrep -x plasmashell >/dev/null; then
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

echo
echo "Done. Drag the \"Limit Rings\" widget from \"Add Widgets\" onto a panel or the desktop."
echo "After an upgrade you may need: systemctl --user restart plasma-plasmashell"
