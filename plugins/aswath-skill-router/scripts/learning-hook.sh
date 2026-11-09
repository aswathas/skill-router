#!/bin/sh
event="${1:-}"
script="$(dirname "$0")/learning-hook.py"
payload="$(mktemp)"
cat > "$payload"
python "$script" --event "$event" --payload-file "$payload" >/dev/null 2>&1 || true
rm -f "$payload"
exit 0
