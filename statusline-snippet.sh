# Inserted by install.sh into ~/.claude/statusline-command.sh after 'input=$(cat)'.
( d="$HOME/.cache/limit-rings"; t=$(mktemp "$d/.statusline.XXXXXX" 2>/dev/null) || exit 0; if printf '%s' "$input" | jq -ce 'select(.rate_limits != null) | {rate_limits, written_at: (now | floor)}' > "$t" 2>/dev/null; then mv -f "$t" "$d/claude-statusline-limits.json"; else rm -f "$t"; fi ) || true
