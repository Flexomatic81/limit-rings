# Shared by install.sh and uninstall.sh. Expects $units, the systemd user unit directory.

# Prints how to install a package on this distribution: install_hint <apt> <pacman> <dnf> <zypper>.
# The distribution comes from ID and ID_LIKE in $OS_RELEASE (default /etc/os-release).
install_hint() {
    local ids
    ids="$(. "${OS_RELEASE:-/etc/os-release}" 2>/dev/null && echo "${ID:-} ${ID_LIKE:-}")" || ids=""
    case " $ids " in
        *" debian "* | *" ubuntu "*) echo "sudo apt install $1" ;;
        *" arch "*) echo "sudo pacman -S $2" ;;
        *" fedora "* | *" rhel "*) echo "sudo dnf install $3" ;;
        *" suse "* | *" opensuse "*) echo "sudo zypper install $4" ;;
        *) echo "install the package \"$1\" with your package manager" ;;
    esac
}

# Stops and removes the systemd timer of an earlier version ($1: unit name without suffix) and deletes the
# files it ran ($2 …) – only if the timer or the first file exists. Stopping waits for a running pass; unless
# both units then report inactive or failed, the script aborts before anything is deleted.
retire_timer() {
    local unit="$1" state states
    shift
    [[ -f "$units/$unit.timer" || -e "$1" ]] || return 0
    systemctl --user stop "$unit.timer" "$unit.service" 2>/dev/null || true
    # Only two explicit "inactive"/"failed" answers count as stopped. No answer at all (no user bus, e.g. over
    # ssh) must not delete the timer file: as long as it exists, the widget's collector does not run next to it.
    states="$(systemctl --user show -p ActiveState --value "$unit.timer" "$unit.service" 2>/dev/null)" || states=""
    if [[ "$(grep -cxE 'inactive|failed' <<< "$states")" != 2 ]]; then
        echo "Error: the old $unit timer could not be stopped, or its state is unknown ($(echo $states)) –" >&2
        echo "  nothing was changed. Check: systemctl --user status $unit.timer $unit.service" >&2
        exit 1
    fi
    systemctl --user disable "$unit.timer" 2>/dev/null || true
    rm -f "$units/$unit.timer" "$units/$unit.service" "$units/timers.target.wants/$unit.timer"
    systemctl --user daemon-reload
    rm -rf "$@"
}
