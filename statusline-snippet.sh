# Von install.sh in ~/.claude/statusline-command.sh nach 'input=$(cat)' eingefügt.
( d="$HOME/.cache/agent-stats"; t=$(mktemp "$d/.statusline.XXXXXX" 2>/dev/null) || exit 0; if printf '%s' "$input" | jq -ce 'select(.rate_limits != null) | {rate_limits, written_at: (now | floor)}' > "$t" 2>/dev/null; then mv -f "$t" "$d/claude-statusline-limits.json"; else rm -f "$t"; fi ) || true
