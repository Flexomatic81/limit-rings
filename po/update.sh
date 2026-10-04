#!/usr/bin/env bash
# Refreshes the translation catalogs from the source code (needs gettext).
#   po/update.sh               extract texts and merge them into every po/*/<lang>.po
#   po/update.sh --extract DIR only write plasmoid.pot and collector.pot to DIR
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root="$(dirname "$here")"

extract() {
    local out="$1"
    (cd "$root" && find plasmoid/io.github.flexomatic81.agentstats/contents \( -name '*.qml' -o -name '*.js' \) | sort \
        | xgettext --from-code=UTF-8 -C --kde -ci18n -ki18n:1 -ki18nc:1c,2 -ki18np:1,2 -ki18ncp:1c,2,3 \
            --package-name=limit-rings --no-location -o "$out/plasmoid.pot" -f -)
    (cd "$root" && find collector/limit_rings -name '*.py' | sort \
        | xgettext --from-code=UTF-8 -L Python -k_ --package-name=limit-rings --no-location \
            -o "$out/collector.pot" -f -)
}

if [[ "${1:-}" == "--extract" ]]; then
    extract "$2"
    exit 0
fi

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
extract "$tmp"
for part in plasmoid collector; do
    for po in "$here/$part"/*.po; do
        [[ -e "$po" ]] || continue
        msgmerge --quiet --update --backup=none "$po" "$tmp/$part.pot"
        echo "updated ${po#"$root"/}"
    done
done
