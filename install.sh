#!/usr/bin/env bash
# Installs the collector, systemd timer and plasmoid. Safe to run repeatedly.
# --statusline: insert the status line hook without asking.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
share="$HOME/.local/share/limit-rings"
bin="$HOME/.local/bin/limit-rings-collect"
units="$HOME/.config/systemd/user"
statusline="$HOME/.claude/statusline-command.sh"
marker="# limit-rings: record limits for the plasmoid"
snippet="$(grep -v '^#' "$here/statusline-snippet.sh")"

auto_statusline=no
[[ "${1:-}" == "--statusline" ]] && auto_statusline=yes

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
        msgfmt -o "$dir/plasma_applet_io.github.flexomatic81.limitrings.mo" "$po" \
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
if kpackagetool6 -t Plasma/Applet --show io.github.flexomatic81.limitrings >/dev/null 2>&1; then
    kpackagetool6 -t Plasma/Applet --upgrade "$here/plasmoid/io.github.flexomatic81.limitrings"
else
    kpackagetool6 -t Plasma/Applet --install "$here/plasmoid/io.github.flexomatic81.limitrings"
fi

echo "→ Status line (fallback for Claude limits)"
if [[ ! -f "$statusline" ]]; then
    echo "  $statusline not found – skipped."
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
    if [[ $answer == [yY] ]]; then
        cp -p "$statusline" "$statusline.bak-limit-rings"
        MARKER="$marker" SNIPPET="$snippet" awk '
            { print }
            !done && /^input=\$\(cat\)/ { print ENVIRON["MARKER"]; print ENVIRON["SNIPPET"]; done = 1 }
        ' "$statusline.bak-limit-rings" > "$statusline"
        echo "  inserted (backup: $statusline.bak-limit-rings)."
    fi
fi

echo
echo "Done. Drag the \"Limit Rings\" widget from \"Add Widgets\" onto a panel or the desktop."
echo "After an upgrade you may need: systemctl --user restart plasma-plasmashell"
