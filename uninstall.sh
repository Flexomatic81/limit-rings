#!/usr/bin/env bash
# Removes the widget and whatever earlier versions left behind. --purge also deletes ~/.cache/limit-rings without asking.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
units="$HOME/.config/systemd/user"
# shellcheck source=tools/install-lib.sh
. "$here/tools/install-lib.sh"
id="io.github.flexomatic81.limitrings"
cache="$HOME/.cache/limit-rings"

# Versions up to 0.2 ran the collector from a systemd timer: stop it before the cache goes, or a pass could rewrite it.
retire_timer limit-rings "$HOME/.local/share/limit-rings" "$HOME/.local/bin/limit-rings-collect"
kpackagetool6 -t Plasma/Applet --remove "$id" 2>/dev/null || true
# A package that is still there would start the collector again and recreate the cache: stop here.
if kpackagetool6 -t Plasma/Applet --show "$id" >/dev/null 2>&1; then
    echo "Error: the widget could not be removed – the cache was kept. Try: kpackagetool6 -t Plasma/Applet --remove $id" >&2
    exit 1
fi
rm -f "$HOME"/.local/share/locale/*/LC_MESSAGES/plasma_applet_$id.mo

if [[ -d "$cache" ]]; then
    answer=n
    if [[ "${1:-}" == "--purge" ]]; then
        answer=y
    elif [[ -t 0 ]]; then
        read -r -p "Delete $cache? [y/N] " answer || answer=n
    fi
    # The package is gone, so no new pass starts; a running one holds the collector's lock until it has
    # written – wait for it, or it would recreate what was just deleted.
    if [[ $answer == [yY] ]]; then
        flock -w 120 "$cache/.lock" rm -rf "$cache"
        echo "Cache deleted."
    fi
fi

if grep -qF "# limit-rings:" "$HOME/.claude/statusline-command.sh" 2>/dev/null; then
    echo "Note: ~/.claude/statusline-command.sh still contains the limit-rings lines (marker '# limit-rings:')."
    echo "They are harmless but can be removed by hand."
fi
echo "Uninstalled. Widgets still placed show an error until you remove them or restart Plasma."
